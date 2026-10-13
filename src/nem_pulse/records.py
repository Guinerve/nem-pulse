"""Detect records: days that set a new high or low for a metric, compared with all earlier days."""

from __future__ import annotations

import pandas as pd

RECORD_METRICS = {
    "renewable_share": ("max", "Highest renewable share"),
    "solar_share": ("max", "Highest solar share"),
    "wind_share": ("max", "Highest wind share"),
    "intensity_g_per_kwh": ("min", "Lowest emissions intensity"),
    "max_demand_mw": ("max", "Highest daily peak demand"),
    "max_price": ("max", "Highest price"),
    "min_price": ("min", "Lowest price"),
    "negative_intervals": ("max", "Most intervals with a negative price"),
}


def find_records(history: pd.DataFrame, day: str, min_history_days: int = 7) -> list[dict]:
    """Records set on `day` by comparison with every earlier day for the same region.

    Needs at least `min_history_days` of history, otherwise everything would be a "record".
    """
    out = []
    for region, g in history.groupby("region"):
        today = g[g["date"] == day]
        before = g[g["date"] < day]
        if today.empty or before["date"].nunique() < min_history_days:
            continue
        for metric, (kind, label) in RECORD_METRICS.items():
            v = float(today[metric].iloc[0])
            prev = float(before[metric].max() if kind == "max" else before[metric].min())
            beaten = v > prev if kind == "max" else v < prev
            if beaten and not (metric == "negative_intervals" and v == 0):
                out.append({"date": day, "region": region, "metric": metric, "label": label,
                            "value": v, "previous": prev, "kind": kind})
    return out
