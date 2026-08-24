# NYAYAFLOW — AGENTIC BUILD PLAN

**For Claude Code · Codex · Antigravity · Cursor · any agentic coding assistant**
20 hours · 3 builders · target: working prototype on real data

---

## HOW TO USE THIS

1. Create the repo, then save **§0 Project Context** verbatim as your agent's context file:
   - Claude Code → `CLAUDE.md` at repo root
   - Codex → `AGENTS.md` at repo root
   - Antigravity / Cursor → `.cursorrules` or the equivalent rules file
2. Run phases in order. Each phase has one prompt — paste it as-is.
3. **Never skip the Verification block.** An agent reporting success is not verification.
4. **Stop conditions are binding.** If one triggers, take the fallback and move on. Do not
   negotiate with a stop condition at hour 14.

**Critical-path note:** P7 (frontend) runs in parallel from H1 against mocked JSON. P3–P6 are
sequential on the data side. Nobody blocks after the contract freeze in P1.

---

# §0 PROJECT CONTEXT
*(save as CLAUDE.md / AGENTS.md — every prompt below assumes the agent has read this)*

```markdown
# JudgeMyWay — Project Context

## What this is
A capacity-planning tool for Indian district court administrators. Given a court's pending
case inventory and historical disposal-time distributions, it projects how many cases will
cross an ageing threshold, and recommends a disposal composition across case categories that
minimises that number under fairness constraints. A registrar can override any recommendation;
the system quantifies the consequence.

## Absolute rules — violating any of these fails the build

1. NEVER rank, score, or expose any individual case. All output is at CASE STREAM level
   (case_type × age_band). The API must not return per-case values, even in debug output.
2. NEVER use these columns as model features: disposition, outcome, decision_date, judge_id,
   judge_position, petitioner_name, respondent_name, petitioner_gender, respondent_gender,
   gender, hearing_date. Party gender EXISTS in this dataset — drop it explicitly.
3. NEVER drop cases with a missing decision date. They are RIGHT-CENSORED and must be kept.
   Dropping them biases every duration estimate downward.
4. NEVER infer urgency (bail, custody, interim relief, vulnerability). That data is absent.
5. NEVER claim capacity causes faster disposal. The decision variable is DISPOSAL TARGETS.
6. NEVER invent data, numbers, or performance figures. If a value isn't computed, don't print it.
7. NEVER add: authentication, user management, LLM calls, computer vision, blockchain,
   Docker, Kubernetes, microservices, ORMs, Redis, Celery, a mobile app.
8. Simulated components must be labelled SIMULATED in the UI.

## Stack (fixed — do not add dependencies)
Python 3.11 · pandas · numpy · duckdb · pyarrow · lifelines · ortools · fastapi · uvicorn ·
pydantic · pyyaml · pytest. Frontend: Vite + React (JS, not TS) + Recharts.

## Core maths
- Time origin: filing date. Event: disposal. Duration in days.
- Censoring: no decision date, or decision date after cutoff → event_observed = 0,
  duration = cutoff − filing.
- Fitting stratum: case_type × court (fallback: × district → × state → global; min 200 events).
- Allocation stream: case_type × age_band, bands 0-1y / 1-3y / 3-5y / 5-10y / 10y+.
- Crossing probability for a pending case at age a, threshold T, horizon H:
      p = S(T) / S(a)   if (T − a) <= H
      p = 0             if (T − a) >  H     # cannot cross within the planning period
- Optimiser: minimise Σ p_s (n_s − x_s), where x_s = target disposals in stream s.
  Constraints: Σx_s ≤ T_cap − reserved; x_s ≥ floor(0.8·b_s); |x_s − h_s| ≤ 0.30·h_s;
  low-confidence streams additionally |x_s − b_s| ≤ 0.15·b_s.
  b_s = proportional-to-inventory baseline. h_s = historical disposal composition.

## Style
Small functions. Type hints on public functions. No classes unless state demands it.
No comments restating code. Fail loudly with assertions, never silently.
Every exclusion increments a named counter that reaches the UI.
```

---

# PHASE MAP

