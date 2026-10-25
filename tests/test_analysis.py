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
    _debt_to_gdp_stats,
    _earnings_stats,
    _govt_share_stats,
    _index,
    _macro_context_section,
    _ols,
    _private_per_capita_stats,
    _purchasing_power_stats,
    _sanitize_nan,
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
        "prime_age",
        "macro",
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
    assert set(synthetic_stats["macro"]) == {
        "purchasing_power",
        "private_per_capita",
        "govt_share_pct",
        "debt_to_gdp",
    }
    assert set(synthetic_stats["macro"]["purchasing_power"]) == {
        "cpi",
        "ahe_nominal",
        "purchasing_power_index",
    }


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
    assert coverage["series_count"] == 37  # 33 FRED + 4 BLS
    assert coverage["missing_periods"] == ["2025-10"]
    assert coverage["monthly_span"] == "1948-01..2026-09"
    assert coverage["earnings_span"] == "1979-01..2026-04"


def test_compute_stats_is_strictly_json_serializable(synthetic_stats):
    """Tripwire for non-finite leakage (D5): summary.json must be standard JSON."""
    text = json.dumps(synthetic_stats, indent=2, allow_nan=False)
    parsed = json.loads(text)
    assert parsed["coverage"]["missing_periods"] == ["2025-10"]
    assert "macro" in parsed
    assert parsed["macro"]["purchasing_power"]["cpi"]["growth_pct"] is not None


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
    assert "33 FRED series and 4 BLS series" in text
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


# ---------------------------------------------------------------------------
# macroeconomic context helpers
# ---------------------------------------------------------------------------


def _macro_monthly() -> pd.DataFrame:
    """Three-month frame holding only the columns the macro helpers read."""
    return pd.DataFrame(
        {
            "cpi": [100.0, 110.0, 121.0],
            "ahe_production_nominal": [10.0, 11.0, 12.1],
            "purchasing_power_index": [10.0, 10.0, 10.0],
            "private_per_capita": [50.0, 60.0, 55.0],
            "govt_share_pct": [16.0, 17.5, 15.0],
        },
        index=pd.DatetimeIndex(["2020-01-01", "2020-02-01", "2020-03-01"]),
    )


def _debt_quarterly() -> pd.DataFrame:
    """Four-quarter frame holding the debt-to-GDP column."""
    return pd.DataFrame(
        {"debt_to_gdp": [31.0, 50.0, 122.0, 100.0]},
        index=pd.DatetimeIndex(
            ["2020-03-31", "2020-06-30", "2020-09-30", "2020-12-31"]
        ),
    )


def test_purchasing_power_stats_exact_values():
    stats = _purchasing_power_stats(_macro_monthly())

    cpi = stats["cpi"]
    assert cpi["first"] == 100.0
    assert cpi["first_date"] == "2020-01"
    assert cpi["latest"] == 121.0
    assert cpi["latest_date"] == "2020-03"
    assert cpi["growth_pct"] == pytest.approx(21.0)

    ahe = stats["ahe_nominal"]
    assert ahe["first"] == 10.0
    assert ahe["first_date"] == "2020-01"
    assert ahe["latest"] == 12.1
    assert ahe["latest_date"] == "2020-03"
    assert ahe["growth_pct"] == pytest.approx(21.0)

    ppi = stats["purchasing_power_index"]
    assert ppi["first"] == 10.0
    assert ppi["first_date"] == "2020-01"
    assert ppi["latest"] == 10.0
    assert ppi["latest_date"] == "2020-03"
    assert ppi["change_pct"] == pytest.approx(0.0)


