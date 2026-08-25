# counterfactual re-solve

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.optimization.allocate import allocate, stream_bounds, clean_p

OVERRIDE_LOG_PATH = "outputs/override_log.jsonl"
AFFECTED_THRESHOLD = 1


def _log_overrides(streams: List[Dict[str, Any]], recommended: Dict[str, int],
                    chosen: Dict[str, int], locked: Dict[str, int]) -> None:
    # Log only. NEVER learn from overrides, never adjust weights, never persist a preference model.
    os.makedirs(os.path.dirname(OVERRIDE_LOG_PATH), exist_ok=True)
    by_id = {s["id"]: s for s in streams}
    timestamp = datetime.now(timezone.utc).isoformat()
    with open(OVERRIDE_LOG_PATH, "a") as f:
        for sid in locked:
            s = by_id.get(sid)
            p = clean_p(s.get("p")) if s else 0.0
            rec = recommended.get(sid, 0)
            chos = chosen.get(sid, rec)
            entry = {
                "timestamp": timestamp,
                "stream_id": sid,
                "recommended": rec,
                "chosen": chos,
                "delta_crossings": p * (rec - chos),
            }
            f.write(json.dumps(entry) + "\n")


def override(streams: List[Dict[str, Any]], throughput: int, reserved: int,
             locked: Dict[str, int], harm_floor: float = 0.8, realism_bound: float = 0.30,
             unc_cap: float = 0.15, recommendation: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    recommendation = recommendation or allocate(streams, throughput, reserved,
                                                  harm_floor, realism_bound, unc_cap)
    by_id = {s["id"]: s for s in streams}
    avail = max(0, throughput - reserved)
    total_n = sum(int(s["n"]) for s in streams)

    violations: List[str] = []
    for sid, val in locked.items():
        s = by_id.get(sid)
        if s is None:
            violations.append(f"{sid}: unknown stream")
            continue
        n = int(s["n"])
        if val < 0 or val > n:
            violations.append(f"{sid}: locked target {val} outside valid range [0, {n}]")
            continue
        stream_with_total = dict(s, _total_n=total_n)
        lo, hi, _b_s, _h_s = stream_bounds(stream_with_total, avail, harm_floor, realism_bound, unc_cap)
        if lo > hi:
            violations.append(
                f"{sid}: no target satisfies this stream's fairness floor and realism bound "
                f"simultaneously at default settings; the lock overrides both"
            )
        elif val < lo or val > hi:
            violations.append(
                f"{sid}: locked target {val} breaks its fairness/realism range [{lo}, {hi}]"
            )

    result = allocate(streams, throughput, reserved, harm_floor, realism_bound, unc_cap,
                       locked=locked)

    if not result["feasible"]:
        return {
            "feasible": False,
            "reason": ("Locked targets cannot be met within available capacity, even after "
                       "relaxing the fairness floor and realism bound to their limits."),
            "before": recommendation["before"],
            "after": recommendation["before"],
            "delta": 0,
            "affected_streams": [],
            "violations": violations,
            "relaxed_constraints": result["relaxed_constraints"],
        }

    affected_streams = []
    for s in streams:
        sid = s["id"]
        rec_val = recommendation["allocation"].get(sid, 0)
        new_val = result["allocation"].get(sid, 0)
        if abs(new_val - rec_val) > AFFECTED_THRESHOLD:
            affected_streams.append(sid)

    after_crossings = sum(
        clean_p(s.get("p")) * (int(s["n"]) - result["allocation"][s["id"]]) for s in streams
    )
    delta = after_crossings - recommendation["after"]["crossings"]

    _log_overrides(streams, recommendation["allocation"], result["allocation"], locked)

    return {
        "feasible": True,
        "before": recommendation["before"],
        "after": {"crossings": after_crossings},
        "delta": delta,
        "affected_streams": affected_streams,
        "violations": violations,
        "relaxed_constraints": result["relaxed_constraints"],
    }
