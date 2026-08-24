import json
import os
import pickle

import pandas as pd
import yaml

from src.data.load import load_raw
from src.data.clean import clean
from src.evaluation.baseline import (
    censoring_impact,
    temporal_validation,
    optimiser_comparison,
    sensitivity_table,
    constraint_audit,
)
from src.streams.build import build_streams

DEFAULT_THRESHOLD_DAYS = 1095
DEFAULT_HORIZON_DAYS = 365

# The full published dataset spans 2010-2018 across every state; loading more than one
# filing year at a time already required cutting scope to avoid OOM (see scripts/02_clean.py).
# Temporal validation needs at least a train + a later cohort, so we extend to the smallest
# window that still tests genuine out-of-time generalization: train on 2010 (the same filing
# year the production pipeline is built from), validate on 2011, test out-of-time on 2012.
TRAIN_YEAR = 2010
VALIDATE_YEAR = 2011
TEST_YEAR = 2012

SENSITIVITY_THRESHOLD_YEARS = [1, 3, 5, 10]
SENSITIVITY_HORIZON_MONTHS = [6, 12, 24]


def _load_cohort(year: int) -> pd.DataFrame:
    df_raw = load_raw(state=None, year_min=year, year_max=year)
    df_clean, _counters = clean(df_raw)
    return df_clean


def _fmt_days(x):
    return "n/a" if x is None else f"{x:,.0f} days"


def _fmt_pct(x):
    return "n/a" if x is None else f"{x:.1f}%"


