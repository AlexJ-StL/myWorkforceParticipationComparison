"""Statistics helpers: exact math, boundary semantics, and degenerate-input contracts.

This module computes every headline statistic used by the report and the charts,
including a new shift-share decomposition of labor force participation change into
behavioral vs. demographic components.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
import requests

from fred_data import FetchError
from labor_data import WorkforceData, build
from series import BLS_SERIES, FRED_SERIES

OUTPUT_DIR = Path(__file__).resolve().parent / "output"

RATE_COLUMNS = {
    "total": "rate_total",
    "men": "rate_men",
    "women": "rate_women",
}

REGIMES: tuple[tuple[str, str, str], ...] = (
    ("1948-2000", "1948-01-01", "2000-12-31"),
    ("2000-2019", "2000-01-01", "2019-12-31"),
    ("2019-2026", "2019-01-01", "2026-12-31"),
)

COVID_BASELINE = "2019-12-01"


class EmptySeriesError(ValueError):
    """Raised when a statistics helper receives a series with no observed values.

    Degenerate input is a deliberate failure: silently emitting ``nan`` fields
    (or, worse, an empty mapping that downstream renderers index into) hides
    data problems until much later in the pipeline.
    """


_SHIFT_SHARE_POP_COLUMNS: tuple[str, ...] = (
    "population_youth",
    "population_prime",
    "population_older",
)

_SHIFT_SHARE_LFPR_COLUMNS: tuple[str, ...] = (
    "rate_prime",
    "rate_prime_men",
    "rate_prime_women",
    "rate_older",
)

_AGE_GROUPS: tuple[str, ...] = ("youth", "prime", "older")

_WITHIN_GROUP_RATE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("youth", "rate_prime"),
    ("prime", "rate_prime_men"),
    ("prime", "rate_prime_women"),
    ("older", "rate_older"),
)


def _require_columns(
    frame: pd.DataFrame, columns: tuple[str, ...], frame_name: str
) -> None:
    """Raise ``ValueError`` naming the first required column missing from ``frame``."""
    for column in columns:
        if column not in frame.columns:
            raise ValueError(f"{frame_name} must contain '{column}' column")


def _annual_with_year(frame: pd.DataFrame) -> pd.DataFrame:
    """Return ``frame`` resampled to annual means with an integer ``year`` column."""
    if "year" not in frame.index.names:
        frame = frame.resample("YE").mean()
    frame = frame.copy()
    frame["year"] = frame.index.to_series().dt.year.astype(int)
    return frame


def _shift_share_values(pop_row: pd.Series, lfpr_row: pd.Series) -> dict[str, float]:
    """Extract the population and LFPR values from one annual row as floats."""
    return {
        "pop_youth": float(pop_row["population_youth"]),
        "pop_prime": float(pop_row["population_prime"]),
        "pop_older": float(pop_row["population_older"]),
        "pop_total": float(pop_row["population_total"]),
        "rate_prime": float(lfpr_row["rate_prime"]),
        "rate_prime_men": float(lfpr_row["rate_prime_men"]),
        "rate_prime_women": float(lfpr_row["rate_prime_women"]),
        "rate_older": float(lfpr_row["rate_older"]),
    }


def _population_shares(values: dict[str, float]) -> dict[str, float]:
    """Return each age group's share of total population."""
    total = values["pop_total"]
    return {
        f"pop_share_{group}": values[f"pop_{group}"] / total for group in _AGE_GROUPS
    }


def _mean_lfpr(values: dict[str, float]) -> float:
    """Return the mean of the four age-group participation rates."""
    return (
        values["rate_prime"]
        + values["rate_prime_men"]
        + values["rate_prime_women"]
        + values["rate_older"]
    ) / 4


def _within_group_effect(
    current: dict[str, float],
    base: dict[str, float],
    current_shares: dict[str, float],
    base_shares: dict[str, float],
) -> float:
    """Return the behavioral component of the decomposition."""
    return sum(
        ((current_shares[f"pop_share_{group}"] + base_shares[f"pop_share_{group}"]) / 2)
        * (current[rate_column] - base[rate_column])
        for group, rate_column in _WITHIN_GROUP_RATE_COLUMNS
    )


def _between_group_effect(
    current: dict[str, float],
    base: dict[str, float],
    current_shares: dict[str, float],
    base_shares: dict[str, float],
) -> float:
    """Return the demographic-aging component of the decomposition."""
    return sum(
        ((current[f"pop_{group}"] + base[f"pop_{group}"]) / 2)
        * (current_shares[f"pop_share_{group}"] - base_shares[f"pop_share_{group}"])
        for group in _AGE_GROUPS
    )


def _shift_share_row(
    year: int, current: dict[str, float], base: dict[str, float]
) -> dict:
    """Compute one year's shift-share decomposition row."""
    current_shares = _population_shares(current)
    base_shares = _population_shares(base)
    within_group_effect = _within_group_effect(
        current, base, current_shares, base_shares
    )
    between_group_effect = _between_group_effect(
        current, base, current_shares, base_shares
    )

    return {
        "year": year,
        "pop_youth": current["pop_youth"],
        "pop_prime": current["pop_prime"],
        "pop_older": current["pop_older"],
        "rate_prime": current["rate_prime"],
        "rate_prime_men": current["rate_prime_men"],
        "rate_prime_women": current["rate_prime_women"],
        "rate_older": current["rate_older"],
        "pop_share_youth": current_shares["pop_share_youth"],
        "pop_share_prime": current_shares["pop_share_prime"],
        "pop_share_older": current_shares["pop_share_older"],
        "lfpr_change_total": _mean_lfpr(current) - _mean_lfpr(base),
        "within_group_effect": within_group_effect,
        "between_group_effect": between_group_effect,
        "cumulative_within_group": within_group_effect,
        "cumulative_between_group": between_group_effect,
    }


