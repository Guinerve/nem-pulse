"""nem-pulse update [--date YYYY-MM-DD] [--days N]: pull, summarise, store, detect records, redraw charts."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

import httpx

from nem import NemClient, NemDataError
from nem.archive import load_prices_day, load_scada_day

from . import charts, records, store, summary

NEM_TZ = timezone(timedelta(hours=10))


def yesterday_nem() -> date:
    return datetime.now(NEM_TZ).date() - timedelta(days=1)


def update_day(day: date, root: Path, generators: pd.DataFrame) -> bool:
    df = summary.summarise_day(day, load_prices_day(day), load_scada_day(day), generators)
    return store.write_day(root, day, df)


def render_readme(root: Path, history: pd.DataFrame) -> None:
    latest = history["date"].max()
    recs = pd.read_csv(root / "records.csv") if (root / "records.csv").exists() else pd.DataFrame()
    today = history[history["date"] == latest].set_index("region")
    lines = [f"_Updated for {latest} (NEM time)._", "", "| Region | Avg price | Renewables | Intensity | Neg. price intervals |", "|---|---:|---:|---:|---:|"]
    for r in ["NSW1", "QLD1", "VIC1", "SA1", "TAS1", "NEM"]:
        if r in today.index:
            t = today.loc[r]
            lines.append(f"| {r} | ${t['avg_price']:.0f}/MWh | {t['renewable_share']:.0%} | {t['intensity_g_per_kwh']:.0f} g/kWh | {int(t['negative_intervals'])} |")
    lines += ["", "### Recent records", ""]
    if recs.empty:
        lines.append("None yet.")
    else:
        for r in recs.sort_values("date", ascending=False).head(10).itertuples():
            fmt = f"{r.value:.1%}" if r.metric.endswith("_share") else f"{r.value:,.1f}"
            lines.append(f"- **{r.date}** {r.region}: {r.label.lower()} ({fmt}, previous best {r.previous:.4g})")
    block = "\n".join(lines)
    readme = Path("README.md")
    text = readme.read_text()
    start, end = "<!-- PULSE:START -->", "<!-- PULSE:END -->"
    if start not in text or end not in text:
        raise summary.SourceDataError("README.md is missing the PULSE markers; refusing to continue silently")
    if True:
        text = text[: text.index(start) + len(start)] + "\n" + block + "\n" + text[text.index(end):]
        readme.write_text(text)


def main(argv: list[str] | None = None) -> int:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    p = argparse.ArgumentParser(prog="nem-pulse")
    p.add_argument("--date", type=date.fromisoformat, default=None, help="Last day to fetch (default: yesterday, NEM time)")
    p.add_argument("--days", type=int, default=1, help="How many days to (re)fetch, ending at --date")
    p.add_argument("--data", type=Path, default=Path("data"))
    args = p.parse_args(argv)

    end = args.date or yesterday_nem()
    changed = False
    try:
        generators = NemClient().generators()
        for i in range(args.days - 1, -1, -1):
            day = end - timedelta(days=i)
            did = update_day(day, args.data, generators)
            print(f"{day}: {'written' if did else 'unchanged'}")
            changed |= did
    except (summary.SourceDataError, NemDataError, httpx.HTTPError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2  # fail loudly so the scheduled workflow goes red instead of committing partial data

    history = store.read_all(args.data)
    store.write_latest(args.data, history)
    new_records = []
    for i in range(args.days - 1, -1, -1):
        new_records += records.find_records(history, (end - timedelta(days=i)).isoformat())
    if new_records:
        path = args.data / "records.csv"
        old = pd.read_csv(path) if path.exists() else pd.DataFrame()
        allr = pd.concat([old, pd.DataFrame(new_records)]).drop_duplicates(["date", "region", "metric"], keep="last")
        allr.to_csv(path, index=False)
    charts.render(history, Path("assets"))
    render_readme(args.data, history)
    print("changed" if changed else "no changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
