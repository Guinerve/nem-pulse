"""CSV storage: data/YYYY/MM/DD.csv per day, plus data/latest.csv (rolling window) and records.csv."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

LATEST_DAYS = 30


def day_path(root: Path, day: date) -> Path:
    return root / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}.csv"


def write_day(root: Path, day: date, df: pd.DataFrame) -> bool:
    """Write a day's CSV. Returns True only if the file changed (so the workflow commits only then)."""
    path = day_path(root, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = df.to_csv(index=False)
    if path.exists() and path.read_text() == text:
        return False
    path.write_text(text)
    return True


def read_all(root: Path) -> pd.DataFrame:
    files = sorted(root.glob("[0-9][0-9][0-9][0-9]/[0-9][0-9]/[0-9][0-9].csv"))
    if not files:
        return pd.DataFrame()
    return pd.concat((pd.read_csv(f) for f in files), ignore_index=True)


def write_latest(root: Path, history: pd.DataFrame) -> None:
    if history.empty:
        raise ValueError("no history to summarise")
    days = sorted(history["date"].unique())[-LATEST_DAYS:]
    history[history["date"].isin(days)].to_csv(root / "latest.csv", index=False)
