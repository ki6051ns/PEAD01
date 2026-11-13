"""Observed price paths. A missing print leaves its scheduled mark empty."""
import numpy as np
import pandas as pd

from .daily import session_close
from .minute import valid_minutes

ETF = "13060"
HORIZONS = (5, 15, 30, 60, 120)
BAR_COLUMNS = ["Date", "Code", "Time", "O", "C", "H", "L", "Vo", "Va"]


def trading_clock(minutes, close=930):
    minutes = np.asarray(minutes)
    end = 925 if close == 930 else close
    return np.clip(minutes - 540, 0, 150) + np.clip(minutes - 750, 0, max(0, end - 750))


def paths_for_event(event, stock, market, baseline, close):
    minutes = stock.index.to_numpy()
    release = event.announcement_datetime.hour * 60 + event.announcement_datetime.minute
    same_day = event.announcement_date == event.first_session
    eligible = minutes > release if same_day else minutes >= 540
    after = stock.loc[eligible]
    if after.empty:
        return [], None
    first = int(after.index[0])
    if same_day and release > 540:
        common = stock.index.intersection(market.index)
        prev = common[(common < release) & ((common >= release - 5) |
                                             ((690 < release <= 750) & (common == 690)))]
        if len(prev):
            baseline = stock.at[prev[-1], "C"], market.at[prev[-1], "C"]
        else:
            prior = stock.index[(stock.index < release) & ((stock.index >= release - 5) |
                                                           ((690 < release <= 750) & (stock.index == 690)))]
            baseline = (stock.at[prior[-1], "C"] if len(prior) else np.nan, np.nan)
    stock_base, market_base = baseline
    # Initial direction is frozen 5 clock minutes after the first observed print.
    initial_bar = first + 4
    initial_price = after.C.get(initial_bar, np.nan)
    initial_market = market.C.get(initial_bar, np.nan)
    initial = initial_price / stock_base - 1
    initial_excess = initial - (initial_market / market_base - 1)
    direction = np.sign(initial_excess)
    entries = [("first", first, first, "O")]
    continuous = np.r_[np.arange(540, 690), np.arange(750, 925 if close == 930 else close)]
    active = continuous[continuous >= first]
    for n in HORIZONS:
        target = first + n
        entries.append((f"wall_{n}", target, target if target in (690, close) else target - 1, "C"))
        if len(active) >= n:
            mark = int(active[n-1])
            entries.append((f"trading_{n}", mark + 1, mark, "C"))
    entries += [("am_close", 690, 690, "C"), ("pm_open", 750, 750, "O"), ("close", close, close, "C")]
    rows = []
    for point, target, mark, col in entries:
        if target > close or mark not in after.index:
            continue
        price = after.at[mark, col]
        mp = market[col].get(mark, np.nan)
        total = price / stock_base - 1
        market_total = mp / market_base - 1
        later = (mark > initial_bar or (mark == initial_bar and col == "C")) and pd.notna(initial_price)
        additional = price / initial_price - 1 if later else np.nan
        extra = additional - (mp / initial_market - 1) if later else np.nan
        rows.append((event.event_id, point, event.first_session + pd.Timedelta(minutes=target),
                     mark, target - first, int(trading_clock(target, close) - trading_clock(first, close)),
                     price, total, total - market_total, additional, extra, initial_excess,
                     bool(direction * extra < 0) if np.isfinite(direction * extra) else None,
                     bool(direction * extra <= -.5 * abs(initial_excess)) if np.isfinite(direction * extra) and direction else None,
                     bool(np.sign(initial) * total <= 0) if later and np.isfinite(initial * total) and initial else None))
    later = after.loc[after.index > initial_bar]
    path = later.C / initial_price - 1
    first_hour = after.iloc[:0] if after.empty else after.loc[after.index < first + 60]
    delay = ((event.first_session + pd.Timedelta(minutes=first)) -
             event.announcement_datetime.tz_localize(None)).total_seconds() / 60
    expected = active
    missing = ~np.isin(expected, after.index)
    boundary = np.flatnonzero(np.diff(np.r_[False, missing, False]))
    longest = int(np.diff(boundary)[::2].max()) if len(boundary) else 0
    if direction and np.isfinite(direction) and len(later):
        high = later.H / initial_price - 1
        low = later.L / initial_price - 1
        favorable = high.max() if direction > 0 else -low.min()
        adverse = low.min() if direction > 0 else -high.max()
    else:
        favorable = adverse = np.nan
    meta = dict(event_id=event.event_id, first_minute=first, first_price=after.O.iloc[0],
                initial_excess=initial_excess, first_delay_minutes=delay,
                favorable=favorable, adverse=adverse,
                peak_minute=path.idxmax() if path.notna().any() else np.nan,
                bottom_minute=path.idxmin() if path.notna().any() else np.nan,
                first5_turnover=after.loc[after.index < first+5, "Va"].sum(),
                turnover_60_share=first_hour.Va.sum() / after.Va.sum() if after.Va.sum() > 0 else np.nan,
                volume_60_share=first_hour.Vo.sum() / after.Vo.sum() if after.Vo.sum() > 0 else np.nan,
                longest_missing_trading_minutes=longest, observations=len(after))
    return rows, meta


