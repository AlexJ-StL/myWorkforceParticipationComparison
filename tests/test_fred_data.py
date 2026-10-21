"""FRED client behavior: CSV parsing strictness, cache discipline, and the
fetch/refresh/re-download state machine."""

from __future__ import annotations

import json
import os
import time

import pandas as pd
import pytest
import requests

import fred_data
from fred_data import FetchError, fetch_bls_series, fetch_fred_series
from series import ALL_BLS_SIDS, ALL_FRED_SIDS

VALID_CSV = "observation_date,TEST\n2020-01-01,1.5\n2020-02-01,2.5\n"
EXTRA_COLUMN_CSV = (
    "observation_date,TEST,realtime_start\n2020-01-01,1.0,x\n2020-02-01,2.0,y\n"
)


class _Response:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code


# ---------------------------------------------------------------------------
# _parse_fred_csv
# ---------------------------------------------------------------------------


def test_parse_fred_csv_returns_named_float_series_with_datetime_index(fred_csv):
    series = fred_data._parse_fred_csv(fred_csv, "TEST")
    assert series.name == "TEST"
    assert isinstance(series.index, pd.DatetimeIndex)
    assert series.dtype == "float64"
    assert list(series) == [1.5, 2.5, 3.5]


def test_parse_fred_csv_reads_value_column_only_and_ignores_extras():
    series = fred_data._parse_fred_csv(EXTRA_COLUMN_CSV, "TEST")
    assert list(series) == [1.0, 2.0]


def test_parse_fred_csv_marks_dot_and_blank_as_nan():
    text = "observation_date,TEST\n2020-01-01,.\n2020-02-01,\n2020-03-01,4.0\n"
    series = fred_data._parse_fred_csv(text, "TEST")
    assert pd.isna(series.iloc[0])
    assert pd.isna(series.iloc[1])
    assert series.iloc[2] == 4.0


def test_parse_fred_csv_preserves_duplicate_dates():
    """Pin (D-behavior): FRED never sends duplicate dates, but _parse does not
    deduplicate or reorder -- it passes the index through verbatim."""
    text = "observation_date,TEST\n2020-01-01,1.0\n2020-01-01,2.0\n"
    series = fred_data._parse_fred_csv(text, "TEST")
    assert list(series) == [1.0, 2.0]
    assert series.index.has_duplicates


def test_parse_fred_csv_single_column_csv_raises():
    with pytest.raises(FetchError, match="unexpected response shape"):
        fred_data._parse_fred_csv("observation_date\n2020-01-01\n", "TEST")


def test_parse_fred_csv_header_only_csv_raises():
    """D1: a header-only response must not silently become an empty Series --
    it is a failed fetch wearing a valid disguise."""
    with pytest.raises(FetchError, match="unexpected response shape"):
        fred_data._parse_fred_csv("observation_date,TEST\n", "TEST")


def test_parse_fred_csv_garbage_header_raises():
    """D1: unrelated header text must not parse to an empty Series."""
    with pytest.raises(FetchError, match="unexpected response shape"):
        fred_data._parse_fred_csv("not,a,csv", "TEST")


def test_parse_fred_csv_unparseable_date_raises():
    with pytest.raises(FetchError, match="unparseable response"):
        fred_data._parse_fred_csv("observation_date,TEST\nnotadate,1.0\n", "TEST")


def test_parse_fred_csv_non_numeric_values_raise():
    with pytest.raises(FetchError, match="unparseable response"):
        fred_data._parse_fred_csv("observation_date,TEST\n2020-01-01,abc\n", "TEST")


def test_parse_fred_csv_empty_text_raises():
    with pytest.raises(FetchError, match="unparseable response"):
        fred_data._parse_fred_csv("", "TEST")


def test_parse_fred_csv_error_carries_series_id():
    with pytest.raises(FetchError) as excinfo:
        fred_data._parse_fred_csv("", "CIVPART")
    assert excinfo.value.series_id == "CIVPART"
    assert "CIVPART" in str(excinfo.value)


# ---------------------------------------------------------------------------
# _parse_bls_json
# ---------------------------------------------------------------------------


