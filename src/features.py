import pandas as pd

CATEGORICAL = ["reason_code", "network", "category", "threeds_status"]

NUMERIC = [
    "amount_inr",
    "account_age_days",
    "prior_txns_same_card",
    "prior_disputes_same_card",
    "days_purchase_to_dispute",
    "days_remaining_to_respond",
    "amount_zscore_vs_merchant",
    "required_evidence_have",
    "required_evidence_need",
    "required_completeness",
    "supporting_completeness",
]

BOOLEAN = [
    "digital_goods",
    "avs_match",
    "cvv_match",
    "ip_billing_match",
    "device_seen_before",
    "delivery_confirmation",
    "tracking_number",
    "signature_proof",
    "usage_logs",
    "refund_policy_disclosure",
    "terms_acceptance",
    "product_description",
    "customer_communication",
    "cancellation_policy",
    "cancellation_records",
    "refund_receipt",
    "has_critical_gap",
]

FEATURES = CATEGORICAL + NUMERIC + BOOLEAN

FORBIDDEN = {"won", "_ring", "dispute_id"}


def build_matrix(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in FEATURES if c not in df.columns]
    if missing:
        raise ValueError(f"missing feature columns: {missing}")
    leaked = FORBIDDEN & set(FEATURES)
    if leaked:
        raise AssertionError(f"leakage: {leaked}")

    X = df[FEATURES].copy()
    for c in CATEGORICAL:
        X[c] = X[c].astype("category")
    for c in BOOLEAN:
        X[c] = X[c].astype(int)
    for c in NUMERIC:
        X[c] = X[c].astype(float)
    return X


def align_categories(X: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    X = X.copy()
    for c in CATEGORICAL:
        X[c] = pd.Categorical(X[c], categories=reference[c].cat.categories)
    return X