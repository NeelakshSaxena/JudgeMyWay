import pandas as pd
import numpy as np
import yaml
from src.data.schema import assert_clean

def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    counters = {}
    
    with open("config/schema.yaml", "r") as f:
        schema = yaml.safe_load(f)
        
    data_cutoff = pd.to_datetime(schema.get('data_cutoff'))
    
    # 1. missing filing_date
    m_filing = df['filing_date'].isna()
    counters['missing_filing'] = int(m_filing.sum())
    df = df[~m_filing].copy()
    
    # 2. impossible dates
    if 'decision_date' in df.columns:
        imp_dates = df['decision_date'].notna() & (df['decision_date'] < df['filing_date'])
        counters['impossible_dates'] = int(imp_dates.sum())
        df = df[~imp_dates].copy()
    else:
        counters['impossible_dates'] = 0
        
    # 3. duplicate case_id
    dup = df.duplicated(subset=['case_id'], keep='first')
    counters['duplicates'] = int(dup.sum())
    df = df[~dup].copy()
    
    # 4. blank/unknown case_type
    if 'case_type' in df.columns:
        m_type = df['case_type'].isna() | (df['case_type'].astype(str).str.strip() == "")
        counters['unknown_case_type'] = int(m_type.sum())
        df = df[~m_type].copy()
    else:
        counters['unknown_case_type'] = 0
        
    # Compute duration first for following filters
    df['filing_date'] = pd.to_datetime(df['filing_date'])
    if 'decision_date' in df.columns:
        df['decision_date'] = pd.to_datetime(df['decision_date'])
        event_observed = df['decision_date'].notna() & (df['decision_date'] <= data_cutoff)
    else:
        event_observed = pd.Series(False, index=df.index)
        
    df['event_observed'] = event_observed.astype(int)
    counters['censored'] = int((~event_observed).sum())
    
    dur_observed = (df['decision_date'] - df['filing_date']).dt.days if 'decision_date' in df.columns else 0
    dur_censored = (data_cutoff - df['filing_date']).dt.days
    
    df['duration_days'] = np.where(event_observed, dur_observed, dur_censored)
    
    # 5. duration == 0 -> floor to 1 day
    same_day = df['duration_days'] == 0
    counters['same_day'] = int(same_day.sum())
    df.loc[same_day, 'duration_days'] = 1
    
    # 6. duration > 7300 days -> winsorise to 7300
    extreme_dur = df['duration_days'] > 7300
    counters['extreme_duration'] = int(extreme_dur.sum())
    df.loc[extreme_dur, 'duration_days'] = 7300
    
    # 7. transfer_flag
    if schema.get('transfer_flag') and 'transfer_flag' in df.columns:
        is_transferred = df['transfer_flag'].astype(str).str.lower().isin(['1', 'true', 't', 'y', 'yes'])
        counters['transferred'] = int(is_transferred.sum())
        df = df[~is_transferred].copy()
    else:
        counters['transferred'] = None

    # registration lag
    if 'registration_date' in df.columns and schema.get('registration_date'):
        df['registration_date'] = pd.to_datetime(df['registration_date'])
        df['registration_lag_days'] = (df['registration_date'] - df['filing_date']).dt.days
        
    # keep only final columns (excluding decision_date)
    final_cols = ['case_id', 'case_type', 'court_id', 'district', 'state', 'filing_date', 'duration_days', 'event_observed']
    if 'registration_lag_days' in df.columns:
        final_cols.append('registration_lag_days')
    if 'act_section_group' in df.columns:
        final_cols.append('act_section_group')
        
    final_cols = [c for c in final_cols if c in df.columns]
    df = df[final_cols]
    
    assert_clean(df)
    
    return df, counters
