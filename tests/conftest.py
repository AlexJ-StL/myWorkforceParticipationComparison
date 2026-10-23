"""Shared fixtures: offline synthetic data, cache isolation, and test doubles.

The synthetic dataset mirrors the shape of the real FRED pipeline:

* monthly series run 1948-01..2026-09; every CPS series **and** CPIAUCSL are NaN
    at 2025-10 (shutdown), while POPTHM / CES / AHETPI keep a value there;
* CES0500000003 starts 2006-03 and AHETPI starts 1964-01, so the hourly frame has
    leading NaNs;
* BLS weekly hours series run 1948-01..2026-09 with Oct 2025 gap;
* quarterly earnings series run 1979-01..2026-04;
* labor force levels are constructed so that ``men + women == total`` exactly and
  ``labor_force / population * 100`` reproduces the published rates exactly, so
    the consistency checks can be pinned to 0.0.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import fred_data
import labor_data
from analysis import compute_stats

MONTHLY_START = "1948-01-01"
MONTHLY_END = "2026-09-01"
QUARTERLY_START = "1979-01-01"
QUARTERLY_END = "2026-04-01"
GAP_MONTH = "2025-10-01"

# Monthly series that are NaN at the October 2025 shutdown (CPS + CPI in the
# real cache); POPTHM / CES0500000003 / AHETPI have values there.
MONTHLY_GAPPED = (
    "CIVPART",
    "LNS11300001",
    "LNS11300002",
    "CLF16OV",
    "LNS11000001",
    "LNS11000002",
    "CNP16OV",
    "LNU00000001",
    "LNU00000002",
    "CE16OV",
    "LNS12000001",
    "LNS12000002",
    "UNRATE",
    "LNS14000001",
    "LNS14000002",
    "CPIAUCSL",
    "LNS12032194",
    "LNS12032195",
    "LNS11300060",
    "LNS11324230",
    "LNU00000012",
    "LNU00000060",
    "LNU00024230",
)


class FakeResponse:
    """Minimal requests.Response double."""

    def __init__(self, text: str = "", status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code


# ---------------------------------------------------------------------------
# global test isolation
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    """Never read or write the real data/raw cache from a test."""
    monkeypatch.setattr(fred_data, "CACHE_DIR", tmp_path / "cache")
    yield


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Fail loudly on any unmocked network call."""

    def guard(url, *args, **kwargs):
        msg = f"unmocked network call to {url}"
        raise AssertionError(msg)

    monkeypatch.setattr(fred_data.requests, "get", guard)
    monkeypatch.setattr(fred_data.requests, "post", guard)


# ---------------------------------------------------------------------------
# synthetic FRED data
# ---------------------------------------------------------------------------


def _monthly_index() -> pd.DatetimeIndex:
    return pd.date_range(MONTHLY_START, MONTHLY_END, freq="MS")


def _covid_dip(index: pd.DatetimeIndex, depth: float) -> np.ndarray:
    """Deterministic triangle dip peaking at 2020-04."""
    offsets = {
        "2020-03-01": -0.2,
        "2020-04-01": -1.0,
        "2020-05-01": -0.6,
        "2020-06-01": -0.3,
    }
    return np.array([offsets.get(day.strftime("%Y-%m-%d"), 0.0) for day in index]) * depth


def _build_monthly() -> dict[str, pd.Series]:
    index = _monthly_index()
    n = len(index)
    dip = _covid_dip(index, 3.0)

    men_rate = np.linspace(86.6, 68.6, n) + dip
    women_rate = np.concatenate(
        [
            np.linspace(33.0, 57.5, 625),
            np.linspace(57.5, 58.5, n - 625),
        ]
    ) + _covid_dip(index, 2.5)
    pop_men = np.linspace(56100.0, 136000.0, n)
    pop_women = np.linspace(57500.0, 139000.0, n)
    pop_total = pop_men + pop_women
    rate_total = (men_rate * pop_men + women_rate * pop_women) / pop_total

    lf_men = men_rate / 100.0 * pop_men
    lf_women = women_rate / 100.0 * pop_women
    lf_total = lf_men + lf_women

    employment = lf_total * 0.94
    unrate = np.linspace(3.8, 4.6, n)

    youth_share = np.linspace(0.20, 0.17, n)
    prime_share = np.linspace(0.55, 0.53, n)
    older_share = 1.0 - youth_share - prime_share
    pop_youth = pop_total * youth_share
    pop_prime = pop_total * prime_share
    pop_older = pop_total * older_share

    prime_rate_men = np.linspace(90.0, 89.0, n) + 0.5 * _covid_dip(index, 3.0)
    prime_rate_women = np.linspace(73.0, 77.0, n) + 0.5 * _covid_dip(index, 2.5)
    prime_rate = (prime_rate_men + prime_rate_women) / 2.0
    older_rate = np.linspace(35.0, 40.0, n) + 0.5 * _covid_dip(index, 1.5)

    series = {
        "CIVPART": rate_total,
        "LNS11300001": men_rate,
        "LNS11300002": women_rate,
        "CLF16OV": lf_total,
        "LNS11000001": lf_men,
        "LNS11000002": lf_women,
        "CNP16OV": pop_total,
        "LNU00000001": pop_men,
        "LNU00000002": pop_women,
        "CE16OV": employment,
        "LNS12000001": lf_men * 0.94,
        "LNS12000002": lf_women * 0.94,
        "UNRATE": unrate,
        "LNS14000001": unrate + 0.2,
        "LNS14000002": unrate - 0.1,
        "CPIAUCSL": np.linspace(24.1, 330.0, n),
        "POPTHM": pop_total * 2.15,
        "AHETPI": np.linspace(2.50, 31.0, n),
        "LNS12032194": np.linspace(40.0, 42.0, n),  # BLS men weekly hours
        "LNS12032195": np.linspace(35.0, 37.0, n),  # BLS women weekly hours
        "LNS11300060": prime_rate,
        "LNS11324230": older_rate,
        "LNU00000012": pop_youth,
        "LNU00000060": pop_prime,
        "LNU00024230": pop_older,
    }
    out = {sid: pd.Series(values, index=index, name=sid) for sid, values in series.items()}

    # CES0500000003 starts 2006-03 in the real cache.
    ces_index = pd.date_range("2006-03-01", MONTHLY_END, freq="MS")
    out["CES0500000003"] = pd.Series(np.linspace(20.04, 36.85, len(ces_index)), index=ces_index, name="CES0500000003")

    for sid in MONTHLY_GAPPED:
        out[sid].loc[pd.Timestamp(GAP_MONTH)] = np.nan
    return out