| # | Phase | Window | Owner | Blocks |
|---|---|---|---|---|
| P0 | Recon & schema discovery | H0–H1 | All | Everything |
| P1 | Scaffold & contract freeze | H1–H2 | P2 | P7 |
| P2 | Ingestion & cleaning | H2–H4 | P1 | P3 |
| P3 | Survival engine | H4–H6.5 | P1 | P4 |
| P4 | Streams & risk | H6.5–H8 | P1 | P5 |
| P5 | Optimiser | H8–H10.5 | P2 | P6 |
| P6 | API | H10.5–H12 | P2 | P8 |
| P7 | Frontend | H2–H12 | P3 | P8 |
| P8 | Integration | H12–H14 | All | Everything after |
| P9 | Override & counterfactual | H14–H16 | P2+P3 | — |
| P10 | Evaluation & data quality | H16–H17.5 | P1 | — |
| P11 | Freeze, QA, backup | H17.5–H20 | All | — |

**P1 = data/stats person · P2 = optimisation/backend · P3 = frontend/integration**

---

# P0 — RECON & SCHEMA DISCOVERY
**H0–H1 · All three · This is the gate. Nothing else starts.**

This phase is **mostly human**. An agent cannot open a Dropbox link or read a JS-rendered
Google Sheet. Do this yourselves.

### Tasks
1. Open `https://www.devdatalab.org/judicial-data`. Follow the Dropbox link. **Report within
   10 minutes whether it downloads without an account.**
2. Open the "all cases metadata" Google Sheet. Record the real column name for each concept below.
3. Download one state, years 2010–2016. **45-minute hard cap.**

### Fill this in — everything downstream reads it

```yaml
# config/schema.yaml
case_id:          ???
filing_date:      ???        # REQUIRED
registration_date: ???
decision_date:    ???        # REQUIRED — label only, never a feature
case_type:        ???        # REQUIRED
court_id:         ???        # REQUIRED
district:         ???
state:            ???
act_section:      ???
pending_flag:     ???        # may not exist — fallback in P2
transfer_flag:    ???        # may not exist — then disclose, don't fake
date_format:      ???        # e.g. "%Y-%m-%d"
data_cutoff:      ???        # max observed decision_date
drop_columns:     []         # every gender/name/judge/disposition column you actually see
```

### Agentic prompt (after files are on disk)
```
Read config/schema.yaml — I have filled it from the dataset's published metadata.

Inspect the raw files in data/raw/ (they are large; do not load them fully into memory —
use duckdb to read the header and a 10,000-row sample).

Produce a single report at outputs/p0_recon.md containing:
1. Actual file list with sizes and formats.
2. Full column list as it appears on disk, compared against config/schema.yaml.
   Flag any mapping in schema.yaml that does NOT match a real column.
3. Row count per file.
4. For each REQUIRED field (filing_date, decision_date, case_type, court_id):
   null rate, distinct count, min/max, and 5 example values.
5. Parsed date range and the true maximum decision_date (this becomes data_cutoff).
6. Presence check for: any pending/status flag, any transfer indicator, any gender column,
   any judge column, any disposition column.
7. Estimated share of rows with a missing decision_date (these are our censored cases).

Do not clean, transform, or write any derived dataset in this phase. Report only.
If a REQUIRED field is absent, say so at the top of the report in bold.
```

### Verification
```bash
test -f outputs/p0_recon.md && grep -c "" outputs/p0_recon.md
```
Read it yourself. Confirm the four required fields exist and `data_cutoff` is a real date.

### 🛑 STOP CONDITION — H1
**Any of `filing_date`, `decision_date`, `case_type`, `court_id` is missing, or the download
is inaccessible.**
→ **Fallback:** switch to schema-based synthetic generation. Same architecture, same phases,
`SIMULATED` badge on every screen and stated aloud in the demo. Update `config/schema.yaml`
to your generator's schema and continue from P1 unchanged.

---

# P1 — SCAFFOLD & CONTRACT FREEZE
**H1–H2 · Builder 2 · Unblocks the frontend**

