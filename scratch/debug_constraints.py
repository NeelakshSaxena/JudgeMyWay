import pandas as pd
from src.optimization.allocate import allocate
import math

s = pd.read_parquet('outputs/stream_metrics.parquet').to_dict('records')
throughput = int(sum(x['n'] for x in s)*0.25)
reserved = 0
harm_floor = 0.0
realism_bound = 1.0
unc_cap = 0.15
avail = throughput - reserved
total_n = sum(x['n'] for x in s)

for stream in s:
    n_s = stream['n']
    b_s = (avail * n_s / total_n) if total_n > 0 else 0
    h_s = stream.get('historical_share', 0.0) * avail
    low_conf = stream.get('low_confidence', False)
    
    c2_floor = math.floor(harm_floor * b_s)
    c3_lo = h_s * (1.0 - realism_bound)
    c3_hi = h_s * (1.0 + realism_bound)
    c4_lo = 0.0
    c4_hi = float(n_s)
    if low_conf:
        c4_lo = b_s * (1.0 - unc_cap)
        c4_hi = b_s * (1.0 + unc_cap)
    
    lo_bound = max(0, c2_floor, math.ceil(c3_lo), math.ceil(c4_lo))
    hi_bound = min(n_s, math.floor(c3_hi), math.floor(c4_hi))
    
    if lo_bound > hi_bound:
        print(f"Conflict on {stream['id']}: lo={lo_bound}, hi={hi_bound}")
        print(f"  n={n_s}, b_s={b_s}, h_s={h_s}, low_conf={low_conf}")
        print(f"  c2_floor={c2_floor}, c3_lo={c3_lo}, c3_hi={c3_hi}, c4_lo={c4_lo}, c4_hi={c4_hi}")
        break
