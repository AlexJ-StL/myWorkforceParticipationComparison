"""Shared helpers for the FRED and BLS data clients.

These helpers are intentionally private to the package: they exist to keep
cache-staleness and date-handling logic in one place instead of duplicating it
within ``fred_data.py``.
"""

from __future__ import annotations

import time
from pathlib import Path


def _is_stale(path: Path, max_age_days: float) -> bool:
    """Return True when the cached file is older than ``max_age_days``."""
    age_days = (time.time() - path.stat().st_mtime) / 86400
    return age_days > max_age_days


def _extract_year_month(date_str: str) -> tuple[int, int]:
    """Extract year and month from YYYY-MM-DD date string."""
    year, month, _ = map(int, date_str.split("-", 2))
    return year, month


def _year_month_to_ordinal(year_month: tuple[int, int]) -> float:
    """Convert (year, month) to ordinal for OLS calculations."""
    year, month = year_month
    return (year - 1948) * 12 + (month - 1)
