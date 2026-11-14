"""Point-in-time signal and fill candidates for the earnings strategy."""
import numpy as np
import pandas as pd

from .__main__ import files
from .daily import lookup, session_close
from .minute import valid_minutes

SCALE = {"TOPIX Core30", "TOPIX Large70", "TOPIX Mid400", "TOPIX Small 1", "TOPIX Small 2"}
ETF = "13060"


def membership(scale):
    return pd.Series(np.select([scale.isin(SCALE), scale.eq("-").fillna(False)],
                               ["topix", "non_topix"], default=None), index=scale.index)


def clock(days, minutes):
    return days + pd.to_timedelta(minutes, unit="m")


def excess(start, end, index_start, index_end):
    return end / start - index_end / index_start


def daily_signals(events, prices, index, sessions, half):
    base = lookup(prices, events.baseline_date, events.security_code)
    blocks = []
    for method in ("A", "C"):
        signal_day = events.first_session if method == "A" else events.next_open_date
        signal_pos = sessions.get_indexer(signal_day)
        loc = signal_pos + 1
        fill_day = pd.Series(sessions.take(loc.clip(0, len(sessions) - 1)), index=events.index)
        fill_day = fill_day.where((signal_pos >= 0) & (loc < len(sessions)))
        signal = lookup(prices, signal_day, events.security_code)
        entry = lookup(prices, fill_day, events.security_code)
        idx_base = index.C.reindex(events.baseline_date).to_numpy()
        idx_signal = index["C" if method == "A" else "O"].reindex(signal_day).to_numpy()
        timing = signal_day.map(lambda d: session_close(d, d in half) if pd.notna(d) else np.nan)
        if method == "C":
            timing = 540
        signal_time = clock(signal_day, timing) + pd.Timedelta(minutes=1)
        response = excess(base.close, signal["close" if method == "A" else "open"], idx_base, idx_signal)
        response = response.where(base.factor_errors.eq(signal.factor_errors))
        blocks.append(pd.DataFrame({
            "event_id": events.event_id, "method": method, "signal_date": signal_day,
            "signal_time": signal_time, "observation_start": clock(events.first_session, 540),
            "order_time": clock(fill_day, 539), "fill_time": clock(fill_day, 540),
            "entry_date": fill_day, "entry": entry.open, "factor_errors": entry.factor_errors,
            "initial_excess": response, "limit_day": entry.limit_flag.eq(True),
            "benchmark": "TOPIX", "bar_turnover": np.nan,
        }))
    return pd.concat(blocks, ignore_index=True)


def intraday_signals(events, prices, minute_input, raw):
    first = minute_input.loc[minute_input.horizon.eq("first_trade"), ["event_id", "session", "entry_minute"]]
    covered = events.merge(first, on="event_id", validate="one_to_one")
    keys = pd.MultiIndex.from_frame(covered[["session", "security_code"]])
    chunks = []
    for path in files(raw, "minute"):
        for chunk in pd.read_csv(path, usecols=["Date", "Code", "Time", "O", "C", "Vo", "Va"],
                                 dtype={"Code": str, "Time": str}, chunksize=500_000):
            chunk["Date"] = pd.to_datetime(chunk.Date)
            keep = pd.MultiIndex.from_frame(chunk[["Date", "Code"]]).isin(keys) | chunk.Code.eq(ETF)
            chunks.append(chunk.loc[keep & chunk.Vo.gt(0)].copy())
    if not chunks:
        return pd.DataFrame()
    bars = pd.concat(chunks, ignore_index=True).drop_duplicates()
    bars["minute"] = bars.Time.str[:2].astype(int) * 60 + bars.Time.str[3:5].astype(int)
    close = np.where(bars.Date.ge("2024-11-05"), 930, 900)
    bars = bars.loc[valid_minutes(bars.minute, close) & bars.O.gt(0) & bars.C.gt(0)]
    groups = {key: g.set_index("minute", verify_integrity=True).sort_index()
              for key, g in bars.groupby(["Date", "Code"], sort=False)}
    rows = []
    for e in covered.itertuples(index=False):
        stock = groups.get((e.session, e.security_code))
        etf = groups.get((e.session, ETF))
        if stock is None or etf is None:
            continue
        today_key = (e.session, e.security_code)
        if today_key not in prices.index or (e.session, ETF) not in prices.index:
            continue
        today = prices.loc[today_key]
        etf_today = prices.loc[(e.session, ETF)]
        # For a release within the session both series use the same completed baseline minute.
        disc_min = e.announcement_datetime.hour * 60 + e.announcement_datetime.minute
        within = e.session == e.announcement_date and disc_min >= 540
        if within:
            candidates = stock.index.intersection(etf.index)
            prior = candidates[(candidates < disc_min) & ((candidates >= disc_min - 5) |
                               ((690 < disc_min <= 750) & (candidates == 690)))]
            if len(prior) == 0:
                continue
            base, etf_base = stock.at[prior[-1], "C"], etf.at[prior[-1], "C"]
        else:
            base_values = []
            for code, current in [(e.security_code, today), (ETF, etf_today)]:
                key = (e.baseline_date, code)
                previous = prices.loc[key] if key in prices.index else None
                base_values.append(previous.close * current.factor_level
                                   if previous is not None and previous.factor_errors == current.factor_errors else np.nan)
            base, etf_base = base_values
        schedule = [(f"M{n}", e.entry_minute + n) for n in (5, 15, 30, 60)]
        if e.session == e.announcement_date and e.session >= pd.Timestamp("2024-11-05"):
            schedule.extend((f"B{minute // 60:02}{minute % 60:02}", minute) for minute in (870, 885, 900))
        for method, signal_min in schedule:
            auction = method.startswith("B")
            if signal_min <= e.entry_minute or signal_min - 1 not in stock.index or signal_min - 1 not in etf.index:
                continue
            if not valid_minutes(np.array([signal_min - 1]), session_close(e.session))[0]:
                continue
            mark = signal_min - 1
            if auction:
                fills = [930] if 930 in stock.index and stock.at[930, "O"] == stock.at[930, "C"] else []
            else:
                fills = stock.index[(stock.index > signal_min) & (stock.index <= signal_min + 5)
                                    & (stock.index < (925 if e.session >= pd.Timestamp("2024-11-05") else 900))]
            if len(fills) == 0:
                continue
            fill = fills[0]
            price = stock.at[fill, "O"]
            rows.append({
                "event_id": e.event_id, "method": method, "signal_date": e.session,
                "observation_start": e.session + pd.Timedelta(minutes=int(e.entry_minute)),
                "signal_time": e.session + pd.Timedelta(minutes=int(signal_min)),
                "order_time": e.session + pd.Timedelta(minutes=int(signal_min), seconds=1),
                "fill_time": e.session + pd.Timedelta(minutes=int(fill)), "entry_date": e.session,
                "entry": price / today.factor_level, "factor_errors": today.factor_errors,
                "initial_excess": excess(base, stock.at[mark, "C"], etf_base, etf.at[mark, "C"]),
                "limit_day": bool(today.limit_flag), "benchmark": "1306 ETF proxy",
                "bar_turnover": stock.at[fill, "Va"],
            })
    return pd.DataFrame(rows)
