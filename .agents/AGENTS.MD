# Project Context

## What this is
A capacity-planning tool for Indian district court administrators. Given a court's pending
case inventory and historical disposal-time distributions, it projects how many cases will
cross an ageing threshold, and recommends a disposal composition across case categories that
minimises that number under fairness constraints. A registrar can override any recommendation;
the system quantifies the consequence.

---

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

---

## Repository layout

**Create files only at these paths. If a task seems to need a new top-level directory,
it doesn't — put it in `outputs/` or ask.**

```
nyayaflow/
├── CLAUDE.md                     this file (AGENTS.md / .cursorrules if your tool prefers)
├── README.md                     what it is · dataset + licence · how to run · limitations
├── requirements.txt              pinned, closed set — see Stack below
├── .gitignore                    data/raw, data/processed, models, .venv, node_modules, *.pyc
│
├── config/                       [shared — coordinate before editing]
│   ├── config.yaml               state, year range, threshold_days, horizon_days,
│   │                             min_events, harm_floor, realism_bound, unc_cap
│   └── schema.yaml               REAL column names discovered in P0. Single source of truth —
│                                 no module may hardcode a column name.
│
├── data/                         [gitignored except demo/]
│   ├── raw/                      untouched download. NEVER write here.
│   ├── processed/                cases_clean.parquet, survival_dataset.parquet
│   └── demo/scenario.json        frozen demo payloads (committed)
│
├── models/                       [gitignored]
│   └── km_curves.pkl             fitted KaplanMeierFitter objects per stratum
│
├── outputs/                      every generated artefact lands here, nowhere else
│   ├── p0_recon.md               P0 schema + data-quality report
│   ├── quality_report.json       cleaning counters
│   ├── stream_metrics.parquet    per-stream n, p, p_lo, p_hi, low_confidence, historical_share
│   ├── evaluation.json           censoring impact, temporal validation, optimiser comparison
│   ├── evaluation_summary.txt    the one page we read aloud
│   ├── override_log.jsonl        append-only override record (logged, never learned from)
│   └── mock_api.json             frozen example responses — frontend develops against this
│
├── src/                          pure logic. No FastAPI imports, no I/O side effects.
│   ├── data/                     ── BUILDER 1 ──
│   │   ├── schema.py             ALLOWED_FEATURES · FORBIDDEN · assert_clean()
│   │   ├── load.py               duckdb read, column projection, date parsing
│   │   └── clean.py              exclusion rules + counters + censoring
│   ├── survival/                 ── BUILDER 1 ──
│   │   ├── km.py                 fit_strata() · p_cross()      ← the technical core
│   │   └── fallback.py           stratum ladder + confidence flags
│   ├── streams/                  ── BUILDER 1 ──
│   │   └── build.py              inventory → allocation streams; AGGREGATES before returning
│   ├── optimization/             ── BUILDER 2 ──
│   │   ├── allocate.py           CP-SAT model + relaxation ladder
│   │   └── override.py           counterfactual re-solve
│   └── evaluation/               ── BUILDER 1 ──
│       └── baseline.py           naive vs KM · temporal split · optimiser comparison
│
├── backend/                      ── BUILDER 2 ── thin. Calls src/, holds no logic.
│   ├── main.py                   six endpoints, CORS, startup state load
│   └── models.py                 pydantic request/response models
│
├── frontend/                     ── BUILDER 3 ── nobody else edits this tree
│   ├── package.json · vite.config.js · index.html
│   └── src/
│       ├── main.jsx · App.jsx
│       ├── api.js                API_BASE constant — mock↔live is a one-line switch
│       ├── theme.js              navy 16255C · ice DCE4F7 · gold C89B3C · bg F7F8FC · ink 1F2430
│       └── components/
│           ├── Header.jsx        title · district · period · RETROSPECTIVE SIMULATION badge
│           ├── Controls.jsx      threshold · horizon · throughput · reserved sliders
│           ├── SummaryCards.jsx  inventory · baseline crossings · optimised · delta
│           ├── StreamTable.jsx   the main table
│           ├── OverridePanel.jsx editable targets + consequence display
│           └── DataQuality.jsx   loaded · excluded · censored · low-confidence
│
├── scripts/                      thin CLI wrappers. Logic lives in src/.
│   ├── 01_ingest.py  02_clean.py  03_fit_km.py  04_build_streams.py
│   ├── 05_freeze_demo.py  06_evaluate.py
│   └── run_all.sh                raw → running backend, one command
│
└── tests/                        ONE FILE PER OWNER — prevents merge conflicts
    ├── test_data.py              B1 · dates, censoring, exclusions, assert_clean
    ├── test_survival.py          B1 · p_cross conditional + horizon + fallback
    └── test_optimization.py      B2 · capacity, floors, realism bound, override
```

### Never create
`utils/` · `helpers/` · `common/` · `core/` · `lib/` · `notebooks/` · `docs/` · `api/v1/` ·
`services/` · `migrations/` · `Dockerfile` · `docker-compose.yml` · `.env` files ·
any second requirements file · any second test file per owner.

### Artefact flow — each stage reads the previous stage's file, never recomputes it
```
data/raw/                      (P0, manual download)
  → data/processed/survival_dataset.parquet     scripts/02_clean.py
  → models/km_curves.pkl                        scripts/03_fit_km.py
  → outputs/stream_metrics.parquet              scripts/04_build_streams.py
  → backend/main.py loads the above at startup
  → data/demo/scenario.json                     scripts/05_freeze_demo.py
```

### Ownership
Builder 1 owns `src/data`, `src/survival`, `src/streams`, `src/evaluation`, `tests/test_data.py`,
`tests/test_survival.py`. Builder 2 owns `src/optimization`, `backend/`,
`tests/test_optimization.py`. Builder 3 owns `frontend/`. `config/` is shared — announce before
editing. **If a task requires editing outside your tree, say so instead of doing it.**

---

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
Column names come from `config/schema.yaml` — never hardcoded in a module.
`src/` is import-pure: no file writes at import time, no FastAPI imports, no network calls.