"""CLI entrypoints: analysis.main and labor_viz.main, plus the JSON validity
tripwire for non-finite stats leakage."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

import analysis
import labor_viz
from analysis import compute_stats
from fred_data import FredFetchError

# ---------------------------------------------------------------------------
# analysis.main — unit tests with full pipeline mocking
# ---------------------------------------------------------------------------


def test_analysis_main_writes_findings_and_summary(
    monkeypatch, tmp_path, synthetic_data, synthetic_stats
):
    monkeypatch.setattr(
        "analysis.build",
        lambda refresh=False, bls_api_key=None: synthetic_data,
    )
    monkeypatch.setattr("analysis.compute_stats", lambda data: synthetic_stats)
    outdir = tmp_path / "out"
    outdir.mkdir()
    monkeypatch.setattr(sys, "argv", ["analysis.py", "--outdir", str(outdir)])
    analysis.main()
    assert (outdir / "findings.md").exists()
    summary = json.loads((outdir / "summary.json").read_text(encoding="utf-8"))
    assert isinstance(summary["prime_age"], dict)
    assert set(summary["prime_age"]) == {"levels", "regimes", "demographic_drag"}
    assert isinstance(summary["prime_age"]["levels"]["total"]["latest"], float)
    assert isinstance(summary["prime_age"]["regimes"]["2019-2026"]["total"], dict)
    assert isinstance(
        summary["prime_age"]["demographic_drag"]["demographic_drag_pp"], float
    )
    assert isinstance(summary["sector_wages"], dict)
    assert set(summary["sector_wages"]) == {
        "headcount_dynamics",
        "real_wage_growth",
        "wage_compression_ratios",
    }
    assert isinstance(
        summary["sector_wages"]["headcount_dynamics"]["agriculture"][
            "latest_headcount"
        ],
        float,
    )
    assert isinstance(
        summary["sector_wages"]["real_wage_growth"]["manufacturing"]["change_pct"],
        float,
    )
    assert isinstance(
        summary["sector_wages"]["wage_compression_ratios"]["construction"][
            "current_ratio"
        ],
        float,
    )
    assert summary["shift_share"]["status"] == "not_publishable"
    assert summary["weekly_hours"]["status"] == "not_publishable"


def test_analysis_main_refresh_flag_passes_through(
    monkeypatch, tmp_path, synthetic_data, synthetic_stats
):
    seen = {}
    monkeypatch.setattr(
        "analysis.build",
        lambda refresh=False, bls_api_key=None: (
            seen.update(refresh=refresh),
            synthetic_data,
        )[1],
    )
    monkeypatch.setattr("analysis.compute_stats", lambda data: synthetic_stats)
    outdir = tmp_path / "out"
    monkeypatch.setattr(
        sys, "argv", ["analysis.py", "--refresh", "--outdir", str(outdir)]
    )
    analysis.main()
    assert seen.get("refresh") is True


def test_analysis_main_network_failure_exits_cleanly(
    monkeypatch, tmp_path, synthetic_data, synthetic_stats
):
    """D11: analysis.main mirrors viz's clean SystemExit on fetch errors."""
    monkeypatch.setattr(
        "analysis.build",
        lambda refresh=False, bls_api_key=None: (_ for _ in ()).throw(
            FredFetchError("CIVPART", "HTTP 404")
        ),
    )
    monkeypatch.setattr("analysis.compute_stats", lambda data: synthetic_stats)
    outdir = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["analysis.py", "--outdir", str(outdir)])
    with pytest.raises(SystemExit) as excinfo:
        analysis.main()
    assert excinfo.value.code == 1


def test_analysis_main_uses_allow_nan_false(
    monkeypatch, tmp_path, synthetic_data, synthetic_stats
):
    """Pin: main() uses json.dumps(..., allow_nan=False)."""
    called = {}
    real_dumps = json.dumps

    def spy(obj, *args, **kwargs):
        called["allow_nan"] = kwargs.get("allow_nan", True)
        return real_dumps(obj, *args, **kwargs)

    monkeypatch.setattr(json, "dumps", spy)
    monkeypatch.setattr(
        "analysis.build",
        lambda refresh=False, bls_api_key=None: synthetic_data,
    )
    monkeypatch.setattr("analysis.compute_stats", lambda data: synthetic_stats)
    monkeypatch.setattr(
        sys, "argv", ["analysis.py", "--outdir", str(tmp_path / "ignored")]
    )
    analysis.main()
    assert called.get("allow_nan") is False


# ---------------------------------------------------------------------------
# labor_viz.main — unit tests with full pipeline mocking
# ---------------------------------------------------------------------------


