#!/usr/bin/env bash
# End-to-end pipeline execution script for JudgeMyWay
set -e

echo "=== 1. Setting PYTHONPATH ==="
export PYTHONPATH="."

echo "=== 2. Running P0: Recon & Schema Discovery ==="
python scripts/00_p0_recon.py

echo "=== 3. Running P2: Ingestion & Data Cleaning ==="
python scripts/02_clean.py

echo "=== 4. Running P3: Fitting Kaplan-Meier Survival Models ==="
python scripts/03_fit_km.py

echo "=== 5. Running P4: Simulating Inventory Streams & Ageing Risk ==="
python scripts/04_build_streams.py

echo "=== 6. Running Full Verification Test Suite ==="
pytest tests/test_all.py tests/test_api.py -v

echo "=== 7. Launching FastAPI Backend Server ==="
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
