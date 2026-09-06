# Chargeback Evidence Responder

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![LightGBM](https://img.shields.io/badge/Model-LightGBM-brightgreen?style=flat-square)](https://lightgbm.readthedocs.io/)
[![UI](https://img.shields.io/badge/Dashboard-Stripe_Radar_Theme-slate?style=flat-square)](#local-dashboard)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)

An end-to-end chargeback defense pipeline that evaluates dispute winnability, executes expected-value decision policies (fight, concede, or escalate), and automatically compiles citation-enforced representment packets under Visa and Mastercard network rules.


---

## System Architecture

```text
Incoming Dispute ──▶ Reason Code Rules ──▶ Evidence Retrieval ──▶ Calibrated LightGBM
                           │                     │                         │
                           │                     ▼                         ▼
                           │              Gap Disclosures        P(Win | Evidence)
                           │                     │                         │
                           ▼                     ▼                         ▼
                     Deadline Tracker ────▶ Expected-Value Decision Engine
                                            (Fight / Concede / Escalate)
                                                          │
                                                          ▼
                                            Cited Representment Packet
                                             + Interactive Radar UI
```

---

## Key Highlights

- **Calibrated Winnability Scoring**: LightGBM classifier paired with isotonic regression on a held-out slice. Outputs true posterior probabilities ($P(\text{win} \mid x)$) rather than uncalibrated ranking scores, preventing skew in downstream monetary calculations.
- **Amount-Dependent Breakeven Policy**: Discards fixed global cutoffs in favor of ticket-specific economics:
  $$\text{Expected Value} = P(\text{win}) \cdot \text{Amount} - \text{Cost}_{\text{ops}}$$
  Fighting is profitable only when $P(\text{win}) > \frac{\text{Cost}_{\text{ops}}}{\text{Amount}}$.
- **Distribution Shift & Novelty Guard**: An Isolation Forest detector trained strictly on normal traffic flags novel, coordinated friendly-fraud anomalies, routing high-ticket edge cases to senior review.
- **Mechanical Citation Contract**: Deterministic packet generator enforcing that every factual assertion in the response packet carries an explicit evidence reference (e.g. `[EV-01]`, `[EV-02]`). Uncited claims are rejected at compile time.
- **Enterprise Local UI**: High-utility dashboard with compact 36px tables, multi-field filters, monospaced transaction numbers, and an evidence slide-drawer.

---

## Policy Benchmark Comparison

Evaluated on a held-out test split of **2,000 disputes** (₹36.1L total at risk):

| Strategy | Contested | Conceded | Escalated | Gross Recovered | Operational Cost | Realised Net P&L |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Concede All** | 0 | 2,000 | 0 | ₹0 | ₹0 | **₹0** |
| **Fight All** | 2,000 | 0 | 0 | ₹15,51,902 | ₹19,00,000 | **-₹3,48,098** |
| **Fixed Cutoff ($t=0.51$)** | 860 | 1,140 | 0 | ₹12,01,629 | ₹8,17,000 | **+₹3,84,629** |
| **Expected Value Engine** | **470** | **1,498** | **32** | **₹10,59,928** | **₹4,97,000** | **+₹5,62,928** |
| **EV + Novelty Shrinkage** | **469** | **1,500** | **31** | **₹10,59,928** | **₹4,94,650** | **+₹5,65,278** |

> **Key takeaway**: Contesting only the ~24% of disputes with positive expected value recovers **₹5.65L net profit**, whereas blind "fight-all" rules run a **₹3.48L net loss** due to analyst overhead.

---

## Quickstart

### 1. Install Dependencies

```bash
pip install lightgbm scikit-learn pandas numpy
```

### 2. Launch the Local Dashboard

Run the auto-launcher from the project root:

```bash
python run_dashboard.py
```

This single command:
1. Verifies existing batch evaluations (or automatically executes the model pipeline on first launch).
2. Starts the local server on `http://localhost:8080`.
3. **Automatically opens the dashboard** in your default web browser.

### 3. Run Headless Batch Pipeline (CLI)

To run the complete batch evaluation and update report artifacts:

```bash
python src/run_batch.py
```

Outputs written to `out/`:
- `results.json`: Full evaluation metrics, calibration tables, and policy P&L.
- `audit_log.json`: Dispute-level audit log containing decisions, probabilities, and gaps.
- `threshold_sweep.csv`: Revenue optimization curve across probability cutoffs.
- `sample_packet.txt`: Example representment packet with cited evidence.

---

## Repository Structure

```text
├── dashboard/
│   ├── server.py              # Multi-threaded HTTP server & REST API (Python stdlib)
│   └── static/
│       ├── index.html         # Semantic layout with KPI strip and slide-drawer
│       ├── styles.css         # Stripe Radar & Brex design system (slate theme)
│       └── app.js             # Client-side filtering, sorting, and packet preview
├── src/
│   ├── features.py            # Feature matrix assembly & leakage guards
│   ├── generate_data.py       # Dispute corpus synthesis & shift holdouts
│   ├── model.py               # LightGBM training & isotonic probability calibration
│   ├── policy.py              # Breakeven economics, EV routing & novelty guard
│   ├── reason_codes.py        # Card network reason codes (Visa & Mastercard)
│   ├── representment.py       # Evidence retrieval & citation-enforced compiler
│   └── run_batch.py           # End-to-end batch execution entrypoint
├── out/                       # Pre-computed evaluation logs and sweep data
├── run_dashboard.py           # Root launcher with automatic browser opening
└── README.md
```

---

## Network Reason Codes Supported

| Network | Code | Category | Statutory Window | Key Required Evidence |
| :--- | :--- | :--- | :---: | :--- |
| **Visa** | 10.4 | Fraud (Card-Absent) | 30 days | AVS response, CVV2 result, 3DS liability shift |
| **Mastercard** | 4837 | Unauthorized Transaction | 45 days | AVS/CVV result, device fingerprint, signature |
| **Visa** | 13.1 | Merchandise Not Received | 30 days | Carrier delivery scan, tracking number |
| **Mastercard** | 4855 | Goods Not Provided | 45 days | Delivery confirmation, handover timestamp |
| **Visa** | 13.3 | Not as Described | 30 days | Product description, accepted return terms |
| **Mastercard** | 4853 | Goods Not as Described | 45 days | Product specifications, checkout acceptance |
| **Visa** | 13.2 | Cancelled Recurring | 30 days | Cancellation logs, recurring agreement records |
| **Visa** | 13.6 | Credit Not Processed | 30 days | Refund receipt, merchant credit transaction ARN |

---

## License

MIT License. See [LICENSE](LICENSE) for details.
