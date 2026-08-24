import pandas as pd
s = pd.read_parquet("outputs/stream_metrics.parquet")
assert (s.p.between(0,1) | s.p.isna()).all()
assert (s[s.age_band=="0-1y"].p == 0).all(), "young streams must be zero-risk in a 12m horizon"
print(s[["id","n","p","low_confidence","historical_share"]].to_string(index=False))
print("projected crossings:", round((s.p*s.n).sum()))
