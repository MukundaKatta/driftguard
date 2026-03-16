# DriftGuard

> Your ML Models Are Drifting. We'll Catch It.

## Overview

DriftGuard continuously monitors machine learning models in production for data drift, concept drift, and performance degradation. Get alerted before your models silently fail.

## Key Features

- **Data Drift Detection** — Statistical tests on feature distributions (KS, PSI, Chi-squared)
- **Concept Drift Detection** — Monitor prediction distribution shifts
- **Performance Tracking** — Real-time accuracy, precision, recall monitoring
- **Alert System** — Slack, email, PagerDuty notifications on drift events
- **Root Cause Analysis** — Identify which features are drifting and why
- **Auto-Retrain Triggers** — Automatically trigger retraining pipelines
- **Dashboard** — Visual drift reports and model health scores

## Tech Stack

- **Backend:** Python, FastAPI
- **ML:** scikit-learn, scipy, evidently
- **Database:** PostgreSQL, TimescaleDB
- **Monitoring:** Prometheus, Grafana
- **Deployment:** Docker, Kubernetes

## Getting Started

```bash
git clone https://github.com/MukundaKatta/driftguard.git
cd driftguard
pip install -e .
driftguard monitor --model model.pkl --data incoming_data.csv
```

---

**Mukunda Katta** · [Officethree Technologies](https://github.com/MukundaKatta/Office3) · 2026
