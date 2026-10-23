"""High-ROI contract tests for the standalone BLS client (``bls_data.py``).

Target analysis
---------------
``tests/test_bls_data.py`` only checks catalog metadata and one missing-SID
path. The uncovered block in ``bls_data.py`` (lines 103-129, 136, 150,
159-195) is the entire cache/network/parse state machine: exactly where a BLS
outage, a 429 rate limit, a corrupt cache, or an upstream schema change would
break the pipeline.

Failure modes considered
------------------------
* HTTP 4xx/5xx and 429 rate limiting -> ``BlsFetchError`` and no poisoned cache.
* DNS/connection failures -> ``requests.RequestException`` propagates unwrapped
    (documented contract).
* Fresh cache -> zero network calls; stale/``refresh`` -> exactly one POST.
* Corrupt cached JSON -> transparent re-download.
* Malformed/empty/wrong-shape JSON -> ``BlsFetchError`` carrying the SID.
* API key absent vs present -> payload shape changes, no key leak.
* ``clear_bls_cache`` -> SID-scoped deletion and a no-op on a missing directory.
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
import requests

import bls_data
from bls_data import BlsFetchError

BLS_SID = "LNS12032194"


class _Response:
    """Minimal ``requests.Response`` double for the BLS client."""

    def __init__(self, text: str = "", status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code


def _bls_json(sid: str = BLS_SID, records: list[dict] | None = None) -> str:
    if records is None:
        records = [
            {"year": "2020", "period": "M02", "value": "2.5"},
            {"year": "2020", "period": "M01", "value": "1.5"},
        ]
    return json.dumps({"series": [{"seriesID": sid, "data": records}]})


def _write_cache(path: Path, text: str, *, age_days: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    stamp = time.time() - age_days * 86400
    os.utime(path, (stamp, stamp))


@pytest.fixture
def bls_cache(tmp_path, monkeypatch) -> Path:
    """Isolate the BLS cache; the shared conftest fixture only redirects FRED."""
    cache = tmp_path / "bls_cache"
    monkeypatch.setattr(bls_data, "CACHE_DIR", cache)
    return cache


# ---------------------------------------------------------------------------
# _parse_bls: exact values and upstream schema shifts
# ---------------------------------------------------------------------------


def test_parse_bls_returns_exact_sorted_float_series():
    series = bls_data._parse_bls(_bls_json(), BLS_SID)

    assert series.name == BLS_SID
    assert series.dtype == "float64"
    assert series.index[0] == pd.Timestamp("2020-01-01")
    assert series.index[1] == pd.Timestamp("2020-02-01")
    assert list(series.to_numpy()) == [1.5, 2.5]


def test_parse_bls_coerces_dash_and_non_numeric_to_nan():
    text = json.dumps(
        {
            "series": [
                {
                    "seriesID": "X",
                    "data": [
                        {"year": "2020", "period": "M01", "value": "-"},
                        {"year": "2020", "period": "M02", "value": "n/a"},
                        {"year": "2020", "period": "M03", "value": "3.5"},
                    ],
                }
            ]
        }
    )
    series = bls_data._parse_bls(text, "X")

    assert pd.isna(series.iloc[0])
    assert pd.isna(series.iloc[1])
    assert series.iloc[2] == 3.5


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (json.dumps({"series": []}), "no series data in response"),
        (json.dumps({"series": None}), "no series data in response"),
        (json.dumps({"unexpected": []}), "no series data in response"),
        (json.dumps({"series": [{"seriesID": "X"}]}), "no data records in series"),
        (json.dumps({"series": [{"seriesID": "X", "data": []}]}), "empty data array"),
        ("not json at all", "unparseable response"),
        (
            json.dumps({"series": [{"seriesID": "X", "data": [{"year": "2020"}]}]}),
            "unparseable response",
        ),
        (
            json.dumps({"series": [{"seriesID": "X", "data": [{"year": "2020", "period": "M01"}]}]}),
            "unparseable response",
        ),
    ],
)
def test_parse_bls_rejects_bad_payloads(payload: str, message: str):
    with pytest.raises(BlsFetchError, match=message):
        bls_data._parse_bls(payload, "SID")


def test_parse_bls_error_carries_series_id_and_reason():
    with pytest.raises(BlsFetchError) as excinfo:
        bls_data._parse_bls("", "LNS12032194")

    assert excinfo.value.series_id == "LNS12032194"
    assert "LNS12032194" in str(excinfo.value)
    assert "unparseable response" in excinfo.value.reason


# ---------------------------------------------------------------------------
# fetch_bls_series: cache state machine
# ---------------------------------------------------------------------------


def test_unknown_sid_fails_before_any_network_call(bls_cache, fake_get):
    fake_get.install(None)

    with pytest.raises(BlsFetchError, match="not in the BLS series catalog"):
        bls_data.fetch_bls_series("NOT_A_BLS_SERIES")

    assert fake_get.calls == []


def test_fresh_cache_hit_avoids_network(bls_cache, fake_get):
    _write_cache(bls_cache / f"{BLS_SID}.json", _bls_json(), age_days=1.0)
    fake_get.install(None)

    series = bls_data.fetch_bls_series(BLS_SID)

    assert list(series) == [1.5, 2.5]
    assert fake_get.calls == []


def test_stale_cache_refetches_and_overwrites_file(bls_cache, fake_get):
    old = _bls_json(records=[{"year": "2000", "period": "M01", "value": "10.0"}])
    _write_cache(bls_cache / f"{BLS_SID}.json", old, age_days=31.0)
    new = _bls_json(records=[{"year": "2020", "period": "M01", "value": "99.0"}])
    fake_get.install(_Response(new))

    series = bls_data.fetch_bls_series(BLS_SID)

    assert series.iloc[-1] == 99.0
    assert len(fake_get.calls) == 1
    call = fake_get.calls[0]
    assert call["url"] == bls_data.BLS_API_URL
    assert call["kwargs"]["timeout"] == bls_data.REQUEST_TIMEOUT_SECONDS
    assert call["kwargs"]["headers"] == {"Content-Type": "application/json"}
    assert call["kwargs"]["json"]["seriesid"] == [BLS_SID]
    assert (bls_cache / f"{BLS_SID}.json").read_text(encoding="utf-8") == new


def test_refresh_forces_download_even_when_cache_is_fresh(bls_cache, fake_get):
    _write_cache(bls_cache / f"{BLS_SID}.json", _bls_json(), age_days=0.5)
    fake_get.install(_Response(_bls_json()))

    bls_data.fetch_bls_series(BLS_SID, refresh=True)

    assert len(fake_get.calls) == 1


def test_corrupt_cache_falls_back_to_download(bls_cache, fake_get):
    _write_cache(bls_cache / f"{BLS_SID}.json", "garbage", age_days=0.0)
    new = _bls_json()
    fake_get.install(_Response(new))

    series = bls_data.fetch_bls_series(BLS_SID)

    assert list(series) == [1.5, 2.5]
    assert len(fake_get.calls) == 1
    assert (bls_cache / f"{BLS_SID}.json").read_text(encoding="utf-8") == new


def test_corrupt_cache_with_failed_download_reports_download_error(bls_cache, fake_get):
    _write_cache(bls_cache / f"{BLS_SID}.json", "garbage", age_days=0.0)
    fake_get.install(_Response("nope", status_code=500))

    with pytest.raises(BlsFetchError, match="HTTP 500"):
        bls_data.fetch_bls_series(BLS_SID)


@pytest.mark.parametrize("status", [400, 404, 429, 500, 503])
def test_http_error_raises_and_writes_no_cache(bls_cache, fake_get, status):
    body = "rate limited" if status == 429 else "error body"
    fake_get.install(_Response(body, status_code=status))

    with pytest.raises(BlsFetchError) as excinfo:
        bls_data.fetch_bls_series(BLS_SID)

    assert excinfo.value.series_id == BLS_SID
    assert excinfo.value.reason == f"HTTP {status}: {body}"
    assert not (bls_cache / f"{BLS_SID}.json").exists()


def test_network_failure_propagates_unwrapped(bls_cache, fake_get):
    """Documented contract: requests.RequestException is not wrapped."""
    fake_get.install(requests.ConnectionError("dns failure"))

    with pytest.raises(requests.ConnectionError):
        bls_data.fetch_bls_series(BLS_SID)

    assert not (bls_cache / f"{BLS_SID}.json").exists()


def test_successful_fetch_writes_cache_then_serves_from_it(bls_cache, fake_get):
    text = _bls_json()
    fake_get.install(_Response(text))

    first = bls_data.fetch_bls_series(BLS_SID)
    cached = bls_cache / f"{BLS_SID}.json"
    assert cached.read_text(encoding="utf-8") == text

    second = bls_data.fetch_bls_series(BLS_SID)
    assert len(fake_get.calls) == 1
    pd.testing.assert_series_equal(first, second)


def test_request_payload_uses_catalog_start_and_current_year(bls_cache, fake_get):
    fake_get.install(_Response(_bls_json()))

    bls_data.fetch_bls_series(BLS_SID)

    payload = fake_get.calls[0]["kwargs"]["json"]
    assert payload["seriesid"] == [BLS_SID]
    assert payload["startyear"] == "1948"
    assert payload["endyear"] == str(datetime.now(UTC).year)
    assert payload["format"] == "json"
    assert "apikey" not in payload


def test_api_key_is_added_to_payload_only_when_supplied(bls_cache, fake_get):
    fake_get.install(_Response(_bls_json()))

    bls_data.fetch_bls_series(BLS_SID, api_key="secret-key")
    assert fake_get.calls[0]["kwargs"]["json"]["apikey"] == "secret-key"

    fake_get.calls.clear()
    fake_get.install(_Response(_bls_json()))
    bls_data.fetch_bls_series(BLS_SID, refresh=True)
    assert "apikey" not in fake_get.calls[0]["kwargs"]["json"]


# ---------------------------------------------------------------------------
# fetch_all_bls_series and clear_bls_cache
# ---------------------------------------------------------------------------


def test_fetch_all_returns_every_catalog_series(bls_cache, fake_get):
    fake_get.install(lambda sid: _Response(_bls_json(sid)))

    result = bls_data.fetch_all_bls_series()

    assert set(result) == set(bls_data.BLS_ALL_SIDS)
    assert len(fake_get.calls) == len(bls_data.BLS_ALL_SIDS)
    for sid in bls_data.BLS_ALL_SIDS:
        assert result[sid].name == sid
        assert list(result[sid]) == [1.5, 2.5]


def test_fetch_all_forwards_refresh_and_api_key(bls_cache, fake_get):
    fake_get.install(lambda sid: _Response(_bls_json(sid)))

    bls_data.fetch_all_bls_series(refresh=True, api_key="k")

    assert len(fake_get.calls) == len(bls_data.BLS_ALL_SIDS)
    for call in fake_get.calls:
        payload = call["kwargs"]["json"]
        assert payload["apikey"] == "k"
        assert payload["seriesid"] == [call["sid"]]


def test_clear_bls_cache_missing_directory_is_noop(bls_cache):
    assert not bls_cache.exists()

    bls_data.clear_bls_cache()

    assert not bls_cache.exists()


def test_clear_bls_cache_deletes_every_catalog_json_only(bls_cache):
    bls_cache.mkdir(parents=True)
    for sid in bls_data.BLS_ALL_SIDS:
        (bls_cache / f"{sid}.json").write_text("{}", encoding="utf-8")
    unrelated = bls_cache / "unrelated.json"
    unrelated.write_text("{}", encoding="utf-8")

    bls_data.clear_bls_cache()

    for sid in bls_data.BLS_ALL_SIDS:
        assert not (bls_cache / f"{sid}.json").exists()
    assert unrelated.exists()
