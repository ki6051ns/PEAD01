"""Rebuild Phase 1 from locally archived J-Quants bulk files."""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from .daily import DAILY_COLUMNS, MASTER_COLUMNS, build_daily, prepare_daily
from .events import FIN_COLUMNS, build_events
from .minute import MINUTE_COLUMNS, build_minute
from .report import summarize


def files(root, dataset, optional=False):
    folder = root / dataset
    if optional and not (folder / "active.json").exists():
        return []
    names = json.loads((folder / "active.json").read_text())
    manifest = json.loads((folder / "manifest.json").read_text())
    paths = [folder / name for name in names]
    for path in paths:
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest[path.name]["sha256"]:
            raise ValueError(f"Snapshot checksum mismatch: {path.name}")
    return paths


def load(root, name, columns, date_column="Date", strings=()):
    parts = []
    for path in files(root, name):
        part = pd.read_csv(path, usecols=lambda c: c in columns, dtype={c: str for c in strings},
                           encoding="utf-8-sig")
        parts.append(part.reindex(columns=columns))
    rows = pd.concat(parts, ignore_index=True).drop_duplicates()
    if date_column:
        rows[date_column] = pd.to_datetime(rows[date_column], format="%Y-%m-%d")
    return rows


def run(raw, output, figures, report, start, end):
    output.mkdir(parents=True, exist_ok=True)
    fin = load(raw, "financials", FIN_COLUMNS, date_column=None, strings=FIN_COLUMNS)
    events = build_events(fin[fin.DiscDate.le(end)])
    events = events.loc[events.announcement_date.between(start, end)].reset_index(drop=True)
    print(f"Financial statement disclosures: {len(events):,}", flush=True)
    daily = load(raw, "daily", DAILY_COLUMNS, strings=["Code"])
    daily = prepare_daily(daily[daily.Date.le(end)])
    master = load(raw, "master", MASTER_COLUMNS, strings=["Code", "Mkt", "ProdCat"])
    master = master.set_index(["Date", "Code"], verify_integrity=True)
    topix = load(raw, "topix", ["Date", "O", "C"])
    topix = topix.loc[topix.Date.le(end)]
    calendar = load(raw, "calendar", ["Date", "HolDiv"], strings=["HolDiv"])
    events, returns = build_daily(events, daily, master, topix, calendar)
    print("Calculated daily returns", flush=True)
    minute_files = files(raw, "minute", optional=True)
    chunks = (
        chunk.loc[chunk.Date.le(end)] for path in minute_files for chunk in pd.read_csv(
            path, usecols=MINUTE_COLUMNS, dtype={"Code": str, "Time": str}, chunksize=500_000
        )
    )
    minute, bad_minutes = build_minute(events, daily, calendar, chunks)
    print(f"Intraday return observations: {len(minute):,}", flush=True)
    for name, table in [("events", events), ("daily_returns", returns), ("minute_returns", minute)]:
        table.to_parquet(output / f"{name}.parquet", index=False)
    summarize(events, returns, minute, bad_minutes, output, figures, report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, default=Path("data/phase1"))
    parser.add_argument("--figures", type=Path, default=Path("figures"))
    parser.add_argument("--report", type=Path, default=Path("reports/phase1_baseline.md"))
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--to", dest="end", required=True)
    args = parser.parse_args()
    run(args.raw, args.output, args.figures, args.report, args.start, args.end)
