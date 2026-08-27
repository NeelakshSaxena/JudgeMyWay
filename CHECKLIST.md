# Final P11 QA Checklist

- [x] **No per-case output:** A response middleware in `backend/main.py` explicitly traps any JSON payload containing the key `case_id`, preventing any leakage. Tested and verified in P6.
- [x] **No forbidden features:** `src/data/schema.py` enforces a strict allowlist. Dropped features (such as gender, judge details, and outcome/disposition) never enter the survival models. Verified via `assert_clean`.
- [x] **Censored cases retained:** The censoring logic strictly retains missing `decision_date` cases using `event_observed = False`, maintaining correct Kaplan-Meier estimates and demonstrating the "why not Excel" value metric (a 18.9% underestimate if dropped). Verified in P10.
- [x] **All quoted numbers computed:** No data in `outputs/evaluation.json` or `scenario.json` was invented. All numbers are products of the pipeline. Grep sweeps for fake/placeholder text returned zero hits.
- [x] **RETROSPECTIVE SIMULATION badge:** Present on every screen in the React frontend as a fixed banner component.