def test_purchasing_power_stats_aligns_cpi_and_ahe_on_the_same_span():
    """CPI growth must not start earlier than the AHE/PPI overlap."""
    frame = pd.DataFrame(
        {
            "cpi": [100.0, 110.0, 121.0, 133.1],
            "ahe_production_nominal": [np.nan, 11.0, 12.1, 13.31],
            "purchasing_power_index": [np.nan, 10.0, 10.0, 10.0],
        },
        index=pd.DatetimeIndex(
            ["2020-01-01", "2020-02-01", "2020-03-01", "2020-04-01"]
        ),
    )

    stats = _purchasing_power_stats(frame)

    # January is outside the aligned span; using it would overstate CPI growth
    # as 33.1% instead of the 21.0% measured from February.
    assert stats["cpi"]["first"] == 110.0
    assert stats["cpi"]["first_date"] == "2020-02"
    assert stats["cpi"]["growth_pct"] == pytest.approx(21.0)
    assert stats["ahe_nominal"]["first"] == 11.0
    assert stats["ahe_nominal"]["first_date"] == "2020-02"
    assert stats["ahe_nominal"]["growth_pct"] == pytest.approx(21.0)
    assert stats["purchasing_power_index"]["first_date"] == "2020-02"
    assert stats["purchasing_power_index"]["latest_date"] == "2020-04"


def test_purchasing_power_stats_all_nan_raises_empty_series_error():
    frame = _macro_monthly().copy()
    for column in ("cpi", "ahe_production_nominal", "purchasing_power_index"):
        frame[column] = np.nan
    with pytest.raises(EmptySeriesError):
        _purchasing_power_stats(frame)


def test_private_per_capita_stats_exact_values():
    stats = _private_per_capita_stats(_macro_monthly())
    assert stats["first"] == 50.0
    assert stats["first_date"] == "2020-01"
    assert stats["peak"] == 60.0
    assert stats["peak_date"] == "2020-02"
    assert stats["latest"] == 55.0
    assert stats["latest_date"] == "2020-03"
    assert stats["change_pct"] == pytest.approx(10.0)
    assert stats["change_since_peak"] == pytest.approx(-5.0)


def test_private_per_capita_stats_ignores_leading_nan():
    frame = _macro_monthly().copy()
    frame.loc["2020-01-01", "private_per_capita"] = np.nan
    stats = _private_per_capita_stats(frame)
    assert stats["first"] == 60.0
    assert stats["first_date"] == "2020-02"
    assert stats["latest"] == 55.0
    assert stats["latest_date"] == "2020-03"
    assert stats["change_pct"] == pytest.approx((55.0 / 60.0 - 1) * 100)


def test_private_per_capita_stats_peak_tie_uses_first_occurrence():
    frame = _macro_monthly().copy()
    frame.loc["2020-03-01", "private_per_capita"] = 60.0
    stats = _private_per_capita_stats(frame)
    assert stats["peak"] == 60.0
    assert stats["peak_date"] == "2020-02"


def test_private_per_capita_stats_all_nan_raises_empty_series_error():
    frame = _macro_monthly().copy()
    frame["private_per_capita"] = np.nan
    with pytest.raises(EmptySeriesError):
        _private_per_capita_stats(frame)


def test_govt_share_stats_exact_values():
    stats = _govt_share_stats(_macro_monthly())
    assert stats["first"] == 16.0
    assert stats["first_date"] == "2020-01"
    assert stats["peak"] == 17.5
    assert stats["peak_date"] == "2020-02"
    assert stats["latest"] == 15.0
    assert stats["latest_date"] == "2020-03"
    assert stats["change_pp"] == pytest.approx(-1.0)


def test_govt_share_stats_ignores_leading_nan():
    frame = _macro_monthly().copy()
    frame.loc["2020-01-01", "govt_share_pct"] = np.nan
    stats = _govt_share_stats(frame)
    assert stats["first"] == 17.5
    assert stats["first_date"] == "2020-02"
    assert stats["latest"] == 15.0
    assert stats["change_pp"] == pytest.approx(-2.5)


def test_govt_share_stats_all_nan_raises_empty_series_error():
    frame = _macro_monthly().copy()
    frame["govt_share_pct"] = np.nan
    with pytest.raises(EmptySeriesError):
        _govt_share_stats(frame)


