# Contributing

Thanks for helping improve this project. The full contributor guide — setup,
conventions, testing philosophy, the defect register, and extension recipes —
lives in **[docs/development.md](docs/development.md)**. This file is the short
version.

## Ground rules

1. **Work inside pixi.** Never use a system Python or `pip`.
   ```powershell
   pixi install
   pixi shell
   ```
2. **Never hardcode a number in a visualization.** Every headline figure comes
   from `analysis.compute_stats()`; read it from `stats`.
3. **Never interpolate the October 2025 CPS gap.** It stays `NaN`.
4. **Keep correlation framed as association**, not causation, in prose and on
   charts.

## Before you commit

```powershell
pixi run style            # ruff format + ruff check --fix
pixi run fmt --check
pixi run ruff check --no-fix
pixi run test
```

- The test suite holds a **high-bar standard**: pin exact math, boundaries, and
  failure modes — not line coverage. See
  [docs/development.md#testing](docs/development.md#testing).
- If your change affects generated output, regenerate and commit it:
  ```powershell
  pixi run analyze
  pixi run viz
  ```

## Where things live

| I want to… | Read |
|---|---|
| Understand the pipeline | [docs/architecture.md](docs/architecture.md) |
| Look up a series or column | [docs/data.md](docs/data.md) |
| Understand a statistic | [docs/methodology.md](docs/methodology.md) |
| Change the report or charts | [docs/outputs.md](docs/outputs.md) |
| Set up, test, or extend | [docs/development.md](docs/development.md) |
| See what's planned | [docs/roadmap.md](docs/roadmap.md) |
