"""Catalog of FRED and BLS series used for the workforce participation analysis.

This catalog includes:
- FRED series for participation rates, labor force levels, employment, population, unemployment, earnings, and price indices
- BLS series for average weekly hours worked by gender in nonagricultural industries

All monthly BLS/CPS series run 1948-01 through 2026-09, and all of them are
missing October 2025 (no CPS field work was conducted during the 2025 federal
government shutdown). The quarterly earnings series run 1979-01 through
2026-04.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Sex = Literal["total", "men", "women"]
Track = Literal["rate", "level", "price", "earnings_nominal", "earnings_real", "debt"]

PALETTE = {
    "bg": "#15202b",
    "grid": "#38444d",
    "muted": "#8899a6",
    "men": "#1da1f2",
    "women": "#f42a60",
    "total": "#ffffff",
    "accent": "#f7b32b",
}


@dataclass(frozen=True)
class SeriesSpec:
    """Metadata for a FRED series."""

    sid: str
    label: str
    short: str
    track: Track
    sex: Sex
    units: str
    seasonal: str = "SA"
    color: str = PALETTE["total"]


@dataclass(frozen=True)
class BlsSeriesSpec:
    """Metadata for a BLS series."""

    sid: str
    label: str
    short: str
    units: str


FRED_SERIES: tuple[SeriesSpec, ...] = (
    # Participation rates (%, monthly, SA) -- 1948-01..2026-09
    SeriesSpec(
        "CIVPART", "Labor Force Participation Rate", "All", "rate", "total", "percent"
    ),
    SeriesSpec(
        "LNS11300001",
        "Labor Force Participation Rate - Men",
        "Men",
        "rate",
        "men",
        "percent",
    ),
    SeriesSpec(
        "LNS11300002",
        "Labor Force Participation Rate - Women",
        "Women",
        "rate",
        "women",
        "percent",
    ),
    # Labor force levels (thousands, monthly, SA)
    SeriesSpec(
        "CLF16OV", "Civilian Labor Force Level", "All", "level", "total", "thousands"
    ),
    SeriesSpec(
        "LNS11000001",
        "Civilian Labor Force Level - Men",
        "Men",
        "level",
        "men",
        "thousands",
    ),
    SeriesSpec(
        "LNS11000002",
        "Civilian Labor Force Level - Women",
        "Women",
        "level",
        "women",
        "thousands",
    ),
    # Civilian noninstitutional population 16+ (thousands, monthly)
    SeriesSpec(
        "CNP16OV",
        "Civilian Noninstitutional Population",
        "All",
        "level",
        "total",
        "thousands",
        "SA",
    ),
    SeriesSpec(
        "LNU00000001",
        "Civilian Noninstitutional Population - Men",
        "Men",
        "level",
        "men",
        "thousands",
        "NSA",
    ),
    SeriesSpec(
        "LNU00000002",
        "Civilian Noninstitutional Population - Women",
        "Women",
        "level",
        "women",
        "thousands",
        "NSA",
    ),
    # Employment levels (thousands, monthly, SA)
    SeriesSpec("CE16OV", "Employment Level", "All", "level", "total", "thousands"),
    SeriesSpec(
        "LNS12000001", "Employment Level - Men", "Men", "level", "men", "thousands"
    ),
    SeriesSpec(
        "LNS12000002",
        "Employment Level - Women",
        "Women",
        "level",
        "women",
        "thousands",
    ),
    # Establishment-survey employment: total private and government
    # (thousands, monthly, SA)
    SeriesSpec(
        "USPRIV",
        "All Employees, Total Private",
        "Private",
        "level",
        "total",
        "thousands",
        "SA",
        color=PALETTE["total"],
    ),
    SeriesSpec(
        "USGOVT",
        "All Employees, Government",
        "Government",
        "level",
        "total",
        "thousands",
        "SA",
        color=PALETTE["accent"],
    ),
    # Unemployment rates (%, monthly, SA)
    SeriesSpec("UNRATE", "Unemployment Rate", "All", "rate", "total", "percent"),
    SeriesSpec(
        "LNS14000001", "Unemployment Rate - Men", "Men", "rate", "men", "percent"
    ),
    SeriesSpec(
        "LNS14000002", "Unemployment Rate - Women", "Women", "rate", "women", "percent"
    ),
    # Average hourly earnings (nominal $, monthly, SA)
    SeriesSpec(
        "CES0500000003",
        "Average Hourly Earnings, Total Private (2006+)",
        "All",
        "earnings_nominal",
        "total",
        "dollars_per_hour",
    ),
    SeriesSpec(
        "AHETPI",
        "Average Hourly Earnings of Production and Nonsupervisory Employees, Total Private",
        "AHE production",
        "earnings_nominal",
        "total",
        "dollars_per_hour",
        color=PALETTE["accent"],
    ),
    # Median usual weekly earnings, full-time wage & salary workers (nominal $, quarterly)
    SeriesSpec(
        "LES1252881500Q",
        "Median Usual Weekly Earnings (nominal)",
        "All",
        "earnings_nominal",
        "total",
        "dollars_per_week",
        "NSA",
    ),
    SeriesSpec(
        "LES1252881800Q",
        "Median Usual Weekly Earnings (nominal) - Men",
        "Men",
        "earnings_nominal",
        "men",
        "dollars_per_week",
        "NSA",
    ),
    SeriesSpec(
        "LES1252882700Q",
        "Median Usual Weekly Earnings (nominal) - Women",
        "Women",
        "earnings_nominal",
        "women",
        "dollars_per_week",
        "NSA",
    ),
    # Same, in constant 1982-84 dollars
    SeriesSpec(
        "LES1252881600Q",
        "Median Usual Weekly Earnings (real, 1982-84 $)",
        "All",
        "earnings_real",
        "total",
        "dollars_per_week",
        "NSA",
    ),
    SeriesSpec(
        "LES1252881900Q",
        "Median Usual Weekly Earnings (real, 1982-84 $) - Men",
        "Men",
        "earnings_real",
        "men",
        "dollars_per_week",
        "NSA",
    ),
    SeriesSpec(
        "LES1252882800Q",
        "Median Usual Weekly Earnings (real, 1982-84 $) - Women",
        "Women",
        "earnings_real",
        "women",
        "dollars_per_week",
        "NSA",
    ),
    # Price index
    SeriesSpec(
        "CPIAUCSL",
        "Consumer Price Index for All Urban Consumers: All Items",
        "CPI",
        "price",
        "total",
        "index",
        "SA",
        color=PALETTE["muted"],
    ),
    # Federal fiscal context (percent of GDP, quarterly, SA)
    SeriesSpec(
        "GFDEGDQ188S",
        "Federal Debt: Total Public Debt as Percent of Gross Domestic Product",
        "Debt/GDP",
        "debt",
        "total",
        "percent",
        "SA",
        color=PALETTE["muted"],
    ),
    # Total US population (monthly, SA) -- context only
    SeriesSpec("POPTHM", "Total US Population", "All", "level", "total", "thousands"),
    # Age-disaggregated LFPR and population (monthly, SA) -- demographics expansion
    SeriesSpec(
        "LNS11300060", "Prime 25–54 LFPR", "Prime 25–54", "rate", "total", "percent"
    ),
    SeriesSpec("LNS11324230", "55+ LFPR", "Older 55+", "rate", "total", "percent"),
    SeriesSpec(
        "LNU00000012",
        "Civilian Pop 16–24",
        "Youth 16–24",
        "level",
        "total",
        "thousands",
    ),
    SeriesSpec(
        "LNU00000060",
        "Civilian Pop 25–54",
        "Prime 25–54",
        "level",
        "total",
        "thousands",
    ),
    SeriesSpec(
        "LNU00024230", "Civilian Pop 55+", "Older 55+", "level", "total", "thousands"
    ),
)


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
    # Prime-age (25-54) labor force participation by sex. FRED mirrors only the
    # total series (LNS11300060); the sex-disaggregated series are published by
    # BLS and must be fetched through the BLS API. The BLS API caps each request
    # at 20 years with a registration key (10 without), so early years may be
    # absent from the cache; those months remain NaN rather than being imputed.
    BlsSeriesSpec(
        "LNS11300061",
        "Labor Force Participation Rate - 25-54 Yrs., Men (Seas)",
        "Prime 25-54 Men",
        "percent",
    ),
    BlsSeriesSpec(
        "LNS11300062",
        "Labor Force Participation Rate - 25-54 Yrs., Women (Seas)",
        "Prime 25-54 Women",
        "percent",
    ),
)


BY_SID: dict[str, SeriesSpec] = {spec.sid: spec for spec in FRED_SERIES}
BLS_BY_SID: dict[str, BlsSeriesSpec] = {spec.sid: spec for spec in BLS_SERIES}


ALL_FRED_SIDS: tuple[str, ...] = tuple(BY_SID)
ALL_BLS_SIDS: tuple[str, ...] = tuple(BLS_BY_SID)


def sid(sex: Sex, track: Track) -> str:
    """Series ID for a sex/track combination, e.g. sid("women", "rate")."""
    for spec in FRED_SERIES:
        if spec.sex == sex and spec.track == track:
            return spec.sid
    raise KeyError(f"No series for sex={sex!r} track={track!r}")
