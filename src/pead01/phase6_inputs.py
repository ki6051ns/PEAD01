"""Construct chronological order paths from immutable Phase 3–5 snapshots."""
import numpy as np
import pandas as pd

from .phase3 import historical_rank, load_market
from .phase3_portfolio import trade_paths
from .daily import session_close
from .phase5 import market_features
from .__main__ import load


def attributes(data, raw):
    signals = pd.read_parquet(data / "phase3/signals.parquet")
    events = signals.drop_duplicates("event_id").set_index("event_id")
    features = pd.read_parquet(data / "phase4/financial_features.parquet").set_index("event_id")
    extra = pd.read_parquet(data / "phase5/events.parquet").set_index("event_id")
    events = events.join(features[["OP_revision_amount", "EPS_revision_amount", "OP_company_surprise",
                                   "EPS_company_surprise", "OP_series_surprise", "op_progress_change"]])
    events = events.join(extra[["adv20", "volume_burst_5", "initial_excess"]].rename(
        columns={"initial_excess": "phase5_initial"}))
    events["first5_prints"] = np.nan
    # A one-day lag makes this an observable density proxy; same-day totals are unavailable.
    by_day = events.groupby("announcement_date").size()
    events["known_busy"] = events.attributes_date.map(by_day).fillna(0).ge(100)
    intraday = pd.read_parquet(data / "phase4/minute_paths.parquet",
                              columns=["event_id", "point", "timestamp", "excess"])
    intraday = intraday.loc[intraday.point.isin(["wall_5", "wall_15", "wall_30", "wall_60"])].copy()
    intraday["method"] = "I" + intraday.point.str[5:]
    intraday["signal_date"] = intraday.timestamp.dt.normalize()
    intraday["historical_rank"] = historical_rank(intraday.rename(columns={"excess": "initial_excess"}))
    cols = ["event_id", "method", "historical_rank"]
    early = intraday.loc[intraday.method.eq("I5"), cols]
    ranks = pd.concat([signals[cols], intraday[cols],
        *(early.assign(method=f"P5_{delay}") for delay in (1, 5, 15))]).set_index(["event_id", "method"]).historical_rank
    topix = load(raw, "topix", ["Date", "C"]).set_index("Date")
    market = market_features(topix, pd.Series(index=topix.index, dtype=float))
    events = events.join(market[["market_20", "vol_20", "vol_threshold"]], on="attributes_date")
    events["sector_group"] = np.where(events.sector.isin(["銀行業", "保険業", "証券、商品先物取引業",
                                      "その他金融業"]), "financial", "other")
    events["past_size"] = np.nan
    # Compare with the empirical distribution on strictly earlier disclosure dates.
    from bisect import bisect_right, insort
    history = []
    for _, group in events.sort_values("announcement_date").groupby("announcement_date"):
        values = group.market_cap.dropna()
        if len(history) >= 250:
            events.loc[values.index, "past_size"] = [bisect_right(history, v)/len(history) for v in values]
        for v in values:
            insort(history, v)
    events.attrs["ranks"] = ranks
    return signals, events, topix