def run():
    with open("config/schema.yaml", "r") as f:
        schema = yaml.safe_load(f)

    print("Loading production survival dataset (train cohort, filing year "
          f"{TRAIN_YEAR})...")
    train_df = pd.read_parquet("data/processed/survival_dataset.parquet")

    with open("models/km_curves.pkl", "rb") as f:
        curves = pickle.load(f)

    streams_df = pd.read_parquet("outputs/stream_metrics.parquet")
    streams = streams_df.to_dict("records")
    for s in streams:
        if pd.isna(s.get("p")):
            s["p"] = 0.0

    with open("outputs/quality_report.json", "r") as f:
        quality = json.load(f)

    # ---- 1. Censoring impact ----
    print("Computing censoring impact (naive median vs Kaplan-Meier median)...")
    censoring = censoring_impact(train_df)

    # ---- 2. Temporal validation ----
    print(f"Loading validate cohort (filing year {VALIDATE_YEAR})...")
    validate_df = _load_cohort(VALIDATE_YEAR)
    print(f"Loading test cohort (filing year {TEST_YEAR})...")
    test_df = _load_cohort(TEST_YEAR)
    print("Computing temporal validation (train-fit curves vs. each cohort's own outcomes)...")
    temporal = temporal_validation(train_df, validate_df, test_df, DEFAULT_THRESHOLD_DAYS)

    # ---- 3. Optimiser comparison ----
    print("Computing optimiser comparison (proportional vs. historical vs. constrained optimum)...")
    disposed = int(quality["records_retained"] - quality["censored"])
    default_throughput = int(max(0, disposed / 9.0))  # same 9-year normalization as /meta
    comparison = optimiser_comparison(streams, throughput=default_throughput)

    # ---- 4. Sensitivity ----
    print("Computing sensitivity grid across thresholds and horizons "
          f"({len(SENSITIVITY_THRESHOLD_YEARS)}x{len(SENSITIVITY_HORIZON_MONTHS)})...")
    streams_by_scenario = {}
    for threshold_years in SENSITIVITY_THRESHOLD_YEARS:
        for horizon_months in SENSITIVITY_HORIZON_MONTHS:
            threshold_days = threshold_years * 365
            horizon_days = round(horizon_months * 30.4375)
            scenario_streams = build_streams(train_df, curves, threshold_days, horizon_days)
            streams_by_scenario[(threshold_years, horizon_months)] = scenario_streams.to_dict("records")
    sensitivity = sensitivity_table(streams_by_scenario)

    # ---- 5. Constraint audit ----
    print("Auditing the reported optimum for constraint violations...")
    optimum = comparison["constrained_optimum"]
    audit = constraint_audit(
        streams, optimum["allocation"], default_throughput, 0, optimum["relaxed_constraints"]
    )

    evaluation = {
        "data_cutoff": schema.get("data_cutoff"),
        "train_filing_year": TRAIN_YEAR,
        "validate_filing_year": VALIDATE_YEAR,
        "test_filing_year": TEST_YEAR,
        "censoring_impact": censoring,
        "temporal_validation": temporal,
        "optimiser_comparison": comparison,
        "sensitivity": sensitivity,
        "constraint_audit": audit,
    }

    os.makedirs("outputs", exist_ok=True)
    with open("outputs/evaluation.json", "w") as f:
        json.dump(evaluation, f, indent=2)

    # ---- Printed summary ----
    print()
    print("=" * 72)
    print("JUDGEMYWAY - EVALUATION SUMMARY (in a retrospective simulation)")
    print("=" * 72)

    h = censoring["headline"]
    print()
    print("1. CENSORING IMPACT - the why-not-Excel number")
    print(f"   Pooled across all case types, in a retrospective simulation, the naive")
    print(f"   approach (median duration of disposed cases only) reports "
          f"{_fmt_days(h['naive_median_days'])}.")
    print(f"   The Kaplan-Meier estimate, which accounts for cases still pending, reports "
          f"{_fmt_days(h['km_median_days'])}.")
    print(f"   The naive approach underestimates true case duration by "
          f"{_fmt_days(h['absolute_underestimate_days'])} "
          f"({_fmt_pct(h['pct_underestimate'])}), in a retrospective simulation.")

    print()
    print("2. TEMPORAL VALIDATION - out-of-time generalization")
    print(f"   Curves fit on {TRAIN_YEAR} filings only, evaluated against the actual "
          f"outcomes of later filing cohorts (never a random split).")
    vmad = temporal["validate_mean_abs_diff"]
    tmad = temporal["test_mean_abs_diff"]
    print(f"   Validate cohort ({VALIDATE_YEAR}): mean absolute difference between "
          f"predicted and observed crossing rate = {vmad:.3f}" if vmad is not None
          else f"   Validate cohort ({VALIDATE_YEAR}): insufficient shared case types to compare.")
    print(f"   Test cohort ({TEST_YEAR}, out-of-time): mean absolute difference = "
          f"{tmad:.3f}" if tmad is not None
          else f"   Test cohort ({TEST_YEAR}, out-of-time): insufficient shared case types to compare.")

    print()
    print("3. OPTIMISER COMPARISON - projected crossings, in a retrospective simulation")
    print(f"   Available capacity: {comparison['available_capacity']:,} "
          f"disposals against {comparison['total_pending_inventory']:,} pending cases.")
    print(f"   (a) Proportional-to-inventory baseline: "
          f"{comparison['proportional_baseline']['crossings']:,.0f} projected crossings.")
    print(f"   (b) Historical-composition baseline:    "
          f"{comparison['historical_composition_baseline']['crossings']:,.0f} projected crossings.")
    print(f"   (c) Constrained optimum:                "
          f"{comparison['constrained_optimum']['crossings']:,.0f} projected crossings.")
    if comparison["optimum_vs_proportional_delta"] > 0:
        print(f"   The constrained optimum yields {comparison['optimum_vs_proportional_delta']:,.0f} "
              f"more projected crossings than the unconstrained proportional baseline - "
              f"the cost of the fairness and realism constraints, in a retrospective simulation.")
    else:
        print(f"   The constrained optimum improves on the proportional baseline by "
              f"{-comparison['optimum_vs_proportional_delta']:,.0f} projected crossings, "
              f"in a retrospective simulation.")

    print()
    print("4. SENSITIVITY - projected crossings across thresholds and horizons")
    print(f"   {'threshold':>10} {'horizon':>10} {'crossings':>14}")
    for row in sensitivity:
        print(f"   {row['threshold_years']:>7}y {row['horizon_months']:>8}mo "
              f"{row['projected_crossings']:>14,.0f}")

    print()
    print("5. CONSTRAINT AUDIT")
    if audit["clean"]:
        print("   No fairness or realism constraint was violated in the reported optimum.")
    else:
        print("   Violations found in the reported optimum:")
        for v in audit["per_stream_violations"]:
            print(f"     - {v}")
    if audit["relaxed_constraints_applied"]:
        print(f"   Relaxation was required to reach feasibility "
              f"({len(audit['relaxed_constraints_applied'])} steps); "
              f"effective settings: harm_floor={audit['effective_harm_floor']}, "
              f"realism_bound={audit['effective_realism_bound']}, "
              f"unc_cap={audit['effective_unc_cap']}.")
    else:
        print("   No relaxation was required at default settings.")

    print()
    print("=" * 72)
    print(f"Full evaluation written to outputs/evaluation.json")


if __name__ == "__main__":
    run()
