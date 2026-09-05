# Chargeback Evidence Responder

Automated pipeline for chargeback dispute winnability assessment, expected-value routing (fight, concede, or escalate), and citation-verified representment packet generation.

## Overview

When a chargeback is received, deciding whether to contest it requires evaluating evidence availability, dispute probability, and operational costs. This repository provides:
- A calibrated LightGBM model to estimate dispute win probability based on transaction, auth, and evidence features.
- An Isolation Forest detector to identify out-of-distribution dispute patterns.
- An expected-value policy that factors in dispute amount, operational costs, and evidence completeness.
- A deterministic packet builder enforcing citation of required artifacts under card network rules (Visa and Mastercard).

## Installation

Install dependencies:

```bash
pip install lightgbm scikit-learn pandas numpy
```

## Usage

Run the end-to-end evaluation pipeline:

```bash
python src/run_batch.py
```

Launch the local management dashboard (automatically runs the batch pipeline if needed and opens your browser):

```bash
python run_dashboard.py
```

Generated outputs are written to the `out/` directory:
- `results.json`: Evaluation metrics across splits and comparative policy P&L.
- `audit_log.json`: Dispute-level audit log containing probabilities, decisions, and evidence tracking.
- `threshold_sweep.csv`: Revenue optimization sweep across global probability thresholds.
- `sample_packet.txt`: Example representment packet with cited evidence.

## Module Structure

- `src/reason_codes.py`: Reason code schemas, required and supporting evidence definitions, and deadlines.
- `src/generate_data.py`: Dataset generation for standard and shifted distributions.
- `src/features.py`: Feature matrix assembly and dtype mapping.
- `src/model.py`: LightGBM model training, isotonic calibration, and evaluation metrics.
- `src/policy.py`: Cost model, expected-value decision rules, threshold sweeps, and novelty filtering.
- `src/representment.py`: Evidence retrieval, argument generation, and citation validation.
- `src/run_batch.py`: End-to-end execution script.