def _mock_viz_pipeline(monkeypatch, synthetic_data, synthetic_stats) -> set:
    """Install fast doubles for all three builders, using real synthetic data."""
    monkeypatch.setattr(
        "labor_viz.build",
        lambda refresh=False, bls_api_key=None: synthetic_data,
    )
    monkeypatch.setattr("analysis.compute_stats", lambda data: synthetic_stats)
    seen: set = set()

    def fake_static(data, stats, outdir):
        seen.add("static")
        return outdir / "twitter_hero.png"

    def fake_animated(data, stats, outdir):
        seen.add("animated")
        return outdir / "twitter_hero.mp4"

    def fake_interactive(data, stats, outdir):
        seen.add("interactive")
        return outdir / "twitter_interactive.html"

    monkeypatch.setattr("labor_viz.build_static", fake_static)
    monkeypatch.setattr("labor_viz.build_animated", fake_animated)
    monkeypatch.setattr("labor_viz.build_interactive", fake_interactive)
    return seen


def test_viz_main_no_flags_builds_all_three(
    monkeypatch, tmp_path, synthetic_data, synthetic_stats
):
    seen = _mock_viz_pipeline(monkeypatch, synthetic_data, synthetic_stats)
    outdir = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["labor_viz.py", "--outdir", str(outdir)])
    labor_viz.main()
    assert seen == {"static", "animated", "interactive"}


@pytest.mark.parametrize(
    "flag,expected",
    [
        ("--static", {"static"}),
        ("--animated", {"animated"}),
        ("--interactive", {"interactive"}),
        ("--all", {"static", "animated", "interactive"}),
    ],
)
def test_viz_main_flag_matrix(
    flag, expected, monkeypatch, tmp_path, synthetic_data, synthetic_stats
):
    seen = _mock_viz_pipeline(monkeypatch, synthetic_data, synthetic_stats)
    outdir = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["labor_viz.py", flag, "--outdir", str(outdir)])
    labor_viz.main()
    assert seen == expected


def test_viz_main_refresh_passes_to_build(
    monkeypatch, tmp_path, synthetic_data, synthetic_stats
):
    seen = {}
    _mock_viz_pipeline(monkeypatch, synthetic_data, synthetic_stats)
    monkeypatch.setattr(
        "labor_viz.build",
        lambda refresh=False, bls_api_key=None: (
            seen.update(refresh=refresh),
            synthetic_data,
        )[1],
    )
    outdir = tmp_path / "out"
    monkeypatch.setattr(
        sys, "argv", ["labor_viz.py", "--refresh", "--static", "--outdir", str(outdir)]
    )
    labor_viz.main()
    assert seen.get("refresh") is True


def test_viz_main_fetch_failure_exits_with_systemexit(monkeypatch, tmp_path):
    """Pin: clean SystemExit(1) with 'Execution Error:' on fetch failures."""
    monkeypatch.setattr(
        "labor_viz.build",
        lambda refresh=False, bls_api_key=None: (_ for _ in ()).throw(
            FredFetchError("CIVPART", "HTTP 404")
        ),
    )
    outdir = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["labor_viz.py", "--outdir", str(outdir)])
    with pytest.raises(SystemExit) as excinfo:
        labor_viz.main()
    assert excinfo.value.code == 1


# ---------------------------------------------------------------------------
# JSON validity tripwires (no CLI, no mocks needed)
# ---------------------------------------------------------------------------


def test_allow_nan_false_rejects_nan_in_stats():
    bad = {"rates": {"men": {"first": float("nan")}}}
    with pytest.raises(ValueError):
        json.dumps(bad, indent=2, allow_nan=False)


def test_allow_nan_false_rejects_infinity_in_stats():
    bad = {"rates": {"men": {"first": float("inf")}}}
    with pytest.raises(ValueError):
        json.dumps(bad, indent=2, allow_nan=False)


def test_synthetic_stats_pass_allow_nan_false(synthetic_stats):
    text = json.dumps(synthetic_stats, indent=2, allow_nan=False)
    roundtrip = json.loads(text)
    assert roundtrip["coverage"]["missing_periods"] == ["2025-10"]


def test_zero_denominator_does_not_leak_into_stats(synthetic_raw):
    """D5: zero denominators must not leak inf/nan into stats (fixed by _safe_ratio)."""
    poisoned = dict(synthetic_raw)
    df = poisoned["LNU00000001"].copy()
    df.iloc[0] = 0.0
    poisoned["LNU00000001"] = df

    from labor_data import assemble

    data = assemble(poisoned)
    stats = compute_stats(data)

    json.dumps(stats, indent=2, allow_nan=False)


# ---------------------------------------------------------------------------
# integration subprocess tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("BLS_API_KEY"),
    reason="Requires BLS_API_KEY environment variable",
)
def test_analysis_cli_subprocess_writes_outputs(tmp_path):
    """Full integration using the real cached FRED files."""
    outdir = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, "-m", "analysis", "--outdir", str(outdir)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0
    assert (outdir / "findings.md").exists()
    assert (outdir / "summary.json").exists()
    text = (outdir / "summary.json").read_text(encoding="utf-8")
    json.loads(
        text, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite"))
    )


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("BLS_API_KEY"),
    reason="Requires BLS_API_KEY environment variable",
)
def test_viz_static_subprocess_writes_png(tmp_path):
    outdir = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, "-m", "labor_viz", "--static", "--outdir", str(outdir)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0
    assert (outdir / "twitter_hero.png").exists()
    assert (outdir / "twitter_hero.png").stat().st_size > 10_000