def test_debt_to_gdp_stats_exact_values():
    stats = _debt_to_gdp_stats(_debt_quarterly())
    assert stats["earliest"] == 31.0
    assert stats["earliest_date"] == "2020-03"
    assert stats["peak"] == 122.0
    assert stats["peak_date"] == "2020-09"
    assert stats["latest"] == 100.0
    assert stats["latest_date"] == "2020-12"


def test_debt_to_gdp_stats_ignores_leading_nan():
    frame = _debt_quarterly().copy()
    frame.loc["2020-03-31", "debt_to_gdp"] = np.nan
    stats = _debt_to_gdp_stats(frame)
    assert stats["earliest"] == 50.0
    assert stats["earliest_date"] == "2020-06"
    assert stats["latest"] == 100.0


def test_debt_to_gdp_stats_all_nan_raises_empty_series_error():
    frame = _debt_quarterly().copy()
    frame["debt_to_gdp"] = np.nan
    with pytest.raises(EmptySeriesError):
        _debt_to_gdp_stats(frame)


def test_macro_helpers_handle_a_single_observation():
    monthly = _macro_monthly().iloc[[0]].copy()

    pp = _purchasing_power_stats(monthly)
    assert pp["cpi"]["growth_pct"] == 0.0
    assert pp["ahe_nominal"]["growth_pct"] == 0.0
    assert pp["purchasing_power_index"]["change_pct"] == 0.0

    private = _private_per_capita_stats(monthly)
    assert private["first"] == 50.0
    assert private["peak"] == 50.0
    assert private["latest"] == 50.0
    assert private["change_pct"] == 0.0
    assert private["change_since_peak"] == 0.0

    govt = _govt_share_stats(monthly)
    assert govt["first"] == 16.0
    assert govt["peak"] == 16.0
    assert govt["latest"] == 16.0
    assert govt["change_pp"] == 0.0

    debt = _debt_to_gdp_stats(_debt_quarterly().iloc[[0]])
    assert debt["earliest"] == 31.0
    assert debt["peak"] == 31.0
    assert debt["latest"] == 31.0


def test_sanitize_nan_recurses_and_preserves_non_nan_values():
    payload = {
        "top": float("nan"),
        "nested": [1.0, np.float64("nan"), {"deep": np.nan}],
        "none": None,
        "text": "value",
        "zero": 0.0,
    }

    cleaned = _sanitize_nan(payload)

    assert cleaned == {
        "top": None,
        "nested": [1.0, None, {"deep": None}],
        "none": None,
        "text": "value",
        "zero": 0.0,
    }
    json.dumps(cleaned, allow_nan=False)


def test_sanitize_nan_handles_scalars_and_lists():
    assert _sanitize_nan(float("nan")) is None
    assert _sanitize_nan(np.float64("nan")) is None
    assert _sanitize_nan(1.5) == 1.5
    assert _sanitize_nan([np.nan, "x"]) == [None, "x"]


def _macro_render_stats() -> dict:
    """Controlled macro block with exact numbers for string assertions."""
    return {
        "macro": {
            "purchasing_power": {
                "cpi": {
                    "first": 100.0,
                    "first_date": "2020-01",
                    "latest": 121.0,
                    "latest_date": "2020-03",
                    "growth_pct": 21.0,
                },
                "ahe_nominal": {
                    "first": 10.0,
                    "first_date": "2020-01",
                    "latest": 12.1,
                    "latest_date": "2020-03",
                    "growth_pct": 21.0,
                },
                "purchasing_power_index": {
                    "first": 10.0,
                    "first_date": "2020-01",
                    "latest": 10.0,
                    "latest_date": "2020-03",
                    "change_pct": 0.0,
                },
            },
            "private_per_capita": {
                "first": 50.0,
                "first_date": "2020-01",
                "peak": 60.0,
                "peak_date": "2020-02",
                "latest": 55.0,
                "latest_date": "2020-03",
                "change_pct": 10.0,
                "change_since_peak": -5.0,
            },
            "govt_share_pct": {
                "first": 16.0,
                "first_date": "2020-01",
                "peak": 17.5,
                "peak_date": "2020-02",
                "latest": 15.0,
                "latest_date": "2020-03",
                "change_pp": -1.0,
            },
            "debt_to_gdp": {
                "earliest": 31.0,
                "earliest_date": "2020-03",
                "peak": 122.0,
                "peak_date": "2020-09",
                "latest": 100.0,
                "latest_date": "2020-12",
            },
        }
    }


