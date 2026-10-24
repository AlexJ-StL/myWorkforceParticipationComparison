# Methodology

Every headline statistic is produced by `analysis.compute_stats()`. This
document defines each statistic precisely and states how to interpret it. The
definitions here mirror the code; the code is authoritative if the two ever
disagree.

## Notation

- **pp** — percentage points: the absolute difference between two percentages.
  A rate moving from 60% to 55% has changed by −5 pp (not −5%).
- **month** / **quarter** indexes are the observation dates (`YYYY-MM` for
  months, quarter starts for the quarterly frame).
- **`_ym(t)`** formats a timestamp as `YYYY-MM`.
- All `NaN`s are dropped before a statistic is computed unless stated otherwise.

## Series summaries (`_series_summary`)

Used for the participation rates, the gender gap, and (with extra fields) the
earnings ratios. Returns:

| Field | Definition |
|---|---|
| `first`, `first_date` | First non-null value and its month. |
| `latest`, `latest_date` | Last non-null value and its month. |
| `peak`, `peak_date` | Maximum **non-null** value and its month. Ties resolve to the **first** occurrence. |
| `trough`, `trough_date` | Minimum non-null value and its month. |
| `change_since_first` | `latest − first`. |
| `change_since_peak` | `latest − peak`. |

For the **gender gap** block, `shrink_pp = first − latest` (positive means the
gap narrowed).

> **Interpretation.** These are describing the endpoints and extremes of a
> published series. They are not model estimates and carry no uncertainty
> interval.

## Trend regimes (`_ols`)

Three fixed regimes are fit by ordinary least squares on the monthly series:

| Label | Window |
|---|---|
| `1948-2000` | 1948-01-01 – 2000-12-31 |
| `2000-2019` | 2000-01-01 – 2019-12-31 |
| `2019-2026` | 2019-01-01 – 2026-12-31 |

For each regime and each of `rate_men`, `rate_women`, `rate_total`, `gap_pp`,
`_ols` returns:

- **`slope_pp_per_year`** — the OLS slope in pp/year. The time regressor is
  **years** (`month_index / 12` over the clean observations), so the slope is
  directly comparable across regimes of different length.
- **`r2`** — the coefficient of determination, `1 − SS_res / SS_tot`.

Edge behaviour (pinned by tests):

- A series with **fewer than 12** clean observations returns `(NaN, NaN)`.
- A **zero-variance** series returns slope `0.0` and `r2 = NaN` (no variance to
  explain).

> **Interpretation.** The regime boundaries are chosen for **interpretability,
> not by a changepoint test**. Readers should treat them as descriptive labels
> for periods of visibly different trend, not as statistically detected breaks.
> In the `2019-2026` window the `r2` values are low (the window is dominated by
> the COVID shock), so its slopes should be read with caution.

## COVID-19 window (`_covid_window`)

A fixed baseline/trough/recovery description of the pandemic shock in each rate
series:

- **`baseline_dec_2019`** — the rate at **2019-12**. If that month is absent, a
  `KeyError` is raised (the baseline is required, not optional).
- **`trough`**, **`trough_date`** — the minimum over **2020-01 … 2020-12**
  (the crisis window). An empty crisis window raises `EmptySeriesError`.
- **`drop_pp`** — `trough − baseline` (negative = a fall).
- **`latest`** — the last non-null value in the series.
- **`change_vs_baseline`** — `latest − baseline`.
- **`recovered`**, **`recovered_date`** — whether, and when, the series first
  returns to (≥) the December 2019 baseline **after the trough**.
- **`months_to_recover`** — whole months from the trough to `recovered_date`
  (`(Δyear × 12) + Δmonth`), or `null` if it never recovered.

Edge behaviour:

- If the trough equals the baseline (no drop), the trough month itself counts as
  the recovery (**0 months**).
- A series with no 2020 observations raises `EmptySeriesError`.
- `NaN`s are ignored when locating the trough.

## Earnings (`_earnings_stats`)

Computed on the quarterly frame for `total`, `men`, and `women`:

