"""Point-in-time disclosures and daily inputs for the Phase 8 comparison."""
import numpy as np
import pandas as pd

from .__main__ import load
from .daily import DAILY_COLUMNS, TSE_MARKETS, lookup, prepare_daily, session_close
from .events import FIN_COLUMNS, build_events


def unique(frame, keys, name):
    if frame.duplicated(keys).any():
        raise ValueError(f"{name}: conflicting rows keyed by {keys}")
    return frame


def compare(current, previous, keys, values):
    """Compare rows over dates present in both archives, including either-side gaps."""
    date = keys[0]
    lower = max(current[date].min(), previous[date].min())
    upper = min(current[date].max(), previous[date].max())
    a = current.loc[current[date].between(lower, upper), keys + values].set_index(keys)
    b = previous.loc[previous[date].between(lower, upper), keys + values].set_index(keys)
    a_dates, b_dates = (f.index.get_level_values(date).unique() for f in (a, b))
    common = a.index.intersection(b.index)
    left, right = a.loc[common], b.loc[common]
    same = left.eq(right) | (left.isna() & right.isna())
    return dict(shared_dates=len(a_dates.intersection(b_dates)), new_only_dates=len(a_dates.difference(b_dates)),
                old_only_dates=len(b_dates.difference(a_dates)), matched=len(common), new_only=len(a)-len(common),
                old_only=len(b)-len(common), changed=int((~same).any(axis=1).sum()),
                changed_by_field={c: int(n) for c, n in (~same).sum().items()})


