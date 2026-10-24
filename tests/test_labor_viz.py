"""Visualization: styling helpers, the hero figure, reveal arithmetic, and all
three builders (static, animated incl. GIF fallbacks, interactive)."""

from __future__ import annotations

import numpy as np
import pytest
from matplotlib import pyplot as plt
from matplotlib.animation import FFMpegWriter, FuncAnimation
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

import labor_viz
from labor_viz import (
    ANIMATION_FPS,
    HeroFigure,
    _dnum,
    _finalize_interactive_html,
    _glow,
    _style_axes,
    build_animated,
    build_interactive,
    build_static,
)
from series import PALETTE

X = np.linspace(0.0, 10.0, 11)
Y = X**2


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def axes():
    fig, ax = plt.subplots()
    yield ax
    plt.close(fig)


def test_dnum_matches_matplotlib_conversion():
    from matplotlib.dates import date2num

    assert _dnum("1948-01-01") == date2num(np.datetime64("1948-01-01"))


def test_glow_returns_three_strokes_with_underglow_zorder(axes):
    strokes = _glow(axes, X, Y, "#ffffff", linestyle="--")
    assert len(strokes) == 3
    assert all(isinstance(stroke, Line2D) for stroke in strokes)
    assert strokes[0].get_alpha() == 0.05
    assert strokes[1].get_alpha() == 0.09
    assert strokes[2].get_linestyle() == "--"
    assert strokes[0].get_zorder() < strokes[2].get_zorder()
    np.testing.assert_allclose(np.asarray(strokes[2].get_ydata()), Y)


def test_glow_respects_custom_zorder(axes):
    strokes = _glow(axes, X, Y, "#ffffff", zorder=9)
    assert strokes[0].get_zorder() == 8
    assert strokes[2].get_zorder() == 9


def test_style_axes_percent_formatter(axes):
    _style_axes(axes, percent=True)
    assert axes.yaxis.get_major_formatter()(50, None) == "50%"
    assert axes.get_facecolor() == matplotlib_color(PALETTE["bg"])
    assert axes.spines["top"].get_visible() is False
    assert axes.spines["bottom"].get_visible() is True


def test_style_axes_dollar_formatter(axes):
    _style_axes(axes, dollars=True)
    assert axes.yaxis.get_major_formatter()(420, None) == "$420"


def test_style_axes_without_formatter_keeps_default(axes):
    _style_axes(axes)
    assert axes.yaxis.get_major_formatter()(420, None) != "$420"


# ---------------------------------------------------------------------------
# HeroFigure
# ---------------------------------------------------------------------------


@pytest.fixture
def hero(synthetic_data, synthetic_stats):
    figure = HeroFigure(synthetic_data, synthetic_stats)
    yield figure
    plt.close(figure.fig)


def test_hero_figure_exposes_both_panels(hero):
    assert hero._panel_a is not None
    assert hero._panel_b is not None
    assert hero._panel_a.twin is None
    assert hero._panel_b.twin is not None  # the W/M ratio axis


def test_hero_figure_registers_end_labels_for_every_series(hero):
    # panel A: 3 series x (leader + text); panel B: 2 x (leader + text)
    assert len(hero._end_labels) == 10


def test_hero_figure_registers_milestone_artists(hero):
    # panel A: 1948 gap arrow, total peak, COVID crash, Oct-2025 band
    assert len(hero._panel_a.artists) == 4
    # panel B: men and women change annotations
    assert len(hero._panel_b.artists) == 2


def test_hero_figure_panel_line_counts(hero):
    # panel A: 3 series; panel B: 2 earnings + 1 ratio
    assert len(hero._panel_a.lines) == 3
    assert len(hero._panel_b.lines) == 3
    for strokes, values in hero._panel_a.lines:
        assert len(strokes) == 3
        assert len(values) == len(hero._panel_a.dates)


# ---------------------------------------------------------------------------
# reveal arithmetic
# ---------------------------------------------------------------------------


def test_reveal_zero_shows_only_the_first_point(hero):
    """Pin (behavior): the 1948 point sits exactly on the panel start, so
    searchsorted(right) leaves one point visible at t=0."""
    hero.reveal(0.0)
    assert visible_point_count(hero._panel_a) == 1
    assert hero._panel_b.ax.get_visible() is False


def test_reveal_one_shows_every_point(hero):
    hero.reveal(1.0)
    assert visible_point_count(hero._panel_a) == len(hero._panel_a.dates)
    assert visible_point_count(hero._panel_b) == len(hero._panel_b.dates)
    assert hero._panel_b.ax.get_visible() is True


@pytest.mark.parametrize("t", [-5.0, -0.1])
def test_reveal_clamps_below_zero(hero, t):
    hero.reveal(t)
    assert visible_point_count(hero._panel_a) == 1


