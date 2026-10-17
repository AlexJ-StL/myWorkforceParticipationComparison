"""FRED client behavior: CSV parsing strictness, cache discipline, and the
fetch/refresh/re-download state machine."""

from __future__ import annotations

import os

import pandas as pd
import pytest
import requests

import fred_data
from fred_data import FredFetchError, fetch_series
from series import ALL_SIDS

VALID_CSV = "observation_date,TEST\n2020-01-01,1.5\n2020-02-01,2.5\n"
EXTRA_COLUMN_CSV = (
    "observation_date,TEST,realtime_start\n2020-01-01,1.0,x\n2020-02-01,2.0,y\n"
)


class _Response:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code


# ---------------------------------------------------------------------------
# _parse
# ---------------------------------------------------------------------------


def test_parse_returns_named_float_series_with_datetime_index(fred_csv):
    series = fred_data._parse(fred_csv, "TEST")
    assert series.name == "TEST"
    assert isinstance(series.index, pd.DatetimeIndex)
    assert series.dtype == "float64"
    assert list(series) == [1.5, 2.5, 3.5]


def test_parse_reads_value_column_only_and_ignores_extras():
    series = fred_data._parse(EXTRA_COLUMN_CSV, "TEST")
    assert list(series) == [1.0, 2.0]


def test_parse_marks_dot_and_blank_as_nan():
    text = "observation_date,TEST\n2020-01-01,.\n2020-02-01,\n2020-03-01,4.0\n"
    series = fred_data._parse(text, "TEST")
    assert pd.isna(series.iloc[0])
    assert pd.isna(series.iloc[1])
    assert series.iloc[2] == 4.0


def test_parse_preserves_duplicate_dates():
    """Pin (D-behavior): FRED never sends duplicate dates, but _parse does not
    deduplicate or reorder -- it passes the index through verbatim."""
    text = "observation_date,TEST\n2020-01-01,1.0\n2020-01-01,2.0\n"
    series = fred_data._parse(text, "TEST")
    assert list(series) == [1.0, 2.0]
    assert series.index.has_duplicates


def test_parse_single_column_csv_raises():
    with pytest.raises(FredFetchError, match="unexpected response shape"):
        fred_data._parse("observation_date\n2020-01-01\n", "TEST")


def test_parse_header_only_csv_raises():
    """D1: a header-only response must not silently become an empty Series --
    it is a failed fetch wearing a valid disguise."""
    with pytest.raises(FredFetchError, match="unexpected response shape"):
        fred_data._parse("observation_date,TEST\n", "TEST")


def test_parse_garbage_header_raises():
    """D1: unrelated header text must not parse to an empty Series."""
    with pytest.raises(FredFetchError, match="unexpected response shape"):
        fred_data._parse("not,a,csv", "TEST")


def test_parse_unparseable_date_raises():
    with pytest.raises(FredFetchError, match="unparseable response"):
        fred_data._parse("observation_date,TEST\nnotadate,1.0\n", "TEST")


def test_parse_non_numeric_values_raise():
    with pytest.raises(FredFetchError, match="unparseable response"):
        fred_data._parse("observation_date,TEST\n2020-01-01,abc\n", "TEST")


def test_parse_empty_text_raises():
    with pytest.raises(FredFetchError, match="unparseable response"):
        fred_data._parse("", "TEST")


def test_parse_error_carries_series_id():
    with pytest.raises(FredFetchError) as excinfo:
        fred_data._parse("", "CIVPART")
    assert excinfo.value.series_id == "CIVPART"
    assert "CIVPART" in str(excinfo.value)


# ---------------------------------------------------------------------------
# fetch_series: cache state machine
# ---------------------------------------------------------------------------


def test_fresh_cache_hit_avoids_network(write_cache, fake_get, fred_csv):
    write_cache("CIVPART", fred_csv, age_days=1.0)
    fake_get.install(None)
    series = fetch_series("CIVPART")
    assert list(series) == [1.5, 2.5, 3.5]
    assert fake_get.calls == []


def test_stale_cache_triggers_refetch(write_cache, fake_get, fred_csv):
    write_cache("CIVPART", "observation_date,CIVPART\n2000-01-01,10.0\n", age_days=31.0)
    fake_get.install(_CsvResponse("observation_date,CIVPART\n2020-01-01,99.0\n"))
    series = fetch_series("CIVPART")
    assert series.iloc[-1] == 99.0
    assert len(fake_get.calls) == 1
    assert (
        (fred_data.CACHE_DIR / "CIVPART.csv")
        .read_text(encoding="utf-8")
        .startswith("observation_date,CIVPART\n2020-01-01")
    )


def test_refresh_forces_download_even_when_fresh(write_cache, fake_get, fred_csv):
    write_cache("CIVPART", fred_csv, age_days=0.5)
    fake_get.install(_CsvResponse(VALID_CSV.replace("TEST", "CIVPART")))
    fetch_series("CIVPART", refresh=True)
    assert len(fake_get.calls) == 1


