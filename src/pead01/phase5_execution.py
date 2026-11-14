"""Minute-bar audit and delayed execution scenarios using the Phase 4 snapshot."""
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from .__main__ import files
from .daily import session_close
from .minute import valid_minutes
from .phase4_paths import ETF

POINTS = (5, 15, 30, 60, 120)
DELAYS = (1, 5, 15)
COSTS = (5, 10, 20, 30)


def audit_point(stock, market, first, horizon, close, initial_ok):
    target = first + horizon
    mark = target if target in (690, close) else target - 1
    if target > close:
        return "session_ended"
    if not valid_minutes(np.array([mark]), close)[0]:
        return "scheduled_break"
    for bar, label in [(stock, "stock"), (market, "etf")]:
        if mark not in bar.index or bar.at[mark, "Vo"] <= 0:
            return label + "_no_print"
        values = bar.loc[mark, ["O", "C", "Vo"]].to_numpy(dtype=float)
        if not (np.isfinite(values) & (values > 0)).all():
            return label + "_invalid"
    return "available" if initial_ok else "baseline_or_initial_missing"


def delayed_trade(stock, first, delay, close):
    signal = first + 5
    entry = signal + delay
    target = first + 60
    mark = target if target in (690, close) else target - 1
    end_continuous = 925 if close == 930 else close
    continuous = 540 <= entry < 690 or 750 <= entry < end_continuous
    if not continuous or target > close or entry >= mark or entry not in stock.index or mark not in stock.index:
        return None
    open_price, volume = stock.loc[entry, ["O", "Vo"]]
    close_price, exit_volume = stock.loc[mark, ["C", "Vo"]]
    if min(open_price, close_price, volume, exit_volume) <= 0 or not np.isfinite(
            [open_price, close_price, volume, exit_volume]).all():
        return None
    return signal, entry, target, open_price, close_price


def replay(events, phase4):
    manifest = json.loads((phase4 / "inputs.json").read_text(encoding="utf-8"))
    sources = []
    for root, item in manifest.items():
        if not isinstance(item, dict) or not (Path(root) / "minute").exists():
            continue
        current = json.loads((Path(root) / "minute/manifest.json").read_text())
        active_files = files(Path(root), "minute")
        if {path.name for path in active_files} != set(item["active"]):
            raise ValueError("Phase 4 minute file list differs")
        for path in active_files:
            if path.name not in item["active"] or current[path.name]["sha256"] != item["manifest"][path.name]["sha256"]:
                raise ValueError("Phase 4 minute snapshot differs")
            sources.append(path)
    if not sources:
        raise ValueError("Phase 4 minute snapshot unavailable")
    keys = pd.MultiIndex.from_frame(events[["first_session", "security_code"]])
    by_day = {d: list(g.itertuples(index=False)) for d, g in events.groupby("first_session")}
    audit, trades = [], []
    for path in sorted(sources, key=lambda p: p.name):
        parts = []
        for chunk in pd.read_csv(path, usecols=["Date", "Code", "Time", "O", "C", "Vo"],
                                 dtype={"Code": str, "Time": str}, chunksize=750_000):
            chunk["Date"] = pd.to_datetime(chunk.Date)
            keep = pd.MultiIndex.from_frame(chunk[["Date", "Code"]]).isin(keys)
            parts.append(chunk.loc[keep | chunk.Code.eq(ETF)])
        bars = pd.concat(parts, ignore_index=True).drop_duplicates()
        bars["minute"] = bars.Time.str[:2].astype(int) * 60 + bars.Time.str[3:5].astype(int)
        for day, day_bars in bars.groupby("Date"):
            if day not in by_day:
                continue
            groups = {code: g.set_index("minute", verify_integrity=True)
                      for code, g in day_bars.groupby("Code")}
            empty = day_bars.iloc[:0].set_index("minute")
            market = groups.get(ETF, empty)
            close = session_close(day)
            for event in by_day[day]:
                stock = groups.get(event.security_code, empty)
                if pd.isna(event.first_minute):
                    release = event.announcement_datetime.hour * 60 + event.announcement_datetime.minute
                    floor = release + 1 if event.announcement_date == day else 540
                    after = stock.loc[(stock.index >= floor) & valid_minutes(stock.index, close)]
                    reason = "invalid_first_print" if after.Vo.gt(0).any() else "no_post_release_print"
                    if floor > close:
                        reason = "session_ended"
                    audit.append((event.event_id, 0, reason))
                    continue
                first = int(event.first_minute)
                initial_ok = np.isfinite(event.initial_excess)
                for point in POINTS:
                    audit.append((event.event_id, point, audit_point(stock, market, first, point, close, initial_ok)))
                if not initial_ok or event.initial_excess == 0:
                    continue
                for delay in DELAYS:
                    trade = delayed_trade(stock, first, delay, close)
                    if trade:
                        signal, entry, exit_time, price, end = trade
                        trades.append((event.event_id, day, delay, signal, entry, exit_time, price, end))
        print(f"{path.name}: {len(trades):,} delayed fills", flush=True)
    return (pd.DataFrame(audit, columns=["event_id", "horizon", "reason"]),
            pd.DataFrame(trades, columns=["event_id", "session", "delay", "signal_minute", "entry_minute",
                                          "exit_minute", "entry", "exit"]))


def portfolio(trades, sessions, cost, participation):
    """Equal ¥1m caps against ¥100m, with capital reserved until the observed exit."""
    rows = []
    groups = {day: g for day, g in trades.groupby("session")}
    for day in sessions:
        gross = net = deployed = 0.
        count = 0
        room = 1e8
        active = []
        if day in groups:
            for t in groups[day].sort_values(["entry_minute", "security_code", "event_id"]).itertuples():
                released = [a for a in active if a[0] < t.entry_minute]
                room += sum(a[1] for a in released)
                active = [a for a in active if a[0] >= t.entry_minute]
                if any(a[2] == t.security_code for a in active):
                    continue
                size = min(1e6, room, t.known_turnover * participation)
                if not np.isfinite(size) or size <= 0:
                    continue
                room -= size
                active.append((t.exit_minute, size, t.security_code))
                deployed += size
                gross += size * t.gross
                net += size * (t.gross - cost / 10000)
                count += 1
        rows.append((day, gross / 1e8, net / 1e8, deployed, count))
    return pd.DataFrame(rows, columns=["date", "gross", "net", "deployed", "fills"])