def paths_from_files(events, sources, daily):
    keys = pd.MultiIndex.from_frame(events[["first_session", "security_code"]])
    seen_days = set()
    paths, metadata = [], []
    by_date = {day: list(part.itertuples(index=False)) for day, part in events.groupby("first_session")}
    required = pd.MultiIndex.from_tuples(
        list({(d, c) for row in events.itertuples(index=False) for d in (row.first_session, row.baseline_date)
              for c in (row.security_code, ETF)}), names=["Date", "Code"])
    prices = dict(zip(required, daily.reindex(required).itertuples(index=False)))
    for file in sources:
        parts = []
        coverage = set()
        for chunk in pd.read_csv(file, usecols=BAR_COLUMNS, dtype={"Code": str, "Time": str}, chunksize=700_000):
            chunk["Date"] = pd.to_datetime(chunk.Date, format="%Y-%m-%d")
            coverage.update(chunk.Date.unique())
            stock = pd.MultiIndex.from_frame(chunk[["Date", "Code"]]).isin(keys)
            keep = chunk.loc[(stock | chunk.Code.eq(ETF)) & chunk.Vo.gt(0) & chunk.O.gt(0) & chunk.C.gt(0)].copy()
            parts.append(keep)
        if any(day in seen_days for day in coverage):
            raise ValueError(f"Overlapping minute snapshots: {file.name}")
        seen_days.update(coverage)
        bars = pd.concat(parts, ignore_index=True).drop_duplicates()
        bars["minute"] = bars.Time.str[:2].astype(int) * 60 + bars.Time.str[3:5].astype(int)
        close = np.where(bars.Date.ge("2024-11-05"), 930, 900)
        bars = bars.loc[valid_minutes(bars.minute, close)]
        for day, day_bars in bars.groupby("Date"):
            if day not in by_date:
                continue
            by_code = {code: data.set_index("minute", verify_integrity=True).sort_index()
                       for code, data in day_bars.groupby("Code")}
            market = by_code.get(ETF, day_bars.iloc[:0].set_index("minute"))
            for event in by_date[day]:
                stock = by_code.get(event.security_code)
                if stock is None:
                    continue
                baseline = []
                for code in (event.security_code, ETF):
                    earlier = prices[event.baseline_date, code]
                    today = prices[event.first_session, code]
                    baseline.append(earlier.close * today.factor_level
                                    if earlier.factor_errors == today.factor_errors else np.nan)
                rows, meta = paths_for_event(event, stock, market, baseline, session_close(day))
                paths.extend(rows)
                if meta is not None:
                    metadata.append(meta)
        print(f"Processed {file.name}: {len(metadata):,} events", flush=True)
    columns = ["event_id", "point", "timestamp", "bar_minute", "elapsed_wall", "elapsed_trading",
               "price", "total", "excess", "additional", "additional_excess", "initial_excess",
               "opposite", "half_retrace", "cross_base"]
    return pd.DataFrame(paths, columns=columns), pd.DataFrame(metadata), seen_days
