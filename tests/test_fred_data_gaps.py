"""Coverage-gap tests for ``fred_data.py`` parsing branches.

Target analysis
---------------
``fred_data.py`` sits at 92% coverage. The two missed branch families are:

* ``_parse_bls_json``'s BLS API v2 ``Results`` wrapper (the format the live
    endpoint actually returns), including its empty/missing/empty-data variants.
* ``_parse_fred_csv``'s non-monotonic-date sort branch.

Failure modes considered
------------------------
* BLS silently switches from the legacy top-level ``series`` shape to the v2
    ``Results.series`` shape -> the parser must still return a correct series.
* BLS returns ``Results`` with an empty or partial series list.
* FRED returns rows newest-first or shuffled -> the parser must sort index and
    values together so dates and observations never pair up wrongly.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

import fred_data
from fred_data import FetchError


def test_parse_bls_json_accepts_results_wrapper_with_exact_values():
    text = json.dumps(
        {
            "status": "REQUEST_SUCCEEDED",
            "Results": {
                "series": [
                    {
                        "seriesID": "TEST",
                        "data": [
                            {"year": "2020", "period": "M02", "value": "2.5"},
                            {"year": "2020", "period": "M01", "value": "1.5"},
                        ],
                    }
                ]
            },
        }
    )

    series = fred_data._parse_bls_json(text, "TEST")

    assert series.name == "TEST"
    assert series.dtype == "float64"
    assert series.index[0] == pd.Timestamp("2020-01-01")
    assert series.index[1] == pd.Timestamp("2020-02-01")
    assert list(series.to_numpy()) == [1.5, 2.5]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"Results": {"series": []}}, "empty series array"),
        ({"Results": {"series": [{"seriesID": "TEST"}]}}, "no data records in series"),
        (
            {"Results": {"series": [{"seriesID": "TEST", "data": []}]}},
            "empty data array",
        ),
        ({"Results": {"status": "REQUEST_SUCCEEDED"}}, "no series data in response"),
    ],
)
def test_parse_bls_json_rejects_bad_results_wrapper(payload, message):
    with pytest.raises(FetchError, match=message):
        fred_data._parse_bls_json(json.dumps(payload), "TEST")


@pytest.mark.parametrize(
    ("rows", "expected_values"),
    [
        (
            "2020-03-01,3.5\n2020-01-01,1.5\n2020-02-01,2.5\n",
            [1.5, 2.5, 3.5],
        ),
        (
            "2020-02-01,2.5\n2020-03-01,3.5\n2020-01-01,1.5\n",
            [1.5, 2.5, 3.5],
        ),
    ],
)
def test_parse_fred_csv_sorts_non_monotonic_dates_and_keeps_values_aligned(
    rows, expected_values
):
    text = "observation_date,TEST\n" + rows

    series = fred_data._parse_fred_csv(text, "TEST")

    assert series.index[0] == pd.Timestamp("2020-01-01")
    assert series.index[1] == pd.Timestamp("2020-02-01")
    assert series.index[2] == pd.Timestamp("2020-03-01")
    assert list(series.to_numpy()) == expected_values
