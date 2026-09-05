from dataclasses import dataclass, field


ARTIFACTS = {
    "delivery_confirmation": "Carrier delivery confirmation with timestamp",
    "tracking_number": "Carrier tracking number and scan history",
    "signature_proof": "Recipient signature or OTP-confirmed handover",
    "avs_result": "Address Verification Service response code",
    "cvv_result": "Card security code match result",
    "threeds_authentication": "3-D Secure authentication result / liability shift",
    "device_fingerprint": "Device ID matched to prior legitimate orders",
    "ip_geolocation": "Order IP address and geolocation vs billing address",
    "customer_communication": "Email/chat/SMS thread with the cardholder",
    "terms_acceptance": "Timestamped acceptance of T&C at checkout",
    "refund_policy_disclosure": "Refund/return policy shown before purchase",
    "product_description": "Product page as displayed at time of purchase",
    "prior_transaction_history": "Prior undisputed orders on the same card",
    "cancellation_policy": "Recurring-billing cancellation terms accepted",
    "cancellation_records": "Record of whether/when cancellation was requested",
    "usage_logs": "Login / consumption logs proving service was used",
    "refund_receipt": "Proof a credit was already issued",
}


@dataclass
class ReasonCode:
    code: str
    network: str
    title: str
    category: str
    required: list = field(default_factory=list)
    supporting: list = field(default_factory=list)
    response_deadline_days: int = 30
    base_win_rate: float = 0.30


REASON_CODES = {
    "10.4": ReasonCode(
        code="10.4",
        network="Visa",
        title="Other Fraud - Card-Absent Environment",
        category="fraud",
        required=["avs_result", "cvv_result"],
        supporting=[
            "threeds_authentication",
            "device_fingerprint",
            "ip_geolocation",
            "prior_transaction_history",
            "delivery_confirmation",
        ],
        response_deadline_days=30,
        base_win_rate=0.32,
    ),
    "4837": ReasonCode(
        code="4837",
        network="Mastercard",
        title="No Cardholder Authorization",
        category="fraud",
        required=["avs_result", "cvv_result"],
        supporting=[
            "threeds_authentication",
            "device_fingerprint",
            "ip_geolocation",
            "prior_transaction_history",
            "signature_proof",
        ],
        response_deadline_days=45,
        base_win_rate=0.30,
    ),
    "13.1": ReasonCode(
        code="13.1",
        network="Visa",
        title="Merchandise / Services Not Received",
        category="not_received",
        required=["delivery_confirmation"],
        supporting=[
            "tracking_number",
            "signature_proof",
            "customer_communication",
            "usage_logs",
        ],
        response_deadline_days=30,
        base_win_rate=0.44,
    ),
    "4855": ReasonCode(
        code="4855",
        network="Mastercard",
        title="Goods or Services Not Provided",
        category="not_received",
        required=["delivery_confirmation"],
        supporting=["tracking_number", "signature_proof", "usage_logs"],
        response_deadline_days=45,
        base_win_rate=0.42,
    ),
    "13.3": ReasonCode(
        code="13.3",
        network="Visa",
        title="Not as Described or Defective Merchandise",
        category="quality",
        required=["product_description"],
        supporting=[
            "customer_communication",
            "refund_policy_disclosure",
            "delivery_confirmation",
            "terms_acceptance",
        ],
        response_deadline_days=30,
        base_win_rate=0.24,
    ),
    "4853": ReasonCode(
        code="4853",
        network="Mastercard",
        title="Cardholder Dispute - Goods Not as Described",
        category="quality",
        required=["product_description"],
        supporting=[
            "customer_communication",
            "refund_policy_disclosure",
            "terms_acceptance",
        ],
        response_deadline_days=45,
        base_win_rate=0.23,
    ),
    "13.2": ReasonCode(
        code="13.2",
        network="Visa",
        title="Cancelled Recurring Transaction",
        category="subscription",
        required=["cancellation_records"],
        supporting=[
            "cancellation_policy",
            "terms_acceptance",
            "usage_logs",
            "customer_communication",
        ],
        response_deadline_days=30,
        base_win_rate=0.35,
    ),
    "13.6": ReasonCode(
        code="13.6",
        network="Visa",
        title="Credit Not Processed",
        category="credit_not_processed",
        required=["refund_receipt"],
        supporting=["refund_policy_disclosure", "customer_communication"],
        response_deadline_days=30,
        base_win_rate=0.48,
    ),
}


def get(code: str) -> ReasonCode:
    return REASON_CODES[code]


def required_artifacts(code: str) -> list:
    return list(REASON_CODES[code].required)


def all_relevant_artifacts(code: str) -> list:
    rc = REASON_CODES[code]
    return list(rc.required) + list(rc.supporting)


def codes_by_category(category: str) -> list:
    return [c for c, rc in REASON_CODES.items() if rc.category == category]