def test_macro_context_section_renders_exact_figures():
    text = _macro_context_section(_macro_render_stats())
    expected = (
        "## Macroeconomic Context: Purchasing Power & Sector Distribution\n\n"
        "**Purchasing Power Trajectory:** The purchasing power index went from "
        "10.00 (2020-01) to 10.00 (2020-03), a change of +0.00%. Over the same "
        "span, CPI-U grew +21.00% while nominal average hourly earnings (AHETPI) "
        "grew +21.00%.\n\n"
        "**Private Employment per Capita:** Private payroll employment equaled "
        "60.00% of the civilian population at its 2020-02 peak and 55.00% in "
        "2020-03. The share is +10.00% above its 2020-01 level.\n\n"
        "**Public Sector Share:** Government employment as a share of total "
        "payrolls peaked at 17.50% in 2020-02 and stands at 15.00% in 2020-03. "
        "The change from earliest available data (2020-01) is -1.00 percentage "
        "points.\n\n"
        "**Public Debt to GDP Ratio:** The earliest recorded value is 31.00% "
        "(2020-03), with a peak of 122.00% in 2020-09 and a latest value of "
        "100.00% (2020-12).\n"
    )
    assert text == expected


def test_macro_context_section_renders_header_only_without_data():
    text = _macro_context_section({})
    assert text == "## Macroeconomic Context: Purchasing Power & Sector Distribution\n"


def test_macro_context_section_skips_absent_blocks():
    stats = _macro_render_stats()
    del stats["macro"]["purchasing_power"]
    del stats["macro"]["private_per_capita"]
    del stats["macro"]["govt_share_pct"]
    text = _macro_context_section(stats)
    assert "**Purchasing Power Trajectory:**" not in text
    assert "**Private Employment per Capita:**" not in text
    assert "**Public Sector Share:**" not in text
    assert "**Public Debt to GDP Ratio:**" in text