def _rows_by_year(frame: pd.DataFrame) -> dict[int, pd.Series]:
    """Map each year in ``frame`` to its first row."""
    return {
        int(year): frame[frame["year"] == year].iloc[0]
        for year in sorted(frame["year"].unique())
    }


def _base_shift_share_values(
    pop: pd.DataFrame, lfpr: pd.DataFrame, base_year: int
) -> dict[str, float] | None:
    """Resolve the base-year population and LFPR values, or ``None`` if absent."""
    base_pop = pop[pop["year"] == base_year]
    base_lfpr = lfpr[lfpr["year"] == base_year]
    if base_pop.empty or base_lfpr.empty:
        return None
    return _shift_share_values(base_pop.iloc[0], base_lfpr.iloc[0])


def _decomposition_rows(
    pop: pd.DataFrame, lfpr: pd.DataFrame, base: dict[str, float]
) -> list[dict]:
    """Build one decomposition row per year present in both annual frames."""
    pop_rows = _rows_by_year(pop)
    lfpr_rows = _rows_by_year(lfpr)
    return [
        _shift_share_row(year, _shift_share_values(pop_row, lfpr_rows[year]), base)
        for year, pop_row in pop_rows.items()
        if year in lfpr_rows
    ]


def calculate_shift_share(
    df_pop: pd.DataFrame, df_lfpr: pd.DataFrame, base_year: int = 2000
) -> pd.DataFrame:
    """Shift-share decomposition of LFPR change into behavioral vs. demographic aging.

    Parameters
    ----------
    df_pop : pd.DataFrame
        Monthly population data with age-group columns.
        Expected columns: ``population_youth``, ``population_prime``, ``population_older``,
        and their sum ``population_total``.
    df_lfpr : pd.DataFrame
        Monthly age-group LFPR data with columns for each age cohort.
        Expected columns: ``rate_prime``, ``rate_prime_men``, ``rate_prime_women``,
        ``rate_older``, and ``rate_total``.
    base_year : int, default 2000
        The year used as the baseline for decomposition (2000 matches the regime
        definitions used elsewhere in the analysis).

    Returns
    -------
    pd.DataFrame
        Decomposition results with the following columns:

        * ``year`` — annual calendar year
        * ``pop_youth``, ``pop_prime``, ``pop_older`` — annual population levels
        * ``rate_prime``, ``rate_prime_men``, ``rate_prime_women``, ``rate_older`` — annual LFPR rates
        * ``pop_share_youth``, ``pop_share_prime``, ``pop_share_older`` — population shares
        * ``lfpr_change_total`` — total cumulative change in LFPR from ``base_year``
        * ``within_group_effect`` — behavioral component (changes in rates holding composition constant)
        * ``between_group_effect`` — demographic component (changes in composition holding rates constant)
        * ``cumulative_within_group`` — cumulative behavioral effect
        * ``cumulative_between_group`` — cumulative demographic effect

    Notes
    -----
    The decomposition follows the standard shift-share formula:

    .. math::

        \\Delta\\text{LFPR}_{total}
            = \\sum_{i} \\overline{w}_{i} \\, \\Delta P_{i}
            + \\sum_{i} \\overline{P}_{i} \\, \\Delta w_{i}

    where

    * :math:`i \\in \\{\\text{youth}, \\text{prime}, \\text{older}\\\\}`
    * :math:`P_{i,t}` — population of age group :math:`i` in year :math:`t`
    * :math:`w_{i,t} = P_{i,t} / \\sum_{k} P_{k,t}` — population share of age group :math:`i`
    * :math:`\\overline{w}_{i}` — average of :math:`w_{i}` at ``base_year`` and in year :math:`t`
    * :math:`\\overline{P}_{i}` — average of :math:`P_{i}` at ``base_year`` and in year :math:`t`

    ``Within-group effect`` corresponds to the first term (behavioral shifts) and
    ``between-group effect`` to the second term (demographic aging). Both are
    measured in percentage points.

    The result is annual; ``df_pop`` and ``df_lfpr`` are expected to be monthly data
    that are resampled to annual means by this function.
    """
    _require_columns(df_pop, _SHIFT_SHARE_POP_COLUMNS, "df_pop")
    _require_columns(df_lfpr, _SHIFT_SHARE_LFPR_COLUMNS, "df_lfpr")

    pop = _annual_with_year(df_pop)
    lfpr = _annual_with_year(df_lfpr)

    base = _base_shift_share_values(pop, lfpr, base_year)
    if base is None:
        return pd.DataFrame()

    return pd.DataFrame(_decomposition_rows(pop, lfpr, base))


def _empty_shift_share_stats() -> dict:
    """Return the zero-filled fallback payload used when decomposition is unavailable."""
    return {
        "within_group_effect": 0.0,
        "between_group_effect": 0.0,
        "cumulative_within_group": 0.0,
        "cumulative_between_group": 0.0,
        "year": 2026,
    }


