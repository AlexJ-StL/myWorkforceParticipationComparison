"""Empty-series guard tests for the remaining ``analysis.py`` branches.

Target analysis
---------------
Coverage showed five missed lines in ``analysis.py``. Four are degenerate-input
guards that protect the report from silently emitting ``nan`` statistics:
``_earnings_stats`` ratio guard (627), ``_counts_stats`` share guard (706),
``_consistency_checks`` implied-rate guard (742), and ``_weekly_hours_stats``
series guard (784). The fifth (1067) is the ``__main__`` entry point.

Failure modes considered
------------------------
A frame with valid headline series but an all-NaN derived ratio/share column is
exactly what a schema change or a failed join produces. Without these guards
the report would publish ``nan`` or crash later in the renderer with an opaque
``IndexError``. Each test pins the specific error message naming the column.
"""

from __future__ import annotations

import pandas as pd
import pytest

import analysis

INDEX = pd.date_range("2020-01-01", periods=1, freq="YS")


def test_earnings_stats_raises_when_ratio_series_is_all_nan():
    quarterly = pd.DataFrame(
        [
            {
                "weekly_nominal_total": 1000.0,
                "weekly_real_total": 500.0,
                "weekly_nominal_men": 1100.0,
                "weekly_real_men": 550.0,
                "weekly_nominal_women": 900.0,
                "weekly_real_women": 450.0,
                "earnings_ratio_nominal": float("nan"),
                "earnings_ratio_real": float("nan"),
            }
        ],
        index=INDEX,
    )

    with pytest.raises(analysis.EmptySeriesError, match="earnings ratio 'nominal'"):
        analysis._earnings_stats(quarterly)


def test_counts_stats_raises_when_share_series_is_all_nan():
    monthly = pd.DataFrame(
        [
            {
                "labor_force_total": 100.0,
                "labor_force_men": 50.0,
                "labor_force_women": 50.0,
                "employment_total": 95.0,
                "population_total": 200.0,
                "women_lf_share": float("nan"),
                "emp_pop_ratio_total": float("nan"),
            }
        ],
        index=INDEX,
    )

    with pytest.raises(
        analysis.EmptySeriesError, match="counts series 'women_lf_share'"
    ):
        analysis._counts_stats(monthly)


def test_consistency_checks_raises_when_implied_rate_is_all_nan():
    monthly = pd.DataFrame(
        [
            {
                "labor_force_men": 50.0,
                "labor_force_women": 50.0,
                "labor_force_total": 100.0,
                "implied_rate_total": float("nan"),
                "rate_total": 60.0,
                "implied_rate_men": 70.0,
                "rate_men": 70.0,
                "implied_rate_women": 50.0,
                "rate_women": 50.0,
            }
        ],
        index=INDEX,
    )

    with pytest.raises(
        analysis.EmptySeriesError,
        match="implied vs published rate check 'total'",
    ):
        analysis._consistency_checks(monthly)


def test_weekly_hours_stats_raises_when_men_series_is_all_nan():
    monthly = pd.DataFrame(
        [
            {
                "weekly_hours_men": float("nan"),
                "weekly_hours_women": 35.0,
                "weekly_hours_total": 40.0,
            }
        ],
        index=INDEX,
    )

    with pytest.raises(analysis.EmptySeriesError, match="weekly hours series 'men'"):
        analysis._weekly_hours_stats(monthly)
