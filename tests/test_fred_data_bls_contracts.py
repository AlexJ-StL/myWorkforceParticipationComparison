"""Remaining BLS contract tests for ``fred_data.py``.

Target analysis
---------------
Coverage missed three ``fred_data.py`` branches in the BLS client:
``except FetchError: pass`` on a corrupt BLS cache (127-128), the API-key payload
branch (137), and the BLS HTTP-error branch (141).

Failure modes considered
------------------------
* A truncated/corrupt cached BLS JSON file must trigger a transparent re-download
    instead of a permanent failure.
* An API key supplied to ``fetch_bls_series`` must reach the POST payload.
* A 404/429/500 BLS response must raise ``FetchError`` and must not poison the
    cache with the error body.
"""

from __future__ import annotations

import json
import os
import time

import pytest

import fred_data
from fred_data import FetchError

BLS_SID = next(iter(fred_data.BLS_BY_SID))


class _Response:
    """Minimal ``requests.Response`` double."""

    def __init__(self, text: str = "", status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code


def _bls_payload(sid: str = BLS_SID) -> str:
    return json.dumps(
        {
            "status": "REQUEST_SUCCEEDED",
            "Results": {
                "series": [
                    {
                        "seriesID": sid,
                        "data": [{"year": "2020", "period": "M01", "value": "1.5"}],
                    }
                ]
            },
        }
    )


def _write_bls_cache(text: str, *, age_days: float) -> None:
    path = fred_data.CACHE_DIR / f"{BLS_SID}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    stamp = time.time() - age_days * 86400
    os.utime(path, (stamp, stamp))


def test_corrupt_bls_cache_falls_back_to_redownload(fake_get):
    _write_bls_cache("garbage", age_days=0.1)
    new = _bls_payload()
    fake_get.install(_Response(new))

    series = fred_data.fetch_bls_series(BLS_SID)

    assert list(series.to_numpy()) == [1.5] * len(fake_get.calls)
    assert len(fake_get.calls) > 1
    cached = (fred_data.CACHE_DIR / f"{BLS_SID}.json").read_text(encoding="utf-8")
    assert fred_data._parse_bls_json(cached, BLS_SID).equals(series)


def test_bls_api_key_is_added_to_payload(fake_get):
    fake_get.install(_Response(_bls_payload()))

    fred_data.fetch_bls_series(BLS_SID, api_key="secret-key")

    payloads = [call["kwargs"]["json"] for call in fake_get.calls]
    assert all(payload["apikey"] == "secret-key" for payload in payloads)
    assert all(payload["seriesid"] == [BLS_SID] for payload in payloads)


@pytest.mark.parametrize("status", [404, 429, 500])
def test_bls_http_error_raises_and_writes_no_cache(fake_get, status):
    fake_get.install(_Response("error body", status_code=status))

    with pytest.raises(FetchError) as excinfo:
        fred_data.fetch_bls_series(BLS_SID)

    assert excinfo.value.series_id == BLS_SID
    assert excinfo.value.reason == f"HTTP {status}: error body"
    assert not (fred_data.CACHE_DIR / f"{BLS_SID}.json").exists()
