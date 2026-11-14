"""Build and evaluate fixed earnings momentum portfolios."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .__main__ import load
from .daily import DAILY_COLUMNS, lookup, prepare_daily
from .phase3_portfolio import HOLD, performance, simulate, trade_paths
from .phase3_signals import daily_signals, intraday_signals, membership
from .phase3_report import reports, walk_forward

STRATEGIES = ("L", "S", "LS", "LSbeta")
UNIVERSES = ("topix", "all", "non_topix")


def select(trades, universe, strategy, rule="sign"):
    mask = pd.Series(True, index=trades.index)
    if universe != "all":
        mask &= trades.universe.eq(universe)
    if strategy in ("L", "S"):
        mask &= trades.side.eq(1 if strategy == "L" else -1)
    if rule == "abs2":
        mask &= trades.gap.abs().ge(.02)
    if rule == "cap10":
        mask &= trades.gap.abs().le(.10)
    if rule == "aligned":
        mask &= np.sign(trades.revision).eq(trades.side)
    if rule == "liquid":
        mask &= trades.adv.ge(1e8) & trades.cap.ge(1e11)
    if rule in ("q5", "q10"):
        tail = .20 if rule == "q5" else .10
        mask &= ((trades.side.eq(1) & trades["rank"].ge(1 - tail)) |
                 (trades.side.eq(-1) & trades["rank"].le(tail)))
    return trades.loc[mask]


def historical_rank(signals):
    from bisect import bisect_left, bisect_right, insort
    result = pd.Series(np.nan, index=signals.index)
    for _, method in signals.dropna(subset=["initial_excess", "signal_date"]).groupby("method"):
        history = []
        for _, today in method.groupby("signal_date", sort=True):
            values = today.initial_excess
            if len(history) >= 250:
                result.loc[today.index] = [
                    (bisect_left(history, v) + bisect_right(history, v)) / (2 * len(history)) for v in values
                ]
            for value in values:
                insort(history, value)
    return result


def beta_at_events(prices, index, sessions, events):
    rows = []
    market = index.C.reindex(sessions).pct_change(fill_method=None)
    by_code = {code: g for code, g in events.groupby("security_code")}
    for code, group in prices.groupby(level="Code", sort=False):
        if code not in by_code:
            continue
        p = group.droplevel("Code").reindex(sessions)
        r = p.close.pct_change(fill_method=None).where(p.factor_errors.diff().eq(0))
        paired = market.where(r.notna())
        beta = r.rolling(120, min_periods=60).cov(paired) / paired.rolling(120, min_periods=60).var()
        observed = by_code[code]
        rows.append(pd.Series(beta.reindex(observed.attributes_date).to_numpy(), index=observed.event_id))
    return pd.concat(rows)


def load_market(raw, events):
    prices = load(raw, "daily", DAILY_COLUMNS, strings=["Code"])
    prices = prepare_daily(prices.loc[prices.Date.le(events.announcement_date.max())])
    index = load(raw, "topix", ["Date", "O", "C"]).set_index("Date").sort_index()
    calendar = load(raw, "calendar", ["Date", "HolDiv"], strings=["HolDiv"])
    sessions = pd.DatetimeIndex(calendar.loc[calendar.HolDiv.isin(["1", "2"]), "Date"]).sort_values()
    sessions = sessions[(sessions >= events.announcement_date.min()) & (sessions <= events.announcement_date.max())]
    half = set(calendar.loc[calendar.HolDiv.eq("2"), "Date"])
    if not sessions.isin(index.index).all():
        raise ValueError("Missing TOPIX session")
    return prices, sessions, half, index


def build_inputs(raw, phase2):
    events = pd.read_parquet(phase2 / "events.parquet").reset_index(drop=True)
    events = events.loc[events.announcement_datetime.notna()].reset_index(drop=True)
    master = load(raw, "master", ["Date", "Code", "ScaleCat", "Mrgn"], strings=["Code", "ScaleCat", "Mrgn"])
    master = master.set_index(["Date", "Code"], verify_integrity=True)
    # Classification is effective-dated. On non-session days use the last preceding session.
    tentative = lookup(master, events.announcement_date, events.security_code)
    events["universe"] = membership(tentative.ScaleCat)
    events["membership_date"] = events.announcement_date.where(tentative.ScaleCat.notna())
    events["membership_scale"] = tentative.ScaleCat
    prior = lookup(master, events.attributes_date, events.security_code)
    non_session = events.announcement_bucket.eq("non_session") & events.universe.isna()
    events.loc[non_session, "universe"] = membership(prior.ScaleCat)[non_session]
    events.loc[non_session, "membership_scale"] = prior.ScaleCat[non_session]
    events.loc[non_session, "membership_date"] = events.attributes_date[non_session]
    events["loanable"] = prior.Mrgn.eq("2")
    del master
    prices, sessions, half, index = load_market(raw, events)
    events["beta"] = events.event_id.map(beta_at_events(prices, index, sessions, events))
    print("Daily inputs and historical membership loaded", flush=True)
    minute = pd.read_parquet(phase2 / "minute_panel.parquet")
    daily = daily_signals(events, prices, index, sessions, half)
    intra = intraday_signals(events, prices, minute, raw)
    signals = pd.concat([daily, intra], ignore_index=True).merge(events, on="event_id", validate="many_to_one")
    ready = signals.fill_time.notna() & signals.signal_time.notna()
    disclosure = signals.announcement_datetime.dt.tz_localize(None)
    ordered = (disclosure.lt(signals.signal_time) & signals.signal_time.lt(signals.order_time)
               & signals.order_time.lt(signals.fill_time))
    signals["clock_rejected"] = ready & ~ordered
    if signals.clock_rejected.any():
        print(signals.loc[signals.clock_rejected].groupby("method").size().to_string(), flush=True)
    signals.loc[signals.clock_rejected, ["entry", "initial_excess"]] = np.nan
    signals["historical_rank"] = historical_rank(signals)
    return signals, prices, sessions, half, index


def backtest(signals, prices, sessions, half, index, output):
    valid = signals.entry.gt(0) & np.isfinite(signals.initial_excess) & signals.initial_excess.ne(0)
    available = signals.loc[valid]
    codes = set(available.security_code)
    panel = prices[["close", "factor_errors", "limit_flag"]]
    quotes = {code: tuple(group.droplevel("Code").reindex(sessions).to_numpy(dtype=float).T)
              for code, group in panel.groupby(level="Code", sort=False) if code in codes}
    scores, streams, fills, comparison = [], [], [], []
    attributes = signals.drop_duplicates("event_id").set_index("event_id")
    for hold in (*HOLD, 0):
        trades = trade_paths(available, quotes, sessions, half, hold)
        trades["cap"] = trades.event_id.map(attributes.market_cap)
        ranks = available.set_index(["event_id", "method"]).historical_rank
        trades["rank"] = ranks.reindex(pd.MultiIndex.from_frame(trades[["event_id", "method"]])).to_numpy()
        if hold == 3:
            methods = ["A", "C", "B1445", "M15"]
            common = trades.loc[trades.method.isin(methods) & trades.universe.eq("topix")]
            ids = common.groupby("event_id").method.nunique()
            common = common.loc[common.event_id.isin(ids.index[ids.eq(len(methods))])]
            for method, subgroup in common.groupby("method"):
                signed = subgroup.side * (subgroup.marks.map(lambda p: p[-1]) - 1)
                comparison.append(subgroup[["event_id", "method", "side", "closed"]].assign(gross_signed=signed))
        for method, subset in trades.groupby("method"):
            if method not in ("A", "C") and hold not in (1, 3, 5):
                continue
            if method in ("A", "C"):
                configs = [(u, s, 20, "sign", "screened") for u in UNIVERSES for s in STRATEGIES
                           if method == "A" or s != "LSbeta"]
            else:
                configs = [(u, s, 20, "sign", "screened") for u in ("all", "topix") for s in STRATEGIES[:3]]
            if method == "A" and hold == 3:
                configs += [("topix", s, bp, "sign", "screened") for bp in (0, 10, 30, 50) for s in STRATEGIES]
                configs += [("topix", s, 20, rule, "screened")
                            for rule in ("abs2", "cap10", "aligned", "liquid", "q5", "q10") for s in STRATEGIES[:3]]
                configs += [("topix", s, 20, "sign", mode)
                            for mode in ("theoretical", "impact", "tight", "borrow300") for s in STRATEGIES[:3]]
            for universe, strategy, bp, rule, mode in configs:
                selected = select(subset, universe, strategy, rule)
                window_sessions = sessions
                if method not in ("A", "C"):
                    start = sessions[subset.start.min()]
                    end = sessions[subset.end.max()]
                    window_sessions = sessions[(sessions >= start) & (sessions <= end)]
                daily, ledger, rejects = simulate(
                    selected, sessions, index, strategy, bp, constrained=mode != "theoretical",
                    borrow_bps=0 if mode == "theoretical" else (300 if mode == "borrow300" else 100),
                    impact=mode == "impact", participation=.001 if mode == "tight" else .01,
                )
                keys = dict(method=method, hold=hold, universe=universe, strategy=strategy,
                            bps=bp, rule=rule, mode=mode)
                daily = daily.loc[window_sessions]
                scores.append({**keys, **performance(daily["return"]), "fills": len(ledger),
                               "open_at_end": int((~ledger.closed).sum()), "securities": selected.code.nunique(),
                               **{f"mean_{k}": daily[k].mean() for k in
                                  ("positions", "entries", "turnover", "gross", "net", "sector_hhi")},
                               **rejects})
                streams.append(daily.rename_axis("date").reset_index().assign(**keys))
                if method == "A" and hold == 3 and universe == "topix" and bp == 20 and rule == "sign" and mode == "screened":
                    fills.append(ledger.assign(**keys))
        print(f"Portfolios complete for holding period {hold}", flush=True)
    summary = pd.DataFrame(scores)
    daily = pd.concat(streams, ignore_index=True)
    summary.to_parquet(output / "summary.parquet", index=False)
    daily.to_parquet(output / "daily.parquet", index=False)
    pd.concat(fills, ignore_index=True).to_parquet(output / "fills.parquet", index=False)
    if comparison:
        pd.concat(comparison, ignore_index=True).to_parquet(output / "common_entry.parquet", index=False)
    return summary, daily


def run(raw, phase2, output, report_dir, figures, reports_only=False, reuse_signals=False):
    output.mkdir(parents=True, exist_ok=True)
    if reports_only:
        signals, summary, daily = (pd.read_parquet(output / f"{name}.parquet")
                                   for name in ("signals", "summary", "daily"))
    else:
        sources = [phase2 / f"{name}.parquet" for name in ("events", "minute_panel")]
        sources += sorted(raw.glob("*/manifest.json")) + sorted(raw.glob("*/active.json"))
        manifest = json.dumps({
            p.as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
        }, indent=2)
        manifest_path = output / "inputs.json"
        if reuse_signals:
            if manifest_path.read_text(encoding="utf-8") != manifest:
                raise ValueError("Saved signals refer to different inputs")
            signals = pd.read_parquet(output / "signals.parquet")
            prices, sessions, half, index = load_market(raw, signals)
        else:
            signals, prices, sessions, half, index = build_inputs(raw, phase2)
            signals.to_parquet(output / "signals.parquet", index=False)
            manifest_path.write_text(manifest, encoding="utf-8")
        summary, daily = backtest(signals, prices, sessions, half, index, output)
    oos = walk_forward(daily)
    oos.to_parquet(output / "oos.parquet", index=False)
    common_path = output / "common_entry.parquet"
    common = pd.read_parquet(common_path) if common_path.exists() else pd.DataFrame()
    reports(signals, summary, daily, oos, report_dir, figures, common)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option, default in [("raw", "data/raw"), ("phase2", "data/phase2"), ("output", "data/phase3"),
                            ("report-dir", "reports"), ("figures", "figures/phase3")]:
        parser.add_argument(f"--{option}", type=Path, default=Path(default))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--reports-only", action="store_true")
    mode.add_argument("--reuse-signals", action="store_true")
    run(**vars(parser.parse_args()))
