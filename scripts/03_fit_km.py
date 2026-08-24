import pandas as pd
import pickle
import os
from src.survival.km import fit_strata

def run():
    print("Loading survival dataset...")
    df = pd.read_parquet("data/processed/survival_dataset.parquet")
    print("Fitting Kaplan-Meier strata (case_type x court)...")
    curves = fit_strata(df, min_events=200)
    
    print(f"Fitted {len(curves)} primary curves.")
    os.makedirs("models", exist_ok=True)
    with open("models/km_curves.pkl", "wb") as f:
        pickle.dump(curves, f)
        
    print("\nSample of fitted strata:")
    for i, (key, kmf) in enumerate(list(curves.items())[:10]):
        n_ev = sum(kmf.event_observed)
        median = kmf.median_survival_time_
        level = "case_type x court"
        print(f"Stratum {key}: n_events={n_ev}, median={median}, level={level}")

if __name__ == "__main__":
    run()