### Agentic prompt
```
Scaffold the repository exactly as below. Create every file; stub bodies are fine but every
module must import cleanly and pytest must run green on an empty suite.

nyayaflow/
  config/{config.yaml, schema.yaml}
  data/{raw,processed,demo}/.gitkeep
  models/.gitkeep
  outputs/.gitkeep
  src/data/{__init__.py, schema.py, load.py, clean.py}
  src/survival/{__init__.py, km.py, fallback.py}
  src/streams/{__init__.py, build.py}
  src/optimization/{__init__.py, allocate.py, override.py}
  src/evaluation/{__init__.py, baseline.py}
  backend/main.py
  scripts/{01_ingest.py,02_clean.py,03_fit_km.py,04_build_streams.py,05_freeze_demo.py}
  tests/test_all.py
  requirements.txt  .gitignore  README.md

requirements.txt must pin exactly and contain nothing else:
pandas==2.2.2 numpy==1.26.4 duckdb==1.0.0 pyarrow==16.1.0 lifelines==0.28.0
ortools==9.10.4067 fastapi==0.111.0 uvicorn==0.30.1 pydantic==2.7.4 pyyaml==6.0.1 pytest==8.2.2

In src/data/schema.py implement the feature guard:
  ALLOWED_FEATURES, LABEL_FIELDS, FORBIDDEN (per CLAUDE.md rule 2)
  assert_clean(df) -> None   # raises AssertionError naming any forbidden or unvetted column
Write two tests for it now: one that passes on a clean frame, one that raises on a frame
containing a column named "petitioner_gender".

In backend/main.py implement all six endpoints returning HARDCODED example JSON matching the
contract below exactly. Correct shapes matter; correct values do not yet. Enable CORS for
http://localhost:5173.

  GET  /health   -> {"ok": true}
  GET  /meta     -> {court, district, period, n_cases, default_throughput,
                     threshold_days, horizon_days, mode}
  GET  /streams?threshold_days=&horizon_days=
                 -> {"streams":[{id, case_type, age_band, n, p, p_lo, p_hi,
                     low_confidence, stratum_level, historical_share, baseline,
                     projected_crossings}]}
  POST /optimize {throughput, reserved, threshold_days, horizon_days}
                 -> {feasible, allocation:{id:int}, before:{crossings},
                     after:{crossings}, relaxed_constraints:[]}
  POST /override {throughput, reserved, threshold_days, horizon_days, locked:{id:int}}
                 -> {before:{crossings}, after:{crossings}, delta,
                     affected_streams:[], violations:[]}
  GET  /quality  -> {records_loaded, records_excluded, records_censored,
                     exclusions:{reason:count}, low_confidence_streams}

Finally write outputs/mock_api.json containing one realistic example response for every
endpoint, so the frontend can develop offline. Use 8 plausible streams.

Do not implement any real logic in this phase.
```

### Verification
```bash
pip install -r requirements.txt && pytest -q && \
uvicorn backend.main:app --port 8000 & sleep 3 && \
curl -s localhost:8000/health && curl -s localhost:8000/streams | head -c 400
```

### 🛑 STOP CONDITION
Contract not frozen by H2 → freeze whatever exists and **tell Builder 3 immediately**.
The contract may be imperfect; it may not be late.

---

# P2 — INGESTION & CLEANING
**H2–H4 · Builder 1**

### Agentic prompt
```
Implement src/data/load.py and src/data/clean.py, driven by config/schema.yaml (never
hardcode column names).

load.py:
  load_raw(state, year_min, year_max) -> pandas.DataFrame
  Use duckdb to read data/raw/ and project ONLY the columns mapped in schema.yaml.
  Drop every column listed in schema.yaml drop_columns at read time, before any DataFrame
  exists. Parse dates using the configured format.

clean.py:
  clean(df) -> (DataFrame, dict counters)
  Apply these rules in order, incrementing a named counter for each:
    missing filing_date               -> DROP  (counter: missing_filing)
    decision_date < filing_date       -> DROP  (counter: impossible_dates)
    duplicate case_id                 -> keep first (counter: duplicates)
    blank/unknown case_type           -> DROP  (counter: unknown_case_type)
    duration == 0                     -> floor to 1 day (counter: same_day)
    duration > 7300 days              -> winsorise to 7300 (counter: extreme_duration)
    transfer_flag set (if the column exists) -> DROP (counter: transferred)

  Then compute censoring — CRITICAL, get this exactly right:
    event_observed = decision_date.notna() & (decision_date <= DATA_CUTOFF)
    duration_days  = where(event_observed,
                           (decision_date - filing_date).days,
                           (DATA_CUTOFF   - filing_date).days)
    counter: censored = (~event_observed).sum()
  A missing decision_date is CENSORED, never dropped.

  Add registration_lag_days if registration_date is mapped.
  Call assert_clean() on the final frame before returning.

Write scripts/02_clean.py to run load -> clean -> write
data/processed/survival_dataset.parquet with columns:
case_id, case_type, court_id, district, state, filing_date, duration_days,
event_observed, registration_lag_days (optional), act_section_group (optional)
and write outputs/quality_report.json with every counter plus records_loaded and
records_retained.

If transfer_flag is absent from schema.yaml, set counters["transferred"] = null and add
"transfer_detection": "unavailable — not flagged in public extract" to the quality report.
```

