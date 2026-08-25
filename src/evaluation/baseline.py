# naive vs KM · temporal split · optimiser comparison

import math
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from lifelines import KaplanMeierFitter

from src.optimization.allocate import allocate, clean_p, stream_bounds

MIN_EVENTS = 200


def _fit_by_case_type(df: pd.DataFrame, min_events: int = MIN_EVENTS) -> Dict[Any, KaplanMeierFitter]:
    curves = {}
    for case_type, group in df.groupby("case_type"):
        if group["event_observed"].sum() >= min_events:
            kmf = KaplanMeierFitter()
            kmf.fit(group["duration_days"], event_observed=group["event_observed"])
            curves[case_type] = kmf
    return curves


def _survival_at(kmf: KaplanMeierFitter, t: float) -> float:
    sf = kmf.survival_function_
    idx = np.searchsorted(sf.index.values, t, side="right") - 1
    idx = max(0, idx)
    return float(sf.iloc[idx, 0])


def censoring_impact(df: pd.DataFrame, top_n: int = 10, min_events: int = MIN_EVENTS) -> Dict[str, Any]:
    """Median duration counting only disposed cases (the naive/Excel approach) vs. the
    Kaplan-Meier median which accounts for censoring, per major case type. This is the
    'why not Excel' number: the naive approach is biased downward because it silently
    drops every case that hasn't been decided yet."""
    counts = df.groupby("case_type")["event_observed"].sum().sort_values(ascending=False)
    major_types = [ct for ct in counts.index if counts[ct] >= min_events][:top_n]

    per_case_type = []
    for ct in major_types:
        group = df[df["case_type"] == ct]
        disposed = group[group["event_observed"] == 1]
        naive_median = float(disposed["duration_days"].median())

        kmf = KaplanMeierFitter()
        kmf.fit(group["duration_days"], event_observed=group["event_observed"])
        km_median = kmf.median_survival_time_
        km_median = float(km_median) if math.isfinite(km_median) else None

        entry = {
            "case_type": str(ct),
            "n_events": int(disposed.shape[0]),
            "naive_median_days": naive_median,
        }
        if km_median is not None:
            entry["km_median_days"] = km_median
            entry["absolute_underestimate_days"] = km_median - naive_median
            entry["pct_underestimate"] = (km_median - naive_median) / km_median * 100.0
        else:
            entry["km_median_days"] = None
            entry["absolute_underestimate_days"] = None
            entry["pct_underestimate"] = None
        per_case_type.append(entry)

    # Headline: the same comparison pooled across all disposed/censored cases.
    disposed_all = df[df["event_observed"] == 1]
    naive_median_all = float(disposed_all["duration_days"].median())
    kmf_all = KaplanMeierFitter()
    kmf_all.fit(df["duration_days"], event_observed=df["event_observed"])
    km_median_all = kmf_all.median_survival_time_
    km_median_all = float(km_median_all) if math.isfinite(km_median_all) else None

    headline = {
        "naive_median_days": naive_median_all,
        "km_median_days": km_median_all,
        "absolute_underestimate_days": (km_median_all - naive_median_all) if km_median_all is not None else None,
        "pct_underestimate": ((km_median_all - naive_median_all) / km_median_all * 100.0)
        if km_median_all is not None else None,
    }

    return {"headline": headline, "by_case_type": per_case_type}


def temporal_validation(train_df: pd.DataFrame, validate_df: pd.DataFrame, test_df: pd.DataFrame,
                         threshold_days: int, min_events: int = MIN_EVENTS) -> Dict[str, Any]:
    """Fit on the train filing cohort only, then compare the train-fit curve's predicted
    eventual crossing probability against each later cohort's OWN Kaplan-Meier crossing
    probability (fit purely on that cohort's outcomes, so it stays correct under whatever
    censoring exists in a recent filing year). Split by filing cohort, never randomly and
    never by disposal date, so a cohort's own future outcomes never leak into its fit."""
    train_curves = _fit_by_case_type(train_df, min_events)

    def _compare(cohort_df: pd.DataFrame, label: str) -> List[Dict[str, Any]]:
        cohort_curves = _fit_by_case_type(cohort_df, min_events)
        rows = []
        for ct in sorted(set(train_curves) & set(cohort_curves), key=str):
            predicted = 1.0 - _survival_at(train_curves[ct], threshold_days)
            observed = 1.0 - _survival_at(cohort_curves[ct], threshold_days)
            rows.append({
                "case_type": str(ct),
                "cohort": label,
                "n_cases": int((cohort_df["case_type"] == ct).sum()),
                "predicted_crossing_rate": predicted,
                "observed_crossing_rate": observed,
                "difference": observed - predicted,
            })
        return rows

    validate_rows = _compare(validate_df, "validate")
    test_rows = _compare(test_df, "test")

    def _mean_abs_diff(rows: List[Dict[str, Any]]) -> Optional[float]:
        if not rows:
            return None
        return float(np.mean([abs(r["difference"]) for r in rows]))

    return {
        "threshold_days": threshold_days,
        "train_case_types_fitted": len(train_curves),
        "validate": validate_rows,
        "test": test_rows,
        "validate_mean_abs_diff": _mean_abs_diff(validate_rows),
        "test_mean_abs_diff": _mean_abs_diff(test_rows),
    }


