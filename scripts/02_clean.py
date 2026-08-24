import pandas as pd
import json
import yaml
import os
from src.data.load import load_raw
from src.data.clean import clean

def run():
    print("Loading raw data...")
    # Cut scope to 1 year to prevent OOM
    df_raw = load_raw(state=None, year_min=2010, year_max=2010)
    records_loaded = len(df_raw)
    print(f"Loaded {records_loaded} records.")
    
    print("Cleaning data...")
    df_clean, counters = clean(df_raw)
    records_retained = len(df_clean)
    print(f"Retained {records_retained} records.")
    
    counters["records_loaded"] = records_loaded
    counters["records_retained"] = records_retained
    
    with open("config/schema.yaml", "r") as f:
        schema = yaml.safe_load(f)
        
    if not schema.get("transfer_flag"):
        counters["transfer_detection"] = "unavailable — not flagged in public extract"
        
    print("Writing quality report...")
    os.makedirs("outputs", exist_ok=True)
    with open("outputs/quality_report.json", "w") as f:
        json.dump(counters, f, indent=2)
        
    print("Writing parquet...")
    os.makedirs("data/processed", exist_ok=True)
    df_clean.to_parquet("data/processed/survival_dataset.parquet", index=False)
    print("Done!")

if __name__ == "__main__":
    run()
