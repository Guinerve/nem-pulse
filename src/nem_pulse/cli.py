"""nem-pulse [--date YYYY-MM-DD] [--days N]: pull, summarise, store, detect records, redraw charts."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pandas as pd
from nem import NemClient, NemDataError
from nem.archive import load_prices_day, load_scada_day

from . import charts, records, store, summary

NEM_TZ = timezone(timedelta(hours=10))
README_START, README_END = "<!-- PULSE:START -->", "<!-- PULSE:END -->"


def latest_archived_day(now: datetime | None = None) -> date:
    """NEMWeb's daily archive trails real time by about two days (observed: on the evening of 12 Oct the
    newest file was 10 Oct), so the newest day we can fetch is NEM-today minus two."""
    return (now or datetime.now(NEM_TZ)).astimezone(NEM_TZ).date() - timedelta(days=2)


def update_day(day: date, root: Path, generators: pd.DataFrame) -> bool:
    df = summary.summarise_day(day, load_prices_day(day), load_scada_day(day), generators)
    return store.write_day(root, day, df)


def _money(value: float) -> str:
    return f"{'-' if value < 0 else ''}${abs(value):,.0f}/MWh"


def _record_value(metric: str, value: float) -> str:
    return f"{value:.1%}" if metric.endswith("_share") else f"{value:,.1f}"


def render_readme(root: Path, history: pd.DataFrame, readme: Path = Path("README.md")) -> None:
    """Rewrite the block between the PULSE markers in `readme` with the latest day and recent records."""
    text = readme.read_text()
    if README_START not in text or README_END not in text:
        raise summary.SourceDataError(f"{readme} is missing the PULSE markers; refusing to continue silently")

    latest = history["date"].max()
    recs = pd.read_csv(root / "records.csv") if (root / "records.csv").exists() else pd.DataFrame()
    today = history[history["date"] == latest].set_index("region")
    lines = [f"_Updated for {latest} (NEM time)._", "",
             "| Region | Avg price | Renewables | Intensity | Negative price intervals |",
             "|---|---:|---:|---:|---:|"]
    for r in ["NSW1", "QLD1", "VIC1", "SA1", "TAS1", "NEM"]:
        if r in today.index:
            t = today.loc[r]
            lines.append(f"| {r} | {_money(t['avg_price'])} | {t['renewable_share']:.0%} | "
                         f"{t['intensity_g_per_kwh']:.0f} g/kWh | {int(t['negative_intervals'])} |")
    lines += ["", "### Recent records", ""]
    if recs.empty:
        lines.append("None yet.")
    else:
        recent = recs.sort_values(["date", "region", "metric"], ascending=[False, True, True], kind="stable")
        for r in recent.head(10).itertuples():
            lines.append(f"- **{r.date}** {r.region}: {r.label.lower()} ({_record_value(r.metric, r.value)}, "
                         f"previous best {_record_value(r.metric, r.previous)})")
    block = "\n".join(lines)
    head, tail = text[: text.index(README_START) + len(README_START)], text[text.index(README_END):]
    readme.write_text(head + "\n" + block + "\n" + tail)


def _positive_int(value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a whole number: {value!r}") from None
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be 1 or more, got {n}")
    return n


def main(argv: list[str] | None = None) -> int:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    p = argparse.ArgumentParser(
        prog="nem-pulse",
        description="Fetch daily NEM data from the AEMO archive, write one CSV per day, "
                    "find records, redraw the charts and update the README.",
    )
    p.add_argument("--date", type=date.fromisoformat, default=None,
                   help="Last day to fetch, as YYYY-MM-DD. Default: NEM today minus 2, because the archive lags.")
    p.add_argument("--days", type=_positive_int, default=1,
                   help="Number of days to fetch, ending at --date. Default: 1.")
    p.add_argument("--data", type=Path, default=Path("data"), help="Data folder. Default: data")
    p.add_argument("--assets", type=Path, default=Path("assets"), help="Chart folder. Default: assets")
    p.add_argument("--readme", type=Path, default=Path("README.md"),
                   help="README with PULSE markers to update. Default: README.md")
    args = p.parse_args(argv)

    end = args.date or latest_archived_day()
    days = [end - timedelta(days=i) for i in range(args.days - 1, -1, -1)]
    changed = False
    try:
        generators = NemClient().generators()
        for day in days:
            did = update_day(day, args.data, generators)
            print(f"{day}: {'written' if did else 'unchanged'}")
            changed |= did

        history = store.read_all(args.data)
        store.write_latest(args.data, history)
        new_records = [rec for day in days for rec in records.find_records(history, day.isoformat())]
        if new_records:
            path = args.data / "records.csv"
            old = pd.read_csv(path) if path.exists() else pd.DataFrame()
            allr = pd.concat([old, pd.DataFrame(new_records)])
            allr.drop_duplicates(["date", "region", "metric"], keep="last").to_csv(path, index=False)
        charts.render(history, args.assets)
        render_readme(args.data, history, args.readme)
    except (summary.SourceDataError, NemDataError, httpx.HTTPError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2  # fail loudly so the scheduled workflow goes red instead of committing partial data
    print("changed" if changed else "no changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
