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
| pixi run fetch | Download every FRED series into data/raw/ (cached 30 days) |
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
| series.py | FRED series catalog: IDs, labels, units, colors (PALETTE) |
| fred_data.py | FRED CSV client with a local cache; defines FredFetchError |
| labor_data.py | Assembles monthly / quarterly / hourly frames + coverage |
| analysis.py | compute_stats() (every headline number) + findings renderer |
| labor_viz.py | Charts: static PNG, animated MP4 reveal, interactive HTML |

analysis.compute_stats() is the single source of truth for every number
that appears in the report **and** on the charts — never hardcode a figure
into a visualization; read it from stats.

## Shift-Share & Demographic Analysis Specifications

- **New Modules/Functions:**
  - `series.py`: Add catalog mappings for `CIVPART`, `LNS11300060` (Prime Total), `LNS11300061` (Prime Male), `LNS11300062` (Prime Female), `LNS11324230` (55+), and population series (`LNU00000012`, `LNU00000060`, `LNU00000242`).
  - `analysis.py`: Add `calculate_shift_share(df_pop, df_lfpr, base_year=2000)` to decompose LFPR change into Within-Group (behavioral) and Between-Group (demographic aging) effects.
  - `labor_viz.py`: Add dual-panel chart rendering (Headline vs. Prime-Age top panel; Shift-Share decomposition bottom panel).
- **Data Rules:** Population shares $w_{i,t} = \text{Pop}_i / \text{Pop}_{\text{total}}$ must be computed on annual resampled means before matrix operations.

## Data notes

- Monthly series run 1948-01 through 2026-09. **October 2025 is missing from
  every CPS series** (no field work during the 2025 shutdown). Gaps stay NaN
  and are annotated on the chart — never interpolate them away.
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
- .kilo/ is scratch space for agent probes (gitignored); output/ and
  data/raw/ are committed deliverables.

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
| F1 | series.sid() | Ambiguous total/earnings_nominal | **PINNED** (no callers) |
| F2 | labor_data._frame | pd.concat default-sort deprecation | **FIXED**: explicit sort=True |

### Remaining Known Issues (Tracked)

- **Suite:** 202 collected → **196 passed, 2 xfailed, 4 xpassed**; coverage **99%**
  (8 uncovered lines, all error/exception paths).
- **4 stale `xfail` markers (xpassed):** the defects they targeted (D5,
  D11, `allow_nan=False`) are fixed, so they now pass. Convert them to ordinary
  tests and drop the `xfail` marks.
- **2 genuine `xfail`s:** CLI unit tests whose monkeypatch of
  `analysis.build` / `labor_viz.build` is unreliable; the integration tests
  cover the real behavior.

## Documentation

This file is the concise agent brief. The full documentation set lives in
`docs/` — start at [docs/README.md](docs/README.md):

- `docs/architecture.md` — pipeline stages, modules, data flow, error handling
- `docs/data.md` — FRED catalog, derived columns, coverage, cache format
- `docs/methodology.md` — statistical definitions and interpretation
- `docs/outputs.md` — report/JSON schema and visual specifications
- `docs/development.md` — setup, conventions, testing philosophy
- `docs/roadmap.md` — planned data sources and enhancements