def _build_quarterly() -> dict[str, pd.Series]:
    index = pd.date_range(QUARTERLY_START, QUARTERLY_END, freq="QS")
    n = len(index)
    series = {
        "LES1252881500Q": np.linspace(270.0, 1280.0, n),
        "LES1252881800Q": np.linspace(340.0, 1420.0, n),
        "LES1252882700Q": np.linspace(205.0, 1160.0, n),
        "LES1252881600Q": np.linspace(380.0, 455.0, n),
        "LES1252881900Q": np.linspace(435.0, 445.0, n),
        "LES1252882800Q": np.linspace(260.0, 430.0, n),
    }
    return {sid: pd.Series(values, index=index, name=sid) for sid, values in series.items()}


@pytest.fixture
def synthetic_raw() -> dict[str, pd.Series]:
    """A complete catalog-shaped raw mapping, built from scratch each test."""
    raw = _build_monthly()
    raw.update(_build_quarterly())
    return raw


@pytest.fixture
def synthetic_data(synthetic_raw) -> labor_data.WorkforceData:
    return labor_data.assemble(synthetic_raw)


@pytest.fixture
def synthetic_stats(synthetic_data) -> dict:
    return compute_stats(synthetic_data)


# ---------------------------------------------------------------------------
# test doubles and helpers
# ---------------------------------------------------------------------------


class GetDouble:
    """requests.get/post double with call recording, installed on demand."""

    def __init__(self, monkeypatch) -> None:
        self.calls: list[dict] = []
        self._monkeypatch = monkeypatch

    def install(self, response) -> None:
        def double(url, *args, **kwargs):
            # Extract sid from various places
            sid = None
            if args:
                sid = args[0]
            elif kwargs.get("params"):
                sid = kwargs["params"].get("id")
            elif kwargs.get("json"):
                sid_list = kwargs["json"].get("seriesid")
                if sid_list:
                    sid = sid_list[0]

            self.calls.append({"url": url, "args": args, "kwargs": kwargs, "sid": sid})
            if isinstance(response, Exception):
                raise response
            if callable(response):
                return response(sid)
            return response

        self._monkeypatch.setattr(fred_data.requests, "get", double)
        self._monkeypatch.setattr(fred_data.requests, "post", double)


@pytest.fixture
def fake_get(monkeypatch) -> GetDouble:
    """Install a requests.get/post double; records every call.

    Usage::

        fake_get.install(FakeResponse(text=..., status_code=200))
        fake_get.install(lambda sid: FakeResponse(text=csv_for(sid)))
        fake_get.install(requests.ConnectionError())
    """
    return GetDouble(monkeypatch)


@pytest.fixture
def write_cache():
    """Write a CSV into the (isolated) FRED cache with a controlled age."""

    def _write(sid: str, text: str, *, age_days: float = 0.0) -> Path:
        path = fred_data.CACHE_DIR / f"{sid}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if age_days:
            stamp = time.time() - age_days * 86400
            os.utime(path, (stamp, stamp))
        return path

    return _write


@pytest.fixture
def fred_csv() -> str:
    """A small but structurally valid FRED CSV."""
    return "observation_date,TEST\n2020-01-01,1.5\n2020-02-01,2.5\n2020-03-01,3.5\n"


@pytest.fixture
def outdir(tmp_path) -> Path:
    path = tmp_path / "out"
    path.mkdir()
    return path