### Verification
```bash
python scripts/02_clean.py
python - <<'EOF'
import pandas as pd, json
d = pd.read_parquet("data/processed/survival_dataset.parquet")
q = json.load(open("outputs/quality_report.json"))
assert d.duration_days.min() >= 1, "durations must be >= 1 day"
assert d.event_observed.isin([0,1,True,False]).all()
assert q["censored"] > 0, "no censored cases — censoring logic is wrong"
assert not {"gender","decision_date","disposition"} & set(d.columns)
print(f"OK  rows={len(d):,}  censored={q['censored']:,} "
      f"({q['censored']/len(d):.1%})  excluded={q['records_loaded']-len(d):,}")
EOF
```
**The censored share is the number you'll quote in the demo. Write it down.**

### 🛑 STOP CONDITION — H4
No valid `survival_dataset.parquet` → cut scope to 3 districts or 3 years. If still failing,
switch to the synthetic generator. **Never fix this by dropping censored rows.**

---

# P3 — SURVIVAL ENGINE
**H4–H6.5 · Builder 1 · The technical core**

### Agentic prompt
```
Implement src/survival/km.py and src/survival/fallback.py.

km.py:
  fit_strata(df, min_events=200) -> dict[(case_type, court_id), KaplanMeierFitter]
    Fit lifelines KaplanMeierFitter per group on duration_days / event_observed.
    Skip groups with fewer than min_events observed events.

  p_cross(kmf, threshold_days, current_age_days, horizon_days) -> (p, lo, hi)
    Return (0.0, 0.0, 0.0) immediately if (threshold_days - current_age_days) > horizon_days.
    Otherwise compute S(T)/S(a) using step-function lookup on kmf.survival_function_:
      index the survival frame with searchsorted(t, side="right") - 1, clamped at 0.
    Compute lo/hi the same way from kmf.confidence_interval_ columns.
    If S(a) <= 1e-9 return (nan, nan, nan) — beyond observed support.
    Clamp all returned probabilities to [0, 1].

fallback.py:
  resolve(case_type, court_id, curves, df) -> (kmf, level:str, low_confidence:bool)
    Ladder: (case_type, court_id) -> (case_type, district) -> (case_type, state) -> global.
    Return the level actually used. low_confidence is True when level is not the first rung
    OR the fitted group had fewer than 500 observed events.

Write scripts/03_fit_km.py to fit and pickle to models/km_curves.pkl, and print a table of
stratum, n_events, median survival, and level.

Then add these tests to tests/test_all.py — write them BEFORE declaring the phase done:
  T1 p_cross(T, a=0, H=huge) equals the unconditional S(T) within 1e-9
  T2 p_cross(T, a, H=huge) >= p_cross(T, 0, H=huge) for a > 0   # conditioning never lowers it
  T3 p_cross returns exactly 0.0 when (T - a) > H
  T4 p_cross returns nan beyond observed support
  T5 all returned probabilities lie in [0, 1] or are nan
  T6 a stratum below min_events triggers the fallback and reports a non-primary level
```

### Verification
```bash
python scripts/03_fit_km.py && pytest tests/test_all.py -q -k "p_cross or fallback"
```
**T2 is the test that catches a wrong conditional probability. If T2 fails, the entire
statistical claim is wrong. Do not proceed.**

### 🛑 STOP CONDITION — H6.5
Curves unusable → stratify on `case_type` alone. **Do not abandon survival analysis** —
it is your answer to "why not Excel."

---

# P4 — STREAMS & RISK
**H6.5–H8 · Builder 1**

