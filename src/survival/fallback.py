import pandas as pd
from lifelines import KaplanMeierFitter
import numpy as np

# Cache the fallbacks so we only fit them once per hierarchy level
FALLBACK_CACHE = {}
COURT_LOC_CACHE = {}
INDEX_CACHE = {}

def get_court_loc(df, court_id):
    if not COURT_LOC_CACHE:
        # Build all at once
        locs = df[['court_id', 'district', 'state']].drop_duplicates('court_id')
        for _, r in locs.iterrows():
            COURT_LOC_CACHE[r['court_id']] = (r['district'], r['state'])
    return COURT_LOC_CACHE.get(court_id, (None, None))
    
def get_fallback(df, key, indices):
    if key not in FALLBACK_CACHE:
        if indices is None or len(indices) == 0:
            FALLBACK_CACHE[key] = None
        else:
            subset = df.iloc[indices]
            events = subset['event_observed'].sum()
            if events >= 200:
                kmf = KaplanMeierFitter().fit(subset['duration_days'], subset['event_observed'])
                FALLBACK_CACHE[key] = kmf
            else:
                FALLBACK_CACHE[key] = None
    return FALLBACK_CACHE[key]

def resolve(case_type, court_id, curves, df):
    # Ensure indices are cached for O(1) lookups
    if not INDEX_CACHE:
        INDEX_CACHE['dist'] = df.groupby(['case_type', 'district']).indices
        INDEX_CACHE['state'] = df.groupby(['case_type', 'state']).indices
        INDEX_CACHE['ctype'] = df.groupby('case_type').indices
        
    # 1. Primary strata
    if (case_type, court_id) in curves:
        kmf = curves[(case_type, court_id)]
        n_ev = sum(kmf.event_observed)
        return kmf, "case_type x court", bool(n_ev < 500)
        
    district, state = get_court_loc(df, court_id)
    
    if district is not None:
        # 2. District level
        key_dist = ("district", case_type, district)
        idx = INDEX_CACHE['dist'].get((case_type, district), [])
        kmf = get_fallback(df, key_dist, idx)
        if kmf is not None:
            return kmf, "case_type x district", True
            
        # 3. State level
        key_state = ("state", case_type, state)
        idx = INDEX_CACHE['state'].get((case_type, state), [])
        kmf = get_fallback(df, key_state, idx)
        if kmf is not None:
            return kmf, "case_type x state", True

    # 4. Global case type
    key_ctype = ("case_type", case_type)
    idx = INDEX_CACHE['ctype'].get(case_type, [])
    kmf = get_fallback(df, key_ctype, idx)
    if kmf is not None:
        return kmf, "case_type", True
        
    # 5. Global fallback
    key_global = ("global",)
    idx = np.arange(len(df))
    kmf = get_fallback(df, key_global, idx)
    return kmf, "global", True
