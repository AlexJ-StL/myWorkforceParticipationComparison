"""BLS API v2 client with local raw-data cache.

BLS series are fetched from the BLS Public Data API v2 endpoint and cached
verbatim under ``data/raw/`` so that analyses are reproducible offline and BLS
is not re-hit on every run. Cached files older than ``CACHE_MAX_AGE_DAYS`` are
re-downloaded automatically.

Network-level failures (DNS, timeouts, connection resets) propagate as
``requests.RequestException``; HTTP error responses are wrapped in
``BlsFetchError``.
"""

from __future__ import annotations

import io
import time
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import cast, Any, TypedDict

import pandas as pd
import requests

from series import BY_SID

CACHE_DIR = Path(__file__).resolve().parent / "data" / "raw"
BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
BLS_API_VERSION = "2"
CACHE_MAX_AGE_DAYS = 30
REQUEST_TIMEOUT_SECONDS = 30


class BlsFetchError(Exception):
    """Raised when a BLS series cannot be fetched or parsed."""

    def __init__(self, series_id: str, reason: str) -> None:
        super().__init__(f"Failed to fetch {series_id}: {reason}")
        self.series_id = series_id
        self.reason = reason


class BlsResponse(TypedDict):
    """Typed shape for a single BLS API response record."""

    seriesID: str
    year: str
    period: str
    value: str
    footnote_codes: str
    periodName: str


@dataclass(frozen=True)
class BlsSeriesSpec:
    """Metadata for a BLS series."""

    sid: str
    label: str
    short: str
    units: str


BLS_SERIES: tuple[BlsSeriesSpec, ...] = (
    # Average weekly hours worked at work in nonagricultural industries
    BlsSeriesSpec(
        "LNS12032194",
        "Average weekly hours worked at work in nonagricultural industries - Men (16 years and over)",
        "Men weekly hours",
        "hours_per_week",
    ),
    BlsSeriesSpec(
        "LNS12032195",
        "Average weekly hours worked at work in nonagricultural industries - Women (16 years and over)",
        "Women weekly hours",
        "hours_per_week",
    ),
)


BLs_SERIES_DICT: dict[str, BlsSeriesSpec] = {spec.sid: spec for spec in BLS_SERIES}


BLS_ALL_SIDS: tuple[str, ...] = tuple(BLBS_SERIES_DICT)


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
        api_key: BLS API key. If None, use unauthenticated requests (rate limited).
    """
    if sid not in BLBS_SERIES_DICT:
        raise BlsFetchError(sid, "not in the BLS series catalog")

    path = CACHE_DIR / f"{sid}.json"
    if path.exists() and not refresh and not _is_stale(path, max_age_days):
        try:
            return _parse_bls(path.read_text(encoding="utf-8"), sid)
        except BlsFetchError:
            pass  # corrupt/truncated cache: fall through to re-download

    headers = {"Content-Type": "application/json"}
    payload = {
        "seriesid": [sid],
        "startyear": "1948",
        "endyear": str(datetime.now(UTC).year),
        "format": "json",
    }
    if api_key:
        payload["apikey"] = api_key

    response = requests.post(
        BLS_API_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
    )
    if response.status_code != 200:
        raise BlsFetchError(sid, f"HTTP {response.status_code}: {response.text}")

    series = _parse_bls(response.text, sid)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(response.text, encoding="utf-8")
    return series


def fetch_all_bls_series(*, refresh: bool = False, api_key: str | None = None) -> dict[str, pd.Series]:
    """Fetch every BLS series in the catalog."""
    return {sid: fetch_bls_series(sid, refresh=refresh, api_key=api_key) for sid in BLS_ALL_SIDS}


def clear_bls_cache() -> None:
    """Delete all cached BLS series files."""
    if not CACHE_DIR.exists():
        return
    for path in CACHE_DIR.glob("*.json"):
        path.unlink()


def _is_stale(path: Path, max_age_days: float) -> bool:
    age_days = (time.time() - path.stat().st_mtime) / 86400
    return age_days > max_age_days


def _parse_bls(text: str, sid: str) -> pd.Series:
    """Parse BLS JSON API response into a pandas Series."""
    import json

    try:
        response_data = json.loads(text)
        if "series" not in response_data or not response_data["series"]:
            raise BlsFetchError(sid, "no series data in response")

        series_data = response_data["series"][0]
        if "data" not in series_data:
            raise BlsFetchError(sid, "no data records in series")

        records: list[BlsResponse] = series_data["data"]
        if not records:
            raise BlsFetchError(sid, "empty data array")

        # Convert to DataFrame then Series with YYYY-MM-01 index
        df = pd.DataFrame(records)

        # Convert year + period to YYYY-MM-01 date string
        df["date"] = df.apply(
            lambda row: f"{row['year']}-{row['period'].replace('M', '')}-01",
            axis=1,
        )

        # Convert value to float, handling '-' as NaN
        df["value"] = pd.to_numeric(df["value"], errors="coerce")

        # Sort by date
        df = df.sort_values("date")

        # Set date as index and return Series
        return pd.Series(df["value"].values, index=pd.DatetimeIndex(df["date"]), name=sid)

    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise BlsFetchError(sid, f"unparseable response: {exc}") from exc


def _extract_year_month(date_str: str) -> tuple[int, int]:
    """Extract year and month from YYYY-MM-DD date string."""
    year, month, _ = map(int, date_str.split("-", 2))
    return year, month


def _year_month_to_ordinal(year_month: tuple[int, int]) -> float:
    """Convert (year, month) to ordinal for OLS calculations."""
    year, month = year_month
    return (year - 1948) * 12 + (month - 1)