### Agentic prompt
```
Implement src/streams/build.py.

Simulate a "current inventory" from the historical data: take cases filed in the final
2 years of the dataset and treat their age as of DATA_CUTOFF as their current age. Label
this clearly in the output as a retrospective inventory — it is NOT a live docket.

  build_streams(df, curves, threshold_days, horizon_days) -> list[dict]
    Assign each pending case an age_band from its current age:
      0-1y, 1-3y, 3-5y, 5-10y, 10y+
    Group into streams keyed by (case_type, age_band).
    For each case, resolve its stratum via fallback.resolve and compute p_cross.
    Stream-level p = inventory-weighted mean of per-case p (and same for lo/hi).
    Stream low_confidence = True if >25% of its cases resolved below the primary rung.
    Compute historical_share h_s = that stream's share of observed disposals in history.
    Emit per stream: id, case_type, age_band, n, p, p_lo, p_hi, low_confidence,
    stratum_level, historical_share, projected_crossings = p * n.

  CRITICAL: per-case probabilities are intermediate only. They must never be returned,
  logged, written to disk, or exposed by any API. Aggregate before returning.

Write scripts/04_build_streams.py -> outputs/stream_metrics.parquet, and print the stream
table plus total projected crossings.

Add tests:
  T7  age-band assignment is correct at exact boundaries (365, 1095, 1825, 3650 days)
  T8  sum of stream n equals the pending inventory size
  T9  no per-case column survives into the stream output
```

### Verification
```bash
python scripts/04_build_streams.py && python - <<'EOF'
import pandas as pd
s = pd.read_parquet("outputs/stream_metrics.parquet")
assert (s.p.between(0,1) | s.p.isna()).all()
assert (s[s.age_band=="0-1y"].p == 0).all(), "young streams must be zero-risk in a 12m horizon"
print(s[["id","n","p","low_confidence","historical_share"]].to_string(index=False))
print("projected crossings:", round((s.p*s.n).sum()))
EOF
```

### 🛑 STOP CONDITION — H8
Streams not producing sane numbers → reduce to 3 case types and 3 age bands. Ship fewer,
correct streams rather than many wrong ones.

---

# P5 — OPTIMISER
**H8–H10.5 · Builder 2**

### Agentic prompt
```
Implement src/optimization/allocate.py using OR-Tools CP-SAT.

  allocate(streams, throughput, reserved=0, harm_floor=0.8,
           realism_bound=0.30, unc_cap=0.15) -> dict

  Variables: x_s integer in [0, n_s] = target disposals from stream s.
  avail = throughput - reserved
  b_s = avail * n_s / total_n                     (proportional baseline)
  h_s = historical_share_s * avail                (historical composition, in units)

  Objective: minimise sum( round(1000 * p_s) * (n_s - x_s) )   # integer-scaled

  Constraints:
    C1  sum(x_s) <= avail
    C2  x_s >= floor(harm_floor * b_s)                        fairness floor
    C3  abs(x_s - h_s) <= realism_bound * h_s                 realism bound
    C4  abs(x_s - b_s) <= unc_cap * b_s     for low_confidence streams only
    Clamp every derived bound into [0, n_s] and ensure lo <= hi before adding the variable.

  Solver time limit 5 seconds.

  Infeasibility handling — required, not optional:
    Relax harm_floor in steps of 0.05 down to 0.0, then realism_bound in steps of 0.05 up
    to 1.0. Record every relaxation applied in relaxed_constraints as human-readable strings
    e.g. "fairness floor relaxed 0.80 -> 0.75". Never fail silently. Never return an
    infeasible plan without saying so.

  Return: {feasible, allocation:{id:int}, before:{crossings}, after:{crossings},
           relaxed_constraints:[], baseline:{id:int}}
  before.crossings = sum(p_s * (n_s - b_s))     # proportional baseline
  after.crossings  = sum(p_s * (n_s - x_s))     # optimised

Add tests:
  T10 sum(allocation) <= throughput - reserved
  T11 every x_s >= floor(0.8 * b_s) when no relaxation was recorded
  T12 every |x_s - h_s| <= 0.30 * h_s when no relaxation was recorded
  T13 throughput = 0 returns feasible with all x_s = 0
  T14 an over-constrained input returns feasible=True with a non-empty relaxed_constraints
  T15 after.crossings <= before.crossings when no relaxation was applied
```

### Verification
```bash
pytest tests/test_all.py -q -k "allocate or optim" && python - <<'EOF'
import pandas as pd
from src.optimization.allocate import allocate
s = pd.read_parquet("outputs/stream_metrics.parquet").to_dict("records")
r = allocate(s, throughput=int(sum(x["n"] for x in s)*0.25))
print("feasible:", r["feasible"], "| relaxations:", r["relaxed_constraints"])
print("before:", round(r["before"]["crossings"]), "-> after:", round(r["after"]["crossings"]))
EOF
```
**If before and after are identical, your constraints are over-tight — check C3 before C2.**

