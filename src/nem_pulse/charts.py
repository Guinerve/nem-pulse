from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

COLORS = {"NSW1": "#1f6feb", "QLD1": "#d9692b", "VIC1": "#8250df", "SA1": "#1a7f4b", "TAS1": "#cf222e"}


def render(history: pd.DataFrame, out: Path, days: int = 60) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    h = history[history["region"] != "NEM"].copy()
    h["date"] = pd.to_datetime(h["date"])
    h = h[h["date"] >= h["date"].max() - pd.Timedelta(days=days - 1)]
    paths = []
    for metric, title, fname, scale, unit in [
        ("renewable_share", "Renewable share of generation", "renewables.png", 100, "%"),
        ("avg_price", "Average daily price", "price.png", 1, "$/MWh"),
        ("intensity_g_per_kwh", "Emissions intensity", "intensity.png", 1, "g CO₂e/kWh"),
    ]:
        fig, ax = plt.subplots(figsize=(9, 3.2))
        for region, g in h.groupby("region"):
            ax.plot(g["date"], g[metric] * scale, label=region, color=COLORS.get(region), lw=1.6)
        ax.set_title(title); ax.set_ylabel(unit); ax.grid(alpha=.25); ax.legend(ncol=5, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.12), frameon=False)
        fig.tight_layout(); p = out / fname; fig.savefig(p, dpi=130); plt.close(fig); paths.append(p)
    return paths
