# B2 - capacity, floors, realism bound, override

import json
import math
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from src.optimization.allocate import allocate
from src.optimization.override import override

@pytest.fixture(scope="module")
def client():
    # TestClient's context manager triggers the app's lifespan (startup/shutdown)
    with TestClient(app) as c:
        yield c

def test_api_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}

def test_api_meta(client):
    response = client.get("/meta")
    assert response.status_code == 200
    data = response.json()
    assert "court" in data
    assert "n_cases" in data
    assert data["n_cases"] > 0
    assert "default_throughput" in data
    assert "case_id" not in json.dumps(data)

def test_api_quality(client):
    response = client.get("/quality")
    assert response.status_code == 200
    data = response.json()
    assert "records_loaded" in data
    assert "exclusions" in data
    assert "case_id" not in json.dumps(data)

def test_api_streams_default(client):
    response = client.get("/streams?threshold_days=1095&horizon_days=365")
    assert response.status_code == 200
    data = response.json()
    assert "streams" in data
    assert len(data["streams"]) > 0
    assert "case_id" not in json.dumps(data)

    # Check the format of the first stream
    stream = data["streams"][0]
    assert "id" in stream
    assert "p" in stream
    assert "n" in stream

def test_api_streams_custom(client):
    # This should trigger the dynamic recompute logic
    response = client.get("/streams?threshold_days=2000&horizon_days=700")
    assert response.status_code == 200
    data = response.json()
    assert "streams" in data
    assert len(data["streams"]) > 0

def test_api_optimize(client):
    req_payload = {
        "throughput": 5000,
        "reserved": 0,
        "threshold_days": 1095,
        "horizon_days": 365
    }
    response = client.post("/optimize", json=req_payload)
    assert response.status_code == 200
    data = response.json()

    assert data["feasible"] is True
    assert "allocation" in data
    assert "before" in data
    assert "after" in data
    assert "relaxed_constraints" in data
    assert "case_id" not in json.dumps(data)

def test_api_override(client):
    streams_response = client.get("/streams?threshold_days=1095&horizon_days=365")
    stream_id = streams_response.json()["streams"][0]["id"]

    req_payload = {
        "throughput": 5000,
        "reserved": 0,
        "threshold_days": 1095,
        "horizon_days": 365,
        "locked": {stream_id: 0}
    }
    response = client.post("/override", json=req_payload)
    assert response.status_code == 200
    data = response.json()

    assert "feasible" in data
    assert "before" in data
    assert "after" in data
    assert "delta" in data
    assert "affected_streams" in data
    assert "violations" in data
    assert "case_id" not in json.dumps(data)

def test_validation_throughput(client):
    # Invalid throughput (< 0)
    req_payload = {
        "throughput": -10,
        "reserved": 0,
        "threshold_days": 1095,
        "horizon_days": 365
    }
    response = client.post("/optimize", json=req_payload)
    assert response.status_code == 422

def test_validation_reserved(client):
    # Reserved > throughput
    req_payload = {
        "throughput": 5000,
        "reserved": 6000,
        "threshold_days": 1095,
        "horizon_days": 365
    }
    response = client.post("/optimize", json=req_payload)
    assert response.status_code == 422

# Balanced fixture: default constraints (harm_floor=0.8, realism_bound=0.30) are
# satisfiable outright, so no relaxation is expected.
BALANCED_STREAMS = [
    {"id": "a", "n": 100, "p": 0.9, "historical_share": 0.5, "low_confidence": False},
    {"id": "b", "n": 100, "p": 0.1, "historical_share": 0.5, "low_confidence": False},
]

# Skewed fixture: one large, high-risk, historically-rare stream vs. one small,
# low-risk, historically-common stream. Default constraints conflict and require
# relaxation before a feasible allocation exists.
SKEWED_STREAMS = [
    {"id": "a", "n": 1000, "p": 0.9, "historical_share": 0.05, "low_confidence": False},
    {"id": "b", "n": 10, "p": 0.1, "historical_share": 0.95, "low_confidence": False},
]

def test_allocate_t10_within_capacity():
    # T10 sum(allocation) <= throughput - reserved
    r = allocate(BALANCED_STREAMS, throughput=100, reserved=10)
    assert r["feasible"] is True
    assert sum(r["allocation"].values()) <= 100 - 10

def test_allocate_t11_fairness_floor():
    # T11 every x_s >= floor(0.8 * b_s) when no relaxation was recorded
    r = allocate(BALANCED_STREAMS, throughput=100)
    assert r["relaxed_constraints"] == []
    avail = 100
    total_n = sum(s["n"] for s in BALANCED_STREAMS)
    for s in BALANCED_STREAMS:
        b_s = avail * s["n"] / total_n
        assert r["allocation"][s["id"]] >= math.floor(0.8 * b_s)

def test_allocate_t12_realism_bound():
    # T12 every |x_s - h_s| <= 0.30 * h_s when no relaxation was recorded
    r = allocate(BALANCED_STREAMS, throughput=100)
    assert r["relaxed_constraints"] == []
    avail = 100
    for s in BALANCED_STREAMS:
        h_s = s["historical_share"] * avail
        assert abs(r["allocation"][s["id"]] - h_s) <= 0.30 * h_s

def test_allocate_t13_zero_throughput():
    # T13 throughput = 0 returns feasible with all x_s = 0
    r = allocate(BALANCED_STREAMS, throughput=0)
    assert r["feasible"] is True
    assert all(v == 0 for v in r["allocation"].values())

def test_allocate_t14_over_constrained_relaxes():
    # T14 an over-constrained input returns feasible=True with a non-empty relaxed_constraints
    r = allocate(SKEWED_STREAMS, throughput=500)
    assert r["feasible"] is True
    assert len(r["relaxed_constraints"]) > 0

def test_allocate_t15_optimum_beats_baseline():
    # T15 after.crossings <= before.crossings when no relaxation was applied
    r = allocate(BALANCED_STREAMS, throughput=100)
    assert r["relaxed_constraints"] == []
    assert r["after"]["crossings"] <= r["before"]["crossings"]

def test_override_t16_locking_recommendation_yields_zero_delta():
    # T16 locking every stream to its recommendation yields delta == 0
    rec = allocate(BALANCED_STREAMS, throughput=100)
    r = override(BALANCED_STREAMS, 100, 0, locked=rec["allocation"], recommendation=rec)
    assert r["feasible"] is True
    assert r["delta"] == 0
    assert r["affected_streams"] == []

def test_override_t17_lock_below_floor_records_violation():
    # T17 locking a stream below its fairness floor records a violation rather than crashing
    rec = allocate(BALANCED_STREAMS, throughput=100)
    r = override(BALANCED_STREAMS, 100, 0, locked={"a": 0}, recommendation=rec)
    assert r["feasible"] is True
    assert len(r["violations"]) > 0

def test_override_t18_impossible_lock_returns_infeasible_reason():
    # T18 an impossible lock returns feasible=False with a reason string
    rec = allocate(BALANCED_STREAMS, throughput=100)
    r = override(BALANCED_STREAMS, 100, 0, locked={"a": 500}, recommendation=rec)
    assert r["feasible"] is False
    assert isinstance(r["reason"], str) and len(r["reason"]) > 0