def test_parse_bls_json_returns_named_float_series_with_datetime_index():
    text = json.dumps(
        {
            "series": [
                {
                    "seriesID": "TEST",
                    "data": [
                        {"year": "2020", "period": "M01", "value": "1.5"},
                        {"year": "2020", "period": "M02", "value": "2.5"},
                    ],
                }
            ]
        }
    )
    series = fred_data._parse_bls_json(text, "TEST")
    assert series.name == "TEST"
    assert isinstance(series.index, pd.DatetimeIndex)
    assert series.dtype == "float64"
    assert list(series) == [1.5, 2.5]


def test_parse_bls_json_marks_dash_as_nan():
    text = json.dumps(
        {
            "series": [
                {
                    "seriesID": "TEST",
                    "data": [
                        {"year": "2020", "period": "M01", "value": "-"},
                        {"year": "2020", "period": "M02", "value": "2.5"},
                    ],
                }
            ]
        }
    )
    series = fred_data._parse_bls_json(text, "TEST")
    assert pd.isna(series.iloc[0])
    assert series.iloc[1] == 2.5


def test_parse_bls_json_missing_series_raises():
    text = json.dumps({"series": []})
    with pytest.raises(FetchError, match="no series data in response"):
        fred_data._parse_bls_json(text, "TEST")


def test_parse_bls_json_missing_data_raises():
    text = json.dumps({"series": [{"seriesID": "TEST"}]})
    with pytest.raises(FetchError, match="no data records in series"):
        fred_data._parse_bls_json(text, "TEST")


def test_parse_bls_json_empty_data_raises():
    text = json.dumps({"series": [{"seriesID": "TEST", "data": []}]})
    with pytest.raises(FetchError, match="empty data array"):
        fred_data._parse_bls_json(text, "TEST")


def test_parse_bls_json_malformed_json_raises():
    with pytest.raises(FetchError, match="unparseable response"):
        fred_data._parse_bls_json("not json", "TEST")


def test_parse_bls_json_error_carries_series_id():
    with pytest.raises(FetchError) as excinfo:
        fred_data._parse_bls_json("", "TEST")
    assert excinfo.value.series_id == "TEST"
    assert "TEST" in str(excinfo.value)


# ---------------------------------------------------------------------------
# fetch_fred_series: cache state machine
# ---------------------------------------------------------------------------


def test_fred_fresh_cache_hit_avoids_network(write_cache, fake_get, fred_csv):
    write_cache("CIVPART", fred_csv, age_days=1.0)
    fake_get.install(None)
    series = fetch_fred_series("CIVPART")
    assert list(series) == [1.5, 2.5, 3.5]
    assert fake_get.calls == []


def test_fred_stale_cache_triggers_refetch(write_cache, fake_get, fred_csv):
    write_cache("CIVPART", "observation_date,CIVPART\n2000-01-01,10.0\n", age_days=31.0)
    fake_get.install(_CsvResponse("observation_date,CIVPART\n2020-01-01,99.0\n"))
    series = fetch_fred_series("CIVPART")
    assert series.iloc[-1] == 99.0
    assert len(fake_get.calls) == 1
    assert (
        (fred_data.CACHE_DIR / "CIVPART.csv")
        .read_text(encoding="utf-8")
        .startswith("observation_date,CIVPART\n2020-01-01")
    )


def test_fred_refresh_forces_download_even_when_fresh(write_cache, fake_get, fred_csv):
    write_cache("CIVPART", fred_csv, age_days=0.5)
    fake_get.install(_CsvResponse(VALID_CSV.replace("TEST", "CIVPART")))
    fetch_fred_series("CIVPART", refresh=True)
    assert len(fake_get.calls) == 1


def test_fred_successful_fetch_writes_cache_then_hits_it(fake_get, fred_csv):
    fake_get.install(_CsvResponse(fred_csv.replace("TEST", "CIVPART")))
    first = fetch_fred_series("CIVPART")
    cached = fred_data.CACHE_DIR / "CIVPART.csv"
    assert cached.exists()
    assert cached.read_text(encoding="utf-8") == fred_csv.replace("TEST", "CIVPART")
    second = fetch_fred_series("CIVPART")
    assert len(fake_get.calls) == 1  # second call served from disk
    pd.testing.assert_series_equal(first, second)


