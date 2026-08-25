# B1 - dates, censoring, exclusions, assert_clean

import pytest
import pandas as pd
from src.data.schema import assert_clean

def test_assert_clean_passes():
    df = pd.DataFrame({"case_id": [1], "filing_date": ["2020-01-01"]})
    assert_clean(df)

def test_assert_clean_raises():
    df = pd.DataFrame({"case_id": [1], "petitioner_gender": ["M"]})
    with pytest.raises(AssertionError, match="Forbidden columns present"):
        assert_clean(df)

def test_assert_clean_unvetted_raises():
    df = pd.DataFrame({"case_id": [1], "unknown_col": [123]})
    with pytest.raises(AssertionError, match="Unvetted columns present"):
        assert_clean(df)