### 🛑 STOP CONDITION — H10.5
CP-SAT not solving → replace with a greedy fill: sort streams by `p_s` descending, assign the
fairness floor to every stream first, then distribute the remainder respecting C3.
**Same signature, same return shape, ~25 lines.** The API never notices.

---

# P6 — API
**H10.5–H12 · Builder 2**

### Agentic prompt
```
Replace the hardcoded responses in backend/main.py with real computation, preserving the
frozen contract exactly — the frontend is already built against it.

Load once at startup into module state: stream_metrics.parquet, km_curves.pkl,
quality_report.json. No database.

  GET /meta      real counts, default_throughput = observed historical disposals per
                 planning period, mode = "REAL" or "SIMULATED"
  GET /streams   recompute p per stream when threshold_days or horizon_days differ from the
                 cached defaults; otherwise serve cached
  POST /optimize call allocate()
  POST /override call override() (stub returning 501 until P9 lands)
  GET /quality   serve quality_report.json plus low_confidence_streams count

Pydantic models for every request and response. Validate: threshold_days > 0,
horizon_days > 0, throughput >= 0, reserved >= 0, reserved <= throughput.

Add a startup assertion that no response model contains a per-case field. Add a response
middleware that raises if any serialised payload contains the key "case_id".

Do not add authentication, rate limiting, logging middleware, or a database.
```

### Verification
```bash
uvicorn backend.main:app --port 8000 & sleep 3
curl -s localhost:8000/meta | python -m json.tool | head -20
curl -s "localhost:8000/streams?threshold_days=1095&horizon_days=365" | python -c "import sys,json; d=json.load(sys.stdin); print(len(d['streams']),'streams'); assert 'case_id' not in json.dumps(d)"
curl -s -X POST localhost:8000/optimize -H 'Content-Type: application/json' \
  -d '{"throughput":5000,"reserved":0,"threshold_days":1095,"horizon_days":365}' | python -m json.tool
```

---

# P7 — FRONTEND
**H2–H12 · Builder 3 · Runs in parallel against `outputs/mock_api.json` from H2**

### Agentic prompt
```
Build a single-screen React console with Vite. JavaScript, not TypeScript. No router,
no auth, no state library — useState and fetch only.

Develop against outputs/mock_api.json until the real API is live. Read the base URL from
an API_BASE constant so the switch is one line.

Layout, top to bottom, on one screen at 1440x900 without scrolling if possible:

1. HEADER — "JudgeMyWay" · district · data period · and a persistent badge reading
   "RETROSPECTIVE SIMULATION" in amber. This badge is never hidden.
2. CONTROLS row — sliders: ageing threshold (1-10 years, default 3), planning horizon
   (3-24 months, default 12), throughput (0.5x-1.5x of default), reserved priority (number).
   Changing a slider refetches /streams. Debounce 300ms.
3. SUMMARY row — four large stat cards: pending inventory, projected crossings (baseline),
   projected crossings (optimised, dash until optimise is run), delta (green when negative).
4. STREAM TABLE — columns: stream, inventory, ageing risk (as a percentage with a small
   confidence range), confidence badge, historical share, baseline target, recommended target,
   change. Low-confidence rows get a muted amber dot and a tooltip naming the stratum level used.
5. "GENERATE PLAN" primary button -> POST /optimize, populate recommended targets, animate
   the summary delta. Show any relaxed_constraints as a visible amber notice.
6. OVERRIDE PANEL — each recommended target becomes editable after a plan exists. On change,
   POST /override and show: delta in projected crossings, affected streams, constraint status.
7. DATA QUALITY strip — records loaded, excluded, censored, low-confidence streams; the
   exclusion reasons expandable.
8. FOOTER — "JudgeMyWay recommends disposal composition across case categories. It never ranks
   individual cases. Listing remains with the registrar." Always visible.

Design: navy 16255C, ice DCE4F7, gold C89B3C, background F7F8FC, ink 1F2430. Serif headings,
sans body. Restrained, institutional, no gradients, no emoji, no icons packs.

Show a loading state on every fetch and an explicit error state — never a blank panel.
Never render a per-case value; the API does not provide one and the UI must not invent one.
```

