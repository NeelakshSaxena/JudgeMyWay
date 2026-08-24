import pandas as pd
import pickle

def run_streams():
    print("Loading data and curves...")
    df = pd.read_parquet("data/processed/survival_dataset.parquet")
    
    with open("models/km_curves.pkl", "rb") as f:
        curves = pickle.load(f)

    from src.streams.build import build_streams
    print("Building streams...")
    
    streams_df = build_streams(df, curves, threshold_days=730, horizon_days=365)
    
    streams_df.to_parquet("outputs/stream_metrics.parquet")
    print(f"Streams written to outputs/stream_metrics.parquet")
    
    print("Stream Table:")
    print(streams_df[["id","n","p","low_confidence","historical_share"]].to_string(index=False))
    
    proj_crossings = round((streams_df['p'] * streams_df['n']).sum())
    print("projected crossings:", proj_crossings)
    
if __name__ == "__main__":
    run_streams()
