# Documentation

This folder documents the U.S. Workforce Participation ("The Great
Convergence") analysis end to end: what it computes, where the data comes from,
how the pipeline is structured, and how to contribute.

Start with the root [README.md](../README.md) for the quick start.

## Map

| Document | Read it when you want to… |
|---|---|
| [architecture.md](architecture.md) | Understand the pipeline stages, module responsibilities, data flow, and error-handling model. |
| [data.md](data.md) | Look up a FRED/BLS series ID, a derived column, the cache format, the October 2025 gap, or the BLS mislabeling defect. |
| [methodology.md](methodology.md) | Know exactly how a statistic is defined (OLS regimes, COVID window, ratios, alignment, weekly hours, shift-share) and how to interpret it. |
| [outputs.md](outputs.md) | Understand the report/JSON schema, the visual specifications, or the CLI. |
| [development.md](development.md) | Set up the environment, follow conventions, run tests, or add a series. |
| [roadmap.md](roadmap.md) | See planned data sources (IPUMS CPS, SSA, Census) and enhancements. |
| [roadmap-original-notes.md](roadmap-original-notes.md) | Archive: original working notes retained for provenance; consolidated into roadmap.md. |

## Orientation

- **Audience:** analysts and developers who will run, extend, or audit the
  analysis.
- **Scope:** the six Python modules (`series.py`, `fred_data.py`, `data_common.py`,
  `labor_data.py`, `analysis.py`, `labor_viz.py`), the test suite, the cached
  raw data, and the generated outputs.
- **Non-goals:** this documentation does not restate the findings themselves.
  Read the generated [`output/findings.md`](../output/findings.md) for those.
  The committed artifact predates the 32-series expansion and the new
  weekly-hours/shift-share blocks; see the known-defect notes in
  [data.md](data.md#bls-series-known-defect) and
  [methodology.md](methodology.md#shift-share-decomposition-calculate_shift_share).
- **Short on time?** The root [CONTRIBUTING.md](../CONTRIBUTING.md) is a
  one-screen summary for contributors.

## Conventions used in these docs

- **pp** = percentage points (an absolute difference between two percentages).
  A move from 60% to 55% is −5 pp.
- Series IDs appear in `code` style (`CIVPART`, `LNS11300001`).
- Column names refer to the assembled pandas frames (`rate_men`, `gap_pp`).
- Paths are relative to the repository root.