| Field group | Definition |
|---|---|
| `nominal_first` / `nominal_latest` (+ dates) | First/last non-null nominal weekly earnings. |
| `real_first` / `real_latest` | First/last non-null real (1982–84 $) weekly earnings. |
| `nominal_change_pct` | `(nominal_latest / nominal_first − 1) × 100`. |
| `real_change_pct` | `(real_latest / real_first − 1) × 100`. |

For the women-to-men ratios (`earnings_ratio_nominal`, `earnings_ratio_real`):

| Field | Definition |
|---|---|
| `first` / `latest` (+ dates) | Endpoint values. |
| `change_pp` | `latest − first`. |
| `slope_pp_per_year`, `r2` | OLS trend over the ratio's own history. |

> **Interpretation.** Nominal growth is dominated by inflation; the **real**
> figures (constant 1982–84 dollars) are the meaningful comparison across time.
> These series cover **full-time wage and salary workers only** and are
> **quarterly**, so they describe levels and long-run trends, not monthly
> dynamics.

## Earnings/participation alignment (`_alignment_stats`)

A descriptive association between the gender participation gap and the
women-to-men earnings ratio:

1. Resample the monthly `gap_pp` to **quarter means** (`resample("QS").mean()`).
2. Join it with `earnings_ratio_nominal` on the quarterly index and drop rows
   where either is missing. An empty join raises `EmptySeriesError`.
3. Compute the **contemporaneous Pearson correlation** (`_corr`) between the two.
4. Search integer lags from **−8 to +8 quarters** (excluding 0) and keep the lag
   whose `|correlation|` is largest.

Returns:

| Field | Definition |
|---|---|
| `observations` | Number of overlapping quarters used. |
| `span` | `YYYY-MM..YYYY-MM` of the overlap. |
| `corr_contemporaneous` | Pearson r at lag 0. |
| `best_lag_quarters` | Lag (in quarters) maximising `|r|`; `0` if lag 0 is best. |
| `corr_best_lag` | `r` at that lag. |

Lag sign convention: the search correlates the gap at quarter `t` against the
ratio shifted by `lag` (pandas `ratio.shift(lag)`), i.e. the ratio at `t − lag`.
A positive `best_lag_quarters` therefore means the ratio moves **ahead of** the
gap by that many quarters.

`_corr` itself returns `NaN` when fewer than **3** paired observations are
available. A one-quarter overlap is **not** treated as degenerate input — the
correlation is honestly `NaN` and the lag search is skipped, preserving the
result shape.

> **Interpretation — read this before quoting the correlation.**
> This is an **in-sample, unadjusted association**. There is no control for
> confounders, no out-of-sample validation, and no significance test on the lag
> search — the "best" lag is simply the largest `|r|` among 16 candidates, which
> overstates precision. The committed output reports a strong contemporaneous
> negative correlation (the participation gap has shrunk as the earnings ratio
> has risen), but **correlation is not causation.**

## Counts and composition (`_counts_stats`)

Levels (`labor_force_total`, `labor_force_men`, `labor_force_women`,
`employment_total`, `population_16plus` — mapped from `population_total`):

| Field | Definition |
|---|---|
| `first` / `latest` (+ dates) | Endpoint values (thousands). |
| `growth_multiple` | `latest / first`, or `NaN` if `first == 0` (never `inf`). |

Shares (`women_lf_share`, `emp_pop_ratio_total`):

| Field | Definition |
|---|---|
| `first` / `latest` (+ dates) | Endpoint values (percent). |
| `change_pp` | `latest − first`. |

## Internal consistency checks (`_consistency_checks`)

Cross-checks that independent published series agree with derived arithmetic:

- **`labor_force_additivity`** — `|labor_force_men + labor_force_women −
  labor_force_total|`, reported as `mean_abs_diff_thousands` and
  `max_abs_diff_thousands`.
- **`implied_vs_published_<sex>`** — `|implied_rate_<sex> − rate_<sex>|` for
  total/men/women, reported as `mean_abs_diff_pp` and `max_abs_diff_pp`.

