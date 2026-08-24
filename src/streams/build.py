import pandas as pd
import numpy as np
import re
from typing import List, Dict, Any
from src.survival.km import p_cross
from src.survival.fallback import resolve

def slugify(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', str(text).lower()).strip('_')

def build_streams(df: pd.DataFrame, curves: dict, threshold_days: int, horizon_days: int) -> List[Dict[str, Any]]:
    # "Simulate a 'current inventory' from the historical data: take cases filed in the final 2 years"
    max_year = df['filing_date'].dt.year.max()
    is_recent = df['filing_date'].dt.year >= (max_year - 1)
    pending = df[(df['event_observed'] == 0) & is_recent].copy()
    
    # Calculate historical shares from ALL closed cases (not just the final 2 years)
    closed_cases = df[df['event_observed'] == 1]
    total_closed = len(closed_cases)
    hist_counts = closed_cases['case_type'].value_counts().to_dict()
    
    # Age band assignment (T7 boundaries)
    bins = [-1, 365, 1095, 1825, 3650, float('inf')]
    labels = ["0-1y", "1-3y", "3-5y", "5-10y", "10y+"]
    pending['age_band'] = pd.cut(pending['duration_days'], bins=bins, labels=labels)
    
    # Vectorized lookups for Fallback & KM curves
    results_p = np.zeros(len(pending), dtype=float)
    results_lo = np.zeros(len(pending), dtype=float)
    results_hi = np.zeros(len(pending), dtype=float)
    results_level = np.empty(len(pending), dtype=object)
    results_low_conf = np.zeros(len(pending), dtype=bool)
    
    unique_groups = pending[['case_type', 'court_id']].drop_duplicates()
    group_info = {}
    for _, row in unique_groups.iterrows():
        ct = row['case_type']
        cid = row['court_id']
        group_info[(ct, cid)] = resolve(ct, cid, curves, df)
        
    case_types = pending['case_type'].values
    court_ids = pending['court_id'].values
    ages = pending['duration_days'].values
    
    p_cache = {}
    for i in range(len(pending)):
        ct = case_types[i]
        cid = court_ids[i]
        age = ages[i]
        
        kmf, level, low_conf = group_info[(ct, cid)]
        cache_key = (id(kmf), age)
        
        if cache_key not in p_cache:
            p_cache[cache_key] = p_cross(kmf, threshold_days, age, horizon_days)
            
        p, lo, hi = p_cache[cache_key]
        
        results_p[i] = p
        results_lo[i] = lo
        results_hi[i] = hi
        results_level[i] = level
        # if the rung is NOT case_type x court (primary) -> True
        # but the prompt says: >25% of cases resolved *below the primary rung*. 
        # So low_conf boolean here means "below primary rung". 
        results_low_conf[i] = (level != "case_type x court")

    pending['p'] = results_p
    pending['lo'] = results_lo
    pending['hi'] = results_hi
    pending['level'] = results_level
    pending['below_primary'] = results_low_conf
    
    streams = []
    
    # "inventory-weighted mean of per-case p" -> which just means mean() in the grouped subset
    for (ctype, age_band), s_group in pending.groupby(['case_type', 'age_band'], observed=True):
        n = len(s_group)
        if n == 0:
            continue
            
        p = s_group['p'].mean()
        p_lo = s_group['lo'].mean()
        p_hi = s_group['hi'].mean()
        
        # True if >25% of its cases resolved below the primary rung
        low_confidence = (s_group['below_primary'].mean() > 0.25)
        stratum_level = s_group['level'].mode()[0] if not s_group['level'].empty else "global"
        
        hist_share = hist_counts.get(ctype, 0) / total_closed if total_closed > 0 else 0
        proj = n * p if not np.isnan(p) else 0.0
        
        streams.append({
            "id": f"stream_{slugify(ctype)}_{slugify(age_band)}",
            "case_type": str(ctype),
            "age_band": str(age_band),
            "n": int(n),
            "p": float(p) if pd.notna(p) else None,
            "p_lo": float(p_lo) if pd.notna(p_lo) else None,
            "p_hi": float(p_hi) if pd.notna(p_hi) else None,
            "low_confidence": bool(low_confidence),
            "stratum_level": str(stratum_level),
            "historical_share": float(hist_share),
            "projected_crossings": float(proj)
        })
        
    return pd.DataFrame(streams)
