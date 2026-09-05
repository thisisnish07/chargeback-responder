import numpy as np
import pandas as pd

from reason_codes import REASON_CODES, required_artifacts, all_relevant_artifacts


RNG_DEFAULT = 42

CODE_MIX = {
    "10.4": 0.20,
    "4837": 0.13,
    "13.1": 0.19,
    "4855": 0.10,
    "13.3": 0.14,
    "4853": 0.08,
    "13.2": 0.10,
    "13.6": 0.06,
}


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def _draw_amount(rng, n, digital):
    mu = np.where(digital, 6.4, 7.4)
    amt = np.exp(rng.normal(mu, 0.85, n))
    return np.clip(amt, 99, 250000).round(2)


FRAUD_HEAVY_MIX = {
    "10.4": 0.42,
    "4837": 0.28,
    "13.1": 0.10,
    "4855": 0.05,
    "13.3": 0.07,
    "4853": 0.03,
    "13.2": 0.03,
    "13.6": 0.02,
}


def _make_base(rng, n, ring_rate, fraud_heavy=False):
    mix = FRAUD_HEAVY_MIX if fraud_heavy else CODE_MIX
    code = rng.choice(list(mix), size=n, p=list(mix.values()))
    category = np.array([REASON_CODES[c].category for c in code])
    network = np.array([REASON_CODES[c].network for c in code])

    p_digital = 0.72 if fraud_heavy else 0.35
    digital = (rng.random(n) < np.where(category == "quality", 0.20, p_digital))
    amount = _draw_amount(rng, n, digital)

    ring = (rng.random(n) < ring_rate) & (category == "fraud") & digital

    account_age = np.clip(rng.gamma(2.0, 210, n), 1, 3000).astype(int)
    account_age = np.where(ring, np.clip(account_age + 400, 1, 3000), account_age)

    prior_txns = rng.poisson(np.clip(account_age / 120, 0.2, 25)).astype(int)
    prior_txns = np.where(ring, prior_txns + rng.poisson(6, n), prior_txns)

    prior_disputes = rng.poisson(0.18, n)
    prior_disputes = np.where(ring, prior_disputes + rng.poisson(0.9, n), prior_disputes)

    p_avs = np.where(category == "fraud", 0.62, 0.80)
    p_avs = np.where(ring, 0.94, p_avs)
    avs_match = rng.random(n) < p_avs

    p_cvv = np.where(category == "fraud", 0.70, 0.86)
    p_cvv = np.where(ring, 0.96, p_cvv)
    cvv_match = rng.random(n) < p_cvv

    tds_roll = rng.random(n)
    threeds = np.where(tds_roll < 0.45, "authenticated",
              np.where(tds_roll < 0.68, "attempted", "none"))
    threeds = np.where(ring & (rng.random(n) < 0.85), "authenticated", threeds)

    ip_match = rng.random(n) < np.where(category == "fraud", 0.55, 0.78)
    ip_match = np.where(ring, rng.random(n) < 0.90, ip_match)

    device_seen = rng.random(n) < np.clip(prior_txns / 12, 0.05, 0.85)
    device_seen = np.where(ring, rng.random(n) < 0.88, device_seen)

    p_delivery = np.where(digital, 0.10, 0.74)
    delivery_confirmed = rng.random(n) < p_delivery
    tracking = delivery_confirmed | (rng.random(n) < np.where(digital, 0.05, 0.55))
    signature = delivery_confirmed & (rng.random(n) < 0.42)
    usage_logs = np.where(digital, rng.random(n) < 0.80, rng.random(n) < 0.18)

    hygiene = np.clip(rng.beta(2.4, 2.0, n), 0.02, 0.98)
    refund_policy = rng.random(n) < hygiene
    terms_acceptance = rng.random(n) < (0.35 + 0.6 * hygiene)
    product_desc = rng.random(n) < (0.45 + 0.5 * hygiene)
    comms = rng.random(n) < (0.25 + 0.55 * hygiene)
    cancel_policy = rng.random(n) < (0.30 + 0.6 * hygiene)
    cancel_records = np.where(
        category == "subscription", rng.random(n) < (0.20 + 0.65 * hygiene), rng.random(n) < 0.25
    )
    refund_receipt = np.where(
        category == "credit_not_processed", rng.random(n) < 0.55, rng.random(n) < 0.08
    )

    days_to_dispute = np.clip(rng.gamma(2.2, 14, n), 1, 180).astype(int)
    days_to_dispute = np.where(ring, np.clip(days_to_dispute + 45, 1, 180), days_to_dispute)
    deadline = np.array([REASON_CODES[c].response_deadline_days for c in code])
    days_remaining = np.clip(deadline - rng.integers(0, 22, n), 0, deadline)

    amount_z = np.clip(rng.normal(0.2, 1.1, n), -3, 6).round(2)
    amount_z = np.where(ring, amount_z + 0.8, amount_z)

    return pd.DataFrame({
        "reason_code": code,
        "network": network,
        "category": category,
        "amount_inr": amount,
        "digital_goods": digital,
        "account_age_days": account_age,
        "prior_txns_same_card": prior_txns,
        "prior_disputes_same_card": prior_disputes,
        "avs_match": avs_match,
        "cvv_match": cvv_match,
        "threeds_status": threeds,
        "ip_billing_match": ip_match,
        "device_seen_before": device_seen,
        "delivery_confirmation": delivery_confirmed,
        "tracking_number": tracking,
        "signature_proof": signature,
        "usage_logs": usage_logs,
        "refund_policy_disclosure": refund_policy,
        "terms_acceptance": terms_acceptance,
        "product_description": product_desc,
        "customer_communication": comms,
        "cancellation_policy": cancel_policy,
        "cancellation_records": cancel_records,
        "refund_receipt": refund_receipt,
        "days_purchase_to_dispute": days_to_dispute,
        "days_remaining_to_respond": days_remaining,
        "amount_zscore_vs_merchant": amount_z,
        "_ring": ring,
    })


