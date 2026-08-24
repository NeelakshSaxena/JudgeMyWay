import pandas as pd
import numpy as np
from lifelines import KaplanMeierFitter

def fit_strata(df: pd.DataFrame, min_events: int = 200) -> dict:
    curves = {}
    grouped = df.groupby(['case_type', 'court_id'])
    for name, group in grouped:
        if group['event_observed'].sum() >= min_events:
            kmf = KaplanMeierFitter()
            kmf.fit(group['duration_days'], event_observed=group['event_observed'])
            curves[name] = kmf
    return curves

def p_cross(kmf, threshold_days: float, current_age_days: float, horizon_days: float) -> tuple:
    if (threshold_days - current_age_days) >= horizon_days:
        return (0.0, 0.0, 0.0)
        
    if kmf is None:
        return (np.nan, np.nan, np.nan)
        
    sf = kmf.survival_function_
    ci = kmf.confidence_interval_
    t = sf.index.values
    
    def lookup(frame, col, val):
        idx = np.searchsorted(t, val, side="right") - 1
        idx = max(0, idx)
        return frame.iloc[idx][col]
        
    s_col = sf.columns[0]
    lo_col = ci.columns[0]
    hi_col = ci.columns[1]
    
    s_a = lookup(sf, s_col, current_age_days)
    if s_a <= 1e-9:
        return (np.nan, np.nan, np.nan)
        
    s_t = lookup(sf, s_col, threshold_days)
    lo_a = lookup(ci, lo_col, current_age_days)
    lo_t = lookup(ci, lo_col, threshold_days)
    hi_a = lookup(ci, hi_col, current_age_days)
    hi_t = lookup(ci, hi_col, threshold_days)
    
    p = s_t / s_a
    lo = lo_t / lo_a if lo_a > 1e-9 else np.nan
    hi = hi_t / hi_a if hi_a > 1e-9 else np.nan
    
    def clamp(v):
        if pd.isna(v): return np.nan
        return float(np.clip(v, 0.0, 1.0))
        
    return (clamp(p), clamp(lo), clamp(hi))
