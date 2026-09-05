import re
from datetime import datetime, timedelta

from reason_codes import REASON_CODES, ARTIFACTS
from generate_data import _artifact_available

import pandas as pd


def collect_evidence(row: pd.Series):
    rc = REASON_CODES[row["reason_code"]]
    one = pd.DataFrame([row])

    found, gaps = {}, []
    for kind, names in (("required", rc.required), ("supporting", rc.supporting)):
        for name in names:
            available = bool(_artifact_available(one, name)[0])
            if available:
                aid = f"EV-{len(found)+1:02d}"
                found[aid] = {
                    "artifact_id": aid,
                    "type": name,
                    "description": ARTIFACTS[name],
                    "tier": kind,
                    "value": _describe(name, row),
                }
            elif kind == "required":
                gaps.append({"type": name, "description": ARTIFACTS[name],
                             "severity": "critical"})
            else:
                gaps.append({"type": name, "description": ARTIFACTS[name],
                             "severity": "minor"})
    return {"artifacts": found, "gaps": gaps,
            "critical_gaps": [g for g in gaps if g["severity"] == "critical"]}


def _describe(name, row):
    if name == "avs_result":
        return "AVS response: full match on address and postal code"
    if name == "cvv_result":
        return "CVV2/CVC2 response: match"
    if name == "threeds_authentication":
        return f"3-D Secure result: {row['threeds_status']} (liability shift applies)"
    if name == "ip_geolocation":
        return "Order IP geolocation consistent with billing address on file"
    if name in ("device_fingerprint", "device_seen_before"):
        return "Device fingerprint matches device used on prior undisputed orders"
    if name == "prior_transaction_history":
        return f"{int(row['prior_txns_same_card'])} prior undisputed orders on this card"
    if name == "delivery_confirmation":
        return "Carrier delivery confirmation recorded with timestamp"
    if name == "tracking_number":
        return "Carrier tracking number with full scan history"
    if name == "signature_proof":
        return "Recipient acknowledgement captured at handover"
    if name == "usage_logs":
        return "Authenticated access logs showing the service was consumed"
    if name == "refund_policy_disclosure":
        return "Refund and return policy displayed and accepted before payment"
    if name == "terms_acceptance":
        return "Terms and conditions accepted at checkout with timestamp"
    if name == "product_description":
        return "Product page as displayed to the cardholder at time of purchase"
    if name == "customer_communication":
        return "Support thread with the cardholder covering the order"
    if name == "cancellation_policy":
        return "Recurring billing terms accepted at sign-up"
    if name == "cancellation_records":
        return "Billing system record of cancellation requests on this subscription"
    if name == "refund_receipt":
        return "Credit issued to the original payment method, with reference"
    return ARTIFACTS.get(name, name)


_OPENERS = {
    "fraud": ("The cardholder asserts this card-absent transaction was not authorised. "
              "The authentication and device evidence below is inconsistent with that assertion."),
    "not_received": ("The cardholder asserts the goods or services were not received. "
                     "Fulfilment records below establish delivery."),
    "quality": ("The cardholder asserts the item was not as described. "
                "The product representation and disclosure records below were accepted before payment."),
    "subscription": ("The cardholder asserts a recurring charge was billed after cancellation. "
                     "Billing and cancellation records below address the charge."),
    "credit_not_processed": ("The cardholder asserts a credit was not processed. "
                             "The refund record below shows the credit was issued."),
}


def build_packet(row: pd.Series, evidence: dict, p_win: float, decision: str) -> str:
    rc = REASON_CODES[row["reason_code"]]
    arts = evidence["artifacts"]
    deadline = datetime.now() + timedelta(days=int(row["days_remaining_to_respond"]))

    lines = [
        f"REPRESENTMENT - {rc.network} {rc.code}: {rc.title}",
        f"Dispute ID: {row['dispute_id']}",
        f"Disputed amount: INR {row['amount_inr']:,.2f}",
        f"Response deadline: {deadline:%d %b %Y} "
        f"({int(row['days_remaining_to_respond'])} days remaining)",
        f"Model win probability: {p_win:.2f}   Decision: {decision.upper()}",
        "",
        "SUMMARY OF MERCHANT POSITION",
        _OPENERS[rc.category],
        "",
        "EVIDENCE RELIED UPON",
    ]

    if not arts:
        lines.append("  (none available)")
    for a in arts.values():
        lines.append(f"  [{a['artifact_id']}] {a['description']} - {a['value']}")

    lines += ["", "ARGUMENT"]
    for sentence in _argument(row, arts):
        lines.append(f"  {sentence}")

    if evidence["gaps"]:
        lines += ["", "DISCLOSED EVIDENCE GAPS"]
        for g in evidence["gaps"]:
            lines.append(f"  ({g['severity']}) {g['description']} - not available")

    lines += ["", "Merchant requests that the disputed amount be represented."]
    return "\n".join(lines)


def _argument(row, arts):
    by_type = {a["type"]: a["artifact_id"] for a in arts.values()}
    S = []

    def claim(text, *types):
        ids = [by_type[t] for t in types if t in by_type]
        if len(ids) == len(types):
            S.append(f"{text} [{', '.join(ids)}]")

    claim("Address and card security code supplied at checkout both matched the "
          "issuer record, which is inconsistent with an unauthorised third party.",
          "avs_result", "cvv_result")
    claim("The transaction was authenticated under 3-D Secure, shifting fraud "
          "liability to the issuer.", "threeds_authentication")
    claim("The ordering device matches a device used on earlier undisputed "
          "orders from this cardholder.", "device_fingerprint")
    claim("The order originated from an IP address geographically consistent "
          "with the billing address on file.", "ip_geolocation")
    claim("This card has a history of completed orders with no prior dispute.",
          "prior_transaction_history")
    claim("The carrier recorded successful delivery of this order.",
          "delivery_confirmation")
    claim("Carrier tracking shows the full scan history for the consignment.",
          "tracking_number")
    claim("Handover was acknowledged by the recipient at the delivery address.",
          "signature_proof")
    claim("Authenticated access logs show the service was used after purchase.",
          "usage_logs")
    claim("The product page shown to the cardholder accurately described the item "
          "supplied.", "product_description")
    claim("The refund and return policy was displayed and accepted before payment "
          "was taken.", "refund_policy_disclosure")
    claim("Terms and conditions were accepted at checkout with a recorded "
          "timestamp.", "terms_acceptance")
    claim("Correspondence with the cardholder covering this order is on record.",
          "customer_communication")
    claim("Recurring billing terms, including cancellation method, were accepted "
          "at sign-up.", "cancellation_policy")
    claim("Billing records address the cancellation status of this subscription "
          "at the time of the charge.", "cancellation_records")
    claim("A credit was issued to the original payment method.", "refund_receipt")

    if not S:
        S.append("No supporting artifact was available for this dispute; "
                 "no factual assertion is made. [NO-EVIDENCE]")
    return S


_CITE = re.compile(r"\[([A-Z0-9\-, ]+)\]")


def verify_citations(packet: str, evidence: dict):
    valid = set(evidence["artifacts"].keys()) | {"NO-EVIDENCE"}
    violations = []

    block = packet.split("ARGUMENT")[-1].split("DISCLOSED EVIDENCE GAPS")[0]
    for line in block.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("Merchant requests"):
            continue
        found = _CITE.findall(line)
        if not found:
            violations.append(f"uncited claim: {line[:70]}")
            continue
        for group in found:
            for aid in [x.strip() for x in group.split(",")]:
                if aid not in valid:
                    violations.append(f"unknown artifact {aid}: {line[:50]}")
    return violations