def inputs(raw, old_raw, old_events, cfg):
    first, last = (pd.Timestamp(cfg[k]) for k in ("first_session", "last_session"))
    quality = {}
    cal = unique(load(raw, "calendar", ["Date", "HolDiv"], strings=["HolDiv"]), ["Date"], "calendar")
    requested = pd.DatetimeIndex(cal.loc[cal.HolDiv.isin(["1", "2"]) & cal.Date.between(first, last),
                                         "Date"]).sort_values()
    market = unique(load(raw, "topix", ["Date", "O", "C"]), ["Date"], "TOPIX").set_index("Date")

    columns = ["Date", "Code", "Mkt", "ProdCat", "S33Nm", "Mrgn"]
    string_columns = columns[1:]
    master = unique(load(raw, "master", columns, strings=string_columns), ["Date", "Code"], "master")
    daily = load(raw, "daily", DAILY_COLUMNS, strings=["Code"])
    financials = load(raw, "financials", FIN_COLUMNS, date_column=None, strings=FIN_COLUMNS)
    months = pd.PeriodIndex(pd.to_datetime(financials.DiscDate.unique()), freq="M")
    spans = {"daily": (daily.Date.min(), daily.Date.max()),
             "master": (master.Date.min(), master.Date.max()),
             "topix": (market.index.min(), market.index.max()),
             "financials_months": (months.min().start_time, months.max().end_time)}
    lo = max(first, *(a for a, _ in spans.values()))
    hi = min(last, *(b for _, b in spans.values()))
    sessions = requested[(requested >= lo) & (requested <= hi)]
    if not len(sessions):
        raise ValueError("No overlapping sessions across data archives")
    first, last = sessions[0], sessions[-1]
    quality["archive_spans"] = {k: [str(a.date()), str(b.date())] for k, (a, b) in spans.items()}
    quality["requested_sessions"], quality["trimmed_sessions"] = len(requested), len(requested)-len(sessions)
    if not sessions.to_period("M").isin(months).all():
        raise ValueError("Monthly gap in financial disclosures")
    market = market.reindex(sessions).rename_axis("Date")
    if not (np.isfinite(market).all().all() and market.gt(0).all().all()):
        raise ValueError("Missing or invalid TOPIX price on a research session")
    master = master.loc[master.Date.le(last)]
    if old_raw:
        before = load(old_raw, "master", columns, strings=string_columns)
        quality["master_overlap"] = compare(master, before, columns[:2], columns[2:])
        del before
    if not sessions.isin(master.Date.unique()).all():
        raise ValueError("Missing point-in-time master session")
    quality["master_rows"] = len(master)
    master = master.set_index(["Date", "Code"])

    financials = financials.loc[financials.DiscDate.le(last.date().isoformat())]
    disclosure_key = ["DiscDate", "Code", "DiscNo"]
    if old_raw:
        before = load(old_raw, "financials", FIN_COLUMNS, date_column=None, strings=FIN_COLUMNS)
        quality["financial_overlap"] = compare(
            unique(financials, disclosure_key, "financials"),
            unique(before, disclosure_key, "old financials"),
            disclosure_key, [c for c in FIN_COLUMNS if c not in disclosure_key])
        del before
    quality["disclosures"] = len(financials)
    events = build_events(financials)
    del financials
    events = events.loc[events.announcement_date.between(first, last)].reset_index(drop=True)
    quality.update(event_count=len(events), first_event=str(events.announcement_date.min().date()),
                   last_event=str(events.announcement_date.max().date()),
                   unknown_times=int(events.announcement_datetime.isna().sum()),
                   repeat_period=int(events.repeat_period.sum()),
                   multiple_statements=int(events.same_day_multiple.sum()))
    prior = sessions.searchsorted(events.announcement_date) - 1
    attr_date = pd.Series(sessions.take(prior.clip(min=0))).where(prior >= 0)
    attrs = lookup(master, attr_date, events.security_code)
    same_day = lookup(master, events.announcement_date, events.security_code)
    common = attrs.ProdCat.fillna(same_day.ProdCat).eq("011") & attrs.Mkt.fillna(same_day.Mkt).isin(TSE_MARKETS)
    events = events.assign(sector=attrs.S33Nm, loanable=attrs.Mrgn.eq("2"),
                           attributes_date=attr_date.where(attrs.Mkt.notna()))
    quality["master_unmatched_events"] = int((attrs.Mkt.isna() & same_day.Mkt.isna()).sum())
    events = events.loc[common & ~events.repeat_period & ~events.same_day_multiple].copy()
    if old_events:
        keys = ["announcement_date", "event_id"]
        fields = ["announcement_datetime", "attributes_date", "security_code", "sector"]
        before = pd.read_parquet(old_events, columns=keys + fields)
        quality["phase2_overlap"] = compare(events, before, keys, fields)
        del before
    del master, attrs, same_day
    quality["eligible_events"] = len(events)
    quality["loanable_events"] = int(events.loanable.sum())
    quality["yearly_events"] = {str(k): int(v) for k, v in events.groupby(events.announcement_date.dt.year).size().items()}

    daily = unique(daily.loc[daily.Date.between(first, last)], ["Date", "Code"], "daily")
    if not daily.Date.isin(sessions).all() or not sessions.isin(daily.Date.unique()).all():
        raise ValueError("Daily/calendar session mismatch")
    if old_raw:
        before = load(old_raw, "daily", DAILY_COLUMNS, strings=["Code"])
        quality["daily_overlap"] = compare(daily, before, ["Date", "Code"], ["O", "H", "L", "C", "Vo", "Va", "AdjFactor", "UL", "LL"])
        before = load(old_raw, "topix", ["Date", "O", "C"])
        quality["topix_overlap"] = compare(market.reset_index(), before, ["Date"], ["O", "C"])
        del before
    prices = prepare_daily(daily)
    quality.update(daily_rows=len(daily), price_codes=int(daily.Code.nunique()),
                   bad_ohlc=int(prices.bad_ohlc.sum()), missing_volume=int(daily.Vo.isna().sum()),
                   zero_volume=int(daily.Vo.eq(0).sum()),
                   invalid_factor=int((~(daily.AdjFactor.gt(0) & np.isfinite(daily.AdjFactor))).sum()),
                   adjustments=int((daily.AdjFactor.gt(0) & daily.AdjFactor.ne(1)).sum()))
    spans = daily.groupby("Code").Date.agg(["min", "max", "size"])
    span_length = sessions.searchsorted(spans["max"], side="right") - sessions.searchsorted(spans["min"])
    quality["missing_bars_inside_code_span"] = int((span_length-spans["size"]).sum())
    quality["codes_ending_before_last_session"] = int(spans["max"].lt(last).sum())
    del daily
    codes = set(events.security_code)
    quality["event_codes_without_prices"] = len(codes - set(spans.index))
    fields = ["open", "close", "factor_errors", "limit_flag", "Va"]
    bars = {code: dict(zip(("O", "C", "errors", "limit", "Va"),
                          g.droplevel("Code").reindex(sessions).to_numpy(float).T))
            for code, g in prices[fields].groupby(level="Code", sort=False) if code in codes}
    half = set(cal.loc[cal.HolDiv.eq("2"), "Date"])
    closes = np.array([session_close(day, day in half) for day in sessions])
    return events, sessions, bars, market, closes, quality
