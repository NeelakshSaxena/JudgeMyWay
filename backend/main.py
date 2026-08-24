from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Dict, Any
import pandas as pd
import pickle
import json
import numpy as np

from src.optimization.allocate import allocate
from src.optimization.override import override
from src.survival.km import p_cross

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class BlockCaseIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if response.headers.get("content-type") == "application/json":
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            if b"case_id" in body:
                raise RuntimeError("CRITICAL ERROR: Response payload contains per-case field 'case_id'")
            return Response(content=body, status_code=response.status_code, 
                            headers=dict(response.headers), media_type="application/json")
        return response

app.add_middleware(BlockCaseIdMiddleware)

@app.get("/health")
def health_api():
    return {"ok": True}

STATE = {}

def check_models():
    for route in app.routes:
        if hasattr(route, "response_model") and route.response_model:
            model = route.response_model
            if hasattr(model, "model_fields"):
                fields = model.model_fields.keys()
            elif hasattr(model, "__fields__"):
                fields = model.__fields__.keys()
            else:
                fields = []
            assert "case_id" not in fields, f"case_id found in {model}"

@app.on_event("startup")
def startup_event():
    check_models()
    STATE['streams_df'] = pd.read_parquet("outputs/stream_metrics.parquet")
    with open("models/km_curves.pkl", "rb") as f:
        STATE['km_curves'] = pickle.load(f)
    with open("outputs/quality_report.json", "r") as f:
        STATE['quality'] = json.load(f)

class OptimizeRequest(BaseModel):
    throughput: int = Field(..., ge=0)
    reserved: int = Field(0, ge=0)
    threshold_days: int = Field(1095, gt=0)
    horizon_days: int = Field(365, gt=0)

    @model_validator(mode='after')
    def check_reserved(self):
        if self.reserved > self.throughput:
            raise ValueError("reserved cannot exceed throughput")
        return self

class OverrideRequest(BaseModel):
    throughput: int = Field(..., ge=0)
    reserved: int = Field(0, ge=0)
    threshold_days: int = Field(1095, gt=0)
    horizon_days: int = Field(365, gt=0)
    locked: Dict[str, int]

    @model_validator(mode='after')
    def check_reserved(self):
        if self.reserved > self.throughput:
            raise ValueError("reserved cannot exceed throughput")
        return self

class MetaResponse(BaseModel):
    court: str
    district: str
    period: str
    n_cases: int
    default_throughput: int
    threshold_days: int
    horizon_days: int
    mode: str

class StreamItem(BaseModel):
    id: str
    case_type: str
    age_band: str
    n: int
    p: Optional[float]
    p_lo: Optional[float]
    p_hi: Optional[float]
    low_confidence: bool
    stratum_level: str
    historical_share: float
    projected_crossings: float

class StreamsResponse(BaseModel):
    streams: List[StreamItem]

class OptimizeResponse(BaseModel):
    feasible: bool
    allocation: Dict[str, int]
    before: Dict[str, int]
    after: Dict[str, int]
    relaxed_constraints: List[str]
    baseline: Dict[str, int]

class OverrideResponse(BaseModel):
    feasible: bool
    before: Dict[str, float]
    after: Dict[str, float]
    delta: float
    affected_streams: List[str]
    violations: List[str]
    relaxed_constraints: List[str]
    reason: Optional[str] = None

class QualityResponse(BaseModel):
    records_loaded: int
    records_excluded: int
    records_censored: int
    exclusions: Dict[str, int]
    low_confidence_streams: int


@app.get("/meta", response_model=MetaResponse)
def meta():
    df = STATE['streams_df']
    n_cases = int(df['n'].sum())
    
    q = STATE['quality']
    total_disposals = q.get('records_retained', 0) - q.get('censored', 0)
    # Estimate 9 years (2010-2018) for annual throughput
    default_throughput = int(max(0, total_disposals / 9.0))
    
    return MetaResponse(
        court="All Courts",
        district="DevDataLab",
        period="2010 - 2018",
        n_cases=n_cases,
        default_throughput=default_throughput,
        threshold_days=1095,
        horizon_days=365,
        mode="REAL"
    )

AGE_BAND_MAPPING = {
    "0-1y": 182.5,
    "1-3y": 730,
    "3-5y": 1460,
    "5-10y": 2737.5,
    "10y+": 3650
}

