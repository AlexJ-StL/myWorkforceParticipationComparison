"""Twitter-optimized visualizations of U.S. workforce participation trends.

Produces three deliverables in ``output/``:

* ``twitter_hero.png``          -- static 1600x900 hero chart
* ``twitter_hero.mp4``          -- animated reveal (ffmpeg; GIF fallback)
* ``twitter_interactive.html``  -- interactive plotly version

Run ``pixi run viz`` to build all three.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import requests
from matplotlib.animation import FFMpegWriter, FuncAnimation, PillowWriter
from matplotlib.artist import Artist
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch
from matplotlib.text import Text

from analysis import col, compute_stats
from fred_data import FredFetchError
from labor_data import WorkforceData, build
from series import PALETTE

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
FIGURE_W = 8.0
FIGURE_H = 4.5
DPI = 200
ANIMATION_FRAMES = 180
ANIMATION_FPS = 15


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _dnum(value: str) -> float:
    """Convert an ISO date string to matplotlib date numbers."""
    return float(mdates.date2num(pd.Timestamp(value)))


def _glow(
    ax: Axes,
    x: np.ndarray,
    y: np.ndarray,
    color: str,
    *,
    linewidth: float = 1.7,
    zorder: int = 3,
    **kwargs,
) -> list[Line2D]:
    """Draw a line with a soft neon underglow; returns all stroke artists."""
    strokes: list[Line2D] = []
    for glow_lw, alpha in ((8.0, 0.05), (4.5, 0.09)):
        strokes.append(
            ax.plot(
                x,
                y,
                color=color,
                linewidth=glow_lw,
                alpha=alpha,
                solid_capstyle="round",
                zorder=zorder - 1,
            )[0]
        )
    strokes.append(
        ax.plot(
            x,
            y,
            color=color,
            linewidth=linewidth,
            solid_capstyle="round",
            zorder=zorder,
            **kwargs,
        )[0]
    )
    return strokes


def _style_axes(ax: Axes, *, percent: bool = False, dollars: bool = False) -> None:
    """Apply the dark chart styling to an axes."""
    ax.set_facecolor(PALETTE["bg"])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_color(PALETTE["grid"])
    ax.grid(True, axis="y", color="#243447", linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(colors=PALETTE["muted"], labelsize=6.2, length=0, pad=2)
    if percent:
        ax.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda value, _: f"{value:.0f}%")
        )
    elif dollars:
        ax.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda value, _: f"${value:.0f}")
        )


@dataclass
class _PanelState:
    """Line data and milestone artists for one chart panel."""

    ax: Axes
    twin: Axes | None
    label: Text
    dates: np.ndarray
    lines: list[tuple[list[Line2D], np.ndarray]]
    artists: list[tuple[float, list[Artist]]]
    start: float
    end: float

    def set_visible(self, visible: bool) -> None:
        self.ax.set_visible(visible)
        if self.twin is not None:
            self.twin.set_visible(visible)
        self.label.set_visible(visible)


# --------------------------------------------------------------------------
# hero figure
# --------------------------------------------------------------------------


class HeroFigure:
    """1600x900 dark-theme hero chart, reusable for the animated reveal."""

    def __init__(self, data: WorkforceData, stats: dict) -> None:
        self._data = data
        self._stats = stats
        self.fig = plt.figure(
            figsize=(FIGURE_W, FIGURE_H), dpi=DPI, facecolor=PALETTE["bg"]
        )
        self._end_labels: list[Artist] = []
        self._draw_header()
        self._draw_chips()
        self._panel_a = self._build_panel_a()
        self._panel_b = self._build_panel_b()
        self._panel_c = self._build_panel_c()
        self._draw_footer()

    # -- static layout -----------------------------------------------------

    def _draw_header(self) -> None:
        stats = self._stats
        men = stats["rates"]["men"]
        women = stats["rates"]["women"]
        fig = self.fig
        fig.text(
            0.055,
            0.972,
            "U.S. LABOR FORCE  ·  1948–2026",
            color=PALETTE["accent"],
            fontsize=6.5,
            fontweight="bold",
            va="top",
        )
        fig.text(
            0.055,
            0.972,
            "U.S. LABOR FORCE  ·  1948–2026",
            color=PALETTE["accent"],
            fontsize=6.5,
            fontweight="bold",
            va="top",
        )
        fig.text(
            0.055,
            0.935,
            "The Great Convergence",
            color=PALETTE["total"],
            fontsize=19,
            fontweight="bold",
            va="top",
        )
        fig.text(
            0.055,
            0.868,
            f"Men's participation fell {abs(men['change_since_first']):.1f} points "
            f"while women's rose {women['change_since_first']:.1f} — "
            "and since 2000, both have stalled",
            color=PALETTE["muted"],
            fontsize=7.2,
            va="top",
        )
        fig.text(
            0.945,
            0.972,
            "Source: BLS via FRED",
            color=PALETTE["muted"],
            fontsize=6.2,
            ha="right",
            va="top",
        )
        fig.text(
            0.945,
            0.947,
            "Data through Sep 2026",
            color=PALETTE["muted"],
            fontsize=6.2,
            ha="right",
            va="top",
        )

    def _draw_chips(self) -> None:
        stats = self._stats
        men = stats["rates"]["men"]
        women = stats["rates"]["women"]
        gap = stats["gap"]
        earnings = stats["earnings"]
        ratio = earnings["ratios"]["nominal"]
        chips = [
            (f"{men['change_since_first']:+.1f} pp", "Men, 1948 → 2026"),
            (f"{women['change_since_first']:+.1f} pp", "Women, 1948 → 2026"),
            (f"{gap['first']:.1f} → {gap['latest']:.1f} pp", "Gender gap"),
            (
                (
                    f"{earnings['series']['women']['real_change_pct']:+.0f}% "
                    f"vs {earnings['series']['men']['real_change_pct']:+.0f}%"
                ),
                "Real pay growth, W/M",
            ),
            (f"{ratio['first']:.1f}% → {ratio['latest']:.1f}%", "W/M earnings ratio"),
        ]
        left = 0.055
        top = 0.785
        width = 0.163
        height = 0.052
        spacing = 0.014
        for index, (value, label) in enumerate(chips):
            self._chip(
                left + index * (width + spacing),
                top,
                width,
                height,
                value,
                label,
            )

    def _chip(
        self, x: float, y: float, w: float, h: float, value: str, label: str
    ) -> None:
        fig = self.fig
        box = FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0,rounding_size=0.008",
            transform=fig.transFigure,
            facecolor="#1c2b3a",
            edgecolor=PALETTE["grid"],
            linewidth=0.7,
        )
        fig.add_artist(box)
        fig.text(
            x + 0.012,
            y + h * 0.66,
            value,
            color=PALETTE["total"],
            fontsize=9.5,
            fontweight="bold",
            va="center",
        )
        fig.text(
            x + 0.012,
            y + h * 0.25,
            label,
            color=PALETTE["muted"],
            fontsize=5.8,
            va="center",
        )

    def _draw_footer(self) -> None:
        fig = self.fig
        fig.text(
            0.055,
            0.075,
            "Rates: monthly, seasonally adjusted, through Sep 2026 (Oct 2025 was "
            "not collected). Earnings: quarterly, full-time wage & salary "
            "workers, constant 1982-84 $.",
            color=PALETTE["muted"],
            fontsize=5.3,
            va="center",
        )
        fig.text(
            0.055,
            0.048,
            "Source: U.S. Bureau of Labor Statistics via FRED · descriptive "
            "analysis, not causal estimates",
            color=PALETTE["muted"],
            fontsize=5.3,
            va="center",
        )

    # -- panels ------------------------------------------------------------

    def _build_panel_a(self) -> _PanelState:
        monthly = self._data.monthly
        ax = self.fig.add_axes((0.055, 0.475, 0.79, 0.265))
        _style_axes(ax, percent=True)
        ax.set_ylim(26, 94)
        ax.set_xlim(_dnum("1947-06-01"), _dnum("2027-06-01"))
        ax.xaxis.set_major_locator(mdates.YearLocator(10))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.yaxis.set_major_locator(mticker.MultipleLocator(10))

        label = self.fig.text(
            0.055,
            0.752,
            "LABOR FORCE PARTICIPATION RATE (%, SA)",
            color=PALETTE["total"],
            fontsize=6.8,
            fontweight="bold",
            va="bottom",
        )

        dates = mdates.date2num(monthly.index.to_numpy())
        lines: list[tuple[list[Line2D], np.ndarray]] = []
        for column, color, linestyle in (
            ("rate_men", PALETTE["men"], "solid"),
            ("rate_women", PALETTE["women"], "solid"),
            ("rate_total", PALETTE["total"], (0, (5, 3))),
        ):
            values = col(monthly, column).to_numpy(dtype=float)
            strokes = _glow(ax, dates, values, color, linestyle=linestyle)
            lines.append((strokes, values))

        milestone_artists: list[tuple[float, list[Artist]]] = []
        self._panel_a_milestones(ax, milestone_artists)
        self._panel_a_end_labels(ax, dates)

        return _PanelState(
            ax=ax,
            twin=None,
            label=label,
            dates=dates,
            lines=lines,
            artists=milestone_artists,
            start=_dnum("1948-01-01"),
            end=_dnum("2026-09-01"),
        )

    def _panel_a_milestones(
        self, ax: Axes, milestone_artists: list[tuple[float, list[Artist]]]
    ) -> None:
        stats = self._stats
        men_first = stats["rates"]["men"]["first"]
        women_first = stats["rates"]["women"]["first"]

        # 1948 starting gap, double-headed arrow
        x_arrow = _dnum("1948-03-01")
        arrow = ax.annotate(
            "",
            xy=(x_arrow, men_first),
            xytext=(x_arrow, women_first),
            arrowprops={
                "arrowstyle": "<->",
                "color": PALETTE["muted"],
                "lw": 0.8,
                "shrinkA": 0,
                "shrinkB": 0,
            },
        )
        gap_text = ax.text(
            _dnum("1950-01-01"),
            68.0,
            f"{stats['gap']['first']:.1f} pt gap",
            color=PALETTE["muted"],
            fontsize=6.2,
            va="center",
        )
        milestone_artists.append((x_arrow, [arrow, gap_text]))

        # total peak, Jan 2000
        peak = stats["rates"]["total"]["peak"]
        peak_date = pd.Timestamp(stats["rates"]["total"]["peak_date"] + "-01")
        dot = ax.plot(
            [_dnum(str(peak_date))],
            [peak],
            marker="o",
            ms=4,
            mfc=PALETTE["bg"],
            mec=PALETTE["total"],
            mew=1.2,
            zorder=6,
        )[0]
        peak_label = ax.annotate(
            f"Total peak {peak:.1f}%\n{stats['rates']['total']['peak_date']}",
            xy=(_dnum(str(peak_date)), peak),
            xytext=(_dnum("2003-01-01"), 79),
            color=PALETTE["total"],
            fontsize=6.2,
            ha="center",
            arrowprops={
                "arrowstyle": "-",
                "color": PALETTE["muted"],
                "lw": 0.6,
                "alpha": 0.7,
            },
        )
        milestone_artists.append((_dnum(str(peak_date)), [dot, peak_label]))

        # COVID crash, Apr 2020
        covid = stats["covid"]["total"]
        trough_date = pd.Timestamp(covid["trough_date"] + "-01")
        covid_dot = ax.plot(
            [_dnum(str(trough_date))],
            [covid["trough"]],
            marker="o",
            ms=4,
            mfc=PALETTE["bg"],
            mec=PALETTE["accent"],
            mew=1.2,
            zorder=6,
        )[0]
        covid_label = ax.annotate(
            f"COVID crash: {covid['drop_pp']:+.1f} pp\nvs Dec 2019",
            xy=(_dnum(str(trough_date)), covid["trough"]),
            xytext=(_dnum("2021-06-01"), 38),
            color=PALETTE["accent"],
            fontsize=6.2,
            ha="center",
            arrowprops={
                "arrowstyle": "-",
                "color": PALETTE["accent"],
                "lw": 0.6,
                "alpha": 0.7,
            },
        )
        milestone_artists.append((_dnum(str(trough_date)), [covid_dot, covid_label]))

        # October 2025 data gap
        band = ax.axvspan(
            _dnum("2025-09-20"),
            _dnum("2025-11-10"),
            color=PALETTE["muted"],
            alpha=0.10,
            zorder=1,
        )
        band_text = ax.text(
            _dnum("2025-10-15"),
            30.0,
            "no Oct '25 data",
            color=PALETTE["muted"],
            fontsize=5.2,
            ha="center",
            va="bottom",
        )
        milestone_artists.append((_dnum("2025-11-10"), [band, band_text]))

    def _panel_a_end_labels(self, ax: Axes, dates: np.ndarray) -> None:
        stats = self._stats
        rows = {"men": 82, "total": 60, "women": 38}
        for sex, color in (
            ("men", PALETTE["men"]),
            ("total", PALETTE["total"]),
            ("women", PALETTE["women"]),
        ):
            latest = stats["rates"][sex]["latest"]
            last_x = float(dates[-1])
            leader = ax.plot(
                [last_x, last_x + 40],
                [latest, rows[sex]],
                color=color,
                lw=0.6,
                alpha=0.6,
                zorder=4,
            )[0]
            text = ax.text(
                last_x + 55,
                rows[sex],
                f"{sex.capitalize()} {latest:.1f}%",
                color=color,
                fontsize=6.6,
                fontweight="bold",
                va="center",
            )
            self._end_labels.extend([leader, text])

    def _build_panel_b(self) -> _PanelState:
        quarterly = self._data.quarterly
        ax = self.fig.add_axes((0.055, 0.155, 0.79, 0.225))
        _style_axes(ax, dollars=True)
        ax.set_ylim(235, 470)
        ax.set_xlim(_dnum("1978-06-01"), _dnum("2027-06-01"))
        ax.xaxis.set_major_locator(mdates.YearLocator(10))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.yaxis.set_major_locator(mticker.MultipleLocator(50))

        label = self.fig.text(
            0.055,
            0.392,
            "MEDIAN USUAL WEEKLY EARNINGS (FULL-TIME, CONSTANT 1982-84 $)  ·  "
            "GOLD = WOMEN/MEN RATIO (RIGHT AXIS)",
            color=PALETTE["total"],
            fontsize=6.8,
            fontweight="bold",
            va="bottom",
        )

        dates = mdates.date2num(quarterly.index.to_numpy())
        lines: list[tuple[list[Line2D], np.ndarray]] = []
        for column, color in (
            ("weekly_real_men", PALETTE["men"]),
            ("weekly_real_women", PALETTE["women"]),
        ):
            values = col(quarterly, column).to_numpy(dtype=float)
            strokes = _glow(ax, dates, values, color)
            lines.append((strokes, values))

        # women-to-men earnings ratio on a secondary axis
        ax2 = ax.twinx()
        ax2.set_ylim(55, 95)
        _style_axes(ax2, percent=True)
        ax2.grid(False)
        ax2.tick_params(labelsize=6.0)
        ratio = col(quarterly, "earnings_ratio_nominal").to_numpy(dtype=float)
        strokes = _glow(ax2, dates, ratio, PALETTE["accent"], linewidth=1.3, zorder=5)
        lines.append((strokes, ratio))

        # in-plot change annotations (appear once the timeline passes 2008)
        milestone_artists: list[tuple[float, list[Artist]]] = []
        for sex, color, row in (
            ("men", PALETTE["men"], 432),
            ("women", PALETTE["women"], 268),
        ):
            change = self._stats["earnings"]["series"][sex]["real_change_pct"]
            milestone_artists.append(
                (
                    _dnum("2008-01-01"),
                    [
                        ax.text(
                            _dnum("2008-01-01"),
                            row,
                            f"{change:+.1f}% real since 1979",
                            color=color,
                            fontsize=6.0,
                            ha="center",
                            va="center",
                        )
                    ],
                )
            )

        self._panel_b_end_labels(ax, dates)

        return _PanelState(
            ax=ax,
            twin=ax2,
            label=label,
            dates=dates,
            lines=lines,
            artists=milestone_artists,
            start=_dnum("1979-01-01"),
            end=_dnum("2026-04-01"),
        )

    def _panel_b_end_labels(self, ax: Axes, dates: np.ndarray) -> None:
        stats = self._stats
        earnings = stats["earnings"]["series"]
        rows = {"men": 445, "women": 355}

        for sex, color in (("men", PALETTE["men"]), ("women", PALETTE["women"])):
            latest = earnings[sex]["real_latest"]
            last_x = float(dates[-1])
            leader = ax.plot(
                [last_x, last_x + 40],
                [latest, rows[sex]],
                color=color,
                lw=0.6,
                alpha=0.6,
                zorder=4,
            )[0]
            text = ax.text(
                last_x + 55,
                rows[sex],
                f"{sex.capitalize()} ${latest:.0f}",
                color=color,
                fontsize=6.6,
                fontweight="bold",
                va="center",
            )
            self._end_labels.extend([leader, text])

    def _build_panel_c(self) -> _PanelState:
        shift_share = self._stats.get("shift_share", {})
        within = shift_share.get("within_group_effect", 0.0)
        between = shift_share.get("between_group_effect", 0.0)
        total = within + between

        # Convert to absolute values for display
        within_abs = abs(within)
        between_abs = abs(between)
        total_abs = abs(total)

        # Calculate percentages for stacking
        if total_abs == 0:
            within_pct = 50.0
            between_pct = 50.0
        else:
            within_pct = (within_abs / total_abs) * 100
            between_pct = (between_abs / total_abs) * 100

        # Colors for the components
        within_color = PALETTE["accent"]  # Using accent color for behavioral
        between_color = PALETTE["total"]  # Using total color for demographic

        # Create a simple bar chart for shift-share decomposition

        # Panel position: below panel B (0.155 height, starting at 0.100)
        ax = self.fig.add_axes((0.055, 0.100, 0.79, 0.080))
        _style_axes(ax)
        ax.set_ylim(0, 100)
        ax.set_xlim(0, 1)

        # Create stacked bar visualization
        bar_width = 0.8
        x_pos = 0.5

        # Draw bars
        ax.bar(
            x_pos,
            within_pct,
            width=bar_width,
            bottom=0,
            color=within_color,
            alpha=0.7,
            linewidth=1.5,
            edgecolor="white",
            zorder=5,
        )

        between_x = x_pos - within_pct / 200  # Offset between bars
        ax.bar(
            between_x,
            between_pct,
            width=bar_width,
            bottom=0,
            color=between_color,
            alpha=0.7,
            linewidth=1.5,
            edgecolor="white",
            zorder=5,
        )

        # Create text labels
        label = self.fig.text(
            0.055,
            0.135,
            "SHIFT-SHARE DECOMPOSITION (2000-2026): Behavioral vs. Demographic",
            color=PALETTE["total"],
            fontsize=6.0,
            fontweight="bold",
            va="bottom",
        )

        # Add legend and values
        ax.text(
            0.065,
            0.105,
            f"Within-group (behavioral): {within:+.1f} pp",
            color=within_color,
            fontsize=5.5,
            ha="left",
            va="top",
            bbox={"boxstyle": "round", "facecolor": "black", "alpha": 0.7, "pad": 0.3},
        )
        ax.text(
            0.065,
            0.090,
            f"Between-group (demographic): {between:+.1f} pp",
            color=between_color,
            fontsize=5.5,
            ha="left",
            va="top",
            bbox={"boxstyle": "round", "facecolor": "black", "alpha": 0.7, "pad": 0.3},
        )

        # Add total line
        ax.plot(
            [0.05, 0.95],
            [50, 50],
            color=PALETTE["muted"],
            linewidth=0.8,
            linestyle="--",
            alpha=0.5,
            zorder=1,
        )
        ax.text(
            0.95,
            50,
            f"Total change: {total:+.1f} pp",
            color=PALETTE["muted"],
            fontsize=5.5,
            ha="right",
            va="center",
        )

        # Hide axes
        ax.set_xticks([])
        ax.set_yticks([])
        ax.spines["bottom"].set_visible(False)
        ax.spines["top"].set_visible(False)
        ax.spines["left"].set_visible(False)
        ax.spines["right"].set_visible(False)

        # Create panel state
        return _PanelState(
            ax=ax,
            twin=None,
            label=label,
            dates=np.array([0.0, 1.0]),
            lines=[],
            artists=[],
            start=0.0,
            end=1.0,
        )

    # -- reveal / animation ------------------------------------------------

    def reveal(self, t: float) -> None:
        """Reveal the chart up to timeline fraction ``t`` in [0, 1]."""
        t = min(max(t, 0.0), 1.0)
        self._reveal_panel(self._panel_a, t)

        panel_b_start = (self._panel_b.start - self._panel_a.start) / (
            self._panel_a.end - self._panel_a.start
        )
        if t <= panel_b_start:
            self._panel_b.set_visible(False)
            return

        self._panel_b.set_visible(True)
        u = (t - panel_b_start) / (1.0 - panel_b_start)
        self._reveal_panel(self._panel_b, u)

        panel_c_start = (self._panel_c.start - self._panel_a.start) / (
            self._panel_a.end - self._panel_a.start
        )
        if t <= panel_c_start:
            self._panel_c.set_visible(False)
            return

        self._panel_c.set_visible(True)
        v = (t - panel_c_start) / (1.0 - panel_c_start)
        self._reveal_panel(self._panel_c, v)

        alpha = min(max((t - 0.88) / 0.12, 0.0), 1.0)
        for artist in self._end_labels:
            artist.set_alpha(alpha)

    def _reveal_panel(self, panel: _PanelState, u: float) -> None:
        cutoff = panel.start + u * (panel.end - panel.start)
        count = int(np.searchsorted(panel.dates, cutoff, side="right"))
        for strokes, values in panel.lines:
            for line in strokes:
                line.set_data(panel.dates[:count], values[:count])
        for date, artists in panel.artists:
            for artist in artists:
                artist.set_visible(date <= cutoff)


# --------------------------------------------------------------------------
# builders
# --------------------------------------------------------------------------


def build_static(data: WorkforceData, stats: dict, outdir: Path) -> Path:
    """Render the final hero chart as a 1600x900 PNG."""
    hero = HeroFigure(data, stats)
    hero.reveal(1.0)
    path = outdir / "twitter_hero.png"
    hero.fig.savefig(path, dpi=DPI, facecolor=PALETTE["bg"])
    plt.close(hero.fig)
    return path


def build_animated(data: WorkforceData, stats: dict, outdir: Path) -> Path:
    """Render an animated reveal of the hero chart."""
    hero = HeroFigure(data, stats)

    def update(frame: int) -> None:
        hero.reveal(frame / (ANIMATION_FRAMES - 1))

    animation = FuncAnimation(
        hero.fig,
        update,
        frames=ANIMATION_FRAMES,
        interval=1000 / ANIMATION_FPS,
    )

    mp4_path = outdir / "twitter_hero.mp4"
    writer = FFMpegWriter(fps=ANIMATION_FPS, bitrate=2600)
    if not writer.isAvailable():
        gif_path = outdir / "twitter_hero.gif"
        animation.save(gif_path, writer=PillowWriter(fps=ANIMATION_FPS))
        plt.close(hero.fig)
        print("[warn] ffmpeg not found; saved GIF instead")
        return gif_path

    try:
        animation.save(mp4_path, writer=writer)
    except OSError as exc:
        gif_path = outdir / "twitter_hero.gif"
        animation.save(gif_path, writer=PillowWriter(fps=ANIMATION_FPS))
        plt.close(hero.fig)
        print(f"[warn] ffmpeg failed ({exc}); saved GIF instead")
        return gif_path

    plt.close(hero.fig)
    return mp4_path


def _finalize_interactive_html(path: Path) -> None:
    """Give the plotly bundle page a real <title> and an HTML5 doctype."""
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "<title>plotly-logomark</title>",
        "<title>The Great Convergence — U.S. workforce participation, "
        "1948–2026</title>",
    )
    if not text.startswith("<!DOCTYPE"):
        text = f"<!DOCTYPE html>\n{text}"
    path.write_text(text, encoding="utf-8")


def build_interactive(data: WorkforceData, stats: dict, outdir: Path) -> Path:
    """Render an interactive plotly version of the same story."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    monthly = data.monthly
    quarterly = data.quarterly

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=False,
        vertical_spacing=0.16,
        row_heights=[0.55, 0.45],
        specs=[[{"secondary_y": False}], [{"secondary_y": True}]],
        subplot_titles=(
            "Labor force participation rate (%)",
            (
                "Median usual weekly earnings, constant 1982-84 $ "
                "(right axis: W/M ratio)"
            ),
        ),
    )

    for column, color, name, dash in (
        ("rate_men", PALETTE["men"], "Men", None),
        ("rate_women", PALETTE["women"], "Women", None),
        ("rate_total", PALETTE["total"], "All", "dash"),
    ):
        series = col(monthly, column)
        fig.add_trace(
            go.Scatter(
                x=series.index,
                y=series,
                name=name,
                mode="lines",
                line={"color": color, "width": 2.2, "dash": dash},
                hovertemplate="%{x|%Y-%m}: %{y:.1f}%<extra></extra>",
            ),
            row=1,
            col=1,
        )

    for column, color, name in (
        ("weekly_real_men", PALETTE["men"], "Men"),
        ("weekly_real_women", PALETTE["women"], "Women"),
    ):
        series = col(quarterly, column)
        fig.add_trace(
            go.Scatter(
                x=series.index,
                y=series,
                name=f"{name} (real)",
                mode="lines",
                line={"color": color, "width": 2.2},
                hovertemplate="%{x|%Y-%m}: $%{y:.0f}<extra></extra>",
            ),
            row=2,
            col=1,
            secondary_y=False,
        )

    ratio = col(quarterly, "earnings_ratio_nominal")
    fig.add_trace(
        go.Scatter(
            x=ratio.index,
            y=ratio,
            name="W/M earnings ratio",
            mode="lines",
            line={"color": PALETTE["accent"], "width": 1.6, "dash": "dot"},
            hovertemplate="%{x|%Y-%m}: %{y:.1f}%<extra></extra>",
        ),
        row=2,
        col=1,
        secondary_y=True,
    )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=PALETTE["bg"],
        plot_bgcolor=PALETTE["bg"],
        font={"color": PALETTE["muted"], "size": 12},
        hovermode="x unified",
        height=950,
        width=1300,
        title={
            "text": (
                "<b>The Great Convergence</b><br>"
                "<sup>U.S. labor force participation & real weekly earnings, "
                "1948–2026 (Oct 2025 not collected)</sup>"
            ),
            "font": {"color": PALETTE["total"], "size": 22},
        },
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.05,
            "xanchor": "right",
            "x": 1,
        },
    )
    fig.update_xaxes(gridcolor=PALETTE["grid"], zerolinecolor=PALETTE["grid"])
    fig.update_yaxes(gridcolor=PALETTE["grid"], zerolinecolor=PALETTE["grid"])
    fig.update_xaxes(rangeslider={"visible": True, "thickness": 0.05}, row=2, col=1)

    path = outdir / "twitter_interactive.html"
    fig.write_html(path, include_plotlyjs=True, full_html=True)
    _finalize_interactive_html(path)
    return path


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Twitter-ready workforce participation visuals"
    )
    parser.add_argument("--static", action="store_true", help="build the hero PNG")
    parser.add_argument(
        "--animated", action="store_true", help="build the animated reveal"
    )
    parser.add_argument(
        "--interactive", action="store_true", help="build the interactive HTML"
    )
    parser.add_argument("--all", action="store_true", help="build everything (default)")
    parser.add_argument(
        "--refresh", action="store_true", help="re-download series from FRED"
    )
    parser.add_argument("--outdir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    build_everything = args.all or not (
        args.static or args.animated or args.interactive
    )

    try:
        data = build(refresh=args.refresh, bls_api_key=os.environ.get("BLS_API_KEY"))
    except (FredFetchError, requests.RequestException) as exc:
        print(f"Execution Error: {exc}")
        raise SystemExit(1) from exc

    stats = compute_stats(data)
    args.outdir.mkdir(parents=True, exist_ok=True)

    built: list[Path] = []
    if build_everything or args.static:
        built.append(build_static(data, stats, args.outdir))
    if build_everything or args.animated:
        built.append(build_animated(data, stats, args.outdir))
    if build_everything or args.interactive:
        built.append(build_interactive(data, stats, args.outdir))

    for path in built:
        print(f"[written] {path}")


if __name__ == "__main__":
    main()