def optimiser_comparison(streams: List[Dict[str, Any]], throughput: int, reserved: int = 0) -> Dict[str, Any]:
    """Projected crossings under (a) proportional-to-inventory baseline, (b)
    historical-composition baseline, (c) our constrained optimum. Reported together,
    including where the constrained optimum loses ground on a secondary metric, since
    fairness/realism constraints trade some efficiency for those protections."""
    avail = max(0, throughput - reserved)
    total_n = sum(int(s["n"]) for s in streams)

    result = allocate(streams, throughput, reserved)

    proportional_crossings = result["before"]["crossings"]
    proportional_alloc = result["baseline"]

    historical_alloc = {}
    for s in streams:
        n = int(s["n"])
        h_s = float(s.get("historical_share") or 0.0) * avail
        historical_alloc[s["id"]] = int(round(max(0.0, min(float(n), h_s))))
    historical_crossings = sum(
        clean_p(s.get("p")) * (int(s["n"]) - historical_alloc[s["id"]]) for s in streams
    )

    optimum_crossings = result["after"]["crossings"]
    optimum_alloc = result["allocation"]

    def _disposal_total(alloc: Dict[str, int]) -> int:
        return sum(alloc.values())

    return {
        "throughput": throughput,
        "reserved": reserved,
        "available_capacity": avail,
        "total_pending_inventory": total_n,
        "proportional_baseline": {
            "crossings": proportional_crossings,
            "total_disposals": _disposal_total(proportional_alloc),
        },
        "historical_composition_baseline": {
            "crossings": historical_crossings,
            "total_disposals": _disposal_total(historical_alloc),
        },
        "constrained_optimum": {
            "crossings": optimum_crossings,
            "total_disposals": _disposal_total(optimum_alloc),
            "relaxed_constraints": result["relaxed_constraints"],
            "allocation": optimum_alloc,
        },
        "optimum_vs_proportional_delta": optimum_crossings - proportional_crossings,
        "optimum_vs_historical_delta": optimum_crossings - historical_crossings,
    }


def sensitivity_table(streams_by_scenario: Dict[tuple, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Projected crossings across a grid of thresholds and horizons. A table, not a claim:
    every cell is the sum of p_s * n_s for streams already built at that threshold/horizon."""
    rows = []
    for (threshold_years, horizon_months), streams in sorted(streams_by_scenario.items()):
        total_n = sum(int(s["n"]) for s in streams)
        projected = sum(clean_p(s.get("p")) * int(s["n"]) for s in streams)
        rows.append({
            "threshold_years": threshold_years,
            "horizon_months": horizon_months,
            "total_pending_inventory": total_n,
            "projected_crossings": projected,
        })
    return rows


def constraint_audit(streams: List[Dict[str, Any]], allocation: Dict[str, int], throughput: int,
                      reserved: int, relaxed_constraints: List[str],
                      harm_floor: float = 0.8, realism_bound: float = 0.30,
                      unc_cap: float = 0.15) -> Dict[str, Any]:
    """Confirm no fairness or realism constraint was violated in the reported optimum,
    at whatever floor/bound the relaxation ladder actually settled on."""
    avail = max(0, throughput - reserved)
    total_n = sum(int(s["n"]) for s in streams)

    effective_floor = harm_floor
    effective_bound = realism_bound
    effective_cap = unc_cap
    for note in relaxed_constraints:
        if note.startswith("fairness floor relaxed"):
            effective_floor = float(note.rsplit("->", 1)[1])
        elif note.startswith("realism bound relaxed"):
            effective_bound = float(note.rsplit("->", 1)[1])
        elif note.startswith("uncertainty cap relaxed"):
            effective_cap = float(note.rsplit("->", 1)[1])

    violations = []
    for s in streams:
        sid = s["id"]
        x = allocation.get(sid, 0)
        stream_with_total = dict(s, _total_n=total_n)
        lo, hi, _b_s, _h_s = stream_bounds(stream_with_total, avail, effective_floor, effective_bound, effective_cap)
        if x < lo or x > hi:
            violations.append(f"{sid}: allocated {x} outside effective range [{lo}, {hi}]")

    capacity_ok = sum(allocation.values()) <= avail

    return {
        "relaxed_constraints_applied": relaxed_constraints,
        "effective_harm_floor": effective_floor,
        "effective_realism_bound": effective_bound,
        "effective_unc_cap": effective_cap,
        "capacity_constraint_respected": capacity_ok,
        "per_stream_violations": violations,
        "clean": capacity_ok and not violations,
    }
