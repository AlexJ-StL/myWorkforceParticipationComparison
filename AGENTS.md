# AGENTS.md

Analysis and visualization of U.S. workforce participation (men vs women),
built for a Twitter-ready chart.

## Setup

All dependencies live in the pixi environment — always work inside it:

```powershell
pixi shell        # activate
```

Dependencies are declared in pixi.toml: pandas, requests, matplotlib,
plotly, pillow, ffmpeg, ruff. No system-level Python packages are used.

## Commands

| Command | What it does |
| --- | --- |
| pixi run fetch | Download every FRED and BLS series into data/raw/ (cached 30 days) |
| pixi run analyze | Regenerate output/findings.md + output/summary.json |
| pixi run viz | Build all three visuals in output/ |
| pixi run viz --static | Only output/twitter_hero.png (1600x900) |
| pixi run viz --animated | Only output/twitter_hero.mp4 (needs ffmpeg) |
| pixi run viz --interactive | Only output/twitter_interactive.html |
| pixi run style | `ruff format` + `ruff check --fix` — **run before committing** |
| pixi run fmt --check | Formatting verification only |
| pixi run ruff check --no-fix | Lint verification only |
| pixi run test | Run the full test suite |
| pixi run test-cov | Run the suite with a coverage report (99% target) |

Any command that loads data accepts --refresh to bypass the cache and
re-download from FRED: pixi run analyze --refresh.

## Architecture

| File | Role |
| --- | --- |
| series.py | FRED/BLS series catalog: IDs, labels, units, colors (PALETTE) |
| data_common.py | Shared cache-staleness and date helpers (no I/O) |
| fred_data.py | FRED CSV + BLS API v2 client with a local cache; defines FetchError |
| labor_data.py | Assembles monthly / quarterly / hourly frames + coverage |
| analysis.py | compute_stats() (every headline number) + findings renderer |
| labor_viz.py | Charts: static PNG, animated MP4 reveal, interactive HTML |

analysis.compute_stats() is the single source of truth for every number
that appears in the report **and** on the charts — never hardcode a figure
into a visualization; read it from stats.

## Shift-Share & Demographic Analysis Status

Implemented but **not publishable**:

- `series.py` has the demographic mappings (`LNS11300060`, `LNS11324230`, `LNU00000012`, `LNU00000060`, `LNU00024230`). FRED does not publish prime-age LFPR by sex, so `rate_prime_men` / `rate_prime_women` are 16+ proxies (`LNS11300001` / `LNS11300002`), not true prime-age rates.
- `analysis.calculate_shift_share(df_pop, df_lfpr, base_year=2000)` and the `shift_share` block exist. **Defect:** `_between_group_effect()` uses average population *levels* instead of average *rates*, producing values in the thousands of pp (e.g. −2,983 pp for 2026). The youth term also reuses `rate_prime`, and the prime term double-counts prime-total plus prime men/women.
- `labor_viz.HeroFigure` renders Panel C for the decomposition; the panel should not be cited until the math is fixed.
- **Data rule to keep:** population shares $w_{i,t} = \text{Pop}_i / \text{Pop}_{\text{total}}$ are computed on annual resampled means before matrix operations.

## BLS Weekly-Hours Status (Known Defect)

The catalog labels `LNS12032194` / `LNS12032195` as average weekly hours, but they
are **Employment Level — Part-Time for Economic Reasons** series (thousands of
persons). The committed JSON cache spans only 1955-05..1957-12 because the BLS
API reduced the requested range to its 10-year limit. The `weekly_hours_*`
columns, the "Average Weekly Hours Worked" report section, and the related stats
are invalid until the IDs are replaced and the cache is regenerated.

## Data notes

- The core monthly CPS series run 1948-01 through 2026-09; the assembled
  `monthly` frame starts 1947-01 because `CPIAUCSL` predates it. **October 2025
  is missing from every CPS series** (no field work during the 2025 shutdown).
  Gaps stay NaN and are annotated on the chart — never interpolate them away.
- Gender earnings are quarterly (1979-01..2026-04) and cover full-time wage
  and salary workers only.
- Participation rates are seasonally adjusted; population levels (LNU...)
  are not.
- Correlations in findings.md are descriptive associations, not causal
  estimates. Keep that framing in any published chart.

## Conventions

- Ruff 0.17 defaults are broad (TRY, BLE, RUF, UP, ISC, I001, ...). Expect:
  custom exception classes, no blind `except Exception`, dict() rewritten
  as literals, sorted imports, datetime.UTC, no implicit string
  concatenation inside collections.