### Verification
Open `http://localhost:5173`. Move every slider. Click Generate Plan. Edit an override.
Trigger an error by stopping the API — confirm the UI degrades visibly rather than blanking.

### 🛑 STOP CONDITION — H12
Not rendering against the mock → cut the override panel and the quality strip. Keep the
summary, the table, and the Generate Plan button. Those three are the demo.

---

# P8 — INTEGRATION
**H12–H14 · All three · THE HARD GATE**

### Agentic prompt
```
Wire the frontend to the live backend. Flip API_BASE to http://localhost:8000.

Then run a full end-to-end trace and fix only what blocks it:
  1. Page loads, /meta and /streams populate, table renders real numbers.
  2. Every slider triggers a refetch and visibly changes the numbers.
  3. Generate Plan returns a real allocation and the summary delta updates.
  4. Data quality strip shows real counters.

For each defect: report the failing layer (data, optimiser, API, UI) before proposing a fix.
Do not add features. Do not refactor. Do not improve styling. Fix only what breaks the trace.

Write scripts/run_all.sh that runs the pipeline end to end from raw data to a running
backend, so the whole thing can be reproduced from scratch in one command.
```

### Verification
Watch someone who did not build it operate the trace unaided. That is the test.

### 🛑 HARD GATE — H14
**If a real solve on real data does not render in the browser by H14: freeze scope now.**
Cut P9 (override), cut the uncertainty cap, cut the quality strip. Spend the remaining hours
making the core reliable. A working core beats a broken system, every time.

---

# P9 — OVERRIDE & COUNTERFACTUAL
**H14–H16 · Builders 2 + 3 · The differentiator**

### Agentic prompt
```
Implement src/optimization/override.py.

  override(streams, throughput, reserved, locked: dict[str,int], **params) -> dict
    Run allocate() once for the recommendation (or accept it as an argument to avoid
    re-solving). Then re-solve with x_s == locked[s] fixed as hard equality for every locked
    stream, all other constraints unchanged.
    Return: before.crossings, after.crossings, delta, affected_streams (streams whose target
    moved by more than 1 unit), violations (constraints that had to be relaxed to accommodate
    the lock).
    If the lock makes the problem infeasible even after full relaxation, return
    feasible=False with a plain-language reason. Never crash.

  Log every override to outputs/override_log.jsonl:
    {timestamp, stream_id, recommended, chosen, delta_crossings}
  Log only. NEVER learn from overrides, never adjust weights, never persist a preference model.

Wire POST /override to it and remove the 501 stub.

Frontend: on target edit, display
  "Projected crossings: <before> -> <after> (<+/-delta>)"
  affected streams as chips; constraint status as OK or a named relaxation.
Language must be neutral. Never "warning", never "you should not", never red for an override.
Amber at most. The system reports a consequence; it does not scold.

Add tests:
  T16 locking every stream to its recommendation yields delta == 0
  T17 locking a stream below its fairness floor records a violation rather than crashing
  T18 an impossible lock returns feasible=False with a reason string
```

### Verification
In the browser: edit a target down, confirm crossings rise and affected streams appear.
Edit it back, confirm delta returns to zero. Then `cat outputs/override_log.jsonl`.

---

# P10 — EVALUATION & DATA QUALITY
**H16–H17.5 · Builder 1 · This is what makes Q&A survivable**

### Agentic prompt
```
Implement src/evaluation/baseline.py and scripts/06_evaluate.py.

Compute and write outputs/evaluation.json — every number computed, none invented:

1. CENSORING IMPACT (the headline number)
   Median duration using only disposed cases (the naive/Excel approach) vs the
   Kaplan-Meier median which accounts for censoring, per major case type.
   Report the absolute and percentage underestimate. THIS IS THE "WHY NOT EXCEL" NUMBER.

2. TEMPORAL VALIDATION — split by FILING COHORT, never randomly, never by disposal date:
   fit on filings 2010-2013, validate 2014-2015, test out-of-time on 2016.
   Report observed vs predicted crossing rate per stream on the test cohort.

3. OPTIMISER COMPARISON — projected crossings under:
   (a) proportional-to-inventory baseline
   (b) historical-composition baseline
   (c) our constrained optimum
   Report all three. If we lose on any secondary metric, report that too.

4. SENSITIVITY — projected crossings across thresholds {1,3,5,10} years and horizons
   {6,12,24} months. A table, not a claim.

5. CONSTRAINT AUDIT — confirm no fairness or realism constraint was violated in the
   reported optimum.

Print a one-page summary to stdout in the exact wording we can read aloud. Use the phrase
"in a retrospective simulation" wherever a result is quoted. Never write "reduces backlog".
```

