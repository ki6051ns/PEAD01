"""Evaluate observed exchange prints using start-labeled one-minute bars."""
from bisect import bisect_left

import numpy as np
import pandas as pd

from .daily import session_close

MINUTE_COLUMNS = ["Date", "Time", "Code", "O", "C", "Vo"]
MINUTE_HORIZONS = (5, 15, 30, 60)


def valid_minutes(minutes, close):
    continuous_end = np.where(close == 930, 925, close)
    return (
        ((minutes >= 540) & (minutes <= 690))
        | ((close > 690) & (minutes >= 750) & (minutes < continuous_end))
        | (minutes == close)
    )


def minute_returns(event, days, daily, half_days):
    day = event.announcement_date
    announcement = event.announcement_datetime
    if pd.isna(announcement) or pd.isna(event.first_session):
        return []
    minute = announcement.hour * 60 + announcement.minute
    session = event.first_session
    close = session_close(session, session in half_days)
    bars = days.get((session, event.security_code))
    opening_minute = minute + 1 if session == day else 540
    if bars is None:
        return []
    times = bars.index.to_numpy()
    i = bisect_left(times, opening_minute)
    if i == len(times):
        return []
    first = times[i]
    entry = bars.O.iloc[i]
    base = np.nan
    if session == day and minute > 540:
        prev = bisect_left(times, minute) - 1
        if prev >= 0 and (minute - times[prev] <= 5 or (690 < minute < 750 and times[prev] == 690)
                          or (minute == 750 and times[prev] == 690)):
            base = bars.C.iloc[prev]
    else:
        before = daily.get((event.baseline_date, event.security_code))
        during = daily.get((session, event.security_code))
        if before is not None and during is not None and during.factor_errors == before.factor_errors:
            base = before.close * during.factor_level

    def result(horizon, mark, price):
        return {
            "event_id": event.event_id, "horizon": str(horizon), "session": session,
            "entry_minute": int(first), "target_minute": int(mark),
            "entry_delay_minutes": int(first - opening_minute),
            "total": price / base - 1 if base > 0 else np.nan,
            "post": price / entry - 1,
        }

    rows = [result("first_trade", first, entry)]
    for horizon in MINUTE_HORIZONS:
        target = first + horizon
        # Use the completed bar immediately preceding the wall-clock horizon.
        # Exact auction prints can be used at their own timestamp.
        mark = target if target in (690, close) else target - 1
        if target <= close and mark in bars.index:
            rows.append(result(horizon, mark, bars.at[mark, "C"]))
    if session == day and close in bars.index:
        rows.append(result("same_day_close", close, bars.at[close, "C"]))
    return rows


def build_minute(events, prices, calendar, chunks):
    eligible = events.loc[events.universe_status.eq("tse_common") & events.announcement_datetime.notna()]
    half = set(calendar.loc[calendar.HolDiv.eq("2"), "Date"])
    keys = pd.MultiIndex.from_arrays([eligible.first_session, eligible.security_code])
    filtered = []
    bad_bars = 0
    for chunk in chunks:
        chunk["Date"] = pd.to_datetime(chunk.Date, format="%Y-%m-%d")
        chunk = chunk.loc[pd.MultiIndex.from_frame(chunk[["Date", "Code"]]).isin(keys)].copy()
        parts = chunk.Time.str.extract(r"^([01]\d|2[0-3]):([0-5]\d)(?::00)?$")
        chunk["minute"] = parts[0].astype(float) * 60 + parts[1].astype(float)
        close = np.where(chunk.Date.isin(half), 690, np.where(chunk.Date.ge("2024-11-05"), 930, 900))
        valid = valid_minutes(chunk.minute, close) & chunk.Vo.gt(0) & chunk.O.gt(0) & chunk.C.gt(0)
        bad_bars += (~valid).sum()
        filtered.append(chunk.loc[valid, ["Date", "Code", "minute", "O", "C"]])
    if not filtered:
        return pd.DataFrame(), 0
    bars = pd.concat(filtered, ignore_index=True).drop_duplicates()
    if bars.empty:
        return pd.DataFrame(), int(bad_bars)
    if bars.duplicated(["Date", "Code", "minute"]).any():
        raise ValueError("Conflicting minute bars")
    days = {key: group.set_index("minute").sort_index()
            for key, group in bars.groupby(["Date", "Code"], sort=False)}
    eligible = eligible.loc[keys.isin(days)]
    daily_keys = set(days) | set(zip(eligible.baseline_date, eligible.security_code))
    daily_index = pd.MultiIndex.from_tuples(list(daily_keys), names=["Date", "Code"])
    daily = dict(zip(daily_index, prices.reindex(daily_index).itertuples(index=False)))
    rows = []
    for event in eligible.itertuples(index=False):
        rows.extend(minute_returns(event, days, daily, half))
    return pd.DataFrame(rows), int(bad_bars)
