import pandas as pd

ALLOWED_FEATURES = {
    "case_id", "filing_date", "registration_date", "case_type",
    "court_id", "district", "state", "act_section",
    "duration_days", "event_observed", "registration_lag_days", "act_section_group"
}

LABEL_FIELDS = {"decision_date"}

FORBIDDEN = {
    "disposition", "outcome", "judge_id", "judge_position",
    "petitioner_name", "respondent_name", "petitioner_gender",
    "respondent_gender", "gender", "hearing_date"
}

def assert_clean(df: pd.DataFrame) -> None:
    cols = set(df.columns)
    forbidden_present = cols.intersection(FORBIDDEN)
    assert not forbidden_present, f"Forbidden columns present: {forbidden_present}"
    
    # We allow unvetted columns for now unless strictly required, but the prompt says:
    # "raises AssertionError naming any forbidden or unvetted column"
    unvetted = cols - ALLOWED_FEATURES - LABEL_FIELDS
    assert not unvetted, f"Unvetted columns present: {unvetted}"