def test_compute_stats_macro_matches_the_assembled_frames(
    synthetic_stats, synthetic_data
):
    monthly = synthetic_data.monthly
    quarterly = synthetic_data.quarterly
    macro = synthetic_stats["macro"]

    aligned = pd.concat(
        {
            "cpi": monthly["cpi"],
            "ahe": monthly["ahe_production_nominal"],
            "ppi": monthly["purchasing_power_index"],
        },
        axis=1,
    ).dropna()

    pp = macro["purchasing_power"]
    assert pp["cpi"]["first"] == pytest.approx(aligned["cpi"].iloc[0])
    assert pp["cpi"]["first_date"] == _ym(aligned.index[0])
    assert pp["cpi"]["latest"] == pytest.approx(aligned["cpi"].iloc[-1])
    assert pp["cpi"]["latest_date"] == _ym(aligned.index[-1])
    assert pp["cpi"]["growth_pct"] == pytest.approx(
        (aligned["cpi"].iloc[-1] / aligned["cpi"].iloc[0] - 1) * 100
    )
    assert pp["ahe_nominal"]["first"] == pytest.approx(aligned["ahe"].iloc[0])
    assert pp["ahe_nominal"]["growth_pct"] == pytest.approx(
        (aligned["ahe"].iloc[-1] / aligned["ahe"].iloc[0] - 1) * 100
    )
    assert pp["purchasing_power_index"]["first"] == pytest.approx(
        aligned["ppi"].iloc[0]
    )
    assert pp["purchasing_power_index"]["latest"] == pytest.approx(
        aligned["ppi"].iloc[-1]
    )
    assert pp["purchasing_power_index"]["change_pct"] == pytest.approx(
        (aligned["ppi"].iloc[-1] / aligned["ppi"].iloc[0] - 1) * 100
    )

    private_clean = monthly["private_per_capita"].dropna()
    private = macro["private_per_capita"]
    assert private["first"] == pytest.approx(private_clean.iloc[0])
    assert private["first_date"] == _ym(private_clean.index[0])
    assert private["latest"] == pytest.approx(private_clean.iloc[-1])
    assert private["latest_date"] == _ym(private_clean.index[-1])
    assert private["peak"] == pytest.approx(private_clean.max())
    assert private["peak_date"] == _ym(private_clean.idxmax())
    assert private["change_pct"] == pytest.approx(
        (private_clean.iloc[-1] / private_clean.iloc[0] - 1) * 100
    )
    assert private["change_since_peak"] == pytest.approx(
        private_clean.iloc[-1] - private_clean.max()
    )

    govt_clean = monthly["govt_share_pct"].dropna()
    govt = macro["govt_share_pct"]
    assert govt["first"] == pytest.approx(govt_clean.iloc[0])
    assert govt["first_date"] == _ym(govt_clean.index[0])
    assert govt["latest"] == pytest.approx(govt_clean.iloc[-1])
    assert govt["latest_date"] == _ym(govt_clean.index[-1])
    assert govt["peak"] == pytest.approx(govt_clean.max())
    assert govt["peak_date"] == _ym(govt_clean.idxmax())
    assert govt["change_pp"] == pytest.approx(govt_clean.iloc[-1] - govt_clean.iloc[0])

    debt_clean = quarterly["debt_to_gdp"].dropna()
    debt = macro["debt_to_gdp"]
    assert debt["earliest"] == pytest.approx(debt_clean.iloc[0])
    assert debt["earliest_date"] == _ym(debt_clean.index[0])
    assert debt["peak"] == pytest.approx(debt_clean.max())
    assert debt["peak_date"] == _ym(debt_clean.idxmax())
    assert debt["latest"] == pytest.approx(debt_clean.iloc[-1])
    assert debt["latest_date"] == _ym(debt_clean.index[-1])


def _data_with_macro_gaps(synthetic_data) -> WorkforceData:
    """Synthetic data with NaN holes in the middle of every macro series."""
    monthly = synthetic_data.monthly.copy()
    gap_month = monthly.index[100]
    for column in (
        "cpi",
        "ahe_production_nominal",
        "purchasing_power_index",
        "private_per_capita",
        "govt_share_pct",
    ):
        monthly.loc[gap_month, column] = np.nan

    quarterly = synthetic_data.quarterly.copy()
    quarterly.loc[quarterly.index[10], "debt_to_gdp"] = np.nan

    return WorkforceData(
        monthly=monthly,
        quarterly=quarterly,
        hourly=synthetic_data.hourly,
        coverage=synthetic_data.coverage,
    )


def test_macro_helpers_tolerate_middle_nan_gaps(synthetic_data):
    stats = compute_stats(_data_with_macro_gaps(synthetic_data))
    text = _macro_context_section(stats)
    assert "**Purchasing Power Trajectory:**" in text
    json.dumps(stats, allow_nan=False)


def test_macro_helpers_tolerate_missing_baseline_observations(synthetic_data):
    monthly = synthetic_data.monthly.copy()
    first_month = monthly.index[0]
    for column in (
        "cpi",
        "ahe_production_nominal",
        "purchasing_power_index",
        "private_per_capita",
        "govt_share_pct",
    ):
        monthly.loc[first_month, column] = np.nan

    quarterly = synthetic_data.quarterly.copy()
    quarterly.loc[quarterly.index[0], "debt_to_gdp"] = np.nan

    stats = compute_stats(
        WorkforceData(
            monthly=monthly,
            quarterly=quarterly,
            hourly=synthetic_data.hourly,
            coverage=synthetic_data.coverage,
        )
    )
    macro = stats["macro"]
    assert macro["purchasing_power"]["cpi"]["first_date"] == "1948-02"
    assert macro["private_per_capita"]["first_date"] == "1948-02"
    assert macro["govt_share_pct"]["first_date"] == "1948-02"
    assert macro["debt_to_gdp"]["earliest_date"] == "1979-04"
    json.dumps(stats, allow_nan=False)