def exact_minute_paths(data, days, config, progress=None):
    """Use archived trade bars for each signal and subsequent fixed exit."""
    import json
    from .__main__ import files
    from .minute import valid_minutes

    paths = pd.read_parquet(data / "phase4/minute_paths.parquet")
    signals = paths.loc[paths.point.isin(["wall_5", "wall_15", "wall_30", "wall_60"])
                        & paths.excess.notna() & paths.excess.ne(0)].copy()
    ev = pd.read_parquet(data / "phase5/events.parquet", columns=["event_id", "security_code", "prior_turnover",
                          "adv20", "first_minute"])
    signals = signals.merge(ev, on="event_id")
    signals["date"] = signals.timestamp.dt.normalize()
    keys = pd.MultiIndex.from_frame(signals[["date", "security_code"]])
    by_day = {d: list(g.itertuples(index=False)) for d,g in signals.groupby("date")}
    manifest = json.loads((data/"phase4/inputs.json").read_text(encoding="utf-8"))
    sources = []
    for label, item in manifest.items():
        root = data.parent / label
        if isinstance(item, dict) and (root/"minute/active.json").exists():
            loaded = files(root,"minute")
            current = json.loads((root/"minute/manifest.json").read_text())
            if {p.name for p in loaded} != set(item["active"]) or any(
                current[p.name]["sha256"] != item["manifest"][p.name]["sha256"] for p in loaded
            ):
                raise ValueError("Minute archive differs from Phase 4 snapshot")
            sources.extend(loaded)
    out = []
    first_five = {}
    for source in sorted(sources, key=lambda p:p.name):
        kept = []
        for chunk in pd.read_csv(source, usecols=["Date","Code","Time","O","C","Vo"],
                                 dtype={"Code":str,"Time":str}, chunksize=750_000):
            chunk["Date"] = pd.to_datetime(chunk.Date)
            matches = pd.MultiIndex.from_frame(chunk[["Date","Code"]]).isin(keys)
            kept.append(chunk.loc[matches & chunk.Vo.gt(0) & chunk.O.gt(0) & chunk.C.gt(0)])
        bars = pd.concat(kept, ignore_index=True).drop_duplicates()
        bars["minute"] = bars.Time.str[:2].astype(int)*60+bars.Time.str[3:5].astype(int)
        for day, part in bars.groupby("Date"):
            if day not in by_day:
                continue
            close = session_close(day)
            books = {c:g.set_index("minute",verify_integrity=True) for c,g in part.groupby("Code")}
            for row in by_day[day]:
                stock = books.get(row.security_code)
                if stock is None:
                    continue
                horizon = int(row.point[5:])
                signal = row.timestamp.hour*60+row.timestamp.minute
                first = int(row.first_minute)
                if horizon == 5:
                    first_five[row.event_id] = int(stock.index.isin(range(first,first+5)).sum())
                enter = signal+1
                if not (540<=enter<690 or 750<=enter<(925 if close==930 else close)) or enter not in stock.index:
                    continue
                price = stock.at[enter,"O"]
                for h in [*config["minute_holds"],"close"]:
                    end = close if h=="close" else enter+h
                    mark = end if end in (690,close) else end-1
                    if end>close or mark not in stock.index or not valid_minutes(np.array([mark]),close)[0]:
                        continue
                    out.append((row.event_id,f"I{horizon}",str(h),day,enter,end,signal,row.excess,
                                stock.at[mark,"C"]/price, row.adv20 if row.adv20>0 else row.prior_turnover))
        print(f"Minute replay {source.name}: {len(out):,} paths", flush=True)
        if progress:
            progress(0, source.name)
    t = pd.DataFrame(out,columns=["event_id","method","hold","date","minute","exit_minute","signal_minute",
                                  "gap","mark","adv"])
    t["capacity"] = t.adv*config["participation"]/config["capital"]
    t["start"] = days.get_indexer(t.date)
    t = t.loc[t.capacity.gt(0) & t.start.ge(0)].copy()
    t["end"],t["marks"],t["cost"],t["frequency"],t["closed"] = t.start,t.mark.map(lambda x:[x]),10,"minute",True
    t["signal_time"] = t.date+pd.to_timedelta(t.signal_minute,unit="m")
    t["available_at"] = t.date+pd.to_timedelta(t.minute,unit="m")
    t["exit_time"] = t.date+pd.to_timedelta(t.exit_minute,unit="m")
    return t, pd.Series(first_five, dtype=float)