def get_recomputed_p(case_type: str, age_band: str, threshold: int, horizon: int) -> tuple:
    age = AGE_BAND_MAPPING.get(age_band, 0)
    matching_curves = [kmf for (ct, cid), kmf in STATE['km_curves'].items() if ct == case_type]
    
    if not matching_curves:
        return (None, None, None)
        
    ps, los, his = [], [], []
    for kmf in matching_curves:
        p, lo, hi = p_cross(kmf, threshold, age, horizon)
        if p is not None and not np.isnan(p):
            ps.append(p)
        if lo is not None and not np.isnan(lo):
            los.append(lo)
        if hi is not None and not np.isnan(hi):
            his.append(hi)
            
    p = np.mean(ps) if ps else None
    lo = np.mean(los) if los else None
    hi = np.mean(his) if his else None
    
    return (float(p) if pd.notna(p) else None, 
            float(lo) if pd.notna(lo) else None, 
            float(hi) if pd.notna(hi) else None)

@app.get("/streams", response_model=StreamsResponse)
def get_streams_api(threshold_days: int = 1095, horizon_days: int = 365):
    df = STATE['streams_df']
    
    if threshold_days == 1095 and horizon_days == 365:
        records = df.to_dict(orient="records")
        for r in records:
            if pd.isna(r.get('p')): r['p'] = None
            if pd.isna(r.get('p_lo')): r['p_lo'] = None
            if pd.isna(r.get('p_hi')): r['p_hi'] = None
        return StreamsResponse(streams=records)
        
    new_records = []
    for _, row in df.iterrows():
        rec = row.to_dict()
        p, p_lo, p_hi = get_recomputed_p(rec['case_type'], rec['age_band'], threshold_days, horizon_days)
        rec['p'] = p
        rec['p_lo'] = p_lo
        rec['p_hi'] = p_hi
        rec['projected_crossings'] = rec['n'] * p if p is not None else 0.0
        new_records.append(rec)
        
    return StreamsResponse(streams=new_records)

@app.post("/optimize", response_model=OptimizeResponse)
def optimize_api(req: OptimizeRequest):
    streams_resp = get_streams_api(req.threshold_days, req.horizon_days)
    streams_list = [s.model_dump() if hasattr(s, 'model_dump') else s.dict() for s in streams_resp.streams]
    
    for s in streams_list:
        if s.get('p') is None:
            s['p'] = 0.0
            
    res = allocate(streams_list, req.throughput, req.reserved)

    return OptimizeResponse(
        feasible=res["feasible"],
        allocation=res["allocation"],
        before={"crossings": int(res["before"]["crossings"])},
        after={"crossings": int(res["after"]["crossings"])},
        relaxed_constraints=res["relaxed_constraints"],
        baseline=res["baseline"]
    )

@app.post("/override", response_model=OverrideResponse)
def override_api(req: OverrideRequest):
    streams_resp = get_streams_api(req.threshold_days, req.horizon_days)
    streams_list = [s.model_dump() if hasattr(s, 'model_dump') else s.dict() for s in streams_resp.streams]

    for s in streams_list:
        if s.get('p') is None:
            s['p'] = 0.0

    res = override(streams_list, req.throughput, req.reserved, req.locked)

    return OverrideResponse(
        feasible=res["feasible"],
        before=res["before"],
        after=res["after"],
        delta=res["delta"],
        affected_streams=res["affected_streams"],
        violations=res["violations"],
        relaxed_constraints=res["relaxed_constraints"],
        reason=res.get("reason")
    )

@app.get("/quality", response_model=QualityResponse)
def quality_api():
    q = STATE['quality']
    df = STATE['streams_df']
    low_conf_count = int(df['low_confidence'].sum())
    
    exclusions = {
        "missing_filing": q.get("missing_filing") or 0,
        "impossible_dates": q.get("impossible_dates") or 0,
        "duplicates": q.get("duplicates") or 0,
        "unknown_case_type": q.get("unknown_case_type") or 0,
        "transferred": q.get("transferred") or 0,
        "same_day": q.get("same_day") or 0,
        "extreme_duration": q.get("extreme_duration") or 0,
    }
    
    return QualityResponse(
        records_loaded=q.get("records_loaded") or 0,
        records_excluded=(q.get("records_loaded") or 0) - (q.get("records_retained") or 0),
        records_censored=q.get("censored") or 0,
        exclusions=exclusions,
        low_confidence_streams=low_conf_count
    )