def test_fred_unknown_sid_fails_before_any_network_call(fake_get):
    fake_get.install(None)
    with pytest.raises(FetchError, match="not in the series catalog"):
        fetch_fred_series("NOT_A_SERIES")
    assert fake_get.calls == []


@pytest.mark.parametrize("status", [404, 429, 500, 503])
def test_fred_http_error_status_raises_and_writes_no_cache(fake_get, status):
    fake_get.install(_CsvResponse("error body", status_code=status))
    with pytest.raises(FetchError, match=f"HTTP {status}"):
        fetch_fred_series("CIVPART")
    assert not (fred_data.CACHE_DIR / "CIVPART.csv").exists()


def test_fred_network_failure_propagates_unwrapped(fake_get):
    """Documented contract: requests.RequestException is not wrapped."""
    fake_get.install(requests.ConnectionError("dns failure"))
    with pytest.raises(requests.ConnectionError):
        fetch_fred_series("CIVPART")
    assert not (fred_data.CACHE_DIR / "CIVPART.csv").exists()


def test_fred_failed_parse_leaves_no_cache_behind(fake_get):
    """D1 + D2 paired: garbage response must raise and must not be cached."""
    fake_get.install(_CsvResponse("not,a,csv"))
    with pytest.raises(FetchError):
        fetch_fred_series("CIVPART")
    assert not (fred_data.CACHE_DIR / "CIVPART.csv").exists()


def test_fred_corrupt_cache_falls_back_to_redownload(write_cache, fake_get, fred_csv):
    """D2: a corrupt cached file must trigger a fresh download, not a hard stop."""
    write_cache("CIVPART", "garbage", age_days=0.1)
    fake_get.install(_CsvResponse(fred_csv.replace("TEST", "CIVPART")))
    series = fetch_fred_series("CIVPART")
    assert list(series) == [1.5, 2.5, 3.5]
    assert (fred_data.CACHE_DIR / "CIVPART.csv").read_text(encoding="utf-8") == (
        fred_csv.replace("TEST", "CIVPART")
    )


def test_fred_corrupt_cache_with_failed_download_reports_the_download_error(
    write_cache, fake_get
):
    write_cache("CIVPART", "garbage", age_days=0.1)
    fake_get.install(_CsvResponse("nope", status_code=500))
    with pytest.raises(FetchError, match="HTTP 500"):
        fetch_fred_series("CIVPART")


def test_fred_request_uses_fred_endpoint_params_and_timeout(fake_get, fred_csv):
    fake_get.install(_CsvResponse(fred_csv.replace("TEST", "CIVPART")))
    fetch_fred_series("CIVPART")
    call = fake_get.calls[0]
    assert call["url"] == fred_data.FRED_CSV_URL
    assert call["kwargs"].get("params") == {"id": "CIVPART"}
    assert call["kwargs"].get("timeout") == fred_data.REQUEST_TIMEOUT_SECONDS


def test_fred_max_age_days_override_honored(write_cache, fake_get, fred_csv):
    write_cache("CIVPART", fred_csv, age_days=5.0)
    fake_get.install(_CsvResponse(VALID_CSV.replace("TEST", "CIVPART")))
    # 5-day-old cache is stale under a 1-day budget -> download
    fetch_fred_series("CIVPART", max_age_days=1.0)
    assert len(fake_get.calls) == 1


# ---------------------------------------------------------------------------
# fetch_bls_series: cache state machine
# ---------------------------------------------------------------------------


def test_bls_fresh_cache_hit_avoids_network(write_cache, fake_get):
    bls_json = json.dumps(
        {
            "series": [
                {
                    "seriesID": "TEST",
                    "data": [{"year": "2020", "period": "M01", "value": "1.5"}],
                }
            ]
        }
    )
    # BLS cache uses .json extension
    path = fred_data.CACHE_DIR / "LNS12032194.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(bls_json, encoding="utf-8")
    import time

    stamp = time.time() - 1.0 * 86400
    os.utime(path, (stamp, stamp))

    fake_get.install(None)
    series = fetch_bls_series("LNS12032194")
    assert list(series) == [1.5]
    assert fake_get.calls == []


