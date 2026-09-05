from dataclasses import dataclass
import numpy as np
from sklearn.ensemble import IsolationForest

from features import build_matrix, align_categories


@dataclass
class CostModel:
    fight_ops_cost: float = 950.0
    escalate_cost: float = 1400.0
    human_sensitivity: float = 0.85
    human_fpr: float = 0.22

    def breakeven_p(self, amount):
        return np.clip(self.fight_ops_cost / np.asarray(amount, float), 0, 1)


class NoveltyGuard:
    def __init__(self, contamination=0.05, seed=42):
        self.iso = IsolationForest(
            n_estimators=300, contamination=contamination, random_state=seed
        )
        self._ref = None
        self.cutoff_ = None

    def fit(self, train_df, quantile=0.97):
        X = build_matrix(train_df)
        self._ref = X
        Xn = self._numeric(X)
        self.iso.fit(Xn)
        s = -self.iso.score_samples(Xn)
        self.cutoff_ = float(np.quantile(s, quantile))
        return self

    def _numeric(self, X):
        Xn = X.copy()
        for c in Xn.columns:
            if str(Xn[c].dtype) == "category":
                Xn[c] = Xn[c].cat.codes
        return Xn.astype(float).to_numpy()

    def score(self, df):
        X = align_categories(build_matrix(df), self._ref)
        return -self.iso.score_samples(self._numeric(X))

    def is_novel(self, df):
        return self.score(df) > self.cutoff_


def decide_global_threshold(p_win, amount, threshold):
    return np.where(np.asarray(p_win) >= threshold, "fight", "concede")


def decide_expected_value(p_win, amount, costs: CostModel,
                          has_critical_gap=None,
                          novel=None,
                          escalate_band=0.10,
                          min_escalate_amount=None):
    p = np.asarray(p_win, float)
    amt = np.asarray(amount, float)
    be = costs.breakeven_p(amt)

    if min_escalate_amount is None:
        min_escalate_amount = 3.0 * costs.escalate_cost

    out = np.where(p > be, "fight", "concede")

    near = np.abs(p - be) < escalate_band
    worth_review = amt >= min_escalate_amount
    out = np.where(near & worth_review, "escalate", out)

    if novel is not None:
        out = np.where(np.asarray(novel, bool) & worth_review, "escalate", out)

    if has_critical_gap is not None:
        gap = np.asarray(has_critical_gap, bool)
        out = np.where(gap & (p < 0.5) & (out == "fight"), "concede", out)

    return out


def apply_novelty_shrinkage(p_win, novel, prior, weight=0.5):
    p = np.asarray(p_win, float)
    n = np.asarray(novel, bool)
    return np.where(n, (1.0 - weight) * p + weight * prior, p)


def simulate(decisions, won, amount, costs: CostModel, seed=7):
    rng = np.random.default_rng(seed)
    d = np.asarray(decisions)
    y = np.asarray(won).astype(bool)
    amt = np.asarray(amount, float)

    net = np.zeros(len(d))
    recovered = np.zeros(len(d))

    f = d == "fight"
    net[f & y] = amt[f & y] - costs.fight_ops_cost
    net[f & ~y] = -costs.fight_ops_cost
    recovered[f & y] = amt[f & y]

    e = d == "escalate"
    if e.any():
        p_fight = np.where(y[e], costs.human_sensitivity, costs.human_fpr)
        human_fights = rng.random(e.sum()) < p_fight
        sub = np.zeros(e.sum()) - costs.escalate_cost
        rec = np.zeros(e.sum())
        hw = human_fights & y[e]
        hl = human_fights & ~y[e]
        sub[hw] += amt[e][hw] - costs.fight_ops_cost
        sub[hl] -= costs.fight_ops_cost
        rec[hw] = amt[e][hw]
        net[e] = sub
        recovered[e] = rec

    at_risk = amt.sum()
    return {
        "n": int(len(d)),
        "n_fight": int(f.sum()),
        "n_concede": int((d == "concede").sum()),
        "n_escalate": int(e.sum()),
        "amount_at_risk": float(at_risk),
        "gross_recovered": float(recovered.sum()),
        "net_pnl": float(net.sum()),
        "recovery_rate": float(recovered.sum() / at_risk) if at_risk else 0.0,
        "fight_win_rate": float(y[f].mean()) if f.any() else 0.0,
        "ops_cost": float(costs.fight_ops_cost * (f.sum() + e.sum())
                          + costs.escalate_cost * e.sum()),
    }


def sweep_threshold(p_win, won, amount, costs: CostModel, grid=None):
    if grid is None:
        grid = np.round(np.arange(0.02, 0.99, 0.01), 2)
    rows = []
    for t in grid:
        d = decide_global_threshold(p_win, amount, t)
        r = simulate(d, won, amount, costs)
        r["threshold"] = float(t)
        rows.append(r)
    best = max(rows, key=lambda r: r["net_pnl"])
    return rows, best