def _artifact_available(df, name):
    direct = {
        "delivery_confirmation", "tracking_number", "signature_proof",
        "usage_logs", "refund_policy_disclosure", "terms_acceptance",
        "product_description", "customer_communication",
        "cancellation_policy", "cancellation_records", "refund_receipt",
        "device_seen_before",
    }
    if name in direct:
        return df[name].to_numpy(bool)
    if name == "avs_result":
        return df["avs_match"].to_numpy(bool)
    if name == "cvv_result":
        return df["cvv_match"].to_numpy(bool)
    if name == "threeds_authentication":
        return (df["threeds_status"] == "authenticated").to_numpy(bool)
    if name == "device_fingerprint":
        return df["device_seen_before"].to_numpy(bool)
    if name == "ip_geolocation":
        return df["ip_billing_match"].to_numpy(bool)
    if name == "prior_transaction_history":
        return (df["prior_txns_same_card"] >= 3).to_numpy(bool)
    raise KeyError(name)


def add_evidence_features(df):
    n = len(df)
    req_have, req_need, sup_have, sup_need = (np.zeros(n) for _ in range(4))

    for code in df["reason_code"].unique():
        m = (df["reason_code"] == code).to_numpy()
        rc = REASON_CODES[code]
        for a in rc.required:
            req_have[m] += _artifact_available(df, a)[m]
        req_need[m] = len(rc.required)
        for a in rc.supporting:
            sup_have[m] += _artifact_available(df, a)[m]
        sup_need[m] = len(rc.supporting)

    out = df.copy()
    out["required_evidence_have"] = req_have.astype(int)
    out["required_evidence_need"] = req_need.astype(int)
    out["required_completeness"] = np.where(req_need > 0, req_have / req_need, 1.0)
    out["supporting_completeness"] = np.where(sup_need > 0, sup_have / sup_need, 0.0)
    out["has_critical_gap"] = out["required_completeness"] < 1.0
    return out


def _latent_win_logit(df, rng):
    n = len(df)
    base = np.array([REASON_CODES[c].base_win_rate for c in df["reason_code"]])
    z = np.log(base / (1 - base))

    cat = df["category"].to_numpy()
    req_c = df["required_completeness"].to_numpy()
    sup_c = df["supporting_completeness"].to_numpy()

    z += np.where(req_c >= 1.0, 0.55, -1.95 * (1.0 - req_c) - 0.35)
    z += 1.15 * sup_c

    tds_auth = (df["threeds_status"] == "authenticated").to_numpy()
    is_fraud = cat == "fraud"
    z += np.where(is_fraud & tds_auth, 1.45, 0.0)
    z += np.where(is_fraud & df["avs_match"].to_numpy() & df["cvv_match"].to_numpy(), 0.50, 0.0)
    z += np.where(is_fraud & df["ip_billing_match"].to_numpy(), 0.30, 0.0)

    nr = cat == "not_received"
    z += np.where(nr & df["delivery_confirmation"].to_numpy(), 0.85, 0.0)
    z += np.where(nr & df["signature_proof"].to_numpy(), 0.60, 0.0)
    z += np.where(nr & df["digital_goods"].to_numpy() & df["usage_logs"].to_numpy(), 0.70, 0.0)

    q = cat == "quality"
    z += np.where(q & df["refund_policy_disclosure"].to_numpy(), 0.55, -0.30)
    z += np.where(q & df["customer_communication"].to_numpy(), 0.40, 0.0)

    sub = cat == "subscription"
    z += np.where(sub & df["cancellation_records"].to_numpy(), 0.75, -0.55)

    pd_ = df["prior_disputes_same_card"].to_numpy()
    z -= 0.42 * np.tanh(pd_ / 1.6)

    z += 0.30 * np.tanh(df["prior_txns_same_card"].to_numpy() / 10.0)
    z -= 0.0055 * np.clip(df["days_purchase_to_dispute"].to_numpy() - 45, 0, None)

    z -= np.where(df["days_remaining_to_respond"].to_numpy() <= 3, 0.35, 0.0)

    z -= 0.16 * np.clip(np.log10(df["amount_inr"].to_numpy() / 2000.0), 0, None)

    z += np.where(df["_ring"].to_numpy(), -2.40, 0.0)

    z += rng.normal(0, 0.62, n)
    return z


def build(n=6000, ring_rate=0.03, seed=RNG_DEFAULT, fraud_heavy=False):
    rng = np.random.default_rng(seed)
    df = _make_base(rng, n, ring_rate, fraud_heavy=fraud_heavy)
    df = add_evidence_features(df)
    z = _latent_win_logit(df, rng)
    p = _sigmoid(z)
    df["won"] = (rng.random(len(df)) < p).astype(int)
    df["dispute_id"] = [f"dp_{seed}_{i:06d}" for i in range(len(df))]
    return df.reset_index(drop=True)


def build_all(seed=RNG_DEFAULT):
    train = build(n=6000, ring_rate=0.03, seed=seed)
    test = build(n=2000, ring_rate=0.03, seed=seed + 1)
    shift = build(n=900, ring_rate=0.80, seed=seed + 2, fraud_heavy=True)
    return train, test, shift


if __name__ == "__main__":
    tr, te, sh = build_all()
    for name, d in [("train", tr), ("test", te), ("shift", sh)]:
        print(f"{name:6s} n={len(d):5d}  win_rate={d.won.mean():.3f}  "
              f"ring={d._ring.mean():.3f}  critical_gap={d.has_critical_gap.mean():.3f}")