# Data

This document is the reference for every input series, every derived column, the
cache format, and the coverage model.

## Sources

All data comes from public U.S. Bureau of Labor Statistics (BLS) programs —
primarily the Current Population Survey (CPS) and Current Employment Statistics
(CES) — retrieved from the Federal Reserve Bank of St. Louis
[FRED](https://fred.stlouisfed.org/) via its `fredgraph.csv` endpoint:

```text
https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SID>
```

**BLS Weekly Hours (optional)** — Two series on average weekly hours worked in non‑agricultural industries are also available directly from the BLS Public Data API v2.
The catalog is declared in [bls_data.py](../bls_data.py). To use these series, set the `BLS_API_KEY` environment variable to your BLS API key (optional; unauthenticated requests are rate‑limited).

The catalog is declared in [`series.py`](../series.py). Each entry is a
`SeriesSpec(sid, label, short, track, sex, units, seasonal)`.

## Frequencies and frames

`labor_data.assemble()` produces three frames with different cadences:

| Frame | Cadence | Contents |
| --- | --- | --- |
| `monthly` | Month‑start (`MS`) | Participation, labor force, employment, population, unemployment, CPI, total population. |
| `quarterly` | Quarter‑start (`QS`) | Median usual weekly earnings (nominal and real, 1982–84 $) by gender. |
| `hourly` | Month‑start (`MS`) | Average hourly earnings (nominal) and their real (CPI‑deflated) counterparts. |

The frames are joined on a union index and sorted; series that start later
introduce leading `NaN`s (for example `ahe_nominal` begins 2006‑03).

## Series catalog

All 27 series (25 FRED + 2 BLS) in `series.py` and `bls_data.py`. "SA"/"NSA" = seasonally adjusted / not adjusted.

| SID | Origin | Label | Units | Freq | Seas. | Track | Sex |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `CIVPART` | FRED | Labor Force Participation Rate | percent | monthly | SA | rate | total |
| `LNS11300001` | FRED | Labor Force Participation Rate – Men | percent | monthly | SA | rate | men |
| `LNS11300002` | FRED | Labor Force Participation Rate – Women | percent | monthly | SA | rate | women |
| `CLF16OV` | FRED | Civilian Labor Force Level | thousands | monthly | SA | level | total |
| `LNS11000001` | FRED | Civilian Labor Force Level – Men | thousands | monthly | SA | level | men |
| `LNS11000002` | FRED | Civilian Labor Force Level – Women | thousands | monthly | SA | level | women |
| `CNP16OV` | FRED | Civilian Noninstitutional Population | thousands | monthly | SA | level | total |
| `LNU00000001` | FRED | Civilian Noninstitutional Population – Men | thousands | monthly | NSA | level | men |
| `LNU00000002` | FRED | Civilian Noninstitutional Population – Women | thousands | monthly | NSA | level | women |
| `CE16OV` | FRED | Employment Level | thousands | monthly | SA | level | total |
| `LNS12000001` | FRED | Employment Level – Men | thousands | monthly | SA | level | men |
| `LNS12000002` | FRED | Employment Level – Women | thousands | monthly | SA | level | women |
| `UNRATE` | FRED | Unemployment Rate | percent | monthly | SA | rate | total |
| `LNS14000001` | FRED | Unemployment Rate – Men | percent | monthly | SA | rate | men |
| `LNS14000002` | FRED | Unemployment Rate – Women | percent | monthly | SA | rate | women |
| `CES0500000003` | FRED | Average Hourly Earnings, Total Private (2006+) | dollars/hour | monthly | SA | earnings_nominal | total |
| `AHETPI` | FRED | Average Hourly Earnings, Production & Nonsupervisory (1964+) | dollars/hour | monthly | SA | earnings_nominal | total |
| `LES1252881500Q` | FRED | Median Usual Weekly Earnings (nominal) | dollars/week | quarterly | NSA | earnings_nominal | total |
| `LES1252881800Q` | FRED | Median Usual Weekly Earnings (nominal) – Men | dollars/week | quarterly | NSA | earnings_nominal | men |
| `LES1252882700Q` | FRED | Median Usual Weekly Earnings (nominal) – Women | dollars/week | quarterly | NSA | earnings_nominal | women |
| `LES1252881600Q` | FRED | Median Usual Weekly Earnings (real, 1982–84 $) | dollars/week | quarterly | NSA | earnings_real | total |
| `LES1252881900Q` | FRED | Median Usual Weekly Earnings (real, 1982–84 $) – Men | dollars/week | quarterly | NSA | earnings_real | men |
| `LES1252882800Q` | FRED | Median Usual Weekly Earnings (real, 1982–84 $) – Women | dollars/week | quarterly | NSA | earnings_real | women |
| `CPIAUCSL` | FRED | Consumer Price Index for All Urban Consumers | index | monthly | SA | price | total |
| `POPTHM` | FRED | Total US Population | thousands | monthly | SA | level | total |

### BLS Weekly Hours (optional)

| SID | Label | Units | Freq | Seas. | Track | Sex |
|---|---|---|---|---|---|---|---|
| `LNS12032194` | Average weekly hours worked in non‑agricultural industries – Men (16 years and over) | hours/week | monthly | SA | hours_per_week | men |
| `LNS12032195` | Average weekly hours worked in non‑agricultural industries – Women (16 years and over) | hours/week | monthly | SA | hours_per_week | women |

### Observed spans

Verified against the committed `data/raw/` cache (including `data/raw/bls/` for the BLS series):

| Group of series | First obs | Last obs |
| --- | --- | --- |
| Assembled `monthly` frame | 1947‑01 | 2026‑09 |
| CPS/BLS labor series (`CIVPART`, `CLF16OV`, `CE16OV`, `UNRATE`, `LNS…`, `CNP16OV`) | 1948‑01 | 2026‑09 |
| Consumer price index (`CPIAUCSL`) | 1947‑01 | 2026‑09 |
| Total population (`POPTHM`) | 1959‑01 | 2026‑08 |
| Average hourly earnings, production (`AHETPI`) | 1964‑01 | 2026‑09 |
| Average hourly earnings, total private (`CES0500000003`) | 2006‑03 | 2026‑09 |
| Median weekly earnings (`LES…` quarterly) | 1979‑01 | 2026‑04 |
| BLS weekly hours (`LNS12032194`, `LNS12032195`) | 1977‑01 | 2026‑09 |

> **Why the monthly frame starts in 1947, not 1948.** The core labor series begin
> in 1948‑01, but `CPIAUCSL` begins in 1947‑01. Because the frames are joined on
> a union index, the assembled `monthly` frame starts in 1947‑01. The report
> header reports this frame-level span.

### Series-ID ambiguity (`sid()`)

`series.sid(sex, track)` returns the **first** catalog entry matching a
`(sex, track)` pair. Note that `("total", "earnings_nominal")` matches three
entries (`CES0500000003`, `AHETPI`, `LES1252881500Q`); `sid()` therefore returns
`CES0500000003`. This is a tracked latent issue (**F1**) — `sid()` currently has
**no callers** in the repository, so the ambiguity is dormant. Use an explicit
SID, or the `labor_data` column mappings, when the specific series matters.

## Column mappings

`labor_data.py` declares one mapping per frame, mapping SID → column name:

### `MONTHLY_COLUMNS`

`rate_total`, `rate_men`, `rate_women`, `labor_force_total`,
`labor_force_men`, `labor_force_women`, `population_total`, `population_men`,
`population_women`, `employment_total`, `employment_men`, `employment_women`,
`unrate_total`, `unrate_men`, `unrate_women`, `cpi`, `population_all_ages`.

### `QUARTERLY_COLUMNS`

`weekly_nominal_total`, `weekly_nominal_men`, `weekly_nominal_women`,
`weekly_real_total`, `weekly_real_men`, `weekly_real_women`.

### `HOURLY_COLUMNS`

`ahe_nominal`, `ahe_production_nominal`, `cpi`.

## Derived columns

Added by `labor_data._add_derived_*()`. Every division is guarded by
`_safe_ratio()`, which returns `NaN` when the denominator is zero (defect **D5**)
so `inf`/`NaN` never reach the stats or the JSON.

### Monthly

| Column | Definition |
| --- | --- |
| `gap_pp` | `rate_men − rate_women` (the gender participation gap, in pp). |
| `rate_ratio_w_m` | `rate_women / rate_men × 100`. |
| `women_lf_share` | `labor_force_women / labor_force_total × 100`. |
| `implied_rate_men` | `labor_force_men / population_men × 100`. |
| `implied_rate_women` | `labor_force_women / population_women × 100`. |
| `implied_rate_total` | `labor_force_total / population_total × 100`. |
| `emp_pop_ratio_total` | `employment_total / population_total × 100`. |

`implied_rate_*` are recomputed from levels (not read from the published rate
series) so they can be compared against the published rates as a consistency
check.

### Quarterly

| Column | Definition |
| --- | --- |
| `earnings_ratio_nominal` | `weekly_nominal_women / weekly_nominal_men × 100`. |
| `earnings_ratio_real` | `weekly_real_women / weekly_real_men × 100`. |

### Hourly

| Column | Definition |
| --- | --- |
| `ahe_real` | `ahe_nominal / cpi × 100`. |
| `ahe_production_real` | `ahe_production_nominal / cpi × 100`. |

## Coverage report

`labor_data._coverage()` returns one row per raw series with:

| Field | Meaning |
| --- | --- |
| `sid`, `label`, `units`, `seasonal` | Catalog metadata for the series. |
| `first_obs`, `last_obs` | First/last **non-null** observation date (`YYYY-MM-DD`), or `None` if empty. |
| `observations` | Total rows in the series index (including missing). |
| `missing` | Count of `NaN` observations. |
| `missing_periods` | Comma-joined `YYYY-MM` list of missing periods, in index order. |

`analysis._coverage_summary()` aggregates this into the `coverage` block of
`summary.json`: total `series_count`, the monthly and earnings spans, and a
sorted, de-duplicated union of missing periods.

## The October 2025 gap

No CPS field work was conducted during the **2025 federal government
shutdown**, so the survey series are missing **October 2025**. Verified against
the cache:

| Series | 2025‑10 value |
| --- | --- |
| CPS series (`CIVPART`, `LNS…`, `CLF16OV`, `CNP16OV`, `CE16OV`, `UNRATE`) | missing (empty field) |
| `CPIAUCSL` | missing |
| `POPTHM` | present |
| `AHETPI` | present |
| `CES0500000003` | present |

Handling rules:

- The gap is left as `NaN`. It is **never interpolated**.
- The static hero chart annotates it with a shaded band and a "no Oct '25 data"
  label; the animated reveal introduces that annotation on the timeline.
- The `coverage.missing_periods` field in `summary.json` records `["2025-10"]`.

> The generated `findings.md` header phrases this as "every monthly series is
> missing that month". Strictly, the gap applies to the CPS series and
> `CPIAUCSL`; `POPTHM`, `AHETPI`, and `CES0500000003` have values there. The
> *derived* analysis columns (`gap_pp`, ratios, implied rates) are `NaN` at
> 2025‑10 because their CPS inputs are.

## Cache format

`fred_data` stores each response verbatim as `data/raw/<sid>.csv`. The on-disk
format is FRED's two-column CSV:

```csv
observation_date,CIVPART
2025‑08‑01,62.6
2025‑09‑01,62.5
2025‑10‑01,
2025‑11‑01,62.4
```

- The first column is the observation date; the second is the value.
- FRED marks missing observations with `.` (or an empty field), which
  `fred_data._parse()` reads as `NaN`.
- Only the second column is used; extra columns are ignored.
- Cached files are considered fresh for **30 days** (`CACHE_MAX_AGE_DAYS`).
- `data/raw/` is a committed deliverable so analyses are reproducible offline.

See [architecture.md](architecture.md#caching-model) for the caching state
machine and [methodology.md](methodology.md) for how these columns are used.
