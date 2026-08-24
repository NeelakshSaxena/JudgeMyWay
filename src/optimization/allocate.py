# CP-SAT model + relaxation ladder

import math
from typing import Any, Dict, List, Optional

from ortools.sat.python import cp_model

SOLVER_TIME_LIMIT_SECONDS = 5.0
HARM_FLOOR_STEP = 0.05
REALISM_BOUND_STEP = 0.05
REALISM_BOUND_MAX = 1.0


def clean_p(p: Optional[float]) -> float:
    if p is None:
        return 0.0
    try:
        if math.isnan(p):
            return 0.0
    except TypeError:
        return 0.0
    return float(p)


def stream_bounds(stream: Dict[str, Any], avail: float, harm_floor: float,
                   realism_bound: float, unc_cap: float) -> tuple:
    """Intersected [lo, hi] integer domain for one stream's target, before any lock."""
    n = int(stream["n"])
    total_n = stream.get("_total_n", n)
    b_s = avail * n / total_n if total_n > 0 else 0.0
    h_s = float(stream.get("historical_share") or 0.0) * avail

    lo = math.floor(harm_floor * b_s)
    hi = n

    r_lo = math.ceil(h_s - realism_bound * h_s)
    r_hi = math.floor(h_s + realism_bound * h_s)
    lo = max(lo, r_lo)
    hi = min(hi, r_hi)

    if stream.get("low_confidence"):
        u_lo = math.ceil(b_s - unc_cap * b_s)
        u_hi = math.floor(b_s + unc_cap * b_s)
        lo = max(lo, u_lo)
        hi = min(hi, u_hi)

    lo = max(0, min(n, int(lo)))
    hi = max(0, min(n, int(hi)))

    return lo, hi, b_s, h_s


def _solve(streams: List[Dict[str, Any]], avail: float, harm_floor: float,
           realism_bound: float, unc_cap: float,
           locked: Optional[Dict[str, int]] = None) -> tuple:
    locked = locked or {}
    total_n = sum(int(s["n"]) for s in streams)
    model = cp_model.CpModel()
    x_vars = {}
    baseline = {}

    for s in streams:
        sid = s["id"]
        n = int(s["n"])
        stream_with_total = dict(s, _total_n=total_n)
        lo, hi, b_s, _h_s = stream_bounds(stream_with_total, avail, harm_floor, realism_bound, unc_cap)
        baseline[sid] = b_s

        var = model.NewIntVar(0, n, f"x_{sid}")
        if sid in locked:
            model.Add(var == int(locked[sid]))
        else:
            # Added as constraints (not domain bounds) so a genuine conflict between
            # the fairness floor and the realism bound surfaces as solver infeasibility
            # and drives the relaxation ladder, instead of being silently collapsed.
            model.Add(var >= lo)
            model.Add(var <= hi)
        x_vars[sid] = var

    model.Add(sum(x_vars.values()) <= int(avail))

    objective_terms = []
    for s in streams:
        sid = s["id"]
        n = int(s["n"])
        weight = round(1000 * clean_p(s.get("p")))
        if weight:
            objective_terms.append(weight * (n - x_vars[sid]))
    if objective_terms:
        model.Minimize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = SOLVER_TIME_LIMIT_SECONDS
    status = solver.Solve(model)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        allocation = {sid: int(solver.Value(v)) for sid, v in x_vars.items()}
        return True, allocation, baseline
    return False, None, baseline


def _solve_with_relaxation(streams: List[Dict[str, Any]], avail: float, harm_floor: float,
                            realism_bound: float, unc_cap: float,
                            locked: Optional[Dict[str, int]] = None) -> tuple:
    """Try the given constraints, then relax harm_floor toward 0, then realism_bound
    toward 1.0, recording every relaxation applied. Returns
    (feasible, allocation, baseline, relaxed_constraints)."""
    relaxed_constraints: List[str] = []

    feasible, allocation, baseline = _solve(streams, avail, harm_floor, realism_bound, unc_cap, locked)
    if feasible:
        return True, allocation, baseline, relaxed_constraints

    floor = harm_floor
    while not feasible and floor > 0.0:
        new_floor = round(max(0.0, floor - HARM_FLOOR_STEP), 2)
        feasible, allocation, baseline = _solve(streams, avail, new_floor, realism_bound, unc_cap, locked)
        relaxed_constraints.append(f"fairness floor relaxed {floor:.2f} -> {new_floor:.2f}")
        floor = new_floor

    bound = realism_bound
    while not feasible and bound < REALISM_BOUND_MAX:
        new_bound = round(min(REALISM_BOUND_MAX, bound + REALISM_BOUND_STEP), 2)
        feasible, allocation, baseline = _solve(streams, avail, floor, new_bound, unc_cap, locked)
        relaxed_constraints.append(f"realism bound relaxed {bound:.2f} -> {new_bound:.2f}")
        bound = new_bound

    # Not in the plan's two-stage ladder, but required by its own "never return an
    # infeasible plan without saying so" rule: a low-confidence stream with a near-zero
    # historical_share pins C3's upper bound near 0 no matter how far realism_bound is
    # relaxed, while C4 (unrelaxed) still pins its lower bound above that — a genuine
    # conflict the two documented stages cannot resolve. Relaxing unc_cap the same way
    # closes it without touching any stream's confidence classification.
    cap = unc_cap
    while not feasible and cap < REALISM_BOUND_MAX:
        new_cap = round(min(REALISM_BOUND_MAX, cap + REALISM_BOUND_STEP), 2)
        feasible, allocation, baseline = _solve(streams, avail, floor, bound, new_cap, locked)
        relaxed_constraints.append(f"uncertainty cap relaxed {cap:.2f} -> {new_cap:.2f}")
        cap = new_cap

    return feasible, allocation, baseline, relaxed_constraints


def allocate(streams: List[Dict[str, Any]], throughput: int, reserved: int = 0,
             harm_floor: float = 0.8, realism_bound: float = 0.30, unc_cap: float = 0.15,
             locked: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    avail = max(0, throughput - reserved)

    feasible, allocation, baseline, relaxed_constraints = _solve_with_relaxation(
        streams, avail, harm_floor, realism_bound, unc_cap, locked
    )

    if not feasible:
        return {
            "feasible": False,
            "allocation": {},
            "before": {"crossings": 0},
            "after": {"crossings": 0},
            "relaxed_constraints": relaxed_constraints,
            "baseline": {sid: int(round(b)) for sid, b in baseline.items()},
        }

    before_crossings = sum(clean_p(s.get("p")) * (int(s["n"]) - baseline[s["id"]]) for s in streams)
    after_crossings = sum(clean_p(s.get("p")) * (int(s["n"]) - allocation[s["id"]]) for s in streams)

    return {
        "feasible": True,
        "allocation": allocation,
        "before": {"crossings": before_crossings},
        "after": {"crossings": after_crossings},
        "relaxed_constraints": relaxed_constraints,
        "baseline": {sid: int(round(b)) for sid, b in baseline.items()},
    }
