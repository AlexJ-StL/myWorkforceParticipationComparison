# Development

How to set up, work in, test, and extend this repository. For the pipeline
itself see [architecture.md](architecture.md); for the statistical contracts see
[methodology.md](methodology.md).

## Prerequisites

- **[pixi](https://pixi.sh/)** — the only environment manager; never use a
  system Python or `pip`.
- The workspace targets **`win-64`** (`pixi.toml` `platforms`). Adding other
  platforms means extending that list and re-solving `pixi.lock`.
- **ffmpeg** ships through pixi; it is only needed to produce the animated
  **MP4** (a GIF fallback exists).

## Setup

```powershell
pixi install      # create the environment from pixi.lock
pixi shell        # or prefix every command with `pixi run`
```

Dependencies are declared in `pixi.toml` and pinned in `pixi.lock`. There is no
`pyproject.toml` / `requirements.txt`; keep it that way and add new dependencies
with `pixi add <package>` so the lock stays authoritative.

## Day-to-day commands

| Command | Purpose |
|---|---|
| `pixi run fetch` | Download all 30 FRED series into `data/raw/`. |
| `pixi run analyze` | Recompute stats → `output/findings.md`, `output/summary.json`. |
| `pixi run viz` | Rebuild all three visuals. |
| `pixi run style` | `ruff format` then `ruff check --fix` — **run before committing**. |
| `pixi run fmt --check` | Verify formatting without writing. |
| `pixi run ruff check --no-fix` | Lint verification only. |
| `pixi run test` | Full pytest suite. |
| `pixi run test-cov` | Suite with per-module line coverage. |

Tasks that load data accept `--refresh`. `labor_viz.py` runs with
`MPLBACKEND=Agg` (set in the `viz` task) so it never opens a window.

### Running a subset of tests

`pixi run test` runs the whole suite. For a focused run, invoke pytest directly
inside the environment:

```powershell
pixi run pytest tests/test_analysis.py -k ols -q
pixi run pytest tests/test_fred_data.py::test_corrupt_cache_falls_back_to_redownload -q
pixi run pytest -m integration -q          # only the real-data integration tests
```

## Repository layout

| Path | What lives there |
|---|---|
| `series.py` | The FRED catalog and `PALETTE` (no I/O). |
| `fred_data.py` | HTTP client + cache; `FredFetchError`. |
| `bls_data.py` | BLS weekly-hours client and JSON cache; `BlsFetchError`. |
| `labor_data.py` | Frame assembly and derived columns. |
| `analysis.py` | `compute_stats()` + report renderer + CLI. |
| `labor_viz.py` | Chart builders + CLI. |
| `tests/` | pytest suite and shared fixtures (`conftest.py`). |
| `data/raw/` | Committed FRED CSVs (the cached inputs). |
| `output/` | Committed generated deliverables. |
| `docs/` | This documentation. |

`pixi.toml` defines tasks; `pytest.ini` sets `pythonpath = .` and the
`integration` marker. `.kilo/` is gitignored agent scratch space.

## Code conventions

- **Formatter/linter:** Ruff 0.17 with broad defaults (`TRY`, `BLE`, `RUF`, `UP`,
  `ISC`, `I001`, …). There is no Ruff config file — defaults *are* the style.
  Tests are held to the same bar as source.
- **Imports:** sorted; **stdlib before third-party before first-party**
  (`import fred_data`, `import labor_data` are first-party, top-level).
- **Typed pandas access:** use `analysis.col(frame, name)` instead of
  `frame[name]` to satisfy the pandas type stubs. Use `analysis._index()` for a
  typed `DatetimeIndex`.
- **Exceptions:** raise explicit, purpose-built exceptions:
  - `fred_data.FredFetchError` for fetch/parse failures (carries `series_id`,
    `reason`).
  - `analysis.EmptySeriesError` for degenerate statistics input.
  - Do **not** catch bare `Exception`, and do not wrap unrelated errors.
- **`datetime`:** use `datetime.UTC` (not `timezone.utc`).
- **Literals:** prefer `dict`/list literals over `dict()`/`list()` calls.
- **Comments** explain *why*, not *what*; keep docstrings on public functions.

Run `pixi run style` until it is clean before finishing any change.

## Testing

### Philosophy

The project holds a **high-bar testing standard**: a test is only worth keeping
if it is *hard to pass*. Tests pin:

- **Exact math** — OLS slopes, Pearson correlations, recovery arithmetic,
  derived-ratio values (hand-computed, not read back from the code).
- **Boundaries** — cache staleness at exactly the budget, reveal cutoffs,
  `< 12`-observation OLS, the 3-point correlation minimum.
- **Failure modes** — malformed/header-only CSV, HTTP 404/429/500, missing
  SIDs, all-NaN series, zero denominators, missing ffmpeg, corrupt cache.
- **Invariants** — the October 2025 gap stays `NaN`; `compute_stats()` stays the
  single source of truth; `summary.json` is always valid standard JSON.

Tests that merely assert a type (e.g. "returns a DataFrame") are not accepted.
Coverage (99%) is a byproduct indicator, not a target.

### Layout

| File | Covers |
|---|---|
| `tests/conftest.py` | Fixtures, the offline synthetic dataset, cache isolation, network guard. |
| `tests/test_series.py` | Catalog integrity and the `sid()` ambiguity. |
| `tests/test_fred_data.py` | CSV parsing strictness, the cache state machine. |
| `tests/test_labor_data.py` | Frame joins, derived math, zero-denominator guards, coverage. |
| `tests/test_analysis.py` | Every statistics helper, exact values, `EmptySeriesError`. |
| `tests/test_labor_viz.py` | Styling helpers, `HeroFigure`, reveal math, all three builders. |
| `tests/test_cli.py` | CLI flag matrix, clean exits, JSON-validity tripwires, integration. |

### Test isolation (non-negotiable)

Two **autouse** fixtures in `conftest.py` protect the outside world:

- `_isolated_cache` — redirects `fred_data.CACHE_DIR` into `tmp_path`, so tests
  never read or write the real `data/raw/`.
- `_no_network` — replaces `requests.get` with a guard that raises on any
  unmocked call. Tests that need the download path install their own double via
  the `fake_get` fixture.

`conftest.py` also calls `matplotlib.use("Agg")` before any pyplot import, and
any CLI test writes to `tmp_path` via `--outdir`.

### Fixtures

| Fixture | Provides |
|---|---|
| `synthetic_raw` | A catalog-shaped `dict[sid, Series]` mirroring the real spans and the Oct-2025 gap. |
| `synthetic_data` | `labor_data.assemble(synthetic_raw)` → a `WorkforceData`. |
| `synthetic_stats` | `compute_stats(synthetic_data)`. |
| `fake_get` | A recording `requests.get` double (`install(FakeResponse(...))`, a callable, or an exception). |
| `write_cache` | Writes a CSV into the isolated cache with a controlled mtime age. |
| `fred_csv` | A small but structurally valid FRED CSV. |
| `outdir` | A fresh temporary output directory. |

The synthetic dataset is deliberately exact: labor-force levels are built so
`men + women == total` and so `labor_force / population * 100` reproduces the
published rates, letting the consistency checks be pinned to `0.0`.

### Markers

- `integration` — tests that need the committed `data/raw/` cache (real-data
  parsing through to `render_report`). Deselect with `-m "not integration"`.

### Current suite status

`pixi run test` → **202 collected: 196 passed, 2 xfailed, 4 xpassed.**
`pixi run test-cov` → **99%** (8 uncovered lines, all error/exception paths).

Two categories of `xfail` need attention:

- **4 xpassed (stale markers).** These tests target defects that are now fixed
  (D5, D11, and `allow_nan=False`), so they pass. Convert them to ordinary tests
  and remove the `xfail` marks. Until then, treat an xpass as a signal that a
  marker is out of date.
- **2 genuine xfails.** CLI unit tests whose monkeypatching of
  `analysis.build` / `labor_viz.build` proved unreliable. The integration tests
  cover the real behavior. Treat these as known, tracked exceptions — not free
  passes.

## Defect register

A running register of confirmed defects and their disposition lives in
[../AGENTS.md](../AGENTS.md#defect-register--disposition). Summary:

| ID | Location | Disposition |
|---|---|---|
| D1 | `fred_data._parse` — header-only/garbage CSV → silent empty Series | **FIXED** (strict validation) |
| D2 | `fred_data.fetch_series` — corrupt cache → permanent failure | **FIXED** (auto re-download) |
| D3 | `labor_data._frame` — missing sid → bare `KeyError` | **PINNED** (programming error) |
| D4 | `labor_data._coverage` — non-catalog sid → `KeyError` | **PINNED** |
| D5 | `labor_data._add_derived_*` — zero denominators → `inf`/`NaN` | **FIXED** (`_safe_ratio`) |
| D6 | `analysis._series_summary` — all-NaN → `ValueError` | **FIXED** (`EmptySeriesError`) |
| D7 | `analysis._earnings_stats` — all-NaN → `IndexError` | **FIXED** (`EmptySeriesError`) |
| D8 | `_alignment_stats` + renderer — empty join → `KeyError` | **FIXED** (`EmptySeriesError`) |
| D9 | `_covid_window` — empty crisis → `ValueError` | **FIXED** (`EmptySeriesError`) |
| D10 | `_counts_stats`, `_consistency_checks` — empty → `IndexError`/`NaN` | **FIXED** (`EmptySeriesError` + guard) |
| D11 | `analysis.main` vs `labor_viz.main` — inconsistent CLI failure | **FIXED** (both `SystemExit(1)`) |
| D12 | `labor_viz.build_animated` — GIF fallbacks unexercised | **FIXED** (monkeypatched tests) |
| F1 | `series.sid()` — ambiguous `("total", "earnings_nominal")` | **PINNED** (no callers) |
| F2 | `labor_data._frame` — `pd.concat` default-sort deprecation | **FIXED** (explicit `sort=True`) |

"FIXED" means behavior changed and a test pins the new contract; "PINNED" means
the behavior is intentional and a test documents it.

## Recipes

### Add a new FRED series

1. Append a `SeriesSpec(sid, label, short, track, sex, units, seasonal)` to
   `SERIES` in `series.py`. Keep `sid` unique.
2. If it should appear in a frame, add it to the matching mapping in
   `labor_data.py` (`MONTHLY_COLUMNS`, `QUARTERLY_COLUMNS`, or `HOURLY_COLUMNS`).
   Column names must be unique within a mapping.
3. Add a derived column in the relevant `_add_derived_*` function if needed,
   using `_safe_ratio()` for any division.
4. Run `pixi run fetch` (or `pixi run analyze --refresh`) so the new CSV is
   cached and committed.
5. Extend `tests/test_series.py` / `tests/test_labor_data.py` and the synthetic
   dataset in `tests/conftest.py` if the new series participates in assembly.

The catalog/assembly contract is guarded by
`test_labor_data_mappings_resolve_in_catalog` and
`test_column_renames_are_unique_within_each_mapping`; both will fail loudly if a
mapping references an unknown SID or collides.

### Add a headline statistic

1. Compute it in the appropriate helper and add it to the `stats` dict inside
   `compute_stats()` — this is the only place numbers are derived.
2. Render it in `render_report()` (add/extend a `_*_section`).
3. Consume it from `stats` in `labor_viz.py` if it should appear on a chart —
   never recompute or hardcode it.
4. Add an exact-value test in `tests/test_analysis.py` and, if rendered, a
   string-shape test for the section.

### Adjust trend regimes or the COVID baseline

The regime windows live in `analysis.REGIMES`; the pandemic baseline is
`analysis.COVID_BASELINE`. Changing either changes the report **and** the
charts, because both read the same `stats`. Note that `_regime_section`'s prose
is coupled to the `"2000-2019"` label (defect **D14**, pinned by a test) — update
both together.

### Change the visual style

Colors live in `series.PALETTE`; line drawing in `labor_viz._glow`; axis styling
in `labor_viz._style_axes`. The hero layout is `HeroFigure`. The static PNG is
8.0×4.5 in at 200 dpi (1600×900). Keep the palette keys exactly as tested by
`test_palette_has_exactly_the_expected_keys`.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `pixi: command not found` | Install pixi; the project has no non-pixi fallback. |
| `FredFetchError: Failed to fetch … HTTP …` | FRED unreachable or rate-limited. Retry later; the cache is fine. |
| `Execution Error: …` on `analyze`/`viz` | A fetch failure; run `pixi run fetch` while online, or check the SID. |
| Animation wrote a `.gif` instead of `.mp4` | ffmpeg unavailable or failed; the GIF fallback is expected. |
| `EmptySeriesError` | A statistics helper received an all-NaN/empty series — inspect the cache for that column. |
| `summary.json` write fails with a non-finite error | A statistic produced `NaN`/`inf`; find and guard the division. |
| Tests hit the network | Use the `fake_get` fixture; the autouse guard blocks real calls. |

## Pre-commit checklist

```powershell
pixi run style            # format + autofix
pixi run fmt --check      # verify formatting
pixi run ruff check --no-fix
pixi run test             # full suite
pixi run test-cov         # coverage sanity
```

Then re-run `pixi run analyze` and `pixi run viz` if you changed anything that
affects the committed deliverables in `output/`, and commit the regenerated
artifacts alongside the code. The interactive HTML is generated on demand and is
not committed; run `pixi run viz --interactive` only when you need it locally.

See [roadmap.md](roadmap.md) for planned work.