def test_successful_fetch_writes_cache_then_hits_it(fake_get, fred_csv):
    fake_get.install(_CsvResponse(fred_csv.replace("TEST", "CIVPART")))
    first = fetch_series("CIVPART")
    cached = fred_data.CACHE_DIR / "CIVPART.csv"
    assert cached.exists()
    assert cached.read_text(encoding="utf-8") == fred_csv.replace("TEST", "CIVPART")
    second = fetch_series("CIVPART")
    assert len(fake_get.calls) == 1  # second call served from disk
    pd.testing.assert_series_equal(first, second)


def test_unknown_sid_fails_before_any_network_call(fake_get):
    fake_get.install(None)
    with pytest.raises(FredFetchError, match="not in the series catalog"):
        fetch_series("NOT_A_SERIES")
    assert fake_get.calls == []


@pytest.mark.parametrize("status", [404, 429, 500, 503])
def test_http_error_status_raises_and_writes_no_cache(fake_get, status):
    fake_get.install(_CsvResponse("error body", status_code=status))
    with pytest.raises(FredFetchError, match=f"HTTP {status}"):
        fetch_series("CIVPART")
    assert not (fred_data.CACHE_DIR / "CIVPART.csv").exists()


def test_network_failure_propagates_unwrapped(fake_get):
    """Documented contract: requests.RequestException is not wrapped."""
    fake_get.install(requests.ConnectionError("dns failure"))
    with pytest.raises(requests.ConnectionError):
        fetch_series("CIVPART")
    assert not (fred_data.CACHE_DIR / "CIVPART.csv").exists()


def test_failed_parse_leaves_no_cache_behind(fake_get):
    """D1 + D2 paired: garbage response must raise and must not be cached."""
    fake_get.install(_CsvResponse("not,a,csv"))
    with pytest.raises(FredFetchError):
        fetch_series("CIVPART")
    assert not (fred_data.CACHE_DIR / "CIVPART.csv").exists()


def test_corrupt_cache_falls_back_to_redownload(write_cache, fake_get, fred_csv):
    """D2: a corrupt cached file must trigger a fresh download, not a hard stop."""
    write_cache("CIVPART", "garbage", age_days=0.1)
    fake_get.install(_CsvResponse(fred_csv.replace("TEST", "CIVPART")))
    series = fetch_series("CIVPART")
    assert list(series) == [1.5, 2.5, 3.5]
    assert (fred_data.CACHE_DIR / "CIVPART.csv").read_text(encoding="utf-8") == (
        fred_csv.replace("TEST", "CIVPART")
    )


def test_corrupt_cache_with_failed_download_reports_the_download_error(
    write_cache, fake_get
):
    write_cache("CIVPART", "garbage", age_days=0.1)
    fake_get.install(_CsvResponse("nope", status_code=500))
    with pytest.raises(FredFetchError, match="HTTP 500"):
        fetch_series("CIVPART")


def test_request_uses_fred_endpoint_params_and_timeout(fake_get, fred_csv):
    fake_get.install(_CsvResponse(fred_csv.replace("TEST", "CIVPART")))
    fetch_series("CIVPART")
    call = fake_get.calls[0]
    assert call["url"] == fred_data.FRED_CSV_URL
    assert call["params"] == {"id": "CIVPART"}
    assert call["timeout"] == fred_data.REQUEST_TIMEOUT_SECONDS


def test_max_age_days_override_honored(write_cache, fake_get, fred_csv):
    write_cache("CIVPART", fred_csv, age_days=5.0)
    fake_get.install(_CsvResponse(VALID_CSV.replace("TEST", "CIVPART")))
    # 5-day-old cache is stale under a 1-day budget -> download
    fetch_series("CIVPART", max_age_days=1.0)
    assert len(fake_get.calls) == 1


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


def test_clear_cache_removes_only_csv_files(write_cache):
    write_cache("CIVPART", VALID_CSV)
    stray = fred_data.CACHE_DIR / "notes.txt"
    stray.write_text("keep me", encoding="utf-8")
    fred_data.clear_cache()
    assert not (fred_data.CACHE_DIR / "CIVPART.csv").exists()
    assert stray.exists()


def test_clear_cache_missing_directory_is_noop():
    assert not fred_data.CACHE_DIR.exists()
    fred_data.clear_cache()  # must not raise


def test_fetch_all_returns_every_catalog_series(fake_get, fred_csv):
    def respond(sid):
        return _CsvResponse(fred_csv.replace("TEST", sid))

    fake_get.install(respond)
    raw = fred_data.fetch_all()
    assert set(raw) == set(ALL_SIDS)
    requested = {call["params"]["id"] for call in fake_get.calls}
    assert requested == set(ALL_SIDS)
    assert len(fake_get.calls) == len(ALL_SIDS)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _CsvResponse(text: str, status_code: int = 200) -> _Response:
    return _Response(text=text, status_code=status_code)
