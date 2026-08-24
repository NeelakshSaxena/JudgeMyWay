# JudgeMyWay

A capacity-planning tool for Indian district court administrators.

Given a court's pending case inventory and historical disposal-time distributions, it projects how many cases will cross an ageing threshold, and recommends a disposal composition across case categories that minimises that number under fairness constraints. A registrar can override any recommendation; the system quantifies the consequence.

## Dataset

This project uses the Indian district court dataset published by DevDataLab:
*   **Link:** [https://www.devdatalab.org/judicial-data](https://www.devdatalab.org/judicial-data)
*   For the current pipeline, download a sample state (e.g., Maharashtra 2010-2016).
*   Extract the CSV file(s) into the `data/raw/` directory.

## Environment Setup

Ensure you have Python 3.11 installed.

```powershell
# Create a virtual environment
python -m venv venv

# Activate it (Windows)
.\venv\Scripts\activate

# Install exact pinned dependencies
pip install -r requirements.txt
```

## Reproducing the Pipeline (Up to P6)

The project is currently built up to **P6: API**. To reproduce the pipeline exactly on your machine, follow these steps in order.

Make sure your `PYTHONPATH` is set to the project root before running scripts:
```powershell
$env:PYTHONPATH="."
```

### 1. P0: Recon & Schema Discovery
This phase verifies the schema mapping against the raw CSV files in `data/raw/`.
```powershell
python scripts/00_p0_recon.py
```
*Output: Generates a recon report at `outputs/p0_recon.md`.*

### 2. P2: Ingestion & Cleaning
This phase reads the raw data, applies strict schema rules, drops forbidden columns (like names or genders), computes censoring (`event_observed`), and calculates `duration_days`.
```powershell
python scripts/02_clean.py
```
*Output: Generates `data/processed/survival_dataset.parquet` and `outputs/quality_report.json`.*

### 3. P3: Survival Engine
This phase fits the Kaplan-Meier survival curves on the cleaned dataset. It builds a hierarchical fallback ladder (`case_type x court` -> `case_type x district` -> `case_type x state` -> `global`) to handle data sparsity.
```powershell
python scripts/03_fit_km.py
```
*Output: Saves fitted models to `models/km_curves.pkl`.*

### 4. P4: Streams & Risk
This phase simulates a retrospective inventory (from the last 2 years of data). It places cases into age bands and computes the probability (`p_cross`) of each case crossing a 2-year threshold within a 12-month horizon. It then aggregates these probabilities to create **case streams**.
```powershell
python scripts/04_build_streams.py
```
*Output: Generates the stream metrics file `outputs/stream_metrics.parquet`.*

### 5. P5 & P6: Optimization Engine & API Server
The backend exposes FastAPI endpoints leveraging OR-Tools CP-SAT to dynamically optimize court allocations. To start the server:
```powershell
python -m uvicorn backend.main:app --port 8000
```
*Output: The backend API runs on `http://localhost:8000`.*

## Verification & Testing

The project has a strict testing suite to guarantee statistical correctness, constraint feasibility, and API functionality.

```powershell
python -m pytest tests/test_all.py tests/test_api.py -v
```
*All tests should pass green.*

---
**Status**: The pipeline is fully prepared up to **P6: API** and is ready to proceed to **P7: Frontend**.
