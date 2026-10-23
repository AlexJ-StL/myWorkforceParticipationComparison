"""Assembly: frame joins, derived-column math, zero-denominator guards, and
the coverage report."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import labor_data
from labor_data import (
    HOURLY_COLUMNS,
    MONTHLY_COLUMNS,
    QUARTERLY_COLUMNS,
    WorkforceData,
    _add_derived_hourly,
    _add_derived_monthly,
    _add_derived_quarterly,
    _coverage,
    _frame,
    assemble,
)

MONTHLY_DERIVED = {
    "gap_pp",
    "rate_ratio_w_m",
    "women_lf_share",
    "implied_rate_men",
    "implied_rate_women",
    "implied_rate_total",
    "emp_pop_ratio_total",
    "weekly_hours_total",
    "weekly_hours_ratio_w_m",
    "rate_prime_men",
    "rate_prime_women",
}
QUARTERLY_DERIVED = {"earnings_ratio_nominal", "earnings_ratio_real"}
HOURLY_DERIVED = {"ahe_real", "ahe_production_real"}


@pytest.fixture
def monthly_frame() -> pd.DataFrame:
    """Hand-built frame with exactly computable derived values."""
    return pd.DataFrame(
        {
            "rate_men": [80.0, 85.0],
            "rate_women": [40.0, 42.5],
            "labor_force_men": [80.0, 85.0],
            "labor_force_women": [40.0, 42.5],
            "labor_force_total": [120.0, 127.5],
            "population_men": [100.0, 100.0],
            "population_women": [100.0, 100.0],
            "population_total": [200.0, 200.0],
            "employment_total": [110.0, 116.0],
            "weekly_hours_men": [40.0, 41.0],
            "weekly_hours_women": [35.0, 36.0],
        },
        index=pd.DatetimeIndex(["2020-01-01", "2020-02-01"]),
    )


# ---------------------------------------------------------------------------
# _frame
# ---------------------------------------------------------------------------


def test_frame_renames_columns_preserving_values():
    raw = {
        "CIVPART": pd.Series([58.6, 58.9], index=pd.DatetimeIndex(["2020-02-01", "2020-01-01"])),
    }
    frame = _frame(raw, {"CIVPART": "rate_total"})
    assert list(frame.columns) == ["rate_total"]
    assert list(frame["rate_total"]) == [58.9, 58.6]  # sorted index
    assert frame.index[0] == pd.Timestamp("2020-01-01")


def test_frame_outer_joins_unequal_spans():
    raw = {
        "CIVPART": pd.Series(
            [1.0, 2.0, 3.0],
            index=pd.DatetimeIndex(["2020-01-01", "2020-02-01", "2020-03-01"]),
        ),
        "CLF16OV": pd.Series([10.0, 20.0], index=pd.DatetimeIndex(["2020-02-01", "2020-03-01"])),
    }
    frame = _frame(raw, {"CIVPART": "a", "CLF16OV": "b"})
    assert len(frame) == 3
    assert pd.isna(frame["b"].iloc[0])
    assert frame["b"].iloc[1] == 10.0
    assert frame["a"].iloc[0] == 1.0
    assert frame["a"].iloc[2] == 3.0


def test_frame_does_not_mutate_input_series(synthetic_raw):
    original = synthetic_raw["CIVPART"].copy()
    _frame(synthetic_raw, {"CIVPART": "rate_total"})
    pd.testing.assert_series_equal(synthetic_raw["CIVPART"], original)


def test_frame_missing_sid_raises_keyerror():
    """Pin (D3): a programming error -- raw is always built from the catalog."""
    raw = {"CIVPART": pd.Series([1.0], index=pd.DatetimeIndex(["2020-01-01"]))}
    with pytest.raises(KeyError, match="CLF16OV"):
        _frame(raw, {"CIVPART": "a", "CLF16OV": "b"})


def test_frame_empty_mapping_raises_value_error():
    with pytest.raises(ValueError, match="No objects to concatenate"):
        _frame({}, {})


# ---------------------------------------------------------------------------
# derived monthly
# ---------------------------------------------------------------------------


def test_derived_monthly_exact_values(monthly_frame):
    out = _add_derived_monthly(monthly_frame)
    assert (out["gap_pp"] == pd.Series([40.0, 42.5], index=monthly_frame.index)).all()
    assert out["rate_ratio_w_m"].iloc[0] == pytest.approx(50.0)
    assert out["women_lf_share"].iloc[0] == pytest.approx(40.0 / 120.0 * 100)
    assert out["implied_rate_men"].iloc[0] == pytest.approx(80.0)
    assert out["implied_rate_women"].iloc[1] == pytest.approx(42.5)
    assert out["implied_rate_total"].iloc[1] == pytest.approx(63.75)
    assert out["emp_pop_ratio_total"].iloc[0] == pytest.approx(55.0)
    # weekly hours derived columns
    # _safe_ratio uses scale=100, so (40+35)/2 * 100 = 3750
    assert out["weekly_hours_total"].iloc[0] == pytest.approx(3750.0)
    assert out["weekly_hours_ratio_w_m"].iloc[0] == pytest.approx(35.0 / 40.0 * 100)


def test_derived_monthly_gap_is_men_minus_women(monthly_frame):
    out = _add_derived_monthly(monthly_frame)
    np.testing.assert_allclose(
        out["gap_pp"].to_numpy(),
        monthly_frame["rate_men"].to_numpy() - monthly_frame["rate_women"].to_numpy(),
    )


def test_derived_monthly_weekly_hours_ratio_is_women_over_men(monthly_frame):
    out = _add_derived_monthly(monthly_frame)
    expected = monthly_frame["weekly_hours_women"] / monthly_frame["weekly_hours_men"] * 100
    np.testing.assert_allclose(out["weekly_hours_ratio_w_m"].to_numpy(), expected.to_numpy())


def test_derived_monthly_zero_denominators_become_nan_not_inf():
    """D5: zero denominators must produce NaN, never inf/nan-by-crash."""
    frame = pd.DataFrame(
        {
            "rate_men": [0.0],
            "rate_women": [40.0],
            "labor_force_men": [0.0],
            "labor_force_women": [0.0],
            "labor_force_total": [0.0],
            "population_men": [0.0],
            "population_women": [0.0],
            "population_total": [0.0],
            "employment_total": [0.0],
            "weekly_hours_men": [0.0],
            "weekly_hours_women": [35.0],
        },
        index=pd.DatetimeIndex(["2020-01-01"]),
    )
    out = _add_derived_monthly(frame)
    # Division-based columns should be NaN when denominator is zero
    division_columns = {
        "rate_ratio_w_m",
        "women_lf_share",
        "implied_rate_men",
        "implied_rate_women",
        "implied_rate_total",
        "emp_pop_ratio_total",
        "weekly_hours_ratio_w_m",
    }
    for column in division_columns:
        assert pd.isna(out[column].iloc[0]), f"{column} should be NaN"
        assert np.isfinite(out[column].dropna()).all()
    # weekly_hours_total divides by 2 (not zero), so it should be finite
    assert np.isfinite(out["weekly_hours_total"].iloc[0])
    assert out["weekly_hours_total"].iloc[0] == pytest.approx(1750.0)
    # gap_pp is a subtraction (0 - 40 = -40), not NaN
    assert out["gap_pp"].iloc[0] == -40.0
    assert np.isfinite(out["gap_pp"].dropna()).all()


def test_derived_monthly_does_not_mutate_input(monthly_frame):
    original = monthly_frame.copy()
    _add_derived_monthly(monthly_frame)
    pd.testing.assert_frame_equal(monthly_frame, original)


# ---------------------------------------------------------------------------
# derived quarterly / hourly
# ---------------------------------------------------------------------------


def test_derived_quarterly_exact_values():
    frame = pd.DataFrame(
        {
            "weekly_nominal_men": [100.0, 200.0],
            "weekly_nominal_women": [60.0, 200.0],
            "weekly_real_men": [200.0, 200.0],
            "weekly_real_women": [100.0, 100.0],
        },
        index=pd.DatetimeIndex(["1980-01-01", "1980-04-01"]),
    )
    out = _add_derived_quarterly(frame)
    assert out["earnings_ratio_nominal"].iloc[0] == pytest.approx(60.0)
    assert out["earnings_ratio_nominal"].iloc[1] == pytest.approx(100.0)
    assert out["earnings_ratio_real"].iloc[0] == pytest.approx(50.0)


def test_derived_quarterly_zero_denominator_is_nan():
    frame = pd.DataFrame(
        {
            "weekly_nominal_men": [0.0],
            "weekly_nominal_women": [60.0],
            "weekly_real_men": [0.0],
            "weekly_real_women": [50.0],
        },
        index=pd.DatetimeIndex(["1980-01-01"]),
    )
    out = _add_derived_quarterly(frame)
    assert pd.isna(out["earnings_ratio_nominal"].iloc[0])
    assert pd.isna(out["earnings_ratio_real"].iloc[0])


def test_derived_hourly_exact_values():
    frame = pd.DataFrame(
        {
            "ahe_nominal": [20.0, 30.0],
            "ahe_production_nominal": [15.0, 22.5],
            "cpi": [200.0, 150.0],
        },
        index=pd.DatetimeIndex(["2020-01-01", "2020-02-01"]),
    )
    out = _add_derived_hourly(frame)
    assert out["ahe_real"].iloc[0] == pytest.approx(10.0)
    assert out["ahe_real"].iloc[1] == pytest.approx(20.0)
    assert out["ahe_production_real"].iloc[0] == pytest.approx(7.5)


def test_derived_hourly_zero_cpi_is_nan():
    frame = pd.DataFrame(
        {"ahe_nominal": [20.0], "ahe_production_nominal": [15.0], "cpi": [0.0]},
        index=pd.DatetimeIndex(["2020-01-01"]),
    )
    out = _add_derived_hourly(frame)
    assert pd.isna(out["ahe_real"].iloc[0])
    assert pd.isna(out["ahe_production_real"].iloc[0])


# ---------------------------------------------------------------------------
# coverage report
# ---------------------------------------------------------------------------


def test_coverage_reports_span_counts_and_metadata():
    raw = {
        "CIVPART": pd.Series(
            [58.6, np.nan, 61.8],
            index=pd.DatetimeIndex(["2020-01-01", "2020-02-01", "2020-03-01"]),
        )
    }
    cov = _coverage(raw)
    row = cov.iloc[0]
    assert row["sid"] == "CIVPART"
    assert row["label"] == "Labor Force Participation Rate"
    assert row["units"] == "percent"
    assert row["first_obs"] == "2020-01-01"
    assert row["last_obs"] == "2020-03-01"
    assert row["observations"] == 3
    assert row["missing"] == 1
    assert row["missing_periods"] == "2020-02"


def test_coverage_flags_the_october_2025_shutdown_gap():
    index = pd.DatetimeIndex(["2025-09-01", "2025-10-01", "2025-11-01"])
    raw = {"CIVPART": pd.Series([62.5, np.nan, 62.5], index=index)}
    cov = _coverage(raw)
    assert cov.iloc[0]["missing_periods"] == "2025-10"


def test_coverage_lists_multiple_missing_periods_in_order():
    index = pd.DatetimeIndex(["2020-01-01", "2020-02-01", "2020-03-01", "2020-04-01"])
    raw = {"CIVPART": pd.Series([1.0, np.nan, 3.0, np.nan], index=index)}
    cov = _coverage(raw)
    assert cov.iloc[0]["missing_periods"] == "2020-02, 2020-04"


def test_coverage_empty_series_reports_null_spans():
    raw = {"CIVPART": pd.Series([np.nan, np.nan], index=pd.DatetimeIndex(["2020-01-01", "2020-02-01"]))}
    cov = _coverage(raw)
    row = cov.iloc[0]
    assert row["first_obs"] is None
    assert row["last_obs"] is None
    assert row["observations"] == 2
    assert row["missing"] == 2


def test_coverage_unknown_sid_uses_sid_as_label():
    """Pin (D4): coverage metadata uses the sid as label for unknown series."""
    raw = {"MYSTERY": pd.Series([1.0], index=pd.DatetimeIndex(["2020-01-01"]))}
    cov = _coverage(raw)
    row = cov.iloc[0]
    assert row["label"] == "MYSTERY"
    assert row["units"] == "unknown"


# ---------------------------------------------------------------------------
# assemble (uses the synthetic catalog-shaped fixture)
# ---------------------------------------------------------------------------


def test_assemble_builds_all_three_frames(synthetic_data):
    assert set(synthetic_data.monthly.columns) == set(MONTHLY_COLUMNS.values()) | MONTHLY_DERIVED
    assert set(synthetic_data.quarterly.columns) == set(QUARTERLY_COLUMNS.values()) | QUARTERLY_DERIVED
    assert set(synthetic_data.hourly.columns) == set(HOURLY_COLUMNS.values()) | HOURLY_DERIVED


def test_assemble_returns_workforce_data(synthetic_data):
    assert isinstance(synthetic_data, WorkforceData)


def test_assemble_sorts_every_frame(synthetic_data):
    for frame in (
        synthetic_data.monthly,
        synthetic_data.quarterly,
        synthetic_data.hourly,
    ):
        assert frame.index.is_monotonic_increasing


def test_assemble_preserves_october_2025_gap_in_derived_columns(synthetic_data):
    """The no-interpolation invariant, applied to derived columns too."""
    gap_row = synthetic_data.monthly.loc["2025-10-01"]
    assert gap_row["rate_men"] != gap_row["rate_men"]  # NaN
    assert pd.isna(gap_row["gap_pp"])
    assert pd.isna(gap_row["rate_ratio_w_m"])
    assert pd.isna(gap_row["implied_rate_men"])
    # BLS weekly hours should also have the gap
    assert pd.isna(gap_row["weekly_hours_men"])
    assert pd.isna(gap_row["weekly_hours_women"])


def test_assemble_leads_with_nan_for_short_series(synthetic_data):
    """CES0500000003 starts 2006-03; the hourly frame must show the leading gap."""
    assert synthetic_data.hourly["ahe_nominal"].first_valid_index() == pd.Timestamp("2006-03-01")
    assert pd.isna(synthetic_data.hourly["ahe_nominal"].iloc[0])


def test_assemble_gap_matches_rate_difference(synthetic_data):
    monthly = synthetic_data.monthly
    mask = monthly["rate_men"].notna() & monthly["rate_women"].notna()
    np.testing.assert_allclose(
        monthly.loc[mask, "gap_pp"].to_numpy(),
        (monthly.loc[mask, "rate_men"] - monthly.loc[mask, "rate_women"]).to_numpy(),
    )


def test_assemble_earnings_ratio_matches_series_division(synthetic_data):
    quarterly = synthetic_data.quarterly
    mask = quarterly["weekly_nominal_men"].notna()
    np.testing.assert_allclose(
        quarterly.loc[mask, "earnings_ratio_nominal"].to_numpy(),
        (quarterly.loc[mask, "weekly_nominal_women"] / quarterly.loc[mask, "weekly_nominal_men"] * 100).to_numpy(),
    )


def test_assemble_weekly_hours_ratio_matches_series_division(synthetic_data):
    monthly = synthetic_data.monthly
    mask = monthly["weekly_hours_men"].notna() & monthly["weekly_hours_women"].notna()
    np.testing.assert_allclose(
        monthly.loc[mask, "weekly_hours_ratio_w_m"].to_numpy(),
        (monthly.loc[mask, "weekly_hours_women"] / monthly.loc[mask, "weekly_hours_men"] * 100).to_numpy(),
    )


def test_assemble_monthly_span(synthetic_data):
    assert synthetic_data.monthly.index[0] == pd.Timestamp("1948-01-01")
    assert synthetic_data.monthly.index[-1] == pd.Timestamp("2026-09-01")


def test_assemble_quarterly_span(synthetic_data):
    assert synthetic_data.quarterly.index[0] == pd.Timestamp("1979-01-01")
    assert synthetic_data.quarterly.index[-1] == pd.Timestamp("2026-04-01")


def test_assemble_no_derived_column_is_infinite_on_clean_data(synthetic_data):
    """D5 guard at the assembly level: finite inputs, finite outputs."""
    for frame in (
        synthetic_data.monthly,
        synthetic_data.quarterly,
        synthetic_data.hourly,
    ):
        for column in frame.columns:
            values = frame[column].astype(float)
            assert np.isfinite(values.dropna()).all(), f"{column} has non-finite values"


def test_assemble_empty_raw_raises_keyerror():
    """Pin (D3): empty input fails on the first missing catalog sid."""
    with pytest.raises(KeyError, match="CIVPART"):
        assemble({})


def test_assemble_partial_raw_reports_a_missing_sid(synthetic_raw):
    broken = dict(synthetic_raw)
    del broken["LES1252881800Q"]
    with pytest.raises(KeyError, match="LES1252881800Q"):
        assemble(broken)


def test_assemble_build_invokes_fetch_and_assemble(monkeypatch):
    """build() is a thin composition; pin it with doubles."""
    sentinel = _empty_workforce_data()
    seen: dict = {}

    def fake_fetch_all(*, refresh: bool = False, bls_api_key: str | None = None):
        seen["refresh"] = refresh
        seen["bls_api_key"] = bls_api_key
        return {"ok": 1}

    def fake_assemble(raw):
        seen["assembled"] = raw
        return sentinel

    monkeypatch.setattr(labor_data.fred_data, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(labor_data, "assemble", fake_assemble)

    assert labor_data.build() is sentinel
    assert seen["assembled"] == {"ok": 1}
    assert seen["bls_api_key"] is None


def test_assemble_build_passes_refresh_flag(monkeypatch):
    seen: dict = {}

    def fake_fetch_all(*, refresh: bool = False, bls_api_key: str | None = None):
        seen["refresh"] = refresh
        seen["bls_api_key"] = bls_api_key
        return {}

    monkeypatch.setattr(labor_data.fred_data, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(labor_data, "assemble", lambda raw: _empty_workforce_data())

    labor_data.build(refresh=True)
    assert seen["refresh"] is True
    assert seen["bls_api_key"] is None


def test_assemble_build_passes_bls_api_key(monkeypatch):
    seen: dict = {}

    def fake_fetch_all(*, refresh: bool = False, bls_api_key: str | None = None):
        seen["bls_api_key"] = bls_api_key
        return {}

    monkeypatch.setattr(labor_data.fred_data, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(labor_data, "assemble", lambda raw: _empty_workforce_data())

    labor_data.build(bls_api_key="test-key-123")
    assert seen["bls_api_key"] == "test-key-123"


def _empty_workforce_data() -> WorkforceData:
    return WorkforceData(
        monthly=pd.DataFrame(),
        quarterly=pd.DataFrame(),
        hourly=pd.DataFrame(),
        coverage=pd.DataFrame(),
    )
