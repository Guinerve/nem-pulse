"""Build one day's summary rows (one per region plus NEM) from 5-minute archive data."""

from __future__ import annotations

from datetime import date

import pandas as pd
from nem.client import REGIONS
from nem.fuels import RENEWABLE_GROUPS

COLUMNS = [
    "date", "region", "intervals", "avg_price", "min_price", "max_price", "negative_intervals",
    "avg_demand_mw", "max_demand_mw", "generation_mwh", "renewable_share", "wind_share", "solar_share",
    "coal_share", "gas_share", "hydro_share", "battery_share", "intensity_g_per_kwh",
]
EXPECTED_INTERVALS = 288


class SourceDataError(ValueError):
    """Raised when source data is missing or malformed, so a scheduled run fails loudly."""


def _validate(prices: pd.DataFrame, scada: pd.DataFrame, day: date) -> None:
    if prices.empty or scada.empty:
        raise SourceDataError(f"{day}: empty source data (prices={len(prices)}, scada={len(scada)})")
    for region in REGIONS:
        n = int((prices["region"] == region).sum())
        if n < EXPECTED_INTERVALS - 3:
            raise SourceDataError(f"{day}: only {n} of {EXPECTED_INTERVALS} price intervals for {region}")
    if prices["rrp"].isna().any() or prices["demand"].isna().any():
        raise SourceDataError(f"{day}: missing prices or demand")
    n_scada = scada["interval_end"].nunique()
    if n_scada < EXPECTED_INTERVALS - 3:
        raise SourceDataError(f"{day}: only {n_scada} of {EXPECTED_INTERVALS} SCADA intervals")


def _share(units: pd.DataFrame, gen: float, fuels) -> float:
    """Share of `gen` MWh produced by units whose fuel is in `fuels` (0 when nothing generated)."""
    return float(units.loc[units["fuel"].isin(fuels), "mwh"].sum() / gen) if gen else 0.0


def summarise_day(day: date, prices: pd.DataFrame, scada: pd.DataFrame, generators: pd.DataFrame) -> pd.DataFrame:
    _validate(prices, scada, day)
    units = scada.merge(generators[["duid", "region", "ef_t_per_mwh", "fuel"]], on="duid", how="inner")
    units = units[units["mw"] > 0].copy()
    units["mwh"] = units["mw"] / 12
    units["t_co2e"] = units["mwh"] * units["ef_t_per_mwh"]

    rows = []
    for region in [*REGIONS, "NEM"]:
        p = prices if region == "NEM" else prices[prices["region"] == region]
        u = units if region == "NEM" else units[units["region"] == region]
        if region == "NEM":
            # demand-weighted NEM price; demand summed across regions per interval
            by_t = p.groupby("interval_end").apply(
                lambda g: pd.Series({"rrp": (g["rrp"] * g["demand"]).sum() / g["demand"].sum(), "demand": g["demand"].sum()}),
                include_groups=False,
            )
            price, demand = by_t["rrp"], by_t["demand"]
        else:
            price, demand = p["rrp"], p["demand"]
        gen = u["mwh"].sum()
        rows.append({
            "date": day.isoformat(), "region": region, "intervals": len(price),
            "avg_price": round(float(price.mean()), 2), "min_price": round(float(price.min()), 2),
            "max_price": round(float(price.max()), 2), "negative_intervals": int((price < 0).sum()),
            "avg_demand_mw": round(float(demand.mean()), 1), "max_demand_mw": round(float(demand.max()), 1),
            "generation_mwh": round(float(gen), 0), "renewable_share": round(_share(u, gen, RENEWABLE_GROUPS), 4),
            "wind_share": round(_share(u, gen, {"Wind"}), 4), "solar_share": round(_share(u, gen, {"Solar"}), 4),
            "coal_share": round(_share(u, gen, {"Black coal", "Brown coal"}), 4), "gas_share": round(_share(u, gen, {"Gas"}), 4),
            "hydro_share": round(_share(u, gen, {"Hydro"}), 4), "battery_share": round(_share(u, gen, {"Battery"}), 4),
            "intensity_g_per_kwh": round(float(u["t_co2e"].sum() / gen * 1000), 1) if gen else 0.0,
        })
    return pd.DataFrame(rows, columns=COLUMNS)
