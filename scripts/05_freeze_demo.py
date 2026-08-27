import os
import json
import sys

# Ensure we're running from the root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# We must run without DEMO_MODE to generate the real outputs
os.environ["DEMO_MODE"] = "0"

from fastapi.testclient import TestClient
from backend.main import app

def freeze_demo():
    print("Freezing demo scenario into data/demo/scenario.json...")
    os.makedirs("data/demo", exist_ok=True)
    
    scenario = {}
    
    with TestClient(app) as client:
        # 1. /meta
        resp = client.get("/meta")
        resp.raise_for_status()
        meta_data = resp.json()
        meta_data["mode"] = "SIMULATED"
        scenario["meta"] = meta_data
        
        # 2. /streams
        resp = client.get("/streams?threshold_days=1095&horizon_days=365")
        resp.raise_for_status()
        streams_data = resp.json()
        scenario["streams"] = streams_data
        
        # 3. /optimize
        # Use default throughput from meta
        throughput = meta_data.get("default_throughput", 5000)
        opt_req = {
            "throughput": throughput,
            "reserved": 0,
            "threshold_days": 1095,
            "horizon_days": 365
        }
        resp = client.post("/optimize", json=opt_req)
        resp.raise_for_status()
        optimize_data = resp.json()
        scenario["optimize"] = optimize_data
        
        # 4. /override
        # Pick the stream with the highest baseline to lock to 0
        baseline = optimize_data.get("baseline", {})
        if baseline:
            highest_stream = max(baseline, key=baseline.get)
            locked = {highest_stream: max(0, baseline[highest_stream] - 100)}
        else:
            locked = {"stream_1": 0}
            
        over_req = {
            "throughput": throughput,
            "reserved": 0,
            "threshold_days": 1095,
            "horizon_days": 365,
            "locked": locked
        }
        resp = client.post("/override", json=over_req)
        resp.raise_for_status()
        override_data = resp.json()
        scenario["override"] = override_data
        
        # 5. /quality
        resp = client.get("/quality")
        resp.raise_for_status()
        quality_data = resp.json()
        scenario["quality"] = quality_data

    with open("data/demo/scenario.json", "w") as f:
        json.dump(scenario, f, indent=2)
        
    print("Demo scenario frozen successfully!")

if __name__ == "__main__":
    freeze_demo()
