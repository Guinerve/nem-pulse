"""Reconcile our daily figures with AEMO's published 'Aggregated price and demand' CSVs.

  uv run python scripts/reconcile.py 202610
"""
import io
import sys
from pathlib import Path

import httpx
import pandas as pd

from nem_pulse import store

month = sys.argv[1] if len(sys.argv) > 1 else "202610"
ours = store.read_all(Path("data"))
ours = ours[ours["region"] != "NEM"]
rows = []
for region in ["NSW1", "QLD1", "SA1", "TAS1", "VIC1"]:
    url = f"https://www.aemo.com.au/aemo/data/nem/priceanddemand/PRICE_AND_DEMAND_{month}_{region}.csv"
    r = httpx.get(url, follow_redirects=True, timeout=60)
    r.raise_for_status()
    a = pd.read_csv(io.StringIO(r.text))
    a["ts"] = pd.to_datetime(a["SETTLEMENTDATE"])
    a["date"] = (a["ts"] - pd.Timedelta(minutes=5)).dt.strftime("%Y-%m-%d")  # market day: interval 00:05..24:00
    g = a.groupby("date").agg(aemo_price=("RRP", "mean"), aemo_demand=("TOTALDEMAND", "mean"),
                              aemo_max_price=("RRP", "max"), aemo_n=("RRP", "size")).reset_index()
    g["region"] = region
    rows.append(g)
aemo = pd.concat(rows)
m = ours.merge(aemo, on=["date", "region"])
m["price_diff"] = m["avg_price"] - m["aemo_price"]
m["demand_diff"] = m["avg_demand_mw"] - m["aemo_demand"]
print(f"{len(m)} region-days compared ({m['date'].min()} to {m['date'].max()})")
print(f"avg price     max |diff| = {m['price_diff'].abs().max():.4f} $/MWh   (mean |diff| {m['price_diff'].abs().mean():.4f})")
print(f"avg demand    max |diff| = {m['demand_diff'].abs().max():.3f} MW   (mean |diff| {m['demand_diff'].abs().mean():.4f})")
print(f"max price     max |diff| = {(m['max_price'] - m['aemo_max_price']).abs().max():.4f} $/MWh")
print("intervals per day (ours/aemo) all 288:", bool((m['intervals'] == 288).all() and (m['aemo_n'] == 288).all()))