def daily_paths(signals, raw, config, output, progress=None):
    prices, days, half, _ = load_market(raw, signals)
    eligible = signals.loc[signals.method.isin(["A", "C", "B1445", "M5", "M15", "M30", "M60"]) &
                           signals.entry.gt(0) & signals.initial_excess.notna() &
                           signals.initial_excess.ne(0) & ~signals.limit_day].copy()
    eligible = eligible.loc[eligible.prior_turnover.gt(0)]
    codes = set(eligible.security_code)
    quotes = {code: tuple(g.droplevel("Code").reindex(days).to_numpy(dtype=float).T)
              for code, g in prices[["close", "factor_errors", "limit_flag"]].groupby(level="Code", sort=False)
              if code in codes}
    opening_path = output / "opening.parquet"
    if not opening_path.exists():
        wanted = prices.index.get_level_values("Code").isin(codes)
        prices.loc[wanted, ["open", "factor_errors", "limit_flag"]].reset_index().to_parquet(opening_path, index=False)
    for hold in config["daily_holds"]:
        target = output / f"daily_{hold}.parquet"
        if target.exists():
            continue
        sub = eligible if hold in (1, 3, 5, 10, 20) else eligible.loc[eligible.method.isin(["A", "C"])]
        t = trade_paths(sub, quotes, days, half, hold)
        t["minute"] = t.fill_time.dt.hour*60 + t.fill_time.dt.minute
        t["exit_minute"] = [session_close(days[i], days[i] in half) if closed else 1440
                            for i, closed in zip(t.end, t.closed)]
        t["frequency"] = "daily"
        t["cost"] = np.where(t.method.isin(["A", "C"]), 20, 10)
        t["capacity"] = t.adv * config["participation"] / config["capital"]
        t["available_at"] = t.fill_time
        t = t.merge(eligible[["event_id", "method", "entry", "factor_errors"]],
                    on=["event_id", "method"], validate="many_to_one")
        t["signal_time"] = pd.MultiIndex.from_frame(t[["event_id", "method"]]).map(
            signals.set_index(["event_id", "method"]).signal_time)
        t["exit_time"] = t.end_time
        columns = ["event_id", "start", "end", "minute", "exit_minute", "marks", "gap", "frequency",
                   "cost", "capacity", "available_at", "signal_time", "exit_time", "method", "hold", "closed",
                   "entry", "factor_errors"]
        pending = target.with_suffix(".tmp")
        t[columns].to_parquet(pending, index=False)
        pending.replace(target)
        print(f"Daily paths {hold}: {len(t):,}", flush=True)
        if progress:
            progress(0, target.name)
    return days


def minute_paths(data, events, days, config):
    events = events.reset_index()
    out = []
    # Phase 5 replay supplies a closer-to-signal exact entry at +1/+5/+15 minutes.
    fills = pd.read_parquet(data / "phase5/fills.parquet")
    fills = fills.merge(events[["event_id", "phase5_initial"]], on="event_id", validate="many_to_one")
    for col, minute_col in [("available_at", "entry_minute"), ("signal_time", "signal_minute"), ("exit_time", "exit_minute")]:
        fills[col] = fills.session + pd.to_timedelta(fills[minute_col], unit="m")
    out.append(fills.rename(columns={"phase5_initial": "gap"}).assign(
        method="P5_" + fills.delay.astype(str), hold="to60"))
    t = pd.concat(out, ignore_index=True)
    t = t.merge(events[["event_id", "prior_turnover", "adv20"]], on="event_id", validate="many_to_one")
    t["capacity"] = t.adv20.fillna(t.prior_turnover) * config["participation"] / config["capital"]
    t = t.loc[t.capacity.gt(0) & t.gap.ne(0) & t.gap.notna()]
    t["start"] = days.get_indexer(t.available_at.dt.normalize())
    t["end"] = t.start
    t["minute"] = t.available_at.dt.hour*60 + t.available_at.dt.minute
    t["exit_minute"] = t.exit_time.dt.hour*60 + t.exit_time.dt.minute
    t["marks"] = [[r] for r in t.exit / t.entry]
    t["frequency"], t["cost"], t["closed"] = "minute", 10, True
    return t.loc[t.start.ge(0)]
