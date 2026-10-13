"""Daily line charts per region (assets/*.png), redrawn on every run."""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

# Fixed colour per region (identity never depends on rank). Checked for colour vision deficiency:
# the closest pair is in the warning band, so every line also carries a direct label at its end.
COLORS = {"NSW1": "#1f6feb", "QLD1": "#d9692b", "SA1": "#1a7f4b", "TAS1": "#cf222e", "VIC1": "#8250df"}
INK, MUTED, GRID = "#1f2328", "#59636e", "#d8dee4"
SOURCE = "Source: AEMO NEMWeb daily archive, summarised by nem-pulse."

CHARTS = [
    # metric, title, file name, scale, unit, footnote
    ("renewable_share", "Renewable share of generation", "renewables.png", 100, "%",
     "Excludes rooftop solar, so daytime renewables in NSW, QLD and SA read low."),
    ("avg_price", "Average daily spot price", "price.png", 1, "$/MWh", "Mean of the 288 five minute prices in each day."),
    ("intensity_g_per_kwh", "Emissions intensity of generation", "intensity.png", 1, "g CO₂e/kWh",
     "Scheduled and semi-scheduled units only."),
]


def _spread(ys: list[float], gap: float) -> list[float]:
    """Push label positions apart (in data units) so no two are closer than `gap`, keeping their order."""
    order = sorted(range(len(ys)), key=lambda i: ys[i])
    out = list(ys)
    for a, b in pairwise(order):
        if out[b] - out[a] < gap:
            out[b] = out[a] + gap
    return out


def render(history: pd.DataFrame, out: Path, days: int = 60) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    h = history[history["region"] != "NEM"].copy()
    h["date"] = pd.to_datetime(h["date"])
    h = h[h["date"] >= h["date"].max() - pd.Timedelta(days=days - 1)]
    first, last = h["date"].min(), h["date"].max()
    span = f"{first:%-d %b} to {last:%-d %b %Y}" if first != last else f"{last:%-d %b %Y}"
    n_days = h["date"].nunique()
    paths = []
    for metric, title, fname, scale, unit, note in CHARTS:
        fig, ax = plt.subplots(figsize=(9, 3.6), facecolor="white")
        ends = []
        for region, g in h.groupby("region"):
            g = g.sort_values("date")
            ax.plot(g["date"], g[metric] * scale, color=COLORS.get(region), lw=2,
                    marker="o" if n_days <= 20 else None, ms=4, label=region)
            ends.append((region, float(g[metric].iloc[-1] * scale)))

        lo, hi = ax.get_ylim()
        label_y = _spread([y for _, y in ends], gap=(hi - lo) * 0.075)
        for (region, _), y in zip(ends, label_y, strict=True):
            ax.annotate(region, xy=(1, y), xycoords=("axes fraction", "data"), xytext=(6, 0),
                        textcoords="offset points", va="center", fontsize=8.5, color=INK)
            ax.plot([1.0, 1.008], [y, y], transform=ax.get_yaxis_transform(), color=COLORS.get(region),
                    lw=2, clip_on=False)

        if metric == "avg_price" and lo < 0 < hi:
            ax.axhline(0, color=MUTED, lw=0.8)
        ax.set_title(title, loc="left", fontsize=12, fontweight="bold", color=INK, pad=22)
        ax.text(0, 1.03, f"{unit}, daily, {span}", transform=ax.transAxes, fontsize=9, color=MUTED)
        fig.text(0.01, 0.015, f"{note} {SOURCE}", fontsize=7.5, color=MUTED)

        locator = mdates.AutoDateLocator(minticks=4, maxticks=8)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%-d %b"))
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(MUTED)
        ax.tick_params(colors=MUTED, labelsize=8.5, length=0)
        ax.legend(ncol=5, fontsize=8.5, loc="upper center", bbox_to_anchor=(0.5, -0.1), frameon=False,
                  labelcolor=INK, handlelength=1.5)
        fig.subplots_adjust(left=0.06, right=0.92, top=0.82, bottom=0.25)
        p = out / fname
        fig.savefig(p, dpi=130, metadata={"Software": None})
        plt.close(fig)
        paths.append(p)
    return paths
