# PowerShell script to run JudgeMyWay end-to-end pipeline
$ErrorActionPreference = "Stop"

Write-Host "=== 1. Initialization ===" -ForegroundColor Green
$env:PYTHONPATH="."
$env:PYTHONWARNINGS="ignore"

# Stop any existing server on port 8000
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | ForEach-Object { 
    Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue 
}

Write-Host "=== 2. Running P0: Recon & Schema Discovery ===" -ForegroundColor Green
python scripts/00_p0_recon.py

Write-Host "=== 3. Running P2: Ingestion & Data Cleaning ===" -ForegroundColor Green
python scripts/02_clean.py

Write-Host "=== 4. Running P3: Fitting Kaplan-Meier Survival Models ===" -ForegroundColor Green
python scripts/03_fit_km.py

Write-Host "=== 5. Running P4: Simulating Inventory Streams & Ageing Risk ===" -ForegroundColor Green
python scripts/04_build_streams.py

Write-Host "=== 6. Running Full Verification Test Suite ===" -ForegroundColor Green
python -m pytest tests/ -v

Write-Host "=== 7. Launching FastAPI Backend Server ===" -ForegroundColor Green
python -m uvicorn backend.main:app --port 8000