- pandas/pyright stub friction: use `analysis.col(frame, name)` for typed
  column access rather than `frame[name]`.
- Visual style: dark Twitter theme from series.PALETTE, 1600x900 @ 200 dpi,
  glow strokes via labor_viz._glow, end labels in the right-hand gutter.
- .kilo/ is scratch space for agent probes (gitignored); output/ (except the
  on-demand `twitter_interactive.html`) and data/raw/ are committed deliverables.

## Testing Philosophy

This project follows a **high-bar testing standard**: a test is only worth keeping if it is hard to pass. Tests pin exact mathematical behavior, boundary conditions, and failure modes — not merely line coverage. The suite includes:

- **Exact-value assertions** on computed math (OLS slopes, correlations, recovery arithmetic, derived ratios)
- **Boundary conditions** (cache staleness boundaries, reveal cutoff math, 3-point correlation threshold)
- **Failure-mode pinning** (malformed CSV, missing sids, empty series, zero denominators, no ffmpeg, HTTP 404, corrupt cache)
- **Invariants that must never break** (NaN gaps stay NaN, compute_stats is single source of truth, summary.json is valid standard JSON)

Tests that merely assert "returns a DataFrame" are rejected. Coverage % (99%) is a byproduct indicator, not a target.

### Defect Register & Disposition

| ID | Location | Defect | Disposition |
| --- | --- | --- | --- |
| D1 | fred_data._parse | Header-only/garbage-header CSV → silent empty Series | **FIXED**: strict validation |
| D2 | fred_data.fetch_series | Corrupt cache → permanent failure | **FIXED**: auto re-download |
| D3 | labor_data._frame | Missing sid → bare KeyError | **PINNED** (programming error) |
| D4 | labor_data._coverage | Non-catalog sid → KeyError | **PINNED** |
| D5 | labor_data._add_derived_* | Zero denominators → inf/NaN | **FIXED**: _safe_ratio guard |
| D6 | analysis._series_summary | All-NaN → unhandled ValueError | **FIXED**: EmptySeriesError |
| D7 | analysis._earnings_stats | All-NaN → unhandled IndexError | **FIXED**: EmptySeriesError |
| D8 | _alignment_stats + renderer | Empty join → {} → KeyError | **FIXED**: EmptySeriesError |
| D9 | _covid_window | Empty crisis → ValueError | **FIXED**: EmptySeriesError |
| D10 | _counts_stats, _consistency_checks | Empty → IndexError/NaN | **FIXED**: EmptySeriesError + NaN guard |
| D11 | analysis.main vs labor_viz.main | Inconsistent CLI failure UX | **FIXED**: both SystemExit(1) |
| D12 | labor_viz.build_animated | GIF fallbacks unexercised | **FIXED**: monkeypatched tests |
| D14 | analysis._regime_section | Prose hard-wired to the 2000-2019 label | **PINNED** (test 1082) |
| D15 | analysis._covid_window | No-drop case must treat the trough as recovery | **PINNED** (test 253) |
| F1 | series.sid() | Ambiguous total/earnings_nominal | **PINNED** (no callers) |
| F2 | labor_data._frame | pd.concat default-sort deprecation | **FIXED**: explicit sort=True |

### Remaining Known Issues (Tracked)

- **Suite:** 274 collected, 274 passed; coverage is 99%. The remaining gap is
  limited to CLI `__main__` guard bodies, whose `main()` functions are already
  tested directly.
- **BLS weekly-hours defect:** the two IDs are mislabeled part-time employment
  series; the cache spans only 32 observations and must be regenerated after the
  IDs are corrected. See [docs/data.md](docs/data.md#bls-series-known-defect).
- **Shift-share defect:** the between-group term uses population levels instead
  of rates and yields non-physical values. See
  [docs/methodology.md](docs/methodology.md#shift-share-decomposition-calculate_shift_share).

## Documentation

This file is the concise agent brief. The full documentation set lives in
`docs/` — start at [docs/README.md](docs/README.md):

- `docs/architecture.md` — pipeline stages, modules, data flow, error handling
- `docs/data.md` — FRED catalog, derived columns, coverage, cache format
- `docs/methodology.md` — statistical definitions and interpretation
- `docs/outputs.md` — report/JSON schema and visual specifications
- `docs/development.md` — setup, conventions, testing philosophy
- `docs/roadmap.md` — planned data sources and enhancements
