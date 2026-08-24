# PowerShell script to run JudgeMyWay end-to-end pipeline
$ErrorActionPreference = "Stop"

Write-Host "=== 1. Setting PYTHONPATH ===" -ForegroundColor Green
$env:PYTHONPATH="."

Write-Host "=== 2. Running P0: Recon & Schema Discovery ===" -ForegroundColor Green
venv/Scripts/python.exe scripts/00_p0_recon.py

Write-Host "=== 3. Running P2: Ingestion & Data Cleaning ===" -ForegroundColor Green
venv/Scripts/python.exe scripts/02_clean.py

Write-Host "=== 4. Running P3: Fitting Kaplan-Meier Survival Models ===" -ForegroundColor Green
venv/Scripts/python.exe scripts/03_fit_km.py

Write-Host "=== 5. Running P4: Simulating Inventory Streams & Ageing Risk ===" -ForegroundColor Green
venv/Scripts/python.exe scripts/04_build_streams.py

Write-Host "=== 6. Running Full Verification Test Suite ===" -ForegroundColor Green
venv/Scripts/python.exe -m pytest tests/test_all.py tests/test_api.py -v

Write-Host "=== 7. Launching FastAPI Backend Server ===" -ForegroundColor Green
venv/Scripts/python.exe -m uvicorn backend.main:app --port 8000
