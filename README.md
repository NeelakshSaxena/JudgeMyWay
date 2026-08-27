<div align="center">
  
# JudgeMyWay

**A Data-Driven Capacity Planning Console for Indian District Courts**

[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com/)
[![OR-Tools](https://img.shields.io/badge/OR--Tools-9.10-red.svg)](https://developers.google.com/optimization)
[![React](https://img.shields.io/badge/React-Vite-61DAFB.svg?logo=react)](https://reactjs.org/)

</div>

---

## Overview

**JudgeMyWay** is a retrospective simulation and capacity-planning tool designed specifically for court administrators and registrars. By analyzing a court's pending case inventory alongside historical disposal-time distributions, it projects how many cases will cross critical ageing thresholds (e.g., 3 years, 5 years). 

The system then recommends an **optimal disposal composition** across case categories to minimize these ageing crossings, while strictly enforcing fairness floors, historical realism bounds, and statistical confidence levels.

---

## Technical Architecture

JudgeMyWay is built on a high-performance, stateless architecture focusing on strict privacy and statistical rigor.

### 1. Survival Engine (Kaplan-Meier)
Instead of relying on flawed averages (which ignore pending cases), the system models the duration until case disposal using **Kaplan-Meier survival curves** (via the `lifelines` library). It gracefully handles right-censored data (cases still pending) to calculate the precise conditional probability of a case crossing a given threshold within the planning horizon. Curves dynamically fall back through a hierarchy (Court → District → State → Global) to ensure sufficient statistical support (n > 200 events).

### 2. Optimization Engine (CP-SAT)
Disposal targets are computed using **Google OR-Tools' CP-SAT solver**. The model seeks to minimize the integer-scaled sum of projected crossings, subject to:
- **Capacity Constraint:** Total targets cannot exceed court capacity minus reserved slots.
- **Fairness Floor:** No case stream receives a target below 80% of its strictly proportional baseline.
- **Realism Bound:** Recommendations cannot deviate from the historical disposal composition by more than 30%.
- **Confidence Cap:** Low-confidence statistical streams are tightly constrained to a 15% variance from their baseline.

If the problem is over-constrained, the solver autonomously applies a documented relaxation ladder rather than failing silently.

### 3. Tech Stack
- **Data Ingestion:** `duckdb` (for massive out-of-core file parsing), `pandas`, `pyarrow`
- **Backend:** `FastAPI`, `uvicorn`, `pydantic`
- **Frontend:** React (JavaScript), Vite, Recharts (Strictly local, no state libraries)

---

## Dataset & Citation

This project relies on the open-access **Development Data Lab (DDL)** Judicial dataset.

> **Citation:** 
> DevDataLab Judicial Dataset. Available at: [https://www.devdatalab.org/judicial-data](https://www.devdatalab.org/judicial-data).

---

## How to Run Locally

*Note: This is a prototype MVP. There is no cloud deployment, and all execution happens locally.*

### 1. Environment Setup
Ensure you have Python 3.11 installed. Create a virtual environment and install the required dependencies:

```bash
# Create environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate
# Activate (Unix/macOS)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Full Pipeline Execution
To process the raw data, fit the survival models, and run the complete optimization pipeline (Phases P0 to P10):

```bash
# On Windows PowerShell:
.\scripts\run_all.ps1

# On Unix/macOS:
./scripts/run_all.sh
```

### 3. Running the Demo (Frozen State)
To run the frozen demo scenario for presentations without triggering live heavy computation:

**Terminal 1 (Backend):**
```bash
# Start API in Demo Mode
DEMO_MODE=1 uvicorn backend.main:app --port 8000
```
*(On Windows PowerShell, use: `$env:DEMO_MODE="1"; uvicorn backend.main:app --port 8000`)*

**Terminal 2 (Frontend):**
```bash
cd frontend
npm install
npm run dev
```
Navigate to `http://localhost:5173` in your browser.

---

## Real vs. Simulated

- **Real:** The underlying math, Kaplan-Meier curves, dataset cleaning, OR-Tools CP-SAT optimization model, and statistical logic are fully operational and operating on real historical data.
- **Simulated:** The API endpoints under `DEMO_MODE=1` serve pre-computed responses frozen into a scenario file. The "pending inventory" evaluated is simulated retrospectively by treating historical cases from the final 2 years of the dataset as currently pending.

---

## Strict Limitations (Verbatim from Spec)

- **NEVER rank, score, or expose any individual case.** All output is strictly at the CASE STREAM aggregate level (`case_type` × `age_band`). The API must not return per-case values, even in debug output.
- **NEVER use forbidden columns as model features.** (e.g., disposition, outcome, decision_date, judge_id, judge_position, petitioner_name, respondent_name, party gender, hearing_date).
- **NEVER drop cases with a missing decision date.** They are strictly treated as **RIGHT-CENSORED** and must be kept. Dropping them biases every duration estimate downward.
- **NEVER infer urgency** (e.g., bail, custody, interim relief, vulnerability). That data is absent.
- **NEVER claim capacity causes faster disposal.** The decision variable is purely DISPOSAL TARGETS.
- **NEVER invent data, numbers, or performance figures.** If a value isn't computed mathematically, it isn't printed.
- **Simulated components must be clearly labelled SIMULATED in the UI.**