def test_bls_stale_cache_triggers_refetch(write_cache, fake_get):
    old_json = json.dumps(
        {
            "series": [
                {
                    "seriesID": "LNS12032194",
                    "data": [{"year": "2000", "period": "M01", "value": "10.0"}],
                }
            ]
        }
    )
    path = fred_data.CACHE_DIR / "LNS12032194.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(old_json, encoding="utf-8")
    stamp = time.time() - 31.0 * 86400
    os.utime(path, (stamp, stamp))

    new_json = json.dumps(
        {
            "series": [
                {
                    "seriesID": "LNS12032194",
                    "data": [{"year": "2020", "period": "M01", "value": "99.0"}],
                }
            ]
        }
    )
    fake_get.install(_CsvResponse(new_json))
    series = fetch_bls_series("LNS12032194")
    assert series.iloc[-1] == 99.0
    assert len(fake_get.calls) == 1
    assert fake_get.calls[0]["kwargs"].get("json", {}).get("seriesid") == [
        "LNS12032194"
    ]


def test_bls_unknown_sid_fails_before_any_network_call(fake_get):
    fake_get.install(None)
    with pytest.raises(FetchError, match="not in the BLS series catalog"):
        fetch_bls_series("NOT_A_BLS_SERIES")
    assert fake_get.calls == []


# ---------------------------------------------------------------------------
# fetch_all
# ---------------------------------------------------------------------------


def test_fetch_all_returns_every_catalog_series(fake_get, fred_csv):
    def respond(sid):
        if sid in set(ALL_BLS_SIDS):
            return _CsvResponse(
                json.dumps(
                    {
                        "series": [
                            {
                                "seriesID": sid,
                                "data": [
                                    {"year": "2020", "period": "M01", "value": "1.5"}
                                ],
                            }
                        ]
                    }
                )
            )
        return _CsvResponse(fred_csv.replace("TEST", sid))

    fake_get.install(respond)
    raw = fred_data.fetch_all()
    assert set(raw) == set(ALL_FRED_SIDS) | set(ALL_BLS_SIDS)
    requested = set()
    for call in fake_get.calls:
        sid = (
            call["kwargs"].get("params", {}).get("id")
            or (call["kwargs"].get("json") or {}).get("seriesid", [None])[0]
        )
        requested.add(sid)
    assert requested == set(ALL_FRED_SIDS) | set(ALL_BLS_SIDS)
    assert len(fake_get.calls) == len(ALL_FRED_SIDS) + len(ALL_BLS_SIDS)


# ---------------------------------------------------------------------------
# _is_stale
# ---------------------------------------------------------------------------


class _FrozenClock:
    def __init__(self, now: float) -> None:
        self._now = now

    def time(self) -> float:
        return self._now


def test_is_stale_boundary_age_equal_to_max_is_fresh(write_cache, monkeypatch):
    """Pin (D-behavior): strictly older-than is stale; exactly-max is fresh."""
    now = 1_700_000_000.0
    monkeypatch.setattr(fred_data, "time", _FrozenClock(now))
    path = write_cache("CIVPART", VALID_CSV)
    stamp = now - 30 * 86400
    os.utime(path, (stamp, stamp))
    assert fred_data._is_stale(path, 30.0) is False
    assert fred_data._is_stale(path, 29.999) is True


def test_is_stale_zero_budget_always_stale(write_cache):
    path = write_cache("CIVPART", VALID_CSV)
    assert fred_data._is_stale(path, 0.0) is True


# ---------------------------------------------------------------------------
# clear_cache / fetch_all
# ---------------------------------------------------------------------------


def test_clear_cache_removes_all_cached_files(write_cache):
    write_cache("CIVPART", VALID_CSV)
    write_cache(
        "LNS12032194",
        '{"series":[{"seriesID":"TEST","data":[{"year":"2020","period":"M01","value":"1.5"}]}]}',
    )
    stray = fred_data.CACHE_DIR / "notes.txt"
    stray.write_text("keep me", encoding="utf-8")
    fred_data.clear_cache()
    assert not (fred_data.CACHE_DIR / "CIVPART.csv").exists()
    assert not (fred_data.CACHE_DIR / "LNS12032194.json").exists()
    assert not stray.exists()


def test_clear_cache_missing_directory_is_noop():
    assert not fred_data.CACHE_DIR.exists()
    fred_data.clear_cache()  # must not raise


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _CsvResponse(text: str, status_code: int = 200) -> _Response:
    return _Response(text=text, status_code=status_code)
