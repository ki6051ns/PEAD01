"""Run Phase 2 against immutable Phase 1 outputs and the archived source data."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .__main__ import load
from .daily import DAILY_COLUMNS, HORIZONS, TSE_MARKETS, prepare_daily
from .events import FIN_COLUMNS, build_events
from .phase2_report import rebuild_reports, write_reports

SIZE = [3e10, 1e11, 5e11, 1e12]
TURNOVER = [1e7, 1e8, 1e9]




def select_controls(candidates, code, cap, turnover):
    candidates = candidates.loc[candidates.index != code].sort_index()
    if candidates.empty or min(cap, turnover) <= 0 or not np.isfinite([cap, turnover]).all():
        return candidates, None
    same = candidates.loc[
        (np.searchsorted(SIZE, candidates.cap, side="right") == np.searchsorted(SIZE, cap, side="right"))
        & (np.searchsorted(TURNOVER, candidates.Va, side="right") == np.searchsorted(TURNOVER, turnover, side="right"))
    ]
    if same.empty:
        return candidates, None
    distance = np.square(np.log(same[["cap", "Va"]].to_numpy() / [cap, turnover])).sum(axis=1)
    return candidates, same.index[distance.argmin()]


def price_return(entry, exit, start_column="open"):
    return (exit.close / entry[start_column] - 1).where(
        exit.factor_errors.eq(entry.factor_errors)
    )


def mark_dates(sessions, entry, horizons=HORIZONS):
    index = sessions.get_indexer([entry])[0]
    if index == -1:
        raise ValueError("Entry date outside exchange calendar")
    return [sessions[index + n - 1] if index + n - 1 < len(sessions) else pd.NaT for n in horizons]


def build_panel(events, universe, prices, topix, sessions, disclosures):
    rows = []
    dates_available = set(prices.index.get_level_values("Date"))
    blank = prices.iloc[:0].droplevel("Date")
    daily = {day: group.droplevel("Date") for day, group in prices.groupby(level="Date", sort=False)}
    topix = topix.set_index("Date")
    disclose_by_day = {day: set(group.Code) for day, group in disclosures.groupby("DiscDate")}
    early = disclosures.DiscTime.str.match(r"^(?:0[0-8]):[0-5]\d", na=False)
    before_open = {day: set(group.Code) for day, group in disclosures.loc[early].groupby("DiscDate")}
    # Use unique date combinations to reuse sector pools and benchmark returns.
    for (day, entry_day), cohort in events.groupby(["announcement_date", "next_open_date"]):
        if entry_day not in dates_available:
            continue
        event_idx = sessions.searchsorted(day)
        if event_idx == 0:
            continue
        prior_day = sessions[event_idx - 1]
        attributes = universe.get(prior_day)
        if attributes is None:
            continue
        excluded = before_open.get(entry_day, set()).union(
            *(disclose_by_day.get(d, set()) for d in pd.date_range(prior_day, entry_day, inclusive="left"))
        )
        entry = daily[entry_day]
        prev = daily.get(prior_day, blank)
        attrs = attributes.join(prev[["MktCap", "Va"]]).rename(columns={"MktCap": "cap"})
        attrs["cap"] *= 1e6
        candidates = attrs.loc[~attrs.index.isin(excluded) & attrs.cap.gt(0) & attrs.Va.gt(0)]
        pools = {sector: group for sector, group in candidates.groupby("S33Nm")}
        ends = mark_dates(sessions, entry_day)
        delayed_day = mark_dates(sessions, entry_day, [2])[0]
        delayed = daily.get(delayed_day, blank)
        old_day = sessions[event_idx - 61] if event_idx >= 61 else pd.NaT
        momentum = price_return(daily.get(old_day, blank).reindex(prev.index), prev, "close")
        raw = {}
        for horizon, end_day in zip(HORIZONS, ends):
            end = daily.get(end_day, blank)
            stock = price_return(entry, end)
            sector_returns = stock.reindex(candidates.index).groupby(candidates.S33Nm).agg(["mean", "count"])
            raw[horizon] = (stock, price_return(delayed, end), sector_returns,
                            market_return(topix, entry_day, end_day),
                            market_return(topix, delayed_day, end_day) if horizon >= 3 else np.nan)
        for event in cohort.itertuples(index=False):
            code = event.security_code
            pool, match = select_controls(pools.get(event.sector, candidates.iloc[:0]), code,
                                          event.market_cap, event.prior_turnover)
            for horizon, end_day in zip(HORIZONS, ends):
                stock, later, sectors, market, delayed_market = raw[horizon]
                value = stock.get(code, np.nan)
                sector, observed = sectors.loc[event.sector] if event.sector in sectors.index else (np.nan, 0)
                control = stock.get(match, np.nan)
                rows.append((event.event_id, horizon, entry_day, end_day, value, value - market,
                             value - sector, value - control, match, len(pool), int(observed),
                             momentum.get(code, np.nan), later.get(code, np.nan) - delayed_market))
    panel = pd.DataFrame(rows, columns=["event_id", "day", "entry_date", "end_date", "raw", "topix",
                                        "industry", "matched", "control", "industry_candidates",
                                        "industry_observed", "momentum", "delayed_topix"])
    grid = pd.MultiIndex.from_product([events.event_id, HORIZONS], names=["event_id", "day"])
    panel = panel.set_index(["event_id", "day"]).reindex(grid).reset_index()
    return panel


def market_return(index, start, end):
    if start in index.index and end in index.index:
        return index.at[end, "C"] / index.at[start, "O"] - 1
    return np.nan


def ranked(values, bins):
    return np.ceil(values.rank(pct=True, method="average") * bins).astype("Int64")


def minute_panel(minute, events):
    minute = minute.merge(events[["event_id", "security_code", "announcement_date",
                                  "announcement_datetime", "announcement_bucket"]], on="event_id")
    minute["timing"] = minute.announcement_bucket.replace(
        {"morning": "intraday", "afternoon": "intraday", "closing_auction": "intraday"})
    start = minute.session.dt.tz_localize("Asia/Tokyo") + pd.to_timedelta(minute.entry_minute, unit="m")
    minute["elapsed_minutes"] = (start - minute.announcement_datetime).dt.total_seconds() / 60
    if minute.elapsed_minutes.le(0).any():
        raise ValueError("Minute observation precedes disclosure")
    return minute


def run(raw, baseline, output, reports, figures):
    output.mkdir(parents=True, exist_ok=True)
    inputs = {name: baseline / f"{name}.parquet" for name in ["events", "daily_returns", "minute_returns"]}
    (output / "inputs.json").write_text(json.dumps({
        name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in inputs.items()
    }, indent=2))
    all_events = pd.read_parquet(inputs["events"])
    old = pd.read_parquet(inputs["daily_returns"])
    ordinary = all_events.loc[all_events.universe_status.eq("tse_common")]
    events = ordinary.loc[~ordinary.repeat_period & ~ordinary.same_day_multiple].copy()
    events["busy"] = events.announcement_date.map(ordinary.groupby("announcement_date").size()).ge(100)
    events["gap"] = events.event_id.map(old.loc[old.horizon.eq("next_open")].set_index("event_id").total_excess)
    events["initial"] = direction(events.gap)
    events["revision"] = direction(events.forecast_revision)
    events["surprise"] = direction(events.company_surprise_op)
    events["year"] = events.announcement_date.dt.year
    events["size"] = pd.cut(events.market_cap, [0, *SIZE, np.inf], right=False, labels=["<30bn", "30-100bn", "100-500bn", "500bn-1tn", ">=1tn"])
    events["liquidity"] = pd.cut(events.prior_turnover, [0, *TURNOVER, np.inf], right=False, labels=["<10m", "10-100m", "100m-1bn", ">=1bn"])
    for bins in [5, 10]:
        events[f"initial_q{bins}"] = ranked(events.gap, bins)
    end = all_events.announcement_date.max()
    fin = load(raw, "financials", FIN_COLUMNS, date_column=None, strings=FIN_COLUMNS)
    histories = build_events(fin.loc[fin.DiscDate.le(end.date().isoformat())], include_revision_prior=True)
    history = histories.set_index("event_id").reindex(events.event_id)
    if not (np.allclose(history.forecast_revision, events.forecast_revision, equal_nan=True)
            and history.revision_prior_date.reset_index(drop=True).equals(events.revision_prior_date.reset_index(drop=True))
            and history.forecast_target.fillna("").tolist() == events.forecast_target.fillna("").tolist()):
        raise ValueError("Forecast revision lineage differs from Phase 1")
    events["revision_amount"] = events.forecast_operating_profit - history.revision_prior_op.to_numpy()
    events["revision_rate_q"] = ranked(events.forecast_revision.where(events.revision.eq("up")), 5)
    events["revision_amount_q"] = ranked(events.revision_amount.where(events.revision.eq("up")), 5)
    minute = minute_panel(pd.read_parquet(inputs["minute_returns"]), events)
    print("Phase 1 inputs and forecast lineage verified", flush=True)
    daily = load(raw, "daily", DAILY_COLUMNS, strings=["Code"])
    prices = prepare_daily(daily.loc[daily.Date.le(end)])[["open", "close", "factor_errors", "MktCap", "Va"]]
    del daily
    master = load(raw, "master", ["Date", "Code", "S33Nm", "Mkt", "ProdCat"], strings=["Code", "Mkt", "ProdCat"])
    master = master.loc[master.Mkt.isin(TSE_MARKETS) & master.ProdCat.eq("011")]
    universe = {day: group.set_index("Code")[["S33Nm"]] for day, group in master.groupby("Date")}
    del master
    topix = load(raw, "topix", ["Date", "O", "C"])
    cal = load(raw, "calendar", ["Date", "HolDiv"], strings=["HolDiv"])
    sessions = pd.DatetimeIndex(cal.loc[cal.HolDiv.isin(["1", "2"]), "Date"].unique()).sort_values()
    disclosures = fin.loc[fin.DocType.str.contains("FinancialStatements_|EarnForecastRevision", na=False),
                          ["Code", "DiscDate", "DiscTime"]].copy()
    disclosures["DiscDate"] = pd.to_datetime(disclosures.DiscDate)
    panel = build_panel(events, universe, prices, topix, sessions, disclosures)
    print("Daily benchmarks and matches calculated", flush=True)
    for name, data in [("events", events), ("daily_panel", panel), ("minute_panel", minute)]:
        data.to_parquet(output / f"{name}.parquet", index=False)
    write_reports(events, old, panel, minute, output, reports, figures)


def direction(values):
    return pd.Series(np.select([values.lt(0), values.gt(0), values.eq(0)], ["down", "up", "flat"],
                               default=None), index=values.index)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option, default in [("raw", "data/raw"), ("baseline", "data/phase1"), ("output", "data/phase2"),
                            ("reports", "reports"), ("figures", "figures/phase2")]:
        parser.add_argument(f"--{option}", type=Path, default=Path(default))
    parser.add_argument("--reports-only", action="store_true")
    args = parser.parse_args()
    if args.reports_only:
        rebuild_reports(args.baseline, args.output, args.reports, args.figures)
    else:
        run(args.raw, args.baseline, args.output, args.reports, args.figures)