@pytest.mark.parametrize("t", [1.1, 5.0])
def test_reveal_clamps_above_one(hero, t):
    hero.reveal(t)
    assert visible_point_count(hero._panel_a) == len(hero._panel_a.dates)
    assert hero._end_labels[0].get_alpha() == 1.0


def test_reveal_panel_b_handoff_boundary(hero):
    fraction = (hero._panel_b.start - hero._panel_a.start) / (
        hero._panel_a.end - hero._panel_a.start
    )
    hero.reveal(fraction - 0.001)
    assert hero._panel_b.ax.get_visible() is False
    hero.reveal(fraction + 0.001)
    assert hero._panel_b.ax.get_visible() is True


def test_reveal_end_labels_alpha_ramp(hero):
    hero.reveal(0.5)
    assert hero._end_labels[0].get_alpha() == 0.0
    hero.reveal(0.94)
    assert hero._end_labels[0].get_alpha() == pytest.approx(0.5)
    hero.reveal(1.0)
    assert hero._end_labels[0].get_alpha() == 1.0


def test_reveal_panel_cutoff_uses_searchsorted_semantics(hero):
    panel = hero._panel_a
    hero._reveal_panel(panel, 0.5)
    cutoff = panel.start + 0.5 * (panel.end - panel.start)
    expected = int(np.searchsorted(panel.dates, cutoff, side="right"))
    assert visible_point_count(panel) == expected
    assert expected < len(panel.dates)


def test_reveal_panel_hides_milestones_before_their_date(hero):
    gaps = [date for date, _ in hero._panel_a.artists]
    earliest = min(gaps)
    hero.reveal(0.1)
    for date, artists in hero._panel_a.artists:
        visible = all(artist.get_visible() for artist in artists)
        if date <= hero._panel_a.start + 0.1 * (
            hero._panel_a.end - hero._panel_a.start
        ):
            assert visible or date == earliest  # earliest group may show 1 point
        else:
            assert not visible


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------


def test_build_static_writes_1600x900_png(synthetic_data, synthetic_stats, outdir):
    path = build_static(synthetic_data, synthetic_stats, outdir)
    assert path == outdir / "twitter_hero.png"
    assert path.exists()
    assert path.stat().st_size > 10_000
    from PIL import Image

    with Image.open(path) as image:
        assert image.size == (1600, 900)


def test_build_animated_writes_mp4_when_ffmpeg_available(
    synthetic_data, synthetic_stats, outdir, monkeypatch
):
    monkeypatch.setattr(labor_viz, "ANIMATION_FRAMES", 6)
    path = build_animated(synthetic_data, synthetic_stats, outdir)
    if FFMpegWriter(fps=ANIMATION_FPS).isAvailable():
        assert path == outdir / "twitter_hero.mp4"
        assert path.exists()
        assert path.stat().st_size > 1000
    else:
        pytest.skip("ffmpeg unavailable in this environment")


def test_build_animated_falls_back_to_gif_without_ffmpeg(
    synthetic_data, synthetic_stats, outdir, monkeypatch
):
    monkeypatch.setattr(labor_viz, "ANIMATION_FRAMES", 6)
    monkeypatch.setattr(FFMpegWriter, "isAvailable", lambda self: False)
    path = build_animated(synthetic_data, synthetic_stats, outdir)
    assert path == outdir / "twitter_hero.gif"
    assert path.exists()
    assert path.stat().st_size > 100


def test_build_animated_falls_back_to_gif_on_save_failure(
    synthetic_data, synthetic_stats, outdir, monkeypatch, capsys
):
    """D12: the OSError fallback path was entirely unexercised."""
    monkeypatch.setattr(labor_viz, "ANIMATION_FRAMES", 6)
    real_save = FuncAnimation.save

    def explode_on_ffmpeg(self, *args, **kwargs):
        writer = kwargs.get("writer")
        if isinstance(writer, FFMpegWriter):
            msg = "ffmpeg exploded"
            raise OSError(msg)
        return real_save(self, *args, **kwargs)

    monkeypatch.setattr(FuncAnimation, "save", explode_on_ffmpeg)
    path = build_animated(synthetic_data, synthetic_stats, outdir)
    assert path == outdir / "twitter_hero.gif"
    assert path.exists()
    assert "ffmpeg failed" in capsys.readouterr().out


def test_finalize_interactive_html_replaces_title_and_adds_doctype(outdir):
    path = outdir / "page.html"
    path.write_text(
        "<html><head><title>plotly-logomark</title></head></html>", encoding="utf-8"
    )
    _finalize_interactive_html(path)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("<!DOCTYPE html>\n")
    assert "<title>The Great Convergence" in text
    assert "plotly-logomark" not in text


