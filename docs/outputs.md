# Outputs

The pipeline emits five artifacts into `output/`. The report and JSON are
produced by `pixi run analyze`; the visuals by `pixi run viz`.

| File | Produced by | Committed |
|---|---|---|
| `output/findings.md` | `analysis.main()` | yes |
| `output/summary.json` | `analysis.main()` | yes |
| `output/twitter_hero.png` | `labor_viz.build_static()` | yes |
| `output/twitter_hero.mp4` (or `.gif`) | `labor_viz.build_animated()` | yes |
| `output/twitter_interactive.html` | `labor_viz.build_interactive()` | yes |

## CLI reference

### `analysis.py` (`pixi run analyze`)

| Flag | Default | Effect |
|---|---|---|
| `--refresh` | off | Re-download all series from FRED instead of using the cache. |
| `--outdir` | `./output` | Directory for `findings.md` and `summary.json`. |

Writes `findings.md` and `summary.json`, prints the report and the written paths.
On `FredFetchError` or `requests.RequestException` it exits non-zero with
`Execution Error: <message>`.

### `labor_viz.py` (`pixi run viz`)

| Flag | Effect |
|---|---|
| `--static` | Build only `twitter_hero.png`. |
| `--animated` | Build only `twitter_hero.mp4` (`.gif` fallback). |
| `--interactive` | Build only `twitter_interactive.html`. |
| `--all` | Build all three (also the default when no selector is given). |
| `--refresh` | Re-download series from FRED. |
| `--outdir` | Output directory (default `./output`). |

Selector semantics: with **no** selector flags, all three are built. Passing one
or more of `--static`/`--animated`/`--interactive` builds only those. `--all`
always builds all three. Runs under `MPLBACKEND=Agg` (set in `pixi.toml`).

## `findings.md`

A markdown report rendered by `analysis.render_report()`, assembled in this
order:

| Section | Content |
|---|---|
| Title + provenance | Generation timestamp (UTC), series count, monthly/earnings spans, and the October 2025 gap note. |
| Participation levels | Table of first/peak/latest and changes for All/Men/Women plus the gender gap. |
| Trend regimes | OLS slope (pp/yr) and R² per regime for men/women/total/gap. |
| COVID-19 shock and recovery | Dec 2019 baseline, 2020 trough, latest, change vs. baseline, recovery. |
| Median usual weekly earnings | Real and nominal endpoints by gender, plus the W/M ratio and the alignment correlation. |
| Counts and composition | Labor force/employment levels with growth multiples and women's share. |
| Internal consistency checks | Additivity and implied-vs-published rate differences. |
| Caveats | The standard interpretation warnings (see [methodology.md](methodology.md#caveats-kept-verbatim-in-the-report)). |

The report is a rendering of `stats` — changing a statistic changes both the
report and the charts together.

## `summary.json`

Strict JSON (`json.dumps(..., allow_nan=False)`), so any non-finite value is a
**hard error** rather than a silently invalid document. Top-level shape:

```jsonc
{
  "rates":  { "total": <seriesSummary>, "men": <seriesSummary>, "women": <seriesSummary> },
  "gap":    <seriesSummary + { "shrink_pp": number }>,
  "regimes": {
    "1948-2000": { "rate_men": <ols>, "rate_women": <ols>, "rate_total": <ols>, "gap_pp": <ols> },
    "2000-2019": { ... },
    "2019-2026": { ... }
  },
  "covid":  { "total": <covidWindow>, "men": <covidWindow>, "women": <covidWindow> },
  "earnings": {
    "series": { "total": <earningsSeries>, "men": <earningsSeries>, "women": <earningsSeries> },
    "ratios": { "nominal": <ratio>, "real": <ratio> },
    "participation_alignment": <alignment>
  },
  "counts": { "levels": { ... }, "shares": { "women_lf_share": <share>, "emp_pop_ratio_total": <share> } },
  "checks": {
    "labor_force_additivity": <additivity>,
    "implied_vs_published_total": <impliedCheck>,
    "implied_vs_published_men": <impliedCheck>,
    "implied_vs_published_women": <impliedCheck>
  },
  "coverage": { "series_count": number, "monthly_span": string, "earnings_span": string, "missing_periods": [string] }
}
```

Field shapes:

| Type | Fields |
|---|---|
| `<seriesSummary>` | `first`, `first_date`, `latest`, `latest_date`, `peak`, `peak_date`, `trough`, `trough_date`, `change_since_first`, `change_since_peak` |
| `<ols>` | `slope_pp_per_year`, `r2` |
| `<covidWindow>` | `baseline_dec_2019`, `trough`, `trough_date`, `drop_pp`, `latest`, `change_vs_baseline`, `recovered`, `recovered_date` (nullable), `months_to_recover` (nullable) |
| `<earningsSeries>` | `nominal_first`, `nominal_first_date`, `nominal_latest`, `nominal_latest_date`, `real_first`, `real_latest`, `real_change_pct`, `nominal_change_pct` |
| `<ratio>` | `first`, `first_date`, `latest`, `latest_date`, `change_pp`, `slope_pp_per_year`, `r2` |
| `<alignment>` | `observations`, `span`, `corr_contemporaneous`, `best_lag_quarters`, `corr_best_lag` |
| `<share>` | `first`, `first_date`, `latest`, `latest_date`, `change_pp` |
| `<additivity>` | `max_abs_diff_thousands`, `mean_abs_diff_thousands` |
| `<impliedCheck>` | `mean_abs_diff_pp`, `max_abs_diff_pp` |

Example (trimmed) from the committed output:

```json
{
  "rates": {
    "men": { "first": 86.7, "first_date": "1948-01", "latest": 67.2,
             "latest_date": "2026-09", "peak": 87.4, "peak_date": "1949-10",
             "trough": 66.1, "trough_date": "2020-04",
             "change_since_first": -19.5, "change_since_peak": -20.2 }
  },
  "gap": { "first": 54.7, "latest": 10.5, "shrink_pp": 44.2 },
  "coverage": { "series_count": 25, "monthly_span": "1947-01..2026-09",
                "earnings_span": "1979-01..2026-04", "missing_periods": ["2025-10"] }
}
```

> `summary.json` is the machine-readable contract. `findings.md` and the charts
> are both renderings of the same stats; downstream tools should read the JSON
> rather than scrape the prose.

## Visual specifications

All three visuals share the dark Twitter theme (`series.PALETTE`) and the same
underlying story.

### Palette

| Key | Hex | Used for |
|---|---|---|
| `bg` | `#15202b` | Figure background. |
| `grid` | `#38444d` | Gridlines, spines, chip borders. |
| `muted` | `#8899a6` | Secondary text, annotations. |
| `men` | `#1da1f2` | Men's lines. |
| `women` | `#f42a60` | Women's lines. |
| `total` | `#ffffff` | Total/all line, primary text. |
| `accent` | `#f7b32b` | Kicker text, W/M ratio, COVID marker. |

### Static hero — `twitter_hero.png`

- **Size:** 1600×900 px (figure 8.0×4.5 in at 200 dpi).
- **Header:** kicker "U.S. LABOR FORCE · 1948–2026", title **"The Great
  Convergence"**, a one-line subtitle, and source/date labels.
- **Chips:** five headline value chips (men's and women's change, gender gap,
  real pay growth W/M, earnings ratio).
- **Panel A — participation:** men (blue), women (red), total (white, dashed);
  y in %; milestones at the 1948 gap (double-headed arrow), the total peak
  (2000-01), the COVID crash (2020-04), and the October 2025 shaded gap band.
- **Panel B — earnings:** men and women real weekly earnings on the left axis ($)
  and the women-to-men ratio on a secondary right axis (%); in-plot change
  annotations and end labels.
- **End labels:** latest values in the right-hand gutter for every series.
- **Footer:** units/definitions and the "descriptive analysis, not causal
  estimates" disclaimer.

### Animated reveal — `twitter_hero.mp4`

- **Spec:** 180 frames at 15 fps (≈ 12 s), H.264 via `FFMpegWriter`, bitrate
  2600.
- **Mechanic:** `FuncAnimation` calls `HeroFigure.reveal(t)` for `t` in [0, 1].
  Panel A reveals across 1948–2026; Panel B appears once the global timeline
  fraction reaches where 1979 falls within Panel A's span. Milestone annotations
  appear when the reveal passes their date; end-label alpha ramps in over the
  final ~12%.
- **Fallback:** if `FFMpegWriter` is unavailable **or** saving raises `OSError`,
  the animation is written as `twitter_hero.gif` via `PillowWriter` and a
  warning is printed. The GIF path is the guaranteed output on hosts without
  ffmpeg.

### Interactive — `twitter_interactive.html`

- **Format:** a single self-contained HTML file (`include_plotlyjs=True`) with
  an HTML5 doctype and a real `<title>` (post-processed from Plotly's default).
- **Layout:** two stacked subplots — participation rates (row 1) and real
  earnings with the W/M ratio on a secondary axis (row 2) — on the
  `plotly_dark` template with `hovermode="x unified"` and a range slider on
  row 2.
- **Size:** ~1300×950 px logical layout. The embedded Plotly bundle makes the
  file large (several MB); this is expected.

See [architecture.md](architecture.md) for how the builders receive the shared
`stats` dict.