> **Interpretation.** These are quality signals, not errors. In the committed
> output the level additivity is within ~0.1 thousand (rounding), and the
> implied-vs-published rate differences are a few hundredths of a pp. Residual
> differences stem from two documented inconsistencies: participation rates are
> **seasonally adjusted** while the gender population levels (`LNU…`) are
> **not**; and published rates carry BLS rounding.

## Weekly hours (`_weekly_hours_stats`)

Descriptive endpoints for `weekly_hours_men`, `weekly_hours_women`, and
`weekly_hours_total`, plus the men/women hours ratio:

| Field | Definition |
|---|---|
| `first` / `latest` (+ dates) | Endpoint values. |
| `change` | `latest − first`. |
| `change_pct` | `(latest / first − 1) × 100`. |
| `ratios.hours_ratio_men_women` | The men/women ratio with `first`, `latest`, `change`, and `slope_pp_per_year`. |

> **Known defect.** The two BLS IDs behind these columns are *not* weekly-hours
> series; they are part-time-for-economic-reasons employment levels. The block
> is invalid until the IDs are replaced. See
> [data.md](data.md#bls-series-known-defect).

## Shift-share decomposition (`calculate_shift_share`)

An **experimental** annual decomposition of LFPR change into behavioral
(within-group) and demographic-aging (between-group) components, using
`base_year=2000`. Population shares are $w_{i,t} = \text{Pop}_{i,t} /
\text{Pop}_{\text{total},t}$, computed on annual resampled means. For each year
`t`:

$$
\text{within}_t = \sum_i \frac{w_{i,t} + w_{i,\text{base}}}{2}\,(r_{i,t} - r_{i,\text{base}})
$$

$$
\text{between}_t = \sum_i \frac{r_{i,t} + r_{i,\text{base}}}{2}\,(w_{i,t} - w_{i,\text{base}})
$$

The returned frame also carries `lfpr_change_total`, `pop_share_*`, the age-group
rates, and `cumulative_*` fields.

Groups: `youth` (16–24), `prime` (25–54, split into men and women), `older` (55+).

> **Known defect.** The shipped `_between_group_effect()` uses average population
> **levels** instead of average **rates** in the between term. Because population
> is in thousands, the result is non-physical (e.g. −2,983 pp for 2026). In
> addition, `rate_prime_men` / `rate_prime_women` are 16+ proxies rather than
> true prime-age rates, and the youth term reuses `rate_prime` because no youth
> LFPR series is cataloged. Treat the entire `shift_share` block as experimental
> and **not publishable** until those issues are corrected.

## Coverage (`_coverage_summary`)

Aggregates the per-series coverage report into:

| Field | Definition |
|---|---|
| `series_count` | Number of raw series (32: 30 FRED + 2 BLS). |
| `monthly_span` | `YYYY-MM..YYYY-MM` of the assembled monthly frame. |
| `earnings_span` | Span of the quarterly earnings frame. |
| `missing_periods` | Sorted, de-duplicated union of all per-series missing months. |

## Caveats (kept verbatim in the report)

`render_report()` always appends a Caveats section stating:

- **Correlation is not causation.** The earnings/participation alignment is
  descriptive; no identification strategy is used.
- **October 2025 is missing** from the CPS series (shutdown); no interpolation
  is applied.
- Participation rates are seasonally adjusted; gender population levels
  (`LNU…`) are not.
- Earnings cover **full-time wage and salary workers only** and are quarterly
  (since 1979), so they cannot explain monthly movements.
- BLS revises seasonal factors and annual population controls, so figures can
  shift slightly between vintages.
- The 1948–2000 and 2000–2026 eras differ in trend, but regime splits are
  chosen for interpretability, not by a formal changepoint test.
- The BLS "weekly hours" block is currently mislabeled and invalid (see
  [data.md](data.md#bls-series-known-defect)).
- The shift-share decomposition is experimental and currently produces
  non-physical between-group values; do not cite it.

See [data.md](data.md) for the underlying columns and
[outputs.md](outputs.md) for where each statistic appears.