def test_finalize_interactive_html_is_idempotent(outdir):
    path = outdir / "page.html"
    path.write_text(
        "<html><head><title>plotly-logomark</title></head></html>", encoding="utf-8"
    )
    _finalize_interactive_html(path)
    once = path.read_text(encoding="utf-8")
    _finalize_interactive_html(path)
    assert path.read_text(encoding="utf-8") == once


def test_finalize_interactive_html_keeps_existing_doctype(outdir):
    path = outdir / "page.html"
    path.write_text(
        "<!DOCTYPE html><html><head><title>plotly-logomark</title></head></html>",
        encoding="utf-8",
    )
    _finalize_interactive_html(path)
    text = path.read_text(encoding="utf-8")
    assert text.count("<!DOCTYPE") == 1
    assert text.startswith("<!DOCTYPE html><html>")


def test_build_interactive_writes_dark_titled_html(
    synthetic_data, synthetic_stats, outdir
):
    path = build_interactive(synthetic_data, synthetic_stats, outdir)
    assert path == outdir / "twitter_interactive.html"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("<!DOCTYPE html>")
    assert "<title>The Great Convergence" in text
    # At least 5 scatter traces; plotly emits some duplicates in the JSON.
    assert text.count('"type":"scatter"') >= 5
    for name in ("Men", "Women", "All", "Men (real)", "Women (real)", "earnings ratio"):
        assert name in text


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def visible_point_count(panel) -> int:
    strokes, _ = panel.lines[0]
    return len(strokes[0].get_xdata())


def matplotlib_color(hex_color: str):
    from matplotlib.colors import to_rgba

    return to_rgba(hex_color)


# ---------------------------------------------------------------------------
# panel C edge cases
# ---------------------------------------------------------------------------


def _with_shift_share(stats: dict, *, within: float, between: float) -> dict:
    """Copy ``stats`` with a hand-set shift-share decomposition block."""
    clone = {**stats, "shift_share": {**stats.get("shift_share", {})}}
    clone["shift_share"]["within_group_effect"] = within
    clone["shift_share"]["between_group_effect"] = between
    return clone


def _panel_c_bar_geometry(synthetic_data, stats):
    """Build a HeroFigure and return the two stacked-bar heights and the
    between-bar center on the x axis."""
    figure = HeroFigure(synthetic_data, stats)
    try:
        ax = figure._panel_c.ax
        assert len(ax.patches) == 2, "panel C should hold exactly the two bars"
        within_bar, between_bar = ax.patches
        assert isinstance(within_bar, Rectangle)
        assert isinstance(between_bar, Rectangle)
        return (
            within_bar.get_height(),
            between_bar.get_height(),
            between_bar.get_x() + between_bar.get_width() / 2,
        )
    finally:
        plt.close(figure.fig)


def test_panel_c_zero_total_falls_back_to_even_split(synthetic_data, synthetic_stats):
    """Pin (behavior): a zero shift-share total must split the bar 50/50
    instead of raising ZeroDivisionError."""
    stats = _with_shift_share(synthetic_stats, within=0.0, between=0.0)
    within_height, between_height, between_center = _panel_c_bar_geometry(
        synthetic_data, stats
    )
    assert within_height == 50.0
    assert between_height == 50.0
    # 50% split: the between bar is offset left by 50/200 = 0.25 from x=0.5.
    assert between_center == pytest.approx(0.25)


def test_panel_c_cancelling_components_also_fall_back_to_even_split(
    synthetic_data, synthetic_stats
):
    """The guard keys on abs(within + between), so +3 and -3 also hit it."""
    stats = _with_shift_share(synthetic_stats, within=3.0, between=-3.0)
    within_height, between_height, _ = _panel_c_bar_geometry(synthetic_data, stats)
    assert within_height == 50.0
    assert between_height == 50.0


def test_panel_c_nonzero_total_uses_component_proportions(
    synthetic_data, synthetic_stats
):
    """Control: 3:1 components must stack 75/25, not the 50/50 fallback."""
    stats = _with_shift_share(synthetic_stats, within=3.0, between=1.0)
    within_height, between_height, _ = _panel_c_bar_geometry(synthetic_data, stats)
    assert within_height == 75.0
    assert between_height == 25.0


def test_reveal_hides_panel_c_until_its_start_fraction(hero):
    """Pin (behavior): panel C stays hidden until the reveal passes its start."""
    panel_a = hero._panel_a
    hero._panel_c.start = panel_a.start + 0.9 * (panel_a.end - panel_a.start)
    hero._panel_c.end = panel_a.end

    hero.reveal(0.9 - 0.001)
    assert hero._panel_c.ax.get_visible() is False

    hero.reveal(0.9 + 0.001)
    assert hero._panel_c.ax.get_visible() is True
