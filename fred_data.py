"""Client for FRED and BLS series with local raw-data cache.

Series are fetched from their public endpoints and cached verbatim under
``data/raw/`` so that analyses are reproducible offline and the APIs are not
re-hit on every run. Cached files older than ``CACHE_MAX_AGE_DAYS`` are
re-downloaded automatically.

Network-level failures propagate as ``requests.RequestException``; HTTP error
responses are wrapped in ``FetchError``.
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

from data_common import _is_stale
from series import BLS_BY_SID, BY_SID

CACHE_DIR = Path(__file__).resolve().parent / "data" / "raw"
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
CACHE_MAX_AGE_DAYS = 30
REQUEST_TIMEOUT_SECONDS = 30


class FetchError(Exception):
    """Raised when a FRED or BLS series cannot be fetched or parsed."""

    def __init__(self, series_id: str, reason: str) -> None:
        super().__init__(f"Failed to fetch {series_id}: {reason}")
        self.series_id = series_id
        self.reason = reason


# Alias for backward compatibility with existing code that uses FredFetchError
FredFetchError = FetchError


def fetch_all(
    *,
    refresh: bool = False,
    max_age_days: float = CACHE_MAX_AGE_DAYS,
    bls_api_key: str | None = None,
) -> dict[str, pd.Series]:
    """Fetch every FRED and BLS series in the catalog.

    Returns a single dictionary combining FRED and BLS series.
    """
    result = {}

    # Fetch all FRED series
    for sid in BY_SID:
        result[sid] = fetch_fred_series(sid, refresh=refresh, max_age_days=max_age_days)

    # Fetch all BLS series
    for sid in BLS_BY_SID:
        result[sid] = fetch_bls_series(
            sid, refresh=refresh, max_age_days=max_age_days, api_key=bls_api_key
        )

    return result


def fetch_fred_series(
    sid: str,
    *,
    refresh: bool = False,
    max_age_days: float = CACHE_MAX_AGE_DAYS,
) -> pd.Series:
    """Return one FRED series, using the local cache when fresh.

    Args:
        sid: FRED series ID (must be in the catalog).
        refresh: Force a re-download even if a fresh cache exists.
        max_age_days: Maximum age of a cache hit before re-downloading.
    """
    if sid not in BY_SID:
        raise FetchError(sid, "not in the series catalog")

    path = CACHE_DIR / f"{sid}.csv"
    if path.exists() and not refresh and not _is_stale(path, max_age_days):
        try:
            return _parse_fred_csv(path.read_text(encoding="utf-8"), sid)
        except FetchError:
            pass  # corrupt/truncated cache: fall through to re-download

    response = requests.get(
        FRED_CSV_URL, params={"id": sid}, timeout=REQUEST_TIMEOUT_SECONDS
    )
    if response.status_code != 200:
        raise FetchError(sid, f"HTTP {response.status_code}")

    series = _parse_fred_csv(response.text, sid)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(response.text, encoding="utf-8")
    return series


def fetch_bls_series(
    sid: str,
    *,
    refresh: bool = False,
    max_age_days: float = CACHE_MAX_AGE_DAYS,
    api_key: str | None = None,
) -> pd.Series:
    """Return one BLS series, using the local cache when fresh.

    Args:
        sid: BLS series ID (must be in the catalog).
        refresh: Force a re-download even if a fresh cache exists.
        max_age_days: Maximum age of a cache hit before re-downloading.
        api_key: BLS API key. If None, use unauthenticated requests.
    """
    if sid not in BLS_BY_SID:
        raise FetchError(sid, "not in the BLS series catalog")

    path = CACHE_DIR / f"{sid}.json"
    if path.exists() and not refresh and not _is_stale(path, max_age_days):
        try:
            return _parse_bls_json(path.read_text(encoding="utf-8"), sid)
        except FetchError:
            pass  # corrupt/truncated cache: fall through to re-download

    end_year = datetime.now(UTC).year
    years_per_request = 20 if api_key else 10
    records: list[dict] = []
    for start_year in range(1948, end_year + 1, years_per_request):
        chunk_end_year = min(start_year + years_per_request - 1, end_year)
        payload = {
            "seriesid": [sid],
            "startyear": str(start_year),
            "endyear": str(chunk_end_year),
            "format": "json",
        }
        if api_key:
            payload["apikey"] = api_key

        response = requests.post(
            BLS_API_URL, json=payload, timeout=REQUEST_TIMEOUT_SECONDS
        )
        if response.status_code != 200:
            raise FetchError(sid, f"HTTP {response.status_code}: {response.text}")
        try:
            response_data = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise FetchError(sid, f"unparseable response: {exc}") from exc

        if not isinstance(response_data, dict):
            raise FetchError(sid, "unexpected response shape (expected an object)")
        if response_data.get("status") != "REQUEST_SUCCEEDED":
            messages = response_data.get("message", [])
            if not isinstance(messages, list):
                messages = [messages]
            message = "; ".join(str(item) for item in messages)
            raise FetchError(sid, f"BLS API request failed: {message}")
        results = response_data.get("Results")
        series_data = results.get("series", []) if isinstance(results, dict) else []
        if not series_data or not isinstance(series_data[0].get("data"), list):
            raise FetchError(sid, "no series data in response")
        records.extend(series_data[0]["data"])

    cached_response = json.dumps({"series": [{"seriesID": sid, "data": records}]})
    series = _parse_bls_json(cached_response, sid)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(cached_response, encoding="utf-8")
    return series


def clear_cache() -> None:
    """Delete all cached raw series files."""
    if not CACHE_DIR.exists():
        return
    for path in CACHE_DIR.glob("*.*"):
        path.unlink()


def _parse_fred_csv(text: str, sid: str) -> pd.Series:
    """Parse FRED's CSV response into a pandas Series."""
    try:
        frame = pd.read_csv(io.StringIO(text), parse_dates=[0], na_values=["."])
        if frame.shape[1] < 2:
            raise FetchError(sid, f"unexpected response shape {frame.shape}")
        if frame.shape[0] < 1:
            raise FetchError(sid, "unexpected response shape (0 data rows)")

        values = frame.iloc[:, 1].astype(float)
        index = pd.DatetimeIndex(frame.iloc[:, 0])
        if not index.is_monotonic_increasing:
            sort_idx = index.argsort()
            index = index[sort_idx]
            values = values.iloc[sort_idx]

    except (ValueError, TypeError) as exc:
        raise FetchError(sid, f"unparseable response: {exc}") from exc

    return pd.Series(values.to_numpy(), index=index, name=sid)


