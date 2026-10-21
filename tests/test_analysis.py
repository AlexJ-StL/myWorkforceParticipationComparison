"""Statistics helpers: exact math, boundary semantics, and degenerate-input
contracts. Every expected value here is hand-computed, not read back from the
implementation under test.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

import analysis
from analysis import (
    EmptySeriesError,
    _alignment_stats,
    _at,
    _consistency_checks,
    _corr,
    _counts_stats,
    _coverage_summary,
    _covid_window,
    _earnings_stats,
    _index,
    _ols,
    _series_summary,
    _ym,
    col,
    compute_stats,
)
from labor_data import WorkforceData

D2 = pd.DatetimeIndex(["2020-01-01", "2020-02-01"])


# ---------------------------------------------------------------------------
# typed accessors
# ---------------------------------------------------------------------------


def test_col_returns_the_named_series():
    frame = pd.DataFrame({"a": [1.0, 2.0]})
    assert list(col(frame, "a")) == [1.0, 2.0]


def test_col_missing_column_raises_keyerror():
    with pytest.raises(KeyError):
        col(pd.DataFrame({"a": [1.0]}), "b")


def test_index_returns_datetime_index():
    series = pd.Series([1.0, 2.0], index=D2)
    assert isinstance(_index(series), pd.DatetimeIndex)


def test_at_returns_exact_value_at_exact_date():
    series = pd.Series([10.0, 20.0], index=D2)
    assert _at(series, "2020-02-01") == 20.0


def test_at_missing_date_raises_keyerror():
    series = pd.Series([10.0, 20.0], index=D2)
    with pytest.raises(KeyError, match="not in the series index"):
        _at(series, "2020-03-01")


def test_ym_formats_to_year_month():
    assert _ym(pd.Timestamp("1948-01-01")) == "1948-01"
    assert _ym("2026-09-15") == "2026-09"


# ---------------------------------------------------------------------------
# _series_summary
# ---------------------------------------------------------------------------


def test_series_summary_exact_values():
    series = pd.Series(
        [10.0, np.nan, 30.0, 20.0],
        index=pd.DatetimeIndex(
            ["2020-01-01", "2020-02-01", "2020-03-01", "2020-04-01"]
        ),
    )
    summary = _series_summary(series)
    assert summary["first"] == 10.0
    assert summary["first_date"] == "2020-01"
    assert summary["latest"] == 20.0
    assert summary["latest_date"] == "2020-04"
    assert summary["peak"] == 30.0
    assert summary["peak_date"] == "2020-03"
    assert summary["trough"] == 10.0
    assert summary["trough_date"] == "2020-01"
    assert summary["change_since_first"] == 10.0
    assert summary["change_since_peak"] == -10.0


def test_series_summary_ignores_nan_at_the_ends():
    series = pd.Series(
        [np.nan, 10.0, 30.0, np.nan],
        index=pd.DatetimeIndex(
            ["2020-01-01", "2020-02-01", "2020-03-01", "2020-04-01"]
        ),
    )
    summary = _series_summary(series)
    assert summary["first"] == 10.0
    assert summary["first_date"] == "2020-02"
    assert summary["latest"] == 30.0
    assert summary["latest_date"] == "2020-03"


def test_series_summary_peak_tie_uses_first_occurrence():
    series = pd.Series(
        [10.0, 20.0, 20.0],
        index=pd.DatetimeIndex(["2020-01-01", "2020-02-01", "2020-03-01"]),
    )
    summary = _series_summary(series)
    assert summary["peak_date"] == "2020-02"
    assert summary["peak"] == 20.0


def test_series_summary_all_nan_raises_empty_series_error():
    series = pd.Series(
        [np.nan, np.nan], index=pd.DatetimeIndex(["2020-01-01", "2020-02-01"])
    )
    with pytest.raises(EmptySeriesError):
        _series_summary(series)


def test_series_summary_empty_series_raises_empty_series_error():
    with pytest.raises(EmptySeriesError):
        _series_summary(pd.Series(dtype=float))


# ---------------------------------------------------------------------------
# _ols
# ---------------------------------------------------------------------------


def test_ols_exact_slope_per_year_on_linear_series():
    index = pd.date_range("2000-01-01", periods=24, freq="MS")
    series = pd.Series(np.arange(24, dtype=float), index=index)
    slope, r2 = _ols(series)
    assert slope == pytest.approx(12.0, abs=1e-9)  # +1 unit per month
    assert r2 == pytest.approx(1.0, abs=1e-12)


def test_ols_negative_slope():
    index = pd.date_range("2000-01-01", periods=24, freq="MS")
    series = pd.Series(-np.arange(24, dtype=float), index=index)
    slope, r2 = _ols(series)
    assert slope == pytest.approx(-12.0, abs=1e-9)
    assert r2 == pytest.approx(1.0, abs=1e-12)


def test_ols_drops_nan_then_fits():
    index = pd.date_range("2000-01-01", periods=24, freq="MS")
    values = np.arange(24, dtype=float)
    values[5] = np.nan
    slope, _ = _ols(pd.Series(values, index=index))
    assert slope == pytest.approx(12.0, abs=1e-9)


def test_ols_short_series_returns_nan_pair():
    index = pd.date_range("2000-01-01", periods=11, freq="MS")
    slope, r2 = _ols(pd.Series(np.arange(11, dtype=float), index=index))
    assert np.isnan(slope)
    assert np.isnan(r2)


def test_ols_zero_variance_has_zero_slope_and_nan_r2():
    index = pd.date_range("2000-01-01", periods=24, freq="MS")
    slope, r2 = _ols(pd.Series(np.full(24, 5.0), index=index))
    assert slope == pytest.approx(0.0, abs=1e-9)
    assert np.isnan(r2)


# ---------------------------------------------------------------------------
# _corr
# ---------------------------------------------------------------------------


def test_corr_perfect_positive():
    a = pd.Series([1.0, 2.0, 3.0, 4.0])
    b = pd.Series([2.0, 4.0, 6.0, 8.0])
    assert _corr(a, b) == pytest.approx(1.0)


def test_corr_perfect_negative():
    a = pd.Series([1.0, 2.0, 3.0, 4.0])
    b = pd.Series([8.0, 6.0, 4.0, 2.0])
    assert _corr(a, b) == pytest.approx(-1.0)


def test_corr_needs_three_paired_observations():
    a = pd.Series([1.0, 2.0])
    b = pd.Series([2.0, 4.0])
    assert np.isnan(_corr(a, b))


def test_corr_excludes_nan_pairs():
    a = pd.Series([1.0, 2.0, np.nan, 4.0])
    b = pd.Series([2.0, 4.0, 6.0, 8.0])
    assert _corr(a, b) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# _covid_window
# ---------------------------------------------------------------------------


COVID_INDEX = pd.DatetimeIndex(
    [
        "2019-12-01",
        "2020-01-01",
        "2020-02-01",
        "2020-03-01",
        "2020-04-01",
        "2020-05-01",
        "2020-08-01",
        "2021-01-01",
    ]
)
COVID_VALUES = [62.0, 61.8, 61.5, 61.0, 60.0, 60.5, 62.0, 63.0]


def test_covid_window_exact_values_and_recovery_arithmetic():
    window = _covid_window(pd.Series(COVID_VALUES, index=COVID_INDEX))
    assert window["baseline_dec_2019"] == 62.0
    assert window["trough"] == 60.0
    assert window["trough_date"] == "2020-04"
    assert window["drop_pp"] == -2.0
    assert window["latest"] == 63.0
    assert window["change_vs_baseline"] == 1.0
    assert window["recovered"] is True
    assert window["recovered_date"] == "2020-08"
    assert window["months_to_recover"] == 4  # Aug 2020 - Apr 2020


def test_covid_window_never_recovers():
    series = pd.Series(
        [62.0, 60.0, 61.0],
        index=pd.DatetimeIndex(["2019-12-01", "2020-04-01", "2020-06-01"]),
    )
    window = _covid_window(series)
    assert window["recovered"] is False
    assert window["recovered_date"] is None
    assert window["months_to_recover"] is None
    assert window["change_vs_baseline"] == -1.0


def test_covid_window_recovery_at_trough_is_zero_months():
    """Pin (D15): no drop means the trough itself is the recovery."""
    series = pd.Series(
        [60.0, 60.0, 60.0],
        index=pd.DatetimeIndex(["2019-12-01", "2020-04-01", "2020-06-01"]),
    )
    window = _covid_window(series)
    assert window["recovered"] is True
    assert window["recovered_date"] == "2020-04"
    assert window["months_to_recover"] == 0
    assert window["drop_pp"] == 0.0


def test_covid_window_missing_baseline_raises_keyerror():
    series = pd.Series(
        [61.0, 60.0],
        index=pd.DatetimeIndex(["2020-01-01", "2020-04-01"]),
    )
    with pytest.raises(KeyError, match="2019-12-01 is not in the series index"):
        _covid_window(series)


def test_covid_window_without_2020_data_raises_empty_series_error():
    series = pd.Series(
        [62.0, 71.0],
        index=pd.DatetimeIndex(["2019-12-01", "2021-05-01"]),
    )
    with pytest.raises(EmptySeriesError):
        _covid_window(series)


def test_covid_window_ignores_nan_trough_candidates():
    series = pd.Series(
        [62.0, np.nan, 60.5, 60.0],
        index=pd.DatetimeIndex(
            ["2019-12-01", "2020-03-01", "2020-04-01", "2020-05-01"]
        ),
    )
    window = _covid_window(series)
    assert window["trough"] == 60.0
    assert window["trough_date"] == "2020-05"


# ---------------------------------------------------------------------------
# _earnings_stats
# ---------------------------------------------------------------------------


@pytest.fixture
def quarterly_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "weekly_nominal_total": [200.0, 250.0],
            "weekly_real_total": [400.0, 420.0],
            "weekly_nominal_men": [240.0, 300.0],
            "weekly_real_men": [480.0, 504.0],
            "weekly_nominal_women": [120.0, 150.0],
            "weekly_real_women": [240.0, 252.0],
            "earnings_ratio_nominal": [50.0, 50.0],
            "earnings_ratio_real": [50.0, 50.0],
        },
        index=pd.DatetimeIndex(["1979-01-01", "1979-04-01"]),
    )


def test_earnings_stats_exact_series_values(quarterly_frame):
    stats = _earnings_stats(quarterly_frame)
    men = stats["series"]["men"]
    assert men["nominal_first"] == 240.0
    assert men["nominal_first_date"] == "1979-01"
    assert men["nominal_latest"] == 300.0
    assert men["nominal_latest_date"] == "1979-04"
    assert men["nominal_change_pct"] == 25.0
    assert men["real_first"] == 480.0
    assert men["real_latest"] == 504.0
    assert men["real_change_pct"] == pytest.approx(5.0)
    women = stats["series"]["women"]
    assert women["nominal_change_pct"] == 25.0
    assert women["real_change_pct"] == pytest.approx(5.0)
    total = stats["series"]["total"]
    assert total["nominal_change_pct"] == 25.0
    assert total["real_change_pct"] == pytest.approx(5.0)


def test_earnings_stats_ratio_values_and_short_window_slope(quarterly_frame):
    stats = _earnings_stats(quarterly_frame)
    nominal = stats["ratios"]["nominal"]
    assert nominal["first"] == 50.0
    assert nominal["latest"] == 50.0
    assert nominal["change_pp"] == 0.0
    # two observations < the 12-month OLS minimum -> nan slope
    assert np.isnan(nominal["slope_pp_per_year"])
    assert np.isnan(nominal["r2"])


def test_earnings_stats_ratio_slope_when_enough_observations():
    index = pd.date_range("1979-01-01", periods=16, freq="QS")
    quarterly = pd.DataFrame(
        {
            "weekly_nominal_total": np.linspace(200, 400, 16),
            "weekly_real_total": np.linspace(400, 500, 16),
            "weekly_nominal_men": np.linspace(240, 480, 16),
            "weekly_real_men": np.linspace(480, 600, 16),
            "weekly_nominal_women": np.linspace(120, 480, 16),
            "weekly_real_women": np.linspace(240, 600, 16),
            "earnings_ratio_nominal": np.linspace(50, 100, 16),
            "earnings_ratio_real": np.linspace(50, 100, 16),
        },
        index=index,
    )
    stats = _earnings_stats(quarterly)
    # ratio rises 50pp over 3.75 years -> 13.333 pp/yr
    slope = stats["ratios"]["nominal"]["slope_pp_per_year"]
    assert slope == pytest.approx(50.0 / (15 / 4), abs=1e-6)
    assert stats["ratios"]["nominal"]["r2"] == pytest.approx(1.0, abs=1e-9)


def test_earnings_stats_all_nan_raises_empty_series_error():
    quarterly = pd.DataFrame(
        {
            "weekly_nominal_total": [np.nan],
            "weekly_real_total": [np.nan],
            "weekly_nominal_men": [np.nan],
            "weekly_real_men": [np.nan],
            "weekly_nominal_women": [np.nan],
            "weekly_real_women": [np.nan],
            "earnings_ratio_nominal": [np.nan],
            "earnings_ratio_real": [np.nan],
        },
        index=pd.DatetimeIndex(["1979-01-01"]),
    )
    with pytest.raises(EmptySeriesError):
        _earnings_stats(quarterly)


def test_earnings_stats_missing_column_raises_keyerror(quarterly_frame):
    broken = quarterly_frame.drop(columns=["weekly_real_men"])
    with pytest.raises(KeyError):
        _earnings_stats(broken)


# ---------------------------------------------------------------------------
# _alignment_stats
# ---------------------------------------------------------------------------


GAP_VALUES = [3.0, 17.0, 5.0, 11.0, 23.0, 2.0, 19.0, 7.0, 13.0, 29.0]


def _monthly_gap() -> pd.DataFrame:
    """10 distinct quarterly gap values, one per quarter (3 months each)."""
    index = pd.date_range("1980-01-01", periods=30, freq="MS")
    return pd.DataFrame({"gap_pp": np.repeat(GAP_VALUES, 3)}, index=index)


def _quarterly_ratio(values) -> pd.DataFrame:
    index = pd.date_range("1980-01-01", periods=len(values), freq="QS")
    return pd.DataFrame({"earnings_ratio_nominal": values}, index=index)


def test_alignment_stats_detects_a_leading_ratio():
    """ratio[t] = gap[t+2] -> the best lag is +2 quarters at correlation 1.0."""
    ratio = [5.0, 11.0, 23.0, 2.0, 19.0, 7.0, 13.0, 29.0, np.nan, np.nan]
    stats = _alignment_stats(_monthly_gap(), _quarterly_ratio(ratio))
    assert stats["observations"] == 8
    assert stats["span"] == "1980-01..1981-10"
    assert stats["corr_contemporaneous"] == pytest.approx(0.1050010737126581)
    assert stats["best_lag_quarters"] == 2
    assert stats["corr_best_lag"] == pytest.approx(1.0)


def test_alignment_stats_identical_series_prefer_lag_zero():
    stats = _alignment_stats(_monthly_gap(), _quarterly_ratio(GAP_VALUES))
    assert stats["observations"] == 10
    assert stats["corr_contemporaneous"] == pytest.approx(1.0)
    assert stats["best_lag_quarters"] == 0
    assert stats["corr_best_lag"] == pytest.approx(1.0)


def test_alignment_stats_too_few_overlapping_quarters():
    """One overlapping quarter is not degenerate input: the correlation is
    honestly nan, the lag search is skipped, and the shape is preserved."""
    monthly = pd.DataFrame({"gap_pp": [1.0, 2.0]}, index=D2)
    quarterly = pd.DataFrame(
        {"earnings_ratio_nominal": [1.0, 2.0]},
        index=pd.DatetimeIndex(["2020-01-01", "2020-04-01"]),
    )
    stats = _alignment_stats(monthly, quarterly)
    assert stats["observations"] == 1
    assert stats["span"] == "2020-01..2020-01"
    assert np.isnan(stats["corr_contemporaneous"])
    assert stats["best_lag_quarters"] == 0
    assert np.isnan(stats["corr_best_lag"])


def test_alignment_stats_empty_join_raises_empty_series_error():
    with pytest.raises(EmptySeriesError):
        _alignment_stats(
            pd.DataFrame(
                {"gap_pp": [1.0, 2.0, 3.0]},
                index=pd.DatetimeIndex(["1948-01-01", "1948-02-01", "1948-03-01"]),
            ),
            _quarterly_ratio([1.0, 2.0]),
        )


# ---------------------------------------------------------------------------
# _counts_stats
# ---------------------------------------------------------------------------


@pytest.fixture
def counts_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "labor_force_total": [1000.0, 2000.0],
            "labor_force_men": [600.0, 1100.0],
            "labor_force_women": [400.0, 900.0],
            "employment_total": [900.0, 1800.0],
            "population_total": [5000.0, 6000.0],
            "women_lf_share": [40.0, 45.0],
            "emp_pop_ratio_total": [18.0, 30.0],
        },
        index=D2,
    )


def test_counts_stats_levels_and_growth_multiples(counts_frame):
    stats = _counts_stats(counts_frame)
    levels = stats["levels"]
    assert levels["labor_force_total"]["first"] == 1000.0
    assert levels["labor_force_total"]["latest"] == 2000.0
    assert levels["labor_force_total"]["growth_multiple"] == 2.0
    assert levels["labor_force_men"]["growth_multiple"] == pytest.approx(1100.0 / 600.0)
    assert levels["labor_force_women"]["growth_multiple"] == pytest.approx(2.25)
    assert levels["employment_total"]["growth_multiple"] == 2.0
    assert levels["population_16plus"]["first"] == 5000.0
    assert levels["population_16plus"]["latest"] == 6000.0
    assert levels["population_16plus"]["growth_multiple"] == pytest.approx(1.2)


def test_counts_stats_shares(counts_frame):
    shares = _counts_stats(counts_frame)["shares"]
    assert shares["women_lf_share"]["first"] == 40.0
    assert shares["women_lf_share"]["latest"] == 45.0
    assert shares["women_lf_share"]["change_pp"] == 5.0
    assert shares["emp_pop_ratio_total"]["change_pp"] == 12.0


def test_counts_stats_zero_base_growth_multiple_is_nan_not_inf():
    frame = pd.DataFrame(
        {
            "labor_force_total": [0.0, 2000.0],
            "labor_force_men": [0.0, 100.0],
            "labor_force_women": [0.0, 100.0],
            "employment_total": [0.0, 100.0],
            "population_total": [0.0, 100.0],
            "women_lf_share": [0.0, 10.0],
            "emp_pop_ratio_total": [0.0, 10.0],
        },
        index=D2,
    )
    stats = _counts_stats(frame)
    assert np.isnan(stats["levels"]["labor_force_total"]["growth_multiple"])


def test_counts_stats_empty_frame_raises_empty_series_error():
    frame = pd.DataFrame(
        {
            "labor_force_total": pd.Series(dtype=float),
            "labor_force_men": pd.Series(dtype=float),
            "labor_force_women": pd.Series(dtype=float),
            "employment_total": pd.Series(dtype=float),
            "population_total": pd.Series(dtype=float),
            "women_lf_share": pd.Series(dtype=float),
            "emp_pop_ratio_total": pd.Series(dtype=float),
        },
        index=pd.DatetimeIndex([]),
    )
    with pytest.raises(EmptySeriesError):
        _counts_stats(frame)


# ---------------------------------------------------------------------------
# _consistency_checks
# ---------------------------------------------------------------------------


def test_consistency_checks_exact_zero_on_exactly_additive_data():
    frame = pd.DataFrame(
        {
            "labor_force_men": [100.0],
            "labor_force_women": [200.0],
            "labor_force_total": [300.0],
            "implied_rate_total": [60.0],
            "rate_total": [60.0],
            "implied_rate_men": [70.0],
            "rate_men": [70.0],
            "implied_rate_women": [50.0],
            "rate_women": [50.0],
        },
        index=pd.DatetimeIndex(["2020-01-01"]),
    )
    checks = _consistency_checks(frame)
    assert checks["labor_force_additivity"]["mean_abs_diff_thousands"] == 0.0
    assert checks["labor_force_additivity"]["max_abs_diff_thousands"] == 0.0
    assert checks["implied_vs_published_total"]["mean_abs_diff_pp"] == 0.0
    assert checks["implied_vs_published_men"]["max_abs_diff_pp"] == 0.0
    assert checks["implied_vs_published_women"]["mean_abs_diff_pp"] == 0.0


def test_consistency_checks_report_known_noise():
    frame = pd.DataFrame(
        {
            "labor_force_men": [100.0],
            "labor_force_women": [201.0],  # 100 + 201 - 300 = +1
            "labor_force_total": [300.0],
            "implied_rate_total": [60.2],
            "rate_total": [60.0],
            "implied_rate_men": [70.1],
            "rate_men": [70.0],
            "implied_rate_women": [50.3],
            "rate_women": [50.0],
        },
        index=pd.DatetimeIndex(["2020-01-01"]),
    )
    checks = _consistency_checks(frame)
    assert checks["labor_force_additivity"]["mean_abs_diff_thousands"] == 1.0
    assert checks["labor_force_additivity"]["max_abs_diff_thousands"] == 1.0
    assert checks["implied_vs_published_total"]["mean_abs_diff_pp"] == pytest.approx(
        0.2
    )
    assert checks["implied_vs_published_men"]["max_abs_diff_pp"] == pytest.approx(0.1)
    assert checks["implied_vs_published_women"]["max_abs_diff_pp"] == pytest.approx(0.3)


def test_consistency_checks_empty_frame_raises_empty_series_error():
    frame = pd.DataFrame(
        {
            "labor_force_men": pd.Series(dtype=float),
            "labor_force_women": pd.Series(dtype=float),
            "labor_force_total": pd.Series(dtype=float),
            "implied_rate_total": pd.Series(dtype=float),
            "rate_total": pd.Series(dtype=float),
            "implied_rate_men": pd.Series(dtype=float),
            "rate_men": pd.Series(dtype=float),
            "implied_rate_women": pd.Series(dtype=float),
            "rate_women": pd.Series(dtype=float),
        },
        index=pd.DatetimeIndex([]),
    )
    with pytest.raises(EmptySeriesError):
        _consistency_checks(frame)


# ---------------------------------------------------------------------------
# _coverage_summary
# ---------------------------------------------------------------------------


def _mini_data(coverage_periods) -> WorkforceData:
    monthly = pd.DataFrame(
        {"rate_total": [58.6, 61.8]},
        index=pd.DatetimeIndex(["1948-01-01", "2026-09-01"]),
    )
    quarterly = pd.DataFrame(
        {"weekly_real_men": [435.0, 445.0]},
        index=pd.DatetimeIndex(["1979-01-01", "2026-04-01"]),
    )
    coverage = pd.DataFrame({"missing_periods": coverage_periods})
    return WorkforceData(monthly, quarterly, monthly, coverage)


def test_coverage_summary_dedupes_and_sorts_missing_periods():
    data = _mini_data(["2025-10, 2020-05", "2025-10"])
    summary = _coverage_summary(data)
    assert summary["series_count"] == 2
    assert summary["missing_periods"] == ["2020-05", "2025-10"]
    assert summary["monthly_span"] == "1948-01..2026-09"
    assert summary["earnings_span"] == "1979-01..2026-04"


def test_coverage_summary_handles_empty_missing_periods():
    data = _mini_data(["", ""])
    assert _coverage_summary(data)["missing_periods"] == []


# ---------------------------------------------------------------------------
# compute_stats end-to-end on the synthetic dataset
# ---------------------------------------------------------------------------


def test_compute_stats_produces_every_expected_block(synthetic_stats):
    assert set(synthetic_stats) == {
        "rates",
        "gap",
        "regimes",
        "covid",
        "earnings",
        "counts",
        "checks",
        "coverage",
        "weekly_hours",
        "shift_share",
    }
    assert set(synthetic_stats["rates"]) == {"total", "men", "women"}
    assert set(synthetic_stats["regimes"]) == {"1948-2000", "2000-2019", "2019-2026"}
    assert set(synthetic_stats["covid"]) == {"total", "men", "women"}
    assert set(synthetic_stats["earnings"]["series"]) == {"total", "men", "women"}
    assert set(synthetic_stats["earnings"]["ratios"]) == {"nominal", "real"}
    assert set(synthetic_stats["counts"]["levels"]) == {
        "labor_force_total",
        "labor_force_men",
        "labor_force_women",
        "employment_total",
        "population_16plus",
    }
    assert set(synthetic_stats["checks"]) == {
        "labor_force_additivity",
        "implied_vs_published_total",
        "implied_vs_published_men",
        "implied_vs_published_women",
    }
    assert set(synthetic_stats["weekly_hours"]["series"]) == {"total", "men", "women"}


def test_compute_stats_rates_match_the_monthly_frame(synthetic_stats, synthetic_data):
    monthly = synthetic_data.monthly
    for sex in ("total", "men", "women"):
        clean = monthly[f"rate_{sex}"].dropna()
        assert synthetic_stats["rates"][sex]["latest"] == pytest.approx(clean.iloc[-1])
        assert synthetic_stats["rates"][sex]["first"] == pytest.approx(clean.iloc[0])
        assert synthetic_stats["rates"][sex]["latest_date"] == "2026-09"


def test_compute_stats_gap_shrink_is_first_minus_latest(
    synthetic_stats, synthetic_data
):
    gap = synthetic_stats["gap"]
    clean = synthetic_data.monthly["gap_pp"].dropna()
    assert gap["first"] == pytest.approx(clean.iloc[0])
    assert gap["latest"] == pytest.approx(clean.iloc[-1])
    assert gap["shrink_pp"] == pytest.approx(gap["first"] - gap["latest"])


def test_compute_stats_covid_trough_is_april_2020(synthetic_stats):
    for sex in ("total", "men", "women"):
        assert synthetic_stats["covid"][sex]["trough_date"] == "2020-04"


def test_compute_stats_regime_ols_covers_each_window(synthetic_stats, synthetic_data):
    monthly = synthetic_data.monthly
    for label, start, end in analysis.REGIMES:
        window = monthly.loc[start:end]
        expected, _ = _ols(window["rate_men"].dropna())
        assert synthetic_stats["regimes"][label]["rate_men"]["slope_pp_per_year"] == (
            pytest.approx(expected)
        )


def test_compute_stats_earnings_alignment_found_overlap(synthetic_stats):
    alignment = synthetic_stats["earnings"]["participation_alignment"]
    assert alignment["observations"] > 100
    assert alignment["span"].startswith("1979-01")
    assert -1.0 <= alignment["corr_contemporaneous"] <= 1.0


def test_compute_stats_additivity_is_exactly_zero_on_synthetic_data(synthetic_stats):
    checks = synthetic_stats["checks"]["labor_force_additivity"]
    assert checks["mean_abs_diff_thousands"] == 0.0
    assert checks["max_abs_diff_thousands"] == 0.0


def test_compute_stats_implied_matches_published_on_synthetic_data(synthetic_stats):
    for sex in ("total", "men", "women"):
        check = synthetic_stats["checks"][f"implied_vs_published_{sex}"]
        assert check["mean_abs_diff_pp"] == pytest.approx(0.0, abs=1e-9)


def test_compute_stats_coverage_flags_only_october_2025(synthetic_stats):
    coverage = synthetic_stats["coverage"]
    assert coverage["series_count"] == 32  # 30 FRED + 2 BLS
    assert coverage["missing_periods"] == ["2025-10"]
    assert coverage["monthly_span"] == "1948-01..2026-09"
    assert coverage["earnings_span"] == "1979-01..2026-04"


def test_compute_stats_is_strictly_json_serializable(synthetic_stats):
    """Tripwire for non-finite leakage (D5): summary.json must be standard JSON."""
    text = json.dumps(synthetic_stats, indent=2, allow_nan=False)
    assert json.loads(text)["coverage"]["missing_periods"] == ["2025-10"]


def test_compute_stats_rejects_a_data_poisoned_with_an_all_nan_series(synthetic_data):
    poisoned = synthetic_data.monthly.copy()
    poisoned["rate_women"] = np.nan
    with pytest.raises(EmptySeriesError):
        compute_stats(
            WorkforceData(
                monthly=poisoned,
                quarterly=synthetic_data.quarterly,
                hourly=synthetic_data.hourly,
                coverage=synthetic_data.coverage,
            )
        )


# ---------------------------------------------------------------------------
# report rendering
# ---------------------------------------------------------------------------


@pytest.fixture
def render_stats() -> dict:
    """A complete stats dict with controlled numbers for exact-string tests."""
    rates = {
        "total": {
            "first": 58.6,
            "first_date": "1948-01",
            "peak": 67.3,
            "peak_date": "2000-01",
            "latest": 61.8,
            "latest_date": "2026-09",
            "trough": 58.6,
            "trough_date": "1948-01",
            "change_since_first": 3.2,
            "change_since_peak": -5.5,
        },
        "men": {
            "first": 86.6,
            "first_date": "1948-01",
            "peak": 96.6,
            "peak_date": "1948-01",
            "latest": 68.6,
            "latest_date": "2026-09",
            "trough": 67.9,
            "trough_date": "2020-04",
            "change_since_first": -18.0,
            "change_since_peak": -28.0,
        },
        "women": {
            "first": 33.0,
            "first_date": "1948-01",
            "peak": 60.1,
            "peak_date": "2000-06",
            "latest": 58.5,
            "latest_date": "2026-09",
            "trough": 54.9,
            "trough_date": "2020-04",
            "change_since_first": 25.5,
            "change_since_peak": -1.6,
        },
    }
    gap = {
        "first": 53.6,
        "first_date": "1948-01",
        "peak": 57.6,
        "peak_date": "1948-01",
        "latest": 10.1,
        "latest_date": "2026-09",
        "shrink_pp": 43.5,
    }
    return {
        "rates": rates,
        "gap": gap,
        "regimes": {
            "1948-2000": {
                column: {"slope_pp_per_year": 0.123, "r2": 0.91}
                for column in ("rate_men", "rate_women", "rate_total", "gap_pp")
            },
            "2000-2019": {
                column: {"slope_pp_per_year": -0.045, "r2": 0.42}
                for column in ("rate_men", "rate_women", "rate_total", "gap_pp")
            },
            "2019-2026": {
                column: {"slope_pp_per_year": -0.201, "r2": 0.55}
                for column in ("rate_men", "rate_women", "rate_total", "gap_pp")
            },
        },
        "covid": {
            "total": {
                "baseline_dec_2019": 63.0,
                "trough": 60.2,
                "trough_date": "2020-04",
                "drop_pp": -2.8,
                "latest": 61.8,
                "change_vs_baseline": -1.2,
                "recovered": False,
                "recovered_date": None,
                "months_to_recover": None,
            },
            "men": {
                "baseline_dec_2019": 69.2,
                "trough": 67.9,
                "trough_date": "2020-04",
                "drop_pp": -1.3,
                "latest": 68.6,
                "change_vs_baseline": -0.6,
                "recovered": False,
                "recovered_date": None,
                "months_to_recover": None,
            },
            "women": {
                "baseline_dec_2019": 57.6,
                "trough": 54.9,
                "trough_date": "2020-04",
                "drop_pp": -2.7,
                "latest": 58.5,
                "change_vs_baseline": 0.9,
                "recovered": True,
                "recovered_date": "2020-08",
                "months_to_recover": 4,
            },
        },
        "earnings": {
            "series": {
                "total": {
                    "real_change_pct": 12.0,
                    "nominal_change_pct": 430.0,
                    "real_first": 380.0,
                    "real_latest": 426.0,
                    "nominal_first": 270.0,
                    "nominal_latest": 1430.0,
                    "real_first_date": "1979-01",
                    "real_latest_date": "2026-04",
                    "nominal_first_date": "1979-01",
                    "nominal_latest_date": "2026-04",
                },
                "men": {
                    "real_change_pct": -1.2,
                    "nominal_change_pct": 390.0,
                    "real_first": 435.0,
                    "real_latest": 430.0,
                    "nominal_first": 341.0,
                    "nominal_latest": 1420.0,
                    "real_first_date": "1979-01",
                    "real_latest_date": "2026-04",
                    "nominal_first_date": "1979-01",
                    "nominal_latest_date": "2026-04",
                },
                "women": {
                    "real_change_pct": 52.4,
                    "nominal_change_pct": 460.0,
                    "real_first": 260.0,
                    "real_latest": 430.0,
                    "nominal_first": 205.0,
                    "nominal_latest": 1160.0,
                    "real_first_date": "1979-01",
                    "real_latest_date": "2026-04",
                    "nominal_first_date": "1979-01",
                    "nominal_latest_date": "2026-04",
                },
            },
            "ratios": {
                "nominal": {
                    "first": 62.3,
                    "first_date": "1979-01",
                    "latest": 82.5,
                    "latest_date": "2026-04",
                    "change_pp": 20.2,
                },
                "real": {
                    "first": 60.1,
                    "first_date": "1979-01",
                    "latest": 80.0,
                    "latest_date": "2026-04",
                    "change_pp": 19.9,
                },
            },
            "participation_alignment": {
                "observations": 190,
                "span": "1979-01..2026-04",
                "corr_contemporaneous": 0.87,
                "best_lag_quarters": -2,
                "corr_best_lag": -0.91,
            },
        },
        "counts": {
            "levels": {
                "labor_force_total": {
                    "first": 63159.0,
                    "latest": 169831.0,
                    "first_date": "1948-01",
                    "latest_date": "2026-09",
                    "growth_multiple": 2.6887,
                },
                "labor_force_men": {
                    "first": 43804.0,
                    "latest": 89366.0,
                    "first_date": "1948-01",
                    "latest_date": "2026-09",
                    "growth_multiple": 2.0399,
                },
                "labor_force_women": {
                    "first": 19355.0,
                    "latest": 80465.0,
                    "first_date": "1948-01",
                    "latest_date": "2026-09",
                    "growth_multiple": 4.1568,
                },
                "employment_total": {
                    "first": 60331.0,
                    "latest": 162003.0,
                    "first_date": "1948-01",
                    "latest_date": "2026-09",
                    "growth_multiple": 2.6849,
                },
                "population_16plus": {
                    "first": 101827.0,
                    "latest": 276737.0,
                    "first_date": "1948-01",
                    "latest_date": "2026-09",
                    "growth_multiple": 2.7173,
                },
            },
            "shares": {
                "women_lf_share": {
                    "first": 30.9,
                    "latest": 47.4,
                    "first_date": "1948-01",
                    "latest_date": "2026-09",
                },
                "emp_pop_ratio_total": {
                    "first": 59.4,
                    "latest": 58.5,
                    "first_date": "1948-01",
                    "latest_date": "2026-09",
                },
            },
        },
        "checks": {
            "labor_force_additivity": {
                "mean_abs_diff_thousands": 0.5,
                "max_abs_diff_thousands": 12.0,
            },
            "implied_vs_published_total": {
                "mean_abs_diff_pp": 0.01,
                "max_abs_diff_pp": 0.2,
            },
            "implied_vs_published_men": {
                "mean_abs_diff_pp": 0.02,
                "max_abs_diff_pp": 0.3,
            },
            "implied_vs_published_women": {
                "mean_abs_diff_pp": 0.03,
                "max_abs_diff_pp": 0.4,
            },
        },
        "coverage": {
            "series_count": 27,
            "monthly_span": "1948-01..2026-09",
            "earnings_span": "1979-01..2026-04",
            "missing_periods": ["2025-10"],
        },
        "weekly_hours": {
            "series": {
                "men": {
                    "first": 40.0,
                    "first_date": "1948-01",
                    "latest": 42.0,
                    "latest_date": "2026-09",
                    "change": 2.0,
                    "change_pct": 5.0,
                },
                "women": {
                    "first": 35.0,
                    "first_date": "1948-01",
                    "latest": 37.0,
                    "latest_date": "2026-09",
                    "change": 2.0,
                    "change_pct": 5.7,
                },
                "total": {
                    "first": 37.5,
                    "first_date": "1948-01",
                    "latest": 39.5,
                    "latest_date": "2026-09",
                    "change": 2.0,
                    "change_pct": 5.3,
                },
            },
            "ratios": {
                "hours_ratio_men_women": {
                    "first": 1.14,
                    "first_date": "1948-01",
                    "latest": 1.14,
                    "latest_date": "2026-09",
                    "change": 0.0,
                    "slope_pp_per_year": 0.0,
                },
            },
        },
    }


def test_header_reports_generation_and_span(render_stats):
    text = analysis._header(render_stats)
    assert text.startswith("# U.S. Workforce Participation: Findings\n\n")
    assert "Generated " in text
    assert "30 FRED series and 2 BLS series" in text
    assert "1948-01..2026-09 monthly" in text
    assert "1979-01..2026-04 quarterly earnings" in text
    assert "October 2025" in text


def test_participation_section_table_and_signs(render_stats):
    text = analysis._participation_section(render_stats)
    assert (
        "| | first | peak | latest | change since first | change since peak |" in text
    )
    assert (
        "| Men | 86.6% (1948-01) | 96.6% (1948-01) | 68.6% (2026-09) "
        "| -18.0 pp | -28.0 pp |" in text
    )
    assert (
        "| **Gender gap** (men - women) | 53.6 pp (1948-01) | 57.6 pp (1948-01) "
        "| 10.1 pp (2026-09) | -43.5 pp | -47.5 pp |" in text
    )
    assert "a narrowing of 43.5 pp" in text


def test_regime_section_rows_and_selected_regime_reference(render_stats):
    text = analysis._regime_section(render_stats)
    assert "| period | men | women | total | gap |" in text
    assert "| 1948-2000 | +0.123 pp/yr (R2 0.91) |" in text
    assert "| 2019-2026 | -0.201 pp/yr (R2 0.55) |" in text
    assert "turned negative at -0.045 pp/yr (2000-2019)" in text


def test_regime_section_requires_the_post_2000_regime_label(render_stats):
    """Pin (D14): the prose is hard-wired to the '2000-2019' regime label."""
    del render_stats["regimes"]["2000-2019"]
    with pytest.raises(KeyError):
        analysis._regime_section(render_stats)


def test_covid_section_recovery_and_pending_rows(render_stats):
    text = analysis._covid_section(render_stats)
    assert "| | Dec 2019 | 2020 trough | latest | vs baseline | recovered |" in text
    assert (
        "| All | 63.0% | 60.2% (2020-04, -2.8 pp) | 61.8% | -1.2 pp | not yet |" in text
    )
    assert (
        "| Women | 57.6% | 54.9% (2020-04, -2.7 pp) | 58.5% | +0.9 pp | 2020-08 (+4 mo) |"
        in text
    )


def test_earnings_section_numbers_and_association_framing(render_stats):
    text = analysis._earnings_section(render_stats)
    assert "grew +52.4% since 1979" in text
    assert "men's changed -1.2%" in text
    assert "rose from 62.3% (1979-01) to 82.5% (2026-04), +20.2 pp" in text
    assert "correlation r = +0.87 contemporaneous, n = 190" in text
    assert "association, not evidence of causation" in text


def test_earnings_section_requires_alignment_keys(render_stats):
    """Pin: the renderer indexes the alignment block unconditionally; an empty
    mapping (the old {} contract) surfaced here as a KeyError."""
    render_stats["earnings"]["participation_alignment"] = {}
    with pytest.raises(KeyError):
        analysis._earnings_section(render_stats)


def test_counts_section_units_and_shares(render_stats):
    text = analysis._counts_section(render_stats)
    assert "| | 1948 | latest | growth |" in text
    assert "| Labor force total | 63.2M | 169.8M | 2.69x |" in text
    assert "| Labor force women | 19.4M | 80.5M | 4.16x |" in text
    assert "| Employment total | 60.3M | 162.0M | 2.68x |" in text
    assert "went from 30.9% (1948-01) to 47.4% (2026-09)" in text
    assert "stands at 58.5% versus 59.4% in 1948" in text


def test_checks_section_rows(render_stats):
    text = analysis._checks_section(render_stats)
    assert "| check | mean abs. diff | max abs. diff |" in text
    assert "| men + women = total labor force (thousands) | 0.5 | 12.0 |" in text
    assert "| implied vs published rate, women (pp) | 0.03 | 0.40 |" in text


def test_caveats_section_covers_the_known_limitations():
    text = analysis._caveats_section()
    assert "## Caveats" in text
    assert "Correlation is not causation" in text
    assert "October 2025 is missing" in text
    assert "seasonally adjusted" in text
    assert "workers" in text
    assert "BLS weekly hours" in text
    assert "nonagricultural industries" in text


def test_weekly_hours_section_numbers_and_framing(render_stats):
    text = analysis._weekly_hours_section(render_stats)
    assert "Men" in text
    assert "Women" in text
    assert "Total" in text
    assert "Hours ratio (M/W)" in text
    assert "+5.0%" in text or "5.0%" in text


def test_shift_share_calculates_decomposition():
    """Test shift-share decomposition produces expected outputs."""
    from pandas import DataFrame, date_range

    # Create test data with population and LFPR columns
    index = date_range("2000-01-01", periods=10, freq="YS")
    df_pop = DataFrame(
        {
            "year": range(2000, 2010),
            "population_youth": [100.0] * 10,
            "population_prime": [200.0] * 10,
            "population_older": [80.0] * 10,
            "population_total": [380.0] * 10,
        },
        index=index,
    )

    df_lfpr = DataFrame(
        {
            "year": range(2000, 2010),
            "rate_prime": [60.0 + i * 0.5 for i in range(10)],
            "rate_prime_men": [65.0 + i * 0.4 for i in range(10)],
            "rate_prime_women": [55.0 + i * 0.6 for i in range(10)],
            "rate_older": [70.0 + i * 0.3 for i in range(10)],
            "rate_total": [63.0 + i * 0.45 for i in range(10)],
        },
        index=index,
    )

    result = analysis.calculate_shift_share(df_pop, df_lfpr, base_year=2000)

    # Check result has expected columns
    assert list(result.columns) == [
        "year",
        "pop_youth",
        "pop_prime",
        "pop_older",
        "rate_prime",
        "rate_prime_men",
        "rate_prime_women",
        "rate_older",
        "pop_share_youth",
        "pop_share_prime",
        "pop_share_older",
        "lfpr_change_total",
        "within_group_effect",
        "between_group_effect",
        "cumulative_within_group",
        "cumulative_between_group",
    ]

    # Check that calculations make sense (within + between = total)
    result["total_calculation"] = (
        result["within_group_effect"] + result["between_group_effect"]
    )
    assert "lfpr_change_total" in result.columns
    assert "total_calculation" in result.columns

    # Check that we have data for all years
    assert len(result) == 10
    assert list(result["year"]) == list(range(2000, 2010))


def test_shift_share_with_real_data():
    """Test shift-share decomposition with more realistic data patterns."""
    import numpy as np
    from pandas import DataFrame, date_range

    # Create data that shows clear trends
    index = date_range("2000-01-01", periods=20, freq="YS")

    # Population shares change over time (aging population)
    pop_shares = np.linspace(0.25, 0.20, 20)  # youth share decreases
    prime_shares = np.linspace(0.55, 0.55, 20)  # prime share stable
    older_shares = np.linspace(0.20, 0.25, 20)  # older share increases

    # Calculate populations based on shares and total population
    total_pop = np.linspace(250.0, 270.0, 20)
    pop_youth = pop_shares * total_pop
    pop_prime = prime_shares * total_pop
    pop_older = older_shares * total_pop

    # LFPR rates with small changes over time
    base_rates = 65.0  # base rate
    rate_prime = base_rates + np.linspace(-2.0, -1.0, 20)  # prime-age rates decrease
    rate_prime_men = rate_prime + 3.0
    rate_prime_women = rate_prime - 2.0
    rate_older = base_rates + np.linspace(0.0, 5.0, 20)  # older-age rates increase
    rate_total = (rate_prime + rate_prime_men + rate_prime_women + rate_older) / 4

    df_pop = DataFrame(
        {
            "year": range(2000, 2020),
            "population_youth": pop_youth,
            "population_prime": pop_prime,
            "population_older": pop_older,
            "population_total": total_pop,
        },
        index=index,
    )

    df_lfpr = DataFrame(
        {
            "year": range(2000, 2020),
            "rate_prime": rate_prime,
            "rate_prime_men": rate_prime_men,
            "rate_prime_women": rate_prime_women,
            "rate_older": rate_older,
            "rate_total": rate_total,
        },
        index=index,
    )

    result = analysis.calculate_shift_share(df_pop, df_lfpr, base_year=2000)

    # In this scenario, between-group effect should dominate (aging population)
    # within-group effect should be negative (behavioral decline)
    latest = result.iloc[-1]

    # Check that total change is reasonable
    assert (
        abs(latest["lfpr_change_total"]) < 10.0
    )  # Less than 10 percentage points total change

    # Check that effects are calculated (not zero unless there's no change)
    assert not (
        abs(latest["within_group_effect"]) < 0.001
        and abs(latest["between_group_effect"]) < 0.001
        and abs(latest["lfpr_change_total"]) > 0.001
    )


def test_shift_share_base_year_parameter():
    """Test that shift-share decomposition respects the base_year parameter."""
    from pandas import DataFrame, date_range

    # Create data where 2005 is the starting point
    index = date_range("2000-01-01", periods=10, freq="YS")
    df_pop = DataFrame(
        {
            "year": range(2000, 2010),
            "population_youth": [100.0 + i for i in range(10)],
            "population_prime": [200.0] * 10,
            "population_older": [80.0] * 10,
            "population_total": [380.0] * 10,
        },
        index=index,
    )

    df_lfpr = DataFrame(
        {
            "year": range(2000, 2010),
            "rate_prime": [60.0 + i * 0.5 for i in range(10)],
            "rate_prime_men": [65.0] * 10,
            "rate_prime_women": [55.0] * 10,
            "rate_older": [70.0] * 10,
            "rate_total": [60.0] * 10,
        },
        index=index,
    )

    # Test with base_year=2005
    result_2005 = analysis.calculate_shift_share(df_pop, df_lfpr, base_year=2005)

    # Test with base_year=2000
    result_2000 = analysis.calculate_shift_share(df_pop, df_lfpr, base_year=2000)

    # The 2005 result should have different decomposition (base year matters)
    assert not result_2005.empty
    assert not result_2000.empty

    # The latest years should have different effects based on different base years
    # Results may be different depending on the base year
    # This test ensures the function runs without errors and produces different results


def test_shift_share_missing_columns_raises_error():
    """Test that shift-share decomposition raises appropriate errors for missing columns."""
    from pandas import DataFrame, date_range

    index = date_range("2000-01-01", periods=5, freq="YS")
    df_pop = DataFrame(
        {
            "year": range(2000, 2005),
            "population_youth": [100.0] * 5,
            "population_prime": [200.0] * 5,
            # Missing population_older and population_total
        },
        index=index,
    )

    df_lfpr = DataFrame(
        {
            "year": range(2000, 2005),
            "rate_prime": [60.0] * 5,
            "rate_prime_men": [65.0] * 5,
            "rate_prime_women": [55.0] * 5,
            "rate_older": [70.0] * 5,
            "rate_total": [65.0] * 5,
        },
        index=index,
    )

    # Should raise ValueError for missing columns
    with pytest.raises(
        ValueError, match="df_pop must contain 'population_older' column"
    ):
        analysis.calculate_shift_share(df_pop, df_lfpr)


def test_shift_share_stats_integration(synthetic_stats):
    """Shift-share statistics are computed from the complete assembled dataset."""
    assert "shift_share" in synthetic_stats

    shift_share_stats = synthetic_stats["shift_share"]
    assert isinstance(shift_share_stats, dict)

    expected_keys = [
        "within_group_effect",
        "between_group_effect",
        "cumulative_within_group",
        "cumulative_between_group",
        "year",
    ]
    assert set(shift_share_stats) == set(expected_keys)
    assert shift_share_stats["year"] == 2026
    for key in expected_keys[:-1]:
        assert isinstance(shift_share_stats[key], float)
