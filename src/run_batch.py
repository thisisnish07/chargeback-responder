import json
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from generate_data import build_all
from model import WinnabilityModel, evaluate, calibration_table
from policy import (CostModel, NoveltyGuard, decide_global_threshold,
                    decide_expected_value, simulate, sweep_threshold,
                    apply_novelty_shrinkage)
from representment import collect_evidence, build_packet, verify_citations

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")
os.makedirs(OUT, exist_ok=True)

COSTS = CostModel()


def hr(t):
    print("\n" + "=" * 74)
    print(t)
    print("=" * 74)


def fmt_inr(x):
    return f"INR {x:>14,.0f}"


def main():
    hr("1. Dataset Summary")
    train, test, shift = build_all()
    for name, d in [("train", train), ("test (in-dist)", test), ("shift (holdout)", shift)]:
        print(f"  {name:18s} n={len(d):5d}  win_rate={d.won.mean():.3f}  "
              f"critical_gap={d.has_critical_gap.mean():.3f}  "
              f"at_risk={fmt_inr(d.amount_inr.sum())}")

    hr("2. Model Training")
    m = WinnabilityModel().fit(train)
    guard = NoveltyGuard().fit(train)
    print("  Top features by importance:")
    for f, g in m.feature_importance(10):
        print(f"    {f:32s} {g:6d}")

    p_test = m.predict_proba(test)
    p_shift = m.predict_proba(shift)
    prior = float(train.won.mean())

    nov_test, nov_shift = guard.is_novel(test), guard.is_novel(shift)
    from sklearn.metrics import precision_score, recall_score
    ring = shift._ring.to_numpy()
    print(f"\n  novelty guard: flags {nov_test.mean():.1%} of in-dist traffic, "
          f"{nov_shift.mean():.1%} of shifted traffic")
    print(f"    vs the true injected pattern -- precision "
          f"{precision_score(ring, nov_shift, zero_division=0):.3f}, "
          f"recall {recall_score(ring, nov_shift, zero_division=0):.3f}")

    hr("3. Model Evaluation")
    mt = evaluate(test.won.to_numpy(), p_test)
    ms = evaluate(shift.won.to_numpy(), p_shift)
    print(f"  {'metric':<14}{'in-dist':>12}{'shifted':>12}{'delta':>12}")
    for k in ["n", "base_rate", "pr_auc", "roc_auc", "brier", "precision", "recall"]:
        a, b = mt[k], ms[k]
        d = "" if k == "n" else f"{b-a:+12.3f}"
        av = f"{a:12d}" if k == "n" else f"{a:12.3f}"
        bv = f"{b:12d}" if k == "n" else f"{b:12.3f}"
        print(f"  {k:<14}{av}{bv}{d}")

    print("\n  calibration, in-distribution:")
    for r in calibration_table(test.won.to_numpy(), p_test):
        print(f"    {r['bucket']:>12}  n={r['n']:5d}  predicted={r['predicted']:.3f}  "
              f"actual={r['actual']:.3f}  gap={r['actual']-r['predicted']:+.3f}")
    print("\n  calibration, shifted:")
    for r in calibration_table(shift.won.to_numpy(), p_shift):
        print(f"    {r['bucket']:>12}  n={r['n']:5d}  predicted={r['predicted']:.3f}  "
              f"actual={r['actual']:.3f}  gap={r['actual']-r['predicted']:+.3f}")

    hr("4. Threshold Optimization")
    rows, best = sweep_threshold(p_test, test.won.to_numpy(),
                                 test.amount_inr.to_numpy(), COSTS)
    for t in [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]:
        r = min(rows, key=lambda r: abs(r["threshold"] - t))
        print(f"    t={r['threshold']:.2f}  fight={r['n_fight']:5d}  "
              f"win_rate={r['fight_win_rate']:.3f}  net={fmt_inr(r['net_pnl'])}")
    print(f"\n  Optimal global cutoff: t={best['threshold']:.2f}  "
          f"net={fmt_inr(best['net_pnl'])}")
    pd.DataFrame(rows).to_csv(f"{OUT}/threshold_sweep.csv", index=False)

    hr("5. Policy Comparison")
    results = {}
    for label, df, p in [("in-dist", test, p_test), ("shifted", shift, p_shift)]:
        amt = df.amount_inr.to_numpy()
        won = df.won.to_numpy()
        gap = df.has_critical_gap.to_numpy()
        novel = guard.is_novel(df)
        p_shrunk = apply_novelty_shrinkage(p, novel, prior, weight=0.5)

        pol = {
            "concede everything":
                np.array(["concede"] * len(df)),
            "fight everything":
                np.array(["fight"] * len(df)),
            f"global cutoff t={best['threshold']:.2f}":
                decide_global_threshold(p, amt, best["threshold"]),
            "expected value (amount-aware)":
                decide_expected_value(p, amt, COSTS, has_critical_gap=gap),
            "EV + novelty escalation":
                decide_expected_value(p, amt, COSTS, has_critical_gap=gap, novel=novel),
            "EV + novelty shrinkage":
                decide_expected_value(p_shrunk, amt, COSTS, has_critical_gap=gap),
        }

        print(f"\n  --- {label} (n={len(df)}, at risk {fmt_inr(amt.sum())}, "
              f"novel-flagged {novel.mean():.1%}) ---")
        print(f"    {'policy':<32}{'fight':>7}{'esc':>6}{'recovered':>16}{'net P&L':>16}")
        results[label] = {}
        for name, d in pol.items():
            r = simulate(d, won, amt, COSTS)
            results[label][name] = r
            print(f"    {name:<32}{r['n_fight']:>7}{r['n_escalate']:>6}"
                  f"{r['gross_recovered']:>16,.0f}{r['net_pnl']:>16,.0f}")

    hr("6. Representment Generation")
    amt = test.amount_inr.to_numpy()
    p_test_adj = apply_novelty_shrinkage(p_test, nov_test, prior, weight=0.5)
    dec = decide_expected_value(p_test_adj, amt, COSTS,
                                has_critical_gap=test.has_critical_gap.to_numpy())
    built = violations = 0
    audit = []
    sample_packet = None

    for i in range(len(test)):
        row = test.iloc[i]
        ev = collect_evidence(row)
        if dec[i] in ("fight", "escalate"):
            pkt = build_packet(row, ev, float(p_test_adj[i]), dec[i])
            v = verify_citations(pkt, ev)
            built += 1
            violations += len(v)
            if sample_packet is None and dec[i] == "fight" and len(ev["artifacts"]) >= 4:
                sample_packet = pkt
        audit.append({
            "dispute_id": row["dispute_id"],
            "reason_code": row["reason_code"],
            "network": row["network"],
            "amount_inr": float(row["amount_inr"]),
            "p_win_raw": round(float(p_test[i]), 4),
            "p_win_adjusted": round(float(p_test_adj[i]), 4),
            "breakeven_p": round(float(COSTS.breakeven_p(row["amount_inr"])), 4),
            "expected_value": round(float(p_test_adj[i] * row["amount_inr"]
                                          - COSTS.fight_ops_cost), 2),
            "artifacts_found": len(ev["artifacts"]),
            "critical_gaps": [g["type"] for g in ev["critical_gaps"]],
            "novelty_flag": bool(nov_test[i]),
            "decision": dec[i],
            "days_remaining": int(row["days_remaining_to_respond"]),
        })

    print(f"  packets built: {built}")
    print(f"  citation violations: {violations}   "
          f"({'PASS' if violations == 0 else 'FAIL'})")

    with open(f"{OUT}/audit_log.json", "w") as fh:
        json.dump(audit, fh, indent=2)
    if sample_packet:
        with open(f"{OUT}/sample_packet.txt", "w") as fh:
            fh.write(sample_packet)
        print("\n  --- sample packet ---")
        print("  " + sample_packet.replace("\n", "\n  ")[:1600])

    with open(f"{OUT}/results.json", "w") as fh:
        json.dump({"metrics": {"in_dist": mt, "shifted": ms},
                   "best_threshold": best, "policies": results}, fh, indent=2)

    hr("7. Summary")
    ind = results["in-dist"]["EV + novelty shrinkage"]
    sh = results["shifted"]["EV + novelty shrinkage"]
    base = results["in-dist"]["fight everything"]
    print(f"  In-distribution ({ind['n']} disputes, {fmt_inr(ind['amount_at_risk'])} at risk):")
    print(f"    recovered {fmt_inr(ind['gross_recovered'])}   "
          f"net {fmt_inr(ind['net_pnl'])}   "
          f"({ind['recovery_rate']:.1%} of amount at risk)")
    print(f"    vs fighting everything: {fmt_inr(ind['net_pnl'] - base['net_pnl'])}")
    print(f"  Shifted holdout ({sh['n']} disputes):")
    print(f"    net {fmt_inr(sh['net_pnl'])}  "
          f"escalated {sh['n_escalate']} to human review")
    print(f"\n  Outputs saved to {OUT}/")


if __name__ == "__main__":
    main()