def _parse_bls_json(text: str, sid: str) -> pd.Series:
    """Parse BLS JSON API response into a pandas Series."""
    try:
        response_data = json.loads(text)

        # Handle BLS API v2.0 response format
        # Response has: {"status": "REQUEST_SUCCEEDED", "Results": {"series": [...]}}
        if "Results" in response_data and "series" in response_data["Results"]:
            series_data = response_data["Results"]["series"]
        else:
            # Fallback for older API formats that might have series at top level
            if "series" not in response_data or not response_data["series"]:
                raise FetchError(sid, "no series data in response")
            series_data = response_data["series"]

        if not series_data:
            raise FetchError(sid, "empty series array")

        series_item = series_data[0]
        if "data" not in series_item:
            raise FetchError(sid, "no data records in series")

        records = series_item["data"]
        if not records:
            raise FetchError(sid, "empty data array")

        df = pd.DataFrame(records)

        df["date"] = df.apply(
            lambda row: f"{row['year']}-{row['period'].replace('M', '')}-01", axis=1
        )

        df["value"] = pd.to_numeric(df["value"], errors="coerce")

        df = df.sort_values("date")

        return pd.Series(
            df["value"].values, index=pd.DatetimeIndex(df["date"]), name=sid
        )

    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise FetchError(sid, f"unparseable response: {exc}") from exc