### Verification
```bash
python scripts/06_evaluate.py | tee outputs/evaluation_summary.txt
```
**Read every number aloud. If one surprises you, it is wrong — find out why before the demo.**

---

# P11 — FREEZE, QA, BACKUP
**H17.5–H20 · All three**

### Agentic prompt
```
1. scripts/05_freeze_demo.py — run the full pipeline once and serialise every API response
   for the exact demo scenario to data/demo/scenario.json. Add a DEMO_MODE env flag to the
   backend that serves this file verbatim. The demo must not depend on live computation.
   The frozen values must be REAL computed outputs — never hand-edited.

2. Run the complete test suite. Every test green, or the failing test is deleted along with
   the feature it covers. No skipped tests, no xfail.

3. Grep the entire repo for fabricated content:
     grep -rniE "TODO|FIXME|lorem|placeholder|dummy|fake|hardcoded" src backend frontend/src
   Report every hit. Remove or justify each.

4. Grep for leakage in output paths:
     grep -rn "case_id" backend/ frontend/src/
   Any hit outside the ingestion layer is a bug.

5. Write README.md: what it is, the dataset with its licence and citation, how to run,
   what is real vs simulated, and the limitations list verbatim from our spec.

6. Print a final CHECKLIST.md confirming: no per-case output, no forbidden features in the
   model, censored cases retained, all quoted numbers computed, RETROSPECTIVE SIMULATION
   badge present on every screen.
```

### Verification — the real one
```bash
DEMO_MODE=1 uvicorn backend.main:app --port 8000 &
# then: run the 90-second demo five times, timed, on the machine you will actually present from
```
Record a screen capture of a clean run as the backup video. **Do this before you are tired.**

### 🛑 FEATURE FREEZE — H18
Nobody opens an editor after H18 except to fix a crash in the demo path. Name the person who
enforces this and give them the authority now, while everyone is still reasonable.

---

# DEPLOYMENT

**There is no cloud deployment and you should not build one.** It adds risk and demonstrates
nothing. Run locally on one machine:

```bash
# terminal 1
source .venv/bin/activate && DEMO_MODE=1 uvicorn backend.main:app --port 8000
# terminal 2
cd frontend && npm run dev
```

If asked about deployment, the honest answer is: *"This is a prototype. Deployment would need
refitting on the court's current CIS data, authorised access, audit logging and periodic
recalibration. We'd call this MVP, not pilot."*

Optional, only if everything else is done: `npm run build` and serve the static bundle from
FastAPI so the whole thing is one process. Saves a terminal at demo time. That is the entire
benefit.

---

# TIMELINE SUMMARY

```
H0 ──── P0 recon ────┐ 🛑 no required fields → synthetic fallback
H1 ──── P1 scaffold ─┤ 🛑 contract must freeze
H2 ──── P2 clean ────┼──────── P7 frontend on mocks ────────┐
H4 ──── P3 survival ─┤ 🛑 T2 must pass                      │
H6.5 ── P4 streams ──┤                                      │
H8 ──── P5 optimiser ┤ 🛑 CP-SAT fails → greedy fill        │
H10.5 ─ P6 API ──────┘                                      │
H12 ─── P8 INTEGRATION ◄────────────────────────────────────┘
H14 ─── 🛑 HARD GATE: real solve renders, or freeze scope
H14 ─── P9 override
H16 ─── P10 evaluation
H17.5 ─ P11 freeze + QA + backup video
H18 ─── 🛑 FEATURE FREEZE
H20 ─── done
```

---

# THE FIVE COMMANDS THAT PROVE IT WORKS

```bash
pytest -q                                        # all green
python scripts/02_clean.py                       # censored > 0
python scripts/03_fit_km.py                      # curves fitted, levels reported
python scripts/06_evaluate.py                    # the censoring-impact number
DEMO_MODE=1 uvicorn backend.main:app --port 8000 # serves the frozen scenario
```

If those five run clean, you have a defensible prototype. Everything else is polish.