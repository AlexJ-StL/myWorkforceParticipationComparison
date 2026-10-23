"""Exact-value contract tests for the shift-share decomposition.

Target analysis
---------------
``tests/test_analysis.py`` exercises shift-share only at the "columns exist"
level: it never checks the actual decomposition arithmetic, the base-year row,
the missing-base-year branch, the ``_ensure_rate_total`` fallback, or the
``_shift_share_stats`` degradation paths. Those are the load-bearing branches
behind the report's behavioral-vs-demographic claims.

Failure modes considered
------------------------
* A silent formula regression (wrong average weights or group mapping).
* A base year absent from the data -> an empty frame instead of a crash.
* Missing population/LFPR columns -> zero-filled payload, not a KeyError.
* A decomposition exception -> zero-filled payload plus a warning.
* A decomposition that returns an empty frame -> zero-filled payload.
* A year present in population but absent in LFPR -> skipped, not misaligned.
"""

from __future__ import annotations

import pandas as pd
import pytest

import analysis

YEARS = (2000, 2001)
INDEX = pd.date_range("2000-01-01", periods=len(YEARS), freq="YS")


def _frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Two-year fixture whose exact decomposition is hand-computable."""
    pop = pd.DataFrame(
        [
            {
                "population_youth": 100.0,
                "population_prime": 200.0,
                "population_older": 100.0,
                "population_total": 400.0,
            },
            {
                "population_youth": 120.0,
                "population_prime": 220.0,
                "population_older": 160.0,
                "population_total": 500.0,
            },
        ],
        index=INDEX,
    )
    lfpr = pd.DataFrame(
        [
            {
                "rate_prime": 60.0,
                "rate_prime_men": 70.0,
                "rate_prime_women": 50.0,
                "rate_older": 20.0,
                "rate_total": 50.0,
            },
            {
                "rate_prime": 62.0,
                "rate_prime_men": 72.0,
                "rate_prime_women": 52.0,
                "rate_older": 24.0,
                "rate_total": 52.5,
            },
        ],
        index=INDEX,
    )
    return pop, lfpr


def test_shift_share_exact_decomposition_math():
    pop, lfpr = _frames()

    result = analysis.calculate_shift_share(pop, lfpr, base_year=2000)

    assert list(result["year"]) == [2000, 2001]

    base = result.iloc[0]
    assert base["pop_share_youth"] == pytest.approx(0.25)
    assert base["pop_share_prime"] == pytest.approx(0.50)
    assert base["pop_share_older"] == pytest.approx(0.25)
    assert base["within_group_effect"] == pytest.approx(0.0)
    assert base["between_group_effect"] == pytest.approx(0.0)
    assert base["lfpr_change_total"] == pytest.approx(0.0)

    latest = result.iloc[1]
    assert latest["pop_share_youth"] == pytest.approx(0.24)
    assert latest["pop_share_prime"] == pytest.approx(0.44)
    assert latest["pop_share_older"] == pytest.approx(0.32)
    # Hand-derived from the documented shift-share formula.
    assert latest["within_group_effect"] == pytest.approx(3.51)
    assert latest["between_group_effect"] == pytest.approx(-4.60)
    assert latest["lfpr_change_total"] == pytest.approx(2.50)


def test_shift_share_missing_base_year_returns_empty_frame():
    pop, lfpr = _frames()

    result = analysis.calculate_shift_share(pop, lfpr, base_year=1999)

    assert result.empty
    assert list(result.columns) == []


def test_shift_share_skips_years_absent_from_lfpr():
    pop = pd.DataFrame(
        [
            {
                "population_youth": 100.0,
                "population_prime": 200.0,
                "population_older": 100.0,
                "population_total": 400.0,
            },
            {
                "population_youth": 110.0,
                "population_prime": 210.0,
                "population_older": 110.0,
                "population_total": 430.0,
            },
            {
                "population_youth": 120.0,
                "population_prime": 220.0,
                "population_older": 120.0,
                "population_total": 460.0,
            },
        ],
        index=pd.date_range("1999-01-01", periods=3, freq="YS"),
    )
    lfpr = pd.DataFrame(
        [
            {
                "rate_prime": 60.0,
                "rate_prime_men": 70.0,
                "rate_prime_women": 50.0,
                "rate_older": 20.0,
            },
            {
                "rate_prime": 64.0,
                "rate_prime_men": 74.0,
                "rate_prime_women": 54.0,
                "rate_older": 24.0,
            },
        ],
        index=pd.DatetimeIndex(["2000-01-01", "2001-01-01"]),
    )

    result = analysis.calculate_shift_share(pop, lfpr, base_year=2000)

    assert list(result["year"]) == [2000, 2001]


def test_ensure_rate_total_adds_row_mean_only_when_absent():
    frame = pd.DataFrame(
        [
            {
                "rate_prime": 60.0,
                "rate_prime_men": 70.0,
                "rate_prime_women": 50.0,
                "rate_older": 20.0,
            }
        ]
    )

    analysis._ensure_rate_total(frame)

    assert "rate_total" in frame.columns
    assert frame["rate_total"].iloc[0] == pytest.approx(50.0)


def test_ensure_rate_total_never_overwrites_an_existing_column():
    frame = pd.DataFrame(
        [
            {
                "rate_prime": 60.0,
                "rate_prime_men": 70.0,
                "rate_prime_women": 50.0,
                "rate_older": 20.0,
                "rate_total": 999.0,
            }
        ]
    )

    analysis._ensure_rate_total(frame)

    assert frame["rate_total"].iloc[0] == pytest.approx(999.0)


def test_shift_share_stats_missing_columns_returns_zero_payload():
    monthly = pd.DataFrame(
        [
            {"population_youth": 100.0, "rate_prime": 60.0},
        ],
        index=pd.date_range("2000-01-01", periods=1, freq="YS"),
    )

    payload = analysis._shift_share_stats(monthly)

    assert payload == {
        "within_group_effect": 0.0,
        "between_group_effect": 0.0,
        "cumulative_within_group": 0.0,
        "cumulative_between_group": 0.0,
        "year": 2026,
    }


def _complete_monthly() -> pd.DataFrame:
    pop, lfpr = _frames()
    return pop.join(lfpr)


def test_shift_share_stats_decomposition_exception_returns_zero_payload(
    monkeypatch, capsys
):
    def boom(*args, **kwargs):
        raise ZeroDivisionError("zero population")

    monkeypatch.setattr(analysis, "calculate_shift_share", boom)

    payload = analysis._shift_share_stats(_complete_monthly())

    assert payload["within_group_effect"] == 0.0
    assert payload["between_group_effect"] == 0.0
    assert payload["year"] == 2026
    assert "Warning: Shift-share decomposition failed: zero population" in (
        capsys.readouterr().out
    )


def test_shift_share_stats_empty_result_returns_zero_payload(monkeypatch):
    monkeypatch.setattr(
        analysis, "calculate_shift_share", lambda *a, **k: pd.DataFrame()
    )

    payload = analysis._shift_share_stats(_complete_monthly())

    assert payload["within_group_effect"] == 0.0
    assert payload["between_group_effect"] == 0.0
    assert payload["year"] == 2026


def test_annual_with_year_skips_resampling_when_year_is_an_index_name():
    frame = pd.DataFrame(
        {"population_youth": [100.0, 120.0]},
        index=pd.DatetimeIndex(["2000-01-01", "2001-01-01"], name="year"),
    )

    result = analysis._annual_with_year(frame)

    assert len(result) == 2
    assert list(result["year"]) == [2000, 2001]