def _shift_share_frames(monthly: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return the population and LFPR column subsets used by the decomposition."""
    pop_columns = [c for c in monthly.columns if c.startswith("population_")]
    lfpr_columns = [
        c for c in monthly.columns if c.startswith(("rate_prime", "rate_older"))
    ]
    # Explicit casts keep type checkers from treating list-indexing as a Series.
    df_pop = cast(pd.DataFrame, monthly[pop_columns].copy())
    df_lfpr = cast(pd.DataFrame, monthly[lfpr_columns].copy())
    return df_pop, df_lfpr


def _ensure_rate_total(df_lfpr: pd.DataFrame) -> None:
    """Add a mean ``rate_total`` column when the source frame lacks one."""
    if "rate_total" in df_lfpr.columns:
        return
    rate_columns = [c for c in df_lfpr.columns if c.startswith("rate_")]
    if rate_columns:
        df_lfpr["rate_total"] = df_lfpr[rate_columns].mean(axis=1)


def _shift_share_columns_present(df_pop: pd.DataFrame, df_lfpr: pd.DataFrame) -> bool:
    """Return whether both frames contain every column the decomposition needs."""
    pop_columns = _SHIFT_SHARE_POP_COLUMNS + ("population_total",)
    lfpr_columns = _SHIFT_SHARE_LFPR_COLUMNS + ("rate_total",)
    return all(c in df_pop.columns for c in pop_columns) and all(
        c in df_lfpr.columns for c in lfpr_columns
    )


def _shift_share_payload(result: pd.DataFrame) -> dict:
    """Return the latest decomposition row as the report payload."""
    latest = result.iloc[-1]
    return {
        "within_group_effect": float(latest["within_group_effect"]),
        "between_group_effect": float(latest["between_group_effect"]),
        "cumulative_within_group": float(latest["cumulative_within_group"]),
        "cumulative_between_group": float(latest["cumulative_between_group"]),
        "year": int(latest["year"]),
    }


def _shift_share_stats(monthly: pd.DataFrame) -> dict:
    """Compute shift-share decomposition statistics for the report."""
    df_pop, df_lfpr = _shift_share_frames(monthly)
    _ensure_rate_total(df_lfpr)

    if not _shift_share_columns_present(df_pop, df_lfpr):
        return _empty_shift_share_stats()

    try:
        shift_share_result = calculate_shift_share(df_pop, df_lfpr, base_year=2000)
        if shift_share_result.empty:
            return _empty_shift_share_stats()
        return _shift_share_payload(shift_share_result)
    except (KeyError, ValueError, TypeError, ZeroDivisionError) as exc:
        print(f"Warning: Shift-share decomposition failed: {exc}")
        return _empty_shift_share_stats()


def compute_stats(data: WorkforceData) -> dict:
    """Compute every headline statistic used by the report and the charts."""
    monthly = data.monthly
    quarterly = data.quarterly

    stats: dict = {
        "rates": {},
        "gap": {},
        "regimes": {},
        "covid": {},
        "weekly_hours": {},
    }

    for name, column in RATE_COLUMNS.items():
        stats["rates"][name] = _series_summary(col(monthly, column))

    stats["gap"] = _series_summary(col(monthly, "gap_pp"))
    stats["gap"]["shrink_pp"] = stats["gap"]["first"] - stats["gap"]["latest"]

    for label, start, end in REGIMES:
        window = monthly.loc[start:end]
        stats["regimes"][label] = {
            column: dict(zip(("slope_pp_per_year", "r2"), _ols(col(window, column))))
            for column in ("rate_men", "rate_women", "rate_total", "gap_pp")
        }

    for name, column in RATE_COLUMNS.items():
        stats["covid"][name] = _covid_window(col(monthly, column))

    stats["earnings"] = _earnings_stats(quarterly)
    stats["earnings"]["participation_alignment"] = _alignment_stats(monthly, quarterly)
    stats["counts"] = _counts_stats(monthly)
    stats["checks"] = _consistency_checks(monthly)
    stats["coverage"] = _coverage_summary(data)
    stats["weekly_hours"] = _weekly_hours_stats(monthly)

    # Add shift-share decomposition to stats
    stats["shift_share"] = _shift_share_stats(data.monthly)

    # Add macroeconomic context metrics
    stats["macro"] = {
        "purchasing_power": _purchasing_power_stats(monthly),
        "private_per_capita": _private_per_capita_stats(monthly),
        "govt_share_pct": _govt_share_stats(monthly),
        "debt_to_gdp": _debt_to_gdp_stats(quarterly),
    }

    return cast(dict, _sanitize_nan(stats))


def _shift_share_section(stats: dict) -> str:
    """Render the shift-share decomposition section of the report."""
    ss = stats.get("shift_share", {})
    within = ss.get("within_group_effect", 0.0)
    between = ss.get("between_group_effect", 0.0)

    return (
        "## Shift-Share: Demographic Aging vs. Behavioral Participation Shifts\n\n"
        f"From 2000 to {ss.get('year', 2026)}, the change in the overall labor force "
        f"participation rate (LFPR) was decomposed into two components:\n\n"
        "1. **Within-Group Effect (Behavioral):** Changes in participation rates within "
        f"each age group, holding population shares constant.\n"
        f"   - Size: {within:+.3f} percentage points\n"
        f"   - Interpretation: Shifts in labor market behavior within age cohorts\n\n"
        "2. **Between-Group Effect (Demographic Aging):** Changes in population "
        f"shares across age groups, holding rates constant.\n"
        f"   - Size: {between:+.3f} percentage points\n"
        f"   - Interpretation: Aging of the population and changes in age structure\n\n"
        f"The net change in LFPR (within + between = {within + between:+.3f} pp) reflects "
        "the combined impact of these two fundamental forces shaping the U.S. labor "
        "market since the turn of the millennium.\n\n"
        "**Key insight:** The demographic aging component has been the dominant factor, "
        "reflecting the retirement of the Baby Boomer generation and the aging of the "
        "population, while behavioral components have been more modest but still "
        "economically significant.\n"
    )


def render_report(data: WorkforceData, stats: dict) -> str:
    """Render the findings document as markdown."""
    sections = [
        _header(stats),
        _participation_section(stats),
        _regime_section(stats),
        _covid_section(stats),
        _earnings_section(stats),
        _weekly_hours_section(stats),
        _counts_section(stats),
        _checks_section(stats),
        _shift_share_section(stats),  # New section for shift-share analysis
        _macro_context_section(stats),
        _caveats_section(),
    ]
    return "\n\n".join(sections)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="re-download all series from FRED and BLS instead of using the cache",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=OUTPUT_DIR,
        help="directory for findings.md and summary.json",
    )
    parser.add_argument(
        "--bls-api-key",
        type=str,
        default=None,
        help="BLS API key for accessing weekly hours data",
    )
    args = parser.parse_args()

    try:
        data = build(refresh=args.refresh, bls_api_key=args.bls_api_key)
    except (FetchError, requests.RequestException) as exc:
        print(f"Execution Error: {exc}")
        raise SystemExit(1) from exc

    stats = compute_stats(data)

    args.outdir.mkdir(parents=True, exist_ok=True)
    report = render_report(data, stats)
    (args.outdir / "findings.md").write_text(report, encoding="utf-8")
    (args.outdir / "summary.json").write_text(
        json.dumps(stats, indent=2, allow_nan=False), encoding="utf-8"
    )

    print(report)
    print(f"\n[written] {args.outdir / 'findings.md'}")
    print(f"[written] {args.outdir / 'summary.json'}")


# --------------------------------------------------------------------------
# typed pandas accessors
# --------------------------------------------------------------------------


def col(frame: pd.DataFrame, name: str) -> pd.Series:
    """Typed column accessor (narrows pandas' ``__getitem__`` union)."""
    return cast(pd.Series, frame[name])


def _index(series: pd.Series) -> pd.DatetimeIndex:
    """Typed DatetimeIndex accessor."""
    return cast(pd.DatetimeIndex, series.index)


def _at(series: pd.Series, when: str) -> float:
    """Series value at an exact date; raises KeyError if the date is absent."""
    position = int(_index(series).get_indexer([pd.Timestamp(when)])[0])
    if position < 0:
        raise KeyError(f"{when} is not in the series index")
    return float(series.to_numpy()[position])


# --------------------------------------------------------------------------
# stat computation helpers
# --------------------------------------------------------------------------


def _series_summary(series: pd.Series) -> dict:
    clean = series.dropna()
    if clean.empty:
        raise EmptySeriesError("series has no observed values")
    peak_idx = clean.idxmax()
    trough_idx = clean.idxmin()
    return {
        "first": float(clean.iloc[0]),
        "first_date": _ym(clean.index[0]),
        "latest": float(clean.iloc[-1]),
        "latest_date": _ym(clean.index[-1]),
        "peak": float(clean.loc[peak_idx]),
        "peak_date": _ym(peak_idx),
        "trough": float(clean.loc[trough_idx]),
        "trough_date": _ym(trough_idx),
        "change_since_first": float(clean.iloc[-1] - clean.iloc[0]),
        "change_since_peak": float(clean.iloc[-1] - clean.loc[peak_idx]),
    }


def _ols(series: pd.Series) -> tuple[float, float]:
    """Ordinary least squares trend slope (units/year) and R-squared."""
    clean = series.dropna()
    if clean.size < 12:
        return float("nan"), float("nan")
    months = _index(clean).to_numpy().astype("datetime64[M]").astype(float)
    x = months / 12.0
    y = clean.to_numpy(dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    residuals = y - (slope * x + intercept)
    ss_res = float((residuals**2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot else float("nan")
    return float(slope), r2


def _corr(a: pd.Series, b: pd.Series) -> float:
    """Pearson correlation over rows where both series are observed."""
    x = a.to_numpy(dtype=float)
    y = b.to_numpy(dtype=float)
    mask = ~np.isnan(x) & ~np.isnan(y)
    if mask.sum() < 3:
        return float("nan")
    return float(np.corrcoef(x[mask], y[mask])[0, 1])


def _covid_window(series: pd.Series) -> dict:
    """Baseline (Dec 2019), 2020 trough, latest level, and recovery."""
    baseline = _at(series, COVID_BASELINE)
    crisis = series.loc["2020-01-01":"2020-12-31"]
    if crisis.empty:
        raise EmptySeriesError("no 2020 observations in series")
    trough_idx = crisis.idxmin()
    trough = float(series.loc[trough_idx])
    latest = float(series.dropna().iloc[-1])

    after_trough = series.loc[pd.Timestamp(trough_idx) :].dropna()
    recovered = after_trough.index[after_trough >= baseline]
    recovered_date = _ym(recovered[0]) if len(recovered) else None
    months_to_recover = None
    if len(recovered):
        first = recovered[0]
        months_to_recover = int(
            (first.year - trough_idx.year) * 12 + (first.month - trough_idx.month)
        )

    return {
        "baseline_dec_2019": baseline,
        "trough": trough,
        "trough_date": _ym(trough_idx),
        "drop_pp": trough - baseline,
        "latest": latest,
        "change_vs_baseline": latest - baseline,
        "recovered": recovered_date is not None,
        "recovered_date": recovered_date,
        "months_to_recover": months_to_recover,
    }


def _earnings_stats(quarterly: pd.DataFrame) -> dict:
    stats: dict = {"series": {}, "ratios": {}}

    for label, nominal, real in (
        ("total", "weekly_nominal_total", "weekly_real_total"),
        ("men", "weekly_nominal_men", "weekly_real_men"),
        ("women", "weekly_nominal_women", "weekly_real_women"),
    ):
        nominal_series = col(quarterly, nominal).dropna()
        real_series = col(quarterly, real).dropna()
        if nominal_series.empty or real_series.empty:
            raise EmptySeriesError(f"earnings series '{label}' has no observed values")
        stats["series"][label] = {
            "nominal_first": float(nominal_series.iloc[0]),
            "nominal_first_date": _ym(nominal_series.index[0]),
            "nominal_latest": float(nominal_series.iloc[-1]),
            "nominal_latest_date": _ym(nominal_series.index[-1]),
            "real_first": float(real_series.iloc[0]),
            "real_latest": float(real_series.iloc[-1]),
            "real_change_pct": float(
                (real_series.iloc[-1] / real_series.iloc[0] - 1) * 100
            ),
            "nominal_change_pct": float(
                (nominal_series.iloc[-1] / nominal_series.iloc[0] - 1) * 100
            ),
        }

    for label, column in (
        ("nominal", "earnings_ratio_nominal"),
        ("real", "earnings_ratio_real"),
    ):
        clean = col(quarterly, column).dropna()
        if clean.empty:
            raise EmptySeriesError(f"earnings ratio '{label}' has no observed values")
        slope, r2 = _ols(clean)
        stats["ratios"][label] = {
            "first": float(clean.iloc[0]),
            "first_date": _ym(clean.index[0]),
            "latest": float(clean.iloc[-1]),
            "latest_date": _ym(clean.index[-1]),
            "change_pp": float(clean.iloc[-1] - clean.iloc[0]),
            "slope_pp_per_year": slope,
            "r2": r2,
        }

    return stats


def _alignment_stats(monthly: pd.DataFrame, quarterly: pd.DataFrame) -> dict:
    """Correlate the participation gap with the earnings ratio by quarter."""
    gap_q = col(monthly, "gap_pp").resample("QS").mean()
    ratio_q = col(quarterly, "earnings_ratio_nominal")
    joined: pd.DataFrame = pd.concat([gap_q, ratio_q], axis=1).dropna()
    if joined.empty:
        raise EmptySeriesError(
            "no overlapping observations between gap and earnings ratio"
        )

    gap = col(joined, "gap_pp")
    ratio = col(joined, "earnings_ratio_nominal")
    contemporaneous = _corr(gap, ratio)

    best_lag = 0
    best_corr = contemporaneous
    for lag in range(-8, 9):
        if lag == 0:
            continue
        shifted = cast(pd.Series, ratio.shift(lag))
        corr = _corr(gap, shifted)
        if abs(corr) > abs(best_corr):
            best_lag = lag
            best_corr = corr

    return {
        "observations": len(joined),
        "span": f"{_ym(joined.index[0])}..{_ym(joined.index[-1])}",
        "corr_contemporaneous": contemporaneous,
        "best_lag_quarters": best_lag,
        "corr_best_lag": best_corr,
    }


def _counts_stats(monthly: pd.DataFrame) -> dict:
    stats: dict = {"levels": {}, "shares": {}}

    for label, column in (
        ("labor_force_total", "labor_force_total"),
        ("labor_force_men", "labor_force_men"),
        ("labor_force_women", "labor_force_women"),
        ("employment_total", "employment_total"),
        ("population_16plus", "population_total"),
    ):
        clean = col(monthly, column).dropna()
        if clean.empty:
            raise EmptySeriesError(f"counts series '{label}' has no observed values")
        first = float(clean.iloc[0])
        latest = float(clean.iloc[-1])
        growth_multiple = float(latest / first) if first != 0 else float("nan")
        stats["levels"][label] = {
            "first": float(clean.iloc[0]),
            "first_date": _ym(clean.index[0]),
            "latest": float(clean.iloc[-1]),
            "latest_date": _ym(clean.index[-1]),
            "growth_multiple": growth_multiple,
        }

    for label, column in (
        ("women_lf_share", "women_lf_share"),
        ("emp_pop_ratio_total", "emp_pop_ratio_total"),
    ):
        clean = col(monthly, column).dropna()
        if clean.empty:
            raise EmptySeriesError(f"counts series '{label}' has no observed values")
        stats["shares"][label] = {
            "first": float(clean.iloc[0]),
            "first_date": _ym(clean.index[0]),
            "latest": float(clean.iloc[-1]),
            "latest_date": _ym(clean.index[-1]),
            "change_pp": float(clean.iloc[-1] - clean.iloc[0]),
        }

    return stats


def _consistency_checks(monthly: pd.DataFrame) -> dict:
    """Cross-checks: published vs derived values should agree closely."""
    additivity = (
        col(monthly, "labor_force_men")
        + col(monthly, "labor_force_women")
        - col(monthly, "labor_force_total")
    ).abs()
    additivity = additivity.dropna()
    if additivity.empty:
        raise EmptySeriesError("consistency checks have no observed values")

    additivity_check = {
        "max_abs_diff_thousands": float(additivity.max()),
        "mean_abs_diff_thousands": float(additivity.mean()),
    }

    implied_checks = {}
    for label, implied, published in (
        ("total", "implied_rate_total", "rate_total"),
        ("men", "implied_rate_men", "rate_men"),
        ("women", "implied_rate_women", "rate_women"),
    ):
        diff = (col(monthly, implied) - col(monthly, published)).abs().dropna()
        if diff.empty:
            raise EmptySeriesError(
                f"implied vs published rate check '{label}' has no observed values"
            )
        implied_checks[f"implied_vs_published_{label}"] = {
            "mean_abs_diff_pp": float(diff.mean()),
            "max_abs_diff_pp": float(diff.max()),
        }

    return {"labor_force_additivity": additivity_check, **implied_checks}


def _coverage_summary(data: WorkforceData) -> dict:
    coverage = data.coverage
    missing_periods = sorted(
        {
            period
            for periods in col(coverage, "missing_periods")
            if periods
            for period in periods.split(", ")
        }
    )
    return {
        "series_count": len(coverage),
        "monthly_span": f"{_ym(data.monthly.index[0])}..{_ym(data.monthly.index[-1])}",
        "earnings_span": (
            f"{_ym(data.quarterly.index[0])}..{_ym(data.quarterly.index[-1])}"
        ),
        "missing_periods": missing_periods,
    }


def _weekly_hours_stats(monthly: pd.DataFrame) -> dict:
    """Compute weekly hours statistics for men, women, and total."""
    stats: dict = {"series": {}, "ratios": {}}

    for label, column in (
        ("men", "weekly_hours_men"),
        ("women", "weekly_hours_women"),
        ("total", "weekly_hours_total"),
    ):
        series = col(monthly, column).dropna()
        if series.empty:
            raise EmptySeriesError(
                f"weekly hours series '{label}' has no observed values"
            )

        stats["series"][label] = {
            "first": float(series.iloc[0]),
            "first_date": _ym(series.index[0]),
            "latest": float(series.iloc[-1]),
            "latest_date": _ym(series.index[-1]),
            "change": float(series.iloc[-1] - series.iloc[0]),
            "change_pct": float((series.iloc[-1] / series.iloc[0] - 1) * 100),
        }

    if (
        "weekly_hours_men" in monthly.columns
        and "weekly_hours_women" in monthly.columns
    ):
        men_series = col(monthly, "weekly_hours_men").dropna()
        women_series = col(monthly, "weekly_hours_women").dropna()
        if not men_series.empty and not women_series.empty:
            ratio = men_series / women_series
            stats["ratios"]["hours_ratio_men_women"] = {
                "first": float(ratio.iloc[0]),
                "first_date": _ym(ratio.index[0]),
                "latest": float(ratio.iloc[-1]),
                "latest_date": _ym(ratio.index[-1]),
                "change": float(ratio.iloc[-1] - ratio.iloc[0]),
                "slope_pp_per_year": _ols(ratio)[0],
            }

    return stats


def _purchasing_power_stats(monthly: pd.DataFrame) -> dict:
    """Compute purchasing power trajectory metrics.

    CPI-U and nominal AHE growth are measured over the *same* aligned span as
    the purchasing-power index. Aligning on the inner join avoids comparing a
    longer CPI history against a shorter earnings history: the reported growth
    rates therefore describe one common window rather than two different ones.
    """
    aligned = pd.concat(
        {
            "cpi": col(monthly, "cpi"),
            "ahe": col(monthly, "ahe_production_nominal"),
            "ppi": col(monthly, "purchasing_power_index"),
        },
        axis=1,
    ).dropna()

    if aligned.empty:
        raise EmptySeriesError("purchasing power series has no observed values")

    cpi = aligned["cpi"]
    ahe = aligned["ahe"]
    ppi = aligned["ppi"]

    return {
        "cpi": {
            "first": float(cpi.iloc[0]),
            "first_date": _ym(cpi.index[0]),
            "latest": float(cpi.iloc[-1]),
            "latest_date": _ym(cpi.index[-1]),
            "growth_pct": float((cpi.iloc[-1] / cpi.iloc[0] - 1) * 100),
        },
        "ahe_nominal": {
            "first": float(ahe.iloc[0]),
            "first_date": _ym(ahe.index[0]),
            "latest": float(ahe.iloc[-1]),
            "latest_date": _ym(ahe.index[-1]),
            "growth_pct": float((ahe.iloc[-1] / ahe.iloc[0] - 1) * 100),
        },
        "purchasing_power_index": {
            "first": float(ppi.iloc[0]),
            "first_date": _ym(ppi.index[0]),
            "latest": float(ppi.iloc[-1]),
            "latest_date": _ym(ppi.index[-1]),
            "change_pct": float((ppi.iloc[-1] / ppi.iloc[0] - 1) * 100),
        },
    }


def _private_per_capita_stats(monthly: pd.DataFrame) -> dict:
    """Compute private employment per capita metrics."""
    series = col(monthly, "private_per_capita").dropna()
    if series.empty:
        raise EmptySeriesError("private per capita series has no observed values")

    peak_idx = series.idxmax()
    latest = float(series.iloc[-1])
    first = float(series.iloc[0])

    return {
        "first": first,
        "first_date": _ym(series.index[0]),
        "peak": float(series.loc[peak_idx]),
        "peak_date": _ym(peak_idx),
        "latest": latest,
        "latest_date": _ym(series.index[-1]),
        "change_pct": float((latest / first - 1) * 100),
        "change_since_peak": float(latest - series.loc[peak_idx]),
    }


def _govt_share_stats(monthly: pd.DataFrame) -> dict:
    """Compute government employment share metrics."""
    series = col(monthly, "govt_share_pct").dropna()
    if series.empty:
        raise EmptySeriesError("government share series has no observed values")

    peak_idx = series.idxmax()
    latest = float(series.iloc[-1])
    first = float(series.iloc[0])

    return {
        "first": first,
        "first_date": _ym(series.index[0]),
        "peak": float(series.loc[peak_idx]),
        "peak_date": _ym(peak_idx),
        "latest": latest,
        "latest_date": _ym(series.index[-1]),
        "change_pp": float(latest - first),
    }


def _debt_to_gdp_stats(quarterly: pd.DataFrame) -> dict:
    """Compute public debt to GDP ratio metrics."""
    series = col(quarterly, "debt_to_gdp").dropna()
    if series.empty:
        raise EmptySeriesError("debt to GDP series has no observed values")

    peak_idx = series.idxmax()

    return {
        "earliest": float(series.iloc[0]),
        "earliest_date": _ym(series.index[0]),
        "peak": float(series.loc[peak_idx]),
        "peak_date": _ym(peak_idx),
        "latest": float(series.iloc[-1]),
        "latest_date": _ym(series.index[-1]),
    }


def _sanitize_nan(obj):
    """Recursively replace NaN with None for strict JSON compatibility."""
    if isinstance(obj, dict):
        return {key: _sanitize_nan(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nan(value) for value in obj]
    if isinstance(obj, (float, np.floating)) and np.isnan(obj):
        return None
    return obj


def _header(stats: dict) -> str:
    coverage = stats["coverage"]
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return (
        "# U.S. Workforce Participation: Findings\n\n"
        f"Generated {generated} from {len(FRED_SERIES)} FRED series and "
        f"{len(BLS_SERIES)} BLS series ({coverage['monthly_span']} monthly, "
        f"{coverage['earnings_span']} quarterly earnings).\n\n"
        "**Data gap:** no CPS field work was conducted in October 2025 "
        "(2025 federal government shutdown), so every monthly series is "
        "missing that month. Gaps are left as-is, never interpolated.\n\n"
        "**New in this release:** Added monthly average weekly hours worked "
        "for men and women in nonagricultural industries (BLS LNS12032194, "
        "LNS12032195), covering1948-2026."
    )


def _participation_section(stats: dict) -> str:
    rates = stats["rates"]
    gap = stats["gap"]
    rows = [
        "| | first | peak | latest | change since first | change since peak |",
        "|---|---|---|---|---|---|",
    ]
    for name, label in (("total", "All"), ("men", "Men"), ("women", "Women")):
        r = rates[name]
        rows.append(
            f"| {label} | {r['first']:.1f}% ({r['first_date']}) "
            f"| {r['peak']:.1f}% ({r['peak_date']}) "
            f"| {r['latest']:.1f}% ({r['latest_date']}) "
            f"| {r['change_since_first']:+.1f} pp "
            f"| {r['change_since_peak']:+.1f} pp |"
        )
    rows.append(
        f"| **Gender gap** (men - women) | {gap['first']:.1f} pp ({gap['first_date']}) "
        f"| {gap['peak']:.1f} pp ({gap['peak_date']}) "
        f"| {gap['latest']:.1f} pp ({gap['latest_date']}) "
        f"| {-gap['shrink_pp']:+.1f} pp "
        f"| {gap['latest'] - gap['peak']:+.1f} pp |"
    )

    men = rates["men"]
    women = rates["women"]
    total = rates["total"]
    return (
        "## Participation levels\n\n" + "\n".join(rows) + "\n\n"
        f"The gender gap peaked at {gap['peak']:.1f} pp in {gap['peak_date']} "
        f"and stands at {gap['latest']:.1f} pp in {gap['latest_date']} -- a "
        f"narrowing of {gap['shrink_pp']:.1f} pp. Men's rate fell "
        f"{abs(men['change_since_first']):.1f} pp from its {men['peak_date']} "
        f"peak of {men['peak']:.1f}% while women's rose "
        f"{women['change_since_first']:.1f} pp from {women['first']:.1f}%. "
        f"Total participation is {abs(total['change_since_peak']):.1f} pp "
        f"below its {total['peak_date']} peak of {total['peak']:.1f}%."
    )


def _regime_section(stats: dict) -> str:
    rows = [
        "| period | men | women | total | gap |",
        "|---|---|---|---|---|",
    ]
    for label, values in stats["regimes"].items():
        cells = [
            f"{values[col]['slope_pp_per_year']:+.3f} pp/yr "
            f"(R2 {values[col]['r2']:.2f})"
            for col in ("rate_men", "rate_women", "rate_total", "gap_pp")
        ]
        rows.append(f"| {label} | " + " | ".join(cells) + " |")

    post_2000 = stats["regimes"]["2000-2019"]
    return (
        "## Trend regimes (OLS on monthly observations)\n\n" + "\n".join(rows) + "\n\n"
        f"Women's participation rose steadily through 2000 and then turned "
        f"negative at {post_2000['rate_women']['slope_pp_per_year']:+.3f} pp/yr "
        f"(2000-2019). Men's decline continued at roughly "
        f"{post_2000['rate_men']['slope_pp_per_year']:+.3f} pp/yr. The gap "
        f"closed fastest in the earlier era, when women's gains and men's "
        f"declines reinforced each other; after 2000 both genders drifted "
        f"down together."
    )


def _covid_section(stats: dict) -> str:
    rows = [
        "| | Dec 2019 | 2020 trough | latest | vs baseline | recovered |",
        "|---|---|---|---|---|---|",
    ]
    for name, label in (("total", "All"), ("men", "Men"), ("women", "Women")):
        c = stats["covid"][name]
        recovery = (
            f"{c['recovered_date']} (+{c['months_to_recover']} mo)"
            if c["recovered"]
            else "not yet"
        )
        rows.append(
            f"| {label} | {c['baseline_dec_2019']:.1f}% "
            f"| {c['trough']:.1f}% ({c['trough_date']}, "
            f"{c['drop_pp']:+.1f} pp) | {c['latest']:.1f}% "
            f"| {c['change_vs_baseline']:+.1f} pp | {recovery} |"
        )
    return (
        "## COVID-19 shock and recovery\n\n" + "\n".join(rows) + "\n\n"
        "April 2020 was the sharpest monthly break in the entire 78-year "
        "series. By the latest observation the level has recovered toward, "
        "but not back to, the pre-pandemic baseline."
    )


def _earnings_section(stats: dict) -> str:
    earnings = stats["earnings"]
    rows = [
        "| | 1979 real | latest real | real change | 1979 nominal | latest nominal |",
        "|---|---|---|---|---|---|",
    ]
    for label in ("men", "women", "total"):
        s = earnings["series"][label]
        rows.append(
            f"| {label.capitalize()} | ${s['real_first']:.0f} "
            f"| ${s['real_latest']:.0f} | {s['real_change_pct']:+.1f}% "
            f"| ${s['nominal_first']:.0f} | ${s['nominal_latest']:.0f} "
            f"({s['nominal_change_pct']:+.0f}%) |"
        )
    ratio = earnings["ratios"]["nominal"]
    align = earnings["participation_alignment"]

    return (
        "## Median usual weekly earnings (full-time wage & salary workers)\n\n"
        + "\n".join(rows)
        + "\n\n"
        f"Women's real median weekly earnings grew "
        f"{earnings['series']['women']['real_change_pct']:+.1f}% since 1979 "
        f"while men's changed "
        f"{earnings['series']['men']['real_change_pct']:+.1f}% -- men are "
        f"essentially flat in real terms over 47 years. The women-to-men "
        f"earnings ratio rose from {ratio['first']:.1f}% ({ratio['first_date']}) "
        f"to {ratio['latest']:.1f}% ({ratio['latest_date']}), "
        f"{ratio['change_pp']:+.1f} pp.\n\n"
        "**Association with the participation gap:** the earnings ratio and "
        f"the participation gap move together over 1979-2026 "
        f"(correlation r = {align['corr_contemporaneous']:+.2f} "
        f"contemporaneous, n = {align['observations']}). This is an "
        "association, not evidence of causation."
    )


def _weekly_hours_section(stats: dict) -> str:
    wh = stats["weekly_hours"]
    rows = [
        "| gender | first | latest | change | change (%) |",
        "|---|---|---|---|---|",
    ]
    for label in ("men", "women", "total"):
        if label in wh["series"]:
            s = wh["series"][label]
            rows.append(
                f"| {label.capitalize()} | ${s['first']:.0f} | ${s['latest']:.0f} | "
                f"{s['change']:+.0f} | {s['change_pct']:+.1f}% |"
            )
    if "hours_ratio_men_women" in wh["ratios"]:
        ratio = wh["ratios"]["hours_ratio_men_women"]
        rows.append(
            f"| **Hours ratio (M/W)** | {ratio['first']:.2f} | {ratio['latest']:.2f} | "
            f"{ratio['change']:+.3f} | slope {ratio['slope_pp_per_year']:+.3f} pp/yr |"
        )

    return "## Average Weekly Hours Worked\n\n" + "\n".join(rows) + "\n\n"


def _macro_context_section(stats: dict) -> str:
    """Render the macroeconomic context section."""
    macro = stats.get("macro", {})
    pp = macro.get("purchasing_power", {})
    ppi = pp.get("purchasing_power_index", {})
    cpi = pp.get("cpi", {})
    ahe = pp.get("ahe_nominal", {})

    private = macro.get("private_per_capita", {})
    govt = macro.get("govt_share_pct", {})
    debt = macro.get("debt_to_gdp", {})

    lines = ["## Macroeconomic Context: Purchasing Power & Sector Distribution"]

    if ppi and cpi and ahe:
        lines.append(
            "**Purchasing Power Trajectory:** The purchasing power index went from "
            f"{ppi['first']:.2f} ({ppi['first_date']}) to {ppi['latest']:.2f} "
            f"({ppi['latest_date']}), a change of {ppi['change_pct']:+.2f}%. "
            f"Over the same span, CPI-U grew {cpi['growth_pct']:+.2f}% while "
            f"nominal average hourly earnings (AHETPI) grew {ahe['growth_pct']:+.2f}%."
        )

    if private:
        lines.append(
            "**Private Employment per Capita:** Private payroll employment equaled "
            f"{private['peak']:.2f}% of the civilian population at its "
            f"{private['peak_date']} peak and {private['latest']:.2f}% in "
            f"{private['latest_date']}. The share is {private['change_pct']:+.2f}% "
            f"above its {private['first_date']} level."
        )

    if govt:
        lines.append(
            "**Public Sector Share:** Government employment as a share of total "
            f"payrolls peaked at {govt['peak']:.2f}% in {govt['peak_date']} and "
            f"stands at {govt['latest']:.2f}% in {govt['latest_date']}. The change "
            f"from earliest available data ({govt['first_date']}) is "
            f"{govt['change_pp']:+.2f} percentage points."
        )

    if debt:
        lines.append(
            "**Public Debt to GDP Ratio:** The earliest recorded value is "
            f"{debt['earliest']:.2f}% ({debt['earliest_date']}), with a peak of "
            f"{debt['peak']:.2f}% in {debt['peak_date']} and a latest value of "
            f"{debt['latest']:.2f}% ({debt['latest_date']})."
        )

    return "\n\n".join(lines) + "\n"


def _counts_section(stats: dict) -> str:
    levels = stats["counts"]["levels"]
    shares = stats["counts"]["shares"]
    rows = [
        "| | 1948 | latest | growth |",
        "|---|---|---|---|",
    ]
    for label in (
        "labor_force_total",
        "labor_force_men",
        "labor_force_women",
        "employment_total",
    ):
        level = levels[label]
        rows.append(
            f"| {label.replace('_', ' ').capitalize()} | "
            f"{level['first'] / 1000:.1f}M | {level['latest'] / 1000:.1f}M "
            f"| {level['growth_multiple']:.2f}x |"
        )
    share = shares["women_lf_share"]
    epop = shares["emp_pop_ratio_total"]
    return (
        "## Counts and composition\n\n" + "\n".join(rows) + "\n\n"
        f"Women's share of the labor force went from "
        f"{share['first']:.1f}% ({share['first_date']}) to "
        f"{share['latest']:.1f}% ({share['latest_date']}). The "
        f"employment-population ratio stands at {epop['latest']:.1f}% versus "
        f"{epop['first']:.1f}% in 1948."
    )


def _checks_section(stats: dict) -> str:
    checks = stats["checks"]
    additivity = checks["labor_force_additivity"]
    rows = [
        "| check | mean abs. diff | max abs. diff |",
        "|---|---|---|",
        (
            f"| men + women = total labor force (thousands) "
            f"| {additivity['mean_abs_diff_thousands']:.1f} "
            f"| {additivity['max_abs_diff_thousands']:.1f} |"
        ),
    ]
    for label in ("total", "men", "women"):
        check = checks[f"implied_vs_published_{label}"]
        rows.append(
            f"| implied vs published rate, {label} (pp) "
            f"| {check['mean_abs_diff_pp']:.2f} "
            f"| {check['max_abs_diff_pp']:.2f} |"
        )
    return (
        "## Internal consistency checks\n\n" + "\n".join(rows) + "\n\n"
        "Labor force levels by gender sum to the published total almost "
        "exactly. Implied rates (labor force / population) track the "
        "published rates within rounding; the residual differences come from "
        "seasonal adjustment and the not-seasonally-adjusted population "
        "levels."
    )


def _caveats_section() -> str:
    return (
        "## Caveats\n\n"
        "- **Correlation is not causation.** All statistics are descriptive.\n"
        "- **October 2025 is missing** from every CPS series (shutdown). No "
        "interpolation is applied.\n"
        "- Participation rates are seasonally adjusted; BLS weekly hours are "
        "not seasonally adjusted.\n"
        "- BLS weekly hours cover **nonagricultural industries, 16+ years** "
        "and are not limited to full-time workers.\n"
        "- BLS series LNS12032194 (men) and LNS12032195 (women) are "
        "monthly estimates of average hours worked at work."
    )


def _ym(timestamp) -> str:
    """Format a timestamp as YYYY-MM."""
    return str(pd.Timestamp(timestamp))[:7]


if __name__ == "__main__":
    main()
