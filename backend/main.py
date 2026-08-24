from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class OptimizeRequest(BaseModel):
    throughput: int
    reserved: int
    threshold_days: int
    horizon_days: int

class OverrideRequest(BaseModel):
    throughput: int
    reserved: int
    threshold_days: int
    horizon_days: int
    locked: Dict[str, int]

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/meta")
def meta():
    return {
        "court": "District Court",
        "district": "Mock District",
        "period": "2010 - 2016",
        "n_cases": 15000,
        "default_throughput": 5000,
        "threshold_days": 1095,
        "horizon_days": 365,
        "mode": "SIMULATED"
    }

@app.get("/streams")
def streams(threshold_days: int = 1095, horizon_days: int = 365):
    return {
        "streams": [
            {
                "id": f"stream_{i}",
                "case_type": "Civil Suit",
                "age_band": "1-3y",
                "n": 1000,
                "p": 0.25,
                "p_lo": 0.20,
                "p_hi": 0.30,
                "low_confidence": False,
                "stratum_level": "case_type x court",
                "historical_share": 0.1,
                "baseline": 100,
                "projected_crossings": 250
            } for i in range(8)
        ]
    }

@app.post("/optimize")
def optimize(req: OptimizeRequest):
    return {
        "feasible": True,
        "allocation": {f"stream_{i}": 120 for i in range(8)},
        "before": {"crossings": 2000},
        "after": {"crossings": 1500},
        "relaxed_constraints": []
    }

@app.post("/override")
def override(req: OverrideRequest):
    return {
        "before": {"crossings": 1500},
        "after": {"crossings": 1550},
        "delta": 50,
        "affected_streams": ["stream_1", "stream_2"],
        "violations": []
    }

@app.get("/quality")
def quality():
    return {
        "records_loaded": 20000,
        "records_excluded": 5000,
        "records_censored": 2000,
        "exclusions": {
            "missing_filing": 1000,
            "impossible_dates": 1000,
            "duplicates": 1000,
            "unknown_case_type": 1000,
            "transferred": 1000
        },
        "low_confidence_streams": 2
    }
