"""Assemble analysis-ready datasets from FRED and BLS series.

Three frames are produced:

* ``monthly``   -- participation, labor force, employment, population, CPI, and weekly hours
* ``quarterly`` -- median usual weekly earnings (nominal and real) by gender
* ``hourly``    -- average hourly earnings, nominal and in 1982-84 dollars

Derived columns (gaps, ratios, implied rates) are added on top. All missing
observations -- notably October 2025, for which no CPS field work was done --
are left as NaN rather than silently interpolated.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

import fred_data
from series import BLS_BY_SID, BY_SID

MONTHLY_COLUMNS: dict[str, str] = {
    "CIVPART": "rate_total",
    "LNS11300001": "rate_men",
    "LNS11300002": "rate_women",
    "CLF16OV": "labor_force_total",
    "LNS11000001": "labor_force_men",
    "LNS11000002": "labor_force_women",
    "CNP16OV": "population_total",
    "LNU00000001": "population_men",
    "LNU00000002": "population_women",
    "CE16OV": "employment_total",
    "LNS12000001": "employment_men",
    "LNS12000002": "employment_women",
    "UNRATE": "unrate_total",
    "LNS14000001": "unrate_men",
    "LNS14000002": "unrate_women",
    # Macro purchasing-power and public-sector series
    "CPIAUCSL": "cpi",
    "AHETPI": "ahe_production_nominal",
    "USPRIV": "employment_private",
    "USGOVT": "employment_government",
    "POPTHM": "population_all_ages",
    "LNS12032194": "weekly_hours_men",
    "LNS12032195": "weekly_hours_women",
    # Demographics expansion series. LNS11300060 (total 25-54) is mirrored by
    # FRED; LNS11300061/62 (men/women 25-54) come from the BLS API.
    "LNS11300060": "lfpr_prime_total",
    "LNS11300061": "lfpr_prime_men",
    "LNS11300062": "lfpr_prime_women",
    "LNS11324230": "rate_older",
    "LNU00000012": "population_youth",
    "LNU00000060": "population_prime",
    "LNU00024230": "population_older",
}

QUARTERLY_COLUMNS: dict[str, str] = {
    "LES1252881500Q": "weekly_nominal_total",
    "LES1252881800Q": "weekly_nominal_men",
    "LES1252882700Q": "weekly_nominal_women",
    "LES1252881600Q": "weekly_real_total",
    "LES1252881900Q": "weekly_real_men",
    "LES1252882800Q": "weekly_real_women",
    "GFDEGDQ188S": "debt_to_gdp",
}

HOURLY_COLUMNS: dict[str, str] = {
    "CES0500000003": "ahe_nominal",
    "AHETPI": "ahe_production_nominal",
    "CPIAUCSL": "cpi",
}


@dataclass(frozen=True)
class WorkforceData:
    """Analysis-ready datasets plus a coverage report."""

    monthly: pd.DataFrame
    quarterly: pd.DataFrame
    hourly: pd.DataFrame
    coverage: pd.DataFrame


def build(
    refresh: bool = False,
    bls_api_key: str | None = None,
) -> WorkforceData:
    """Fetch (or reuse cached) series and assemble the datasets."""
    raw = fred_data.fetch_all(refresh=refresh, bls_api_key=bls_api_key)
    return assemble(raw)


def assemble(raw: dict[str, pd.Series]) -> WorkforceData:
    """Assemble datasets from an already-fetched mapping of series."""
    monthly = _frame(raw, MONTHLY_COLUMNS)
    quarterly = _frame(raw, QUARTERLY_COLUMNS)
    hourly = _frame(raw, HOURLY_COLUMNS)

    monthly = _add_derived_monthly(monthly)
    quarterly = _add_derived_quarterly(quarterly)
    hourly = _add_derived_hourly(hourly)

    return WorkforceData(
        monthly=monthly,
        quarterly=quarterly,
        hourly=hourly,
        coverage=_coverage(raw),
    )


def _frame(raw: dict[str, pd.Series], mapping: dict[str, str]) -> pd.DataFrame:
    """Join the selected series into one frame with renamed columns."""
    columns = [raw[sid].rename(name) for sid, name in mapping.items()]
    # Explicit sort=True silences Pandas4Warning about future default change.
    return pd.concat(columns, axis=1, sort=True).sort_index()


def _safe_ratio(
    numerator: pd.Series, denominator: pd.Series, *, scale: float = 100.0
) -> pd.Series:
    """Compute numerator/denominator * scale, returning NaN where denominator is zero.

    This prevents inf/0/0->nan from leaking into downstream stats and JSON output.
    """
    result = numerator / denominator * scale
    return result.where(denominator != 0)


def _add_derived_monthly(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["gap_pp"] = out["rate_men"] - out["rate_women"]
    out["rate_ratio_w_m"] = _safe_ratio(out["rate_women"], out["rate_men"])
    out["women_lf_share"] = _safe_ratio(
        out["labor_force_women"], out["labor_force_total"]
    )
    out["implied_rate_men"] = _safe_ratio(out["labor_force_men"], out["population_men"])
    out["implied_rate_women"] = _safe_ratio(
        out["labor_force_women"], out["population_women"]
    )
    out["implied_rate_total"] = _safe_ratio(
        out["labor_force_total"], out["population_total"]
    )
    out["emp_pop_ratio_total"] = _safe_ratio(
        out["employment_total"], out["population_total"]
    )
    # Standardized prime-age columns (lfpr_prime_total / _men / _women) arrive
    # directly from MONTHLY_COLUMNS. Missing months -- including the October
    # 2025 shutdown gap and any years the BLS API truncates -- remain NaN and
    # are never interpolated.
    #
    # Legacy aliases retained for the shift-share decomposition, whose contract
    # predates the sex-disaggregated prime-age series. The prime total is the
    # published series; men/women remain 16+ proxies so existing decomposition
    # outputs do not silently change. Only alias when the source column exists
    # so hand-built frames in the unit tests remain valid.
    if "lfpr_prime_total" in out.columns:
        out["rate_prime"] = out["lfpr_prime_total"]
    out["rate_prime_men"] = out["rate_men"]
    out["rate_prime_women"] = out["rate_women"]
    out["weekly_hours_total"] = _safe_ratio(
        out["weekly_hours_men"] + out["weekly_hours_women"],
        pd.Series([2] * len(out), index=out.index),  # Average people in total
    )
    out["weekly_hours_ratio_w_m"] = _safe_ratio(
        out["weekly_hours_women"], out["weekly_hours_men"]
    )
    # Macro purchasing-power and public-sector metrics. Missing observations
    # (including the October 2025 CPI shutdown gap) remain NaN rather than being
    # imputed; _safe_ratio converts zero denominators to NaN instead of inf.
    # USPRIV and CNP16OV are both in thousands, so the ratio is unitless and the
    # *100 scale expresses private employment as a percent of population.
    out["purchasing_power_index"] = _safe_ratio(
        out["ahe_production_nominal"], out["cpi"]
    )
    out["private_per_capita"] = _safe_ratio(
        out["employment_private"], out["population_total"]
    )
    out["govt_share_pct"] = _safe_ratio(
        out["employment_government"],
        out["employment_private"] + out["employment_government"],
    )
    return out


def _add_derived_quarterly(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["earnings_ratio_nominal"] = _safe_ratio(
        out["weekly_nominal_women"], out["weekly_nominal_men"]
    )
    out["earnings_ratio_real"] = _safe_ratio(
        out["weekly_real_women"], out["weekly_real_men"]
    )
    return out


def _add_derived_hourly(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["ahe_real"] = _safe_ratio(out["ahe_nominal"], out["cpi"])
    out["ahe_production_real"] = _safe_ratio(out["ahe_production_nominal"], out["cpi"])
    return out


def _coverage(raw: dict[str, pd.Series]) -> pd.DataFrame:
    """Per-series coverage report: span, observation counts, gaps."""
    rows = []
    for sid, series in raw.items():
        clean = series.dropna()
        missing_mask = series.isna().to_numpy()
        missing_dates = series.index.to_numpy()[missing_mask]
        missing_str = ", ".join(str(d)[:7] for d in missing_dates)
        spec = BY_SID.get(sid) or BLS_BY_SID.get(sid)
        label = spec.label if spec else sid
        units = spec.units if spec else "unknown"
        rows.append(
            {
                "sid": sid,
                "label": label,
                "units": units,
                "first_obs": str(clean.index[0])[:10] if clean.size else None,
                "last_obs": str(clean.index[-1])[:10] if clean.size else None,
                "observations": int(series.size),
                "missing": int(missing_mask.sum()),
                "missing_periods": missing_str,
            }
        )
    return pd.DataFrame(rows)