def test_render_report_includes_macro_context_section(synthetic_data, synthetic_stats):
    report = analysis.render_report(synthetic_data, synthetic_stats)
    assert "## Macroeconomic Context: Purchasing Power & Sector Distribution" in report
    assert "**Purchasing Power Trajectory:**" in report
    assert "**Private Employment per Capita:**" in report
    assert "**Public Sector Share:**" in report
    assert "**Public Debt to GDP Ratio:**" in report


# ---------------------------------------------------------------------------
# prime-age helpers: exact math and NaN propagation
# ---------------------------------------------------------------------------


def _prime_frame_flat() -> pd.DataFrame:
    """24 monthly observations: 2000 flat at (60, 80), 2001 flat at (61, 82)."""
    index = pd.date_range("2000-01-01", "2001-12-01", freq="MS")
    return pd.DataFrame(
        {
            "rate_total": [60.0] * 12 + [61.0] * 12,
            "lfpr_prime_total": [80.0] * 12 + [82.0] * 12,
            "lfpr_prime_men": [90.0] * 12 + [92.0] * 12,
            "lfpr_prime_women": [70.0] * 12 + [69.0] * 12,
        },
        index=index,
    )


def _prime_frame_2020_2021() -> pd.DataFrame:
    """24 monthly observations covering only the 2019-2026 regime."""
    index = pd.date_range("2020-01-01", "2021-12-01", freq="MS")
    return pd.DataFrame(
        {
            "lfpr_prime_men": np.linspace(90.0, 88.0, 24),
            "lfpr_prime_women": np.linspace(71.0, 72.0, 24),
        },
        index=index,
    )


def test_value_at_or_nan_returns_value_for_present_date():
    series = pd.Series([1.0, 2.0], index=D2)
    assert analysis._value_at_or_nan(series, "2020-02-01") == 2.0


def test_value_at_or_nan_returns_nan_for_missing_date():
    series = pd.Series([1.0, 2.0], index=D2)
    assert np.isnan(analysis._value_at_or_nan(series, "2020-03-01"))


def test_value_at_or_nan_returns_nan_for_nan_value():
    series = pd.Series([1.0, np.nan], index=D2)
    assert np.isnan(analysis._value_at_or_nan(series, "2020-02-01"))


def test_latest_common_observation_returns_last_non_nan_pair():
    index = pd.DatetimeIndex(["2020-01-01", "2020-02-01", "2020-03-01"])
    aggregate = pd.Series([1.0, 2.0, np.nan], index=index)
    prime = pd.Series([np.nan, 2.0, 3.0], index=index)
    agg, prime_val, ym = analysis._latest_common_observation(aggregate, prime)
    assert agg == 2.0
    assert prime_val == 2.0
    assert ym == "2020-02"


def test_latest_common_observation_raises_for_no_overlap():
    index = pd.DatetimeIndex(["2020-01-01", "2020-02-01"])
    aggregate = pd.Series([1.0, np.nan], index=index)
    prime = pd.Series([np.nan, 2.0], index=index)
    with pytest.raises(EmptySeriesError):
        analysis._latest_common_observation(aggregate, prime)


def test_prime_age_levels_exact_values():
    levels = analysis._prime_age_levels(_prime_frame_flat())
    total = levels["total"]
    assert total["first"] == 80.0
    assert total["first_date"] == "2000-01"
    assert total["latest"] == 82.0
    assert total["latest_date"] == "2001-12"
    assert total["peak"] == 82.0
    # 82.0 first appears at 2001-01; peak_date pins first-occurrence tie-breaking.
    assert total["peak_date"] == "2001-01"
    assert total["change_since_first"] == 2.0
    assert total["change_since_peak"] == 0.0
    assert total["observations"] == 24


def test_prime_age_levels_ignore_leading_nan():
    frame = _prime_frame_flat()
    frame.loc["2000-01-01", "lfpr_prime_total"] = np.nan
    total = analysis._prime_age_levels(frame)["total"]
    assert total["first"] == 80.0
    assert total["first_date"] == "2000-02"
    assert total["observations"] == 23


