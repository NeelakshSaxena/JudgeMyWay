import pytest
from fastapi.testclient import TestClient
from backend.main import app
import json

@pytest.fixture(scope="module")
def client():
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

def test_api_override_stub(client):
    req_payload = {
        "throughput": 5000,
        "reserved": 0,
        "threshold_days": 1095,
        "horizon_days": 365,
        "locked": {"stream_1": 100}
    }
    response = client.post("/override", json=req_payload)
    assert response.status_code == 501
    
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
