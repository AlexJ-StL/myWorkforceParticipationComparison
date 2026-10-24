# Roadmap

Where the analysis is, and where it is going. The catalog currently spans
**Tier 1** — public aggregate BLS/CPS/CES series retrieved from FRED. Tiers 2–4
add richer (and eventually record-level and administrative) sources to audit the
survey-based picture against.

**Status legend:** ✅ implemented · 🔜 planned · 💭 under consideration

## Where we are now

| Area | Status | Notes |
|---|---|---|
| Aggregate participation, levels, employment, unemployment | ✅ | Tier 1 catalog, 1948-01 → 2026-09. |
| Median usual weekly earnings (nominal + real) by gender | ✅ | Quarterly, 1979-01 → 2026-04, full-time wage & salary workers. |
| Average hourly earnings (level + CPI-deflated) | ✅ | Monthly; `AHETPI` from 1964-01, `CES0500000003` from 2006-03. |
| Trend regimes, COVID window, consistency checks | ✅ | See [methodology.md](methodology.md). |
| Earnings/participation alignment (descriptive) | ✅ | In-sample correlation only; not causal. |
| Census / IPUMS / SSA data | 🔜 | Tiers 2–4 below. |
| Distributional (top-tail) analysis | 🔜 | Requires Tier 3 microdata. |
| Survey-vs-administrative reconciliation | 🔜 | Requires Tier 4. |

## Data acquisition tiers

### Tier 1 — Aggregate macro series ✅

Implemented. Source: FRED / BLS. The full catalog is in
[data.md](data.md#series-catalog):

- **Participation:** `CIVPART`, `LNS11300001` (men), `LNS11300002` (women).
- **Labor force / employment / population:** `CLF16OV`, `LNS11000001/2`,
  `CE16OV`, `LNS12000001/2`, `CNP16OV`, `LNU00000001/2`, `POPTHM`.
- **Unemployment:** `UNRATE`, `LNS14000001/2`.
- **Earnings:** `AHETPI`, `CES0500000003`, and the `LES125288*Q` weekly series
  (nominal and real).
- **Prices:** `CPIAUCSL`.

### Tier 2 — Survey wage & income tables 🔜

Source: U.S. Census Bureau (ASEC) and FRED quarterly weekly-earnings series.

- **Weekly earnings (quarterly FRED series):**
  - `LEU0252881900Q` — men's *nominal* median weekly earnings (full-time)
  - `LEU0252882800Q` — women's *nominal* median weekly earnings (full-time)
  - `LES1252881900Q` — men's *real* median weekly earnings (1982–84 constant $)
  - `LES1252882800Q` — women's *real* median weekly earnings (1982–84 constant $)

  > **Verify before use.** The implemented catalog uses `LES1252881500Q` /
  > `1800Q` / `2700Q` for the *nominal* weekly series and `LES1252881600Q` /
  > `1900Q` / `2800Q` for the real series ([data.md](data.md#series-catalog)).
  > Reconcile the `LEU…` IDs above against FRED before adding them, to avoid
  > duplicating or mislabelling an existing series.

- **Census P-series tables (ASEC):**
  - **Table P-8** — *Income Distribution by Sex (full-time, year-round workers).*
  - **Table P-10** — *Mean and Median Income by Sex and Age.* Intended to audit
    the mean/median gap for men caused by top-tail outliers.

### Tier 3 — Record-level microdata & truncation 🔜

Source: Integrated Public Use Microdata Series, CPS
([cps.ipums.org](https://cps.ipums.org/)).

Extract variables:

| Variable | Meaning |
|---|---|
| `YEAR`, `MONTH` | Survey period. |
| `SEX` | Respondent gender designation. |
| `PAIDHOUR` | Hourly status (`2` = paid hourly, `1` = non-hourly/salaried). |
| `HOURWAGE` | Reported hourly pay rate. |
| `INCWAGE` | Total annual wage/salary income. |
| `EARNWT` / `ASECWTH` | Sampling weights for national expansion. |

**Analysis intent:** filter to hourly/working respondents, compute top-1%
cutoffs per group (`INCWAGE.quantile(0.99)`), and compare trimmed means against
raw medians to quantify top-tail sensitivity.

### Tier 4 — Administrative tax records 🔜

Source: SSA Office of Research, Evaluation, and Statistics — *Annual
Statistical Supplement*, Section 4.B (Employment and Earnings).

| Table | Contents |
|---|---|
| **4.B3** | Covered-worker counts, aggregate wage volume, mean and median earnings by sex and age. |
| **4.B7** | Worker distribution by exact wage bracket (e.g. \$5k increments), separated by sex. |
| **4.B9** | Counts/percentages of male vs. female earners at or above the Social Security taxable wage cap. |

**Analysis intent:** compare SSA tax-file medians directly against Census/BLS
survey medians to surface survey non-response bias, sampling skew, and
underreporting.

## Analysis enhancements

| Idea | Status | Notes |
|---|---|---|
| Annual-averaged view | 💭 | `resample("YE").mean()` for a smoother headline series. |
| Changepoint detection | 💭 | Replace the fixed `REGIMES` heuristic with a formal break test; today the splits are chosen for interpretability only. |
| Top-tail trimming | 🔜 | Needs Tier 3 microdata. |
| Alignment robustness | 💭 | Add controls and out-of-sample checks; the current correlation is in-sample and unadjusted. |
| Uncertainty intervals | 💭 | Standard errors on slopes and correlations. |
| Unemployment / EPOP panels | 💭 | The catalog already has the data; only the charts are missing. |
| Population controls by gender over time | 💭 | The `LNU…` NSA population series could support cohort analysis. |
| Shift-share decomposition | ⚠️ | Implemented (`calculate_shift_share`, Panel C, `summary.shift_share`) but the between-group term is non-physical; not publishable. See [methodology.md](methodology.md#shift-share-decomposition-calculate_shift_share). |
| BLS weekly hours | ⚠️ | Implemented but the catalog IDs are mislabeled part-time employment levels; the cache is invalid. See [data.md](data.md#bls-series-known-defect). |

## Engineering enhancements

| Idea | Status | Notes |
|---|---|---|
| Continuous integration | 💭 | Run `pixi run test` + `pixi run style` on push. |
| License file | 💭 | None declared yet; add before distributing. |
| Reproducibility badge / env export | 💭 | `pixi.lock` is already committed and pinned. |
| Split machine-readable outputs | 💭 | Optionally emit per-topic JSON (rates, earnings, counts) alongside `summary.json`. |
| Chart annotation from `stats` only | ✅ | Enforced invariant: no hardcoded figures in visuals. |
| Additional platforms in `pixi.toml` | 💭 | Currently `win-64` only. |

## Provenance

This roadmap consolidates and supersedes the original
*"Master Data Retrieval & Audit Roadmap — US Worker (men & women) Wages"*
working note, preserving its four tiers and series/table identifiers. The raw
original is archived at [roadmap-original-notes.md](roadmap-original-notes.md)
for provenance. This is planning material, not a commitment or a schedule.
