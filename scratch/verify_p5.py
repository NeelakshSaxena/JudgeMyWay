import pandas as pd
from src.optimization.allocate import allocate
s = pd.read_parquet("outputs/stream_metrics.parquet").to_dict("records")
r = allocate(s, throughput=int(sum(x["n"] for x in s)*0.25))
print("feasible:", r["feasible"], "| relaxations:", r["relaxed_constraints"])
print("before:", round(r["before"]["crossings"]), "-> after:", round(r["after"]["crossings"]))