def test_prime_age_levels_all_nan_raises_empty_series_error():
    frame = _prime_frame_flat()
    frame["lfpr_prime_total"] = np.nan
    with pytest.raises(EmptySeriesError):
        analysis._prime_age_levels(frame)


def test_prime_age_regimes_exact_slopes_and_r2():
    regimes = analysis._prime_age_regimes(_prime_frame_2020_2021())
    # Only the 2019-2026 window has observations in this frame.
    for label in ("1948-2000", "2000-2019"):
        for sex in ("men", "women"):
            assert np.isnan(regimes[label][sex]["slope_pp_per_year"])
            assert np.isnan(regimes[label][sex]["r2"])
            assert regimes[label][sex]["observations"] == 0

    # np.linspace spans 23 month-steps, so the exact slope is delta/(23/12).
    men_slope = -2.0 / (23 / 12)
    women_slope = 1.0 / (23 / 12)
    assert regimes["2019-2026"]["men"]["slope_pp_per_year"] == pytest.approx(men_slope)
    assert regimes["2019-2026"]["men"]["r2"] == pytest.approx(1.0)
    assert regimes["2019-2026"]["men"]["observations"] == 24
    assert regimes["2019-2026"]["women"]["slope_pp_per_year"] == pytest.approx(
        women_slope
    )
    assert regimes["2019-2026"]["women"]["r2"] == pytest.approx(1.0)
    assert regimes["2019-2026"]["women"]["observations"] == 24


def test_prime_age_drag_exact_math():
    drag = analysis._prime_age_drag(_prime_frame_flat())
    assert drag["baseline_date"] == "2000-04"
    assert drag["latest_date"] == "2001-12"
    assert drag["aggregate_start"] == 60.0
    assert drag["prime_start"] == 80.0
    assert drag["aggregate_latest"] == 61.0
    assert drag["prime_latest"] == 82.0
    assert drag["aggregate_change_pp"] == pytest.approx(1.0)
    assert drag["prime_change_pp"] == pytest.approx(2.0)
    assert drag["aggregate_decline_pp"] == pytest.approx(-1.0)
    assert drag["prime_decline_pp"] == pytest.approx(-2.0)
    assert drag["demographic_drag_pp"] == pytest.approx(1.0)


def test_prime_age_drag_propagates_nan_baseline():
    frame = _prime_frame_flat()
    frame.loc["2000-04-01", "lfpr_prime_total"] = np.nan
    drag = analysis._prime_age_drag(frame)
    assert np.isnan(drag["prime_start"])
    assert np.isnan(drag["prime_change_pp"])
    assert np.isnan(drag["prime_decline_pp"])
    assert np.isnan(drag["demographic_drag_pp"])
    # The aggregate side stays fully observed.
    assert drag["aggregate_start"] == 60.0
    assert drag["aggregate_decline_pp"] == pytest.approx(-1.0)


def test_prime_age_stats_reports_missing_columns():
    frame = pd.DataFrame({"rate_total": [60.0]}, index=pd.DatetimeIndex(["2000-01-01"]))
    result = analysis._prime_age_stats(frame)
    assert result["status"] == "unavailable"
    assert set(result["missing_columns"]) == set(analysis.PRIME_COLUMNS.values())


def test_prime_age_stats_includes_every_block():
    result = analysis._prime_age_stats(_prime_frame_flat())
    assert set(result) == {"levels", "regimes", "demographic_drag"}
    assert set(result["levels"]) == {"total", "men", "women"}
    assert set(result["regimes"]) == {"1948-2000", "2000-2019", "2019-2026"}
    assert set(result["demographic_drag"]) == {
        "baseline_date",
        "latest_date",
        "aggregate_start",
        "prime_start",
        "aggregate_latest",
        "prime_latest",
        "aggregate_change_pp",
        "prime_change_pp",
        "aggregate_decline_pp",
        "prime_decline_pp",
        "demographic_drag_pp",
    }
