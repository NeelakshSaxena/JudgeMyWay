# B1 - p_cross conditional + horizon + fallback

import numpy as np
import pandas as pd
from lifelines import KaplanMeierFitter
from src.survival.km import fit_strata, p_cross
from src.survival.fallback import resolve
from src.streams.build import build_streams

def test_p_cross_t1():
    # T1 p_cross(T, a=0, H=huge) equals the unconditional S(T) within 1e-9
    df = pd.DataFrame({"duration_days": [10, 20, 30], "event_observed": [1, 1, 0]})
    kmf = KaplanMeierFitter().fit(df['duration_days'], df['event_observed'])
    p, lo, hi = p_cross(kmf, 15, 0, 10000)
    s_t = kmf.survival_function_at_times(15).iloc[0]
    assert abs(p - s_t) < 1e-9

def test_p_cross_t2():
    # T2 p_cross(T, a, H=huge) >= p_cross(T, 0, H=huge) for a > 0
    df = pd.DataFrame({"duration_days": [10, 20, 30, 40], "event_observed": [1, 1, 1, 0]})
    kmf = KaplanMeierFitter().fit(df['duration_days'], df['event_observed'])
    p_a0, _, _ = p_cross(kmf, 25, 0, 10000)
    p_a15, _, _ = p_cross(kmf, 25, 15, 10000)
    assert p_a15 >= p_a0

def test_p_cross_t3():
    # T3 p_cross returns exactly 0.0 when (T - a) > H
    df = pd.DataFrame({"duration_days": [10, 20], "event_observed": [1, 1]})
    kmf = KaplanMeierFitter().fit(df['duration_days'], df['event_observed'])
    p, lo, hi = p_cross(kmf, 50, 10, 20)
    assert p == 0.0

def test_p_cross_t4():
    # T4 p_cross returns nan beyond observed support
    df = pd.DataFrame({"duration_days": [10, 20], "event_observed": [1, 1]})
    kmf = KaplanMeierFitter().fit(df['duration_days'], df['event_observed'])
    p, lo, hi = p_cross(kmf, 30, 25, 10000)
    assert np.isnan(p)

def test_p_cross_t5():
    # T5 all returned probabilities lie in [0, 1] or are nan
    df = pd.DataFrame({"duration_days": [10, 20], "event_observed": [1, 1]})
    kmf = KaplanMeierFitter().fit(df['duration_days'], df['event_observed'])
    for a in [0, 5, 15, 25]:
        for T in [5, 15, 25]:
            p, lo, hi = p_cross(kmf, T, a, 10000)
            for val in [p, lo, hi]:
                assert np.isnan(val) or (0.0 <= val <= 1.0)

def test_fallback_t6():
    # T6 a stratum below min_events triggers the fallback and reports a non-primary level
    df = pd.DataFrame({
        "case_type": ["A", "A", "A", "A"],
        "court_id": [1, 1, 2, 2],
        "district": ["D1", "D1", "D1", "D1"],
        "state": ["S1", "S1", "S1", "S1"],
        "duration_days": [10, 20, 30, 40],
        "event_observed": [1, 1, 1, 1]
    })
    curves = fit_strata(df, min_events=200)  # Returns empty dict
    kmf, level, low_conf = resolve("A", 1, curves, df)
    # The fallback should drop to global or case_type since counts are too small everywhere.
    assert level in ["case_type", "global"]
    assert low_conf is True

def test_build_streams_t7():
    # T7 age-band assignment is correct at exact boundaries (365, 1095, 1825, 3650 days)
    df = pd.DataFrame({
        "case_type": ["A"] * 4,
        "court_id": [1] * 4,
        "district": ["D1"] * 4,
        "state": ["S1"] * 4,
        "filing_date": pd.to_datetime(["2017-06-01"] * 4),  # Ensure it's recent so it is picked up
        "duration_days": [365, 1095, 1825, 3650],
        "event_observed": [0, 0, 0, 0]
    })
    curves = fit_strata(df, min_events=200)
    streams = build_streams(df, curves, 730, 365)

    # We should have one stream per age_band populated
    age_bands = set(streams['age_band'].values)
    assert "0-1y" in age_bands
    assert "1-3y" in age_bands
    assert "3-5y" in age_bands
    assert "5-10y" in age_bands

def test_build_streams_t8():
    # T8 sum of stream n equals the pending inventory size
    df = pd.DataFrame({
        "case_type": ["A", "B", "C"],
        "court_id": [1, 2, 3],
        "district": ["D1", "D2", "D3"],
        "state": ["S1", "S2", "S3"],
        "filing_date": pd.to_datetime(["2020-01-01"] * 3),
        "duration_days": [10, 400, 2000],
        "event_observed": [0, 0, 0]
    })
    curves = {}
    streams = build_streams(df, curves, 730, 365)
    assert streams['n'].sum() == 3

def test_build_streams_t9():
    # T9 no per-case column survives into the stream output
    df = pd.DataFrame({
        "case_type": ["A"],
        "court_id": [1],
        "district": ["D1"],
        "state": ["S1"],
        "filing_date": pd.to_datetime(["2020-01-01"]),
        "duration_days": [10],
        "event_observed": [0]
    })
    curves = {}
    streams = build_streams(df, curves, 730, 365)
    columns = set(streams.columns)
    # Check that per-case columns are NOT present
    for col in ["court_id", "district", "state", "filing_date", "duration_days", "event_observed"]:
        assert col not in columns
