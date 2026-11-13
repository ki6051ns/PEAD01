"""Cash-aware event portfolio accounting and ex-ante signal rules."""
from collections import Counter

import numpy as np
import pandas as pd

from .daily import session_close

HOLD = (1, 2, 3, 5, 10, 20)
CAPITAL = 100_000_000
SLOT = 0.01
PARTICIPATION = .01


def trade_paths(signals, quotes, sessions, half, horizon):
    outcome = []
    offsets = {day: i for i, day in enumerate(sessions)}
    for row in signals.itertuples(index=False):
        start = offsets.get(row.entry_date)
        n = horizon if horizon else (5 if row.initial_excess > 0 else 3)
        # A close fill counts the following trading day as the first holding day.
        target = start + n - (0 if row.method.startswith("B") else 1)
        # End-of-sample entry cutoff is common to all prices and independent of outcomes.
        if target >= len(sessions):
            continue
        close, error, limits = quotes[row.security_code]
        end = target
        for j in range(target, min(target + 5, len(sessions))):
            if close[j] > 0 and error[j] == row.factor_errors and limits[j] == 0:
                end = j
                break
        else:
            end = len(sessions) - 1
        marks = np.r_[row.entry, np.where(error[start:end + 1] == row.factor_errors,
                                         close[start:end + 1], np.nan)]
        latest = np.maximum.accumulate(np.where(np.isfinite(marks), np.arange(len(marks)), 0))
        marks = marks[latest]
        sign = 1 if row.initial_excess > 0 else -1
        closed = (end >= target and end < target + 5 and close[end] > 0
                  and error[end] == row.factor_errors and limits[end] == 0)
        outcome.append((row.event_id, row.method, row.security_code, row.sector, row.universe, row.loanable,
                        start, end, sign, row.beta, row.prior_turnover, row.bar_turnover,
                        row.initial_excess, row.forecast_revision, row.fill_time, row.entry_date,
                        target, sessions[end] + pd.Timedelta(minutes=session_close(sessions[end], sessions[end] in half))
                        if closed else pd.NaT,
                        closed, bool(row.limit_day), marks[1:] / row.entry, n))
    return pd.DataFrame(outcome, columns=["event_id", "method", "code", "sector", "universe", "loanable",
                        "start", "end", "side", "beta", "adv", "bar_turnover", "gap", "revision",
                        "fill_time", "entry_date", "target", "end_time", "closed", "limit_day", "marks", "hold"])


def simulate(trades, sessions, index, strategy, bps, constrained=True, borrow_bps=100, impact=False, participation=PARTICIPATION):
    """Allocate fixed initial 1% slots with portfolio-level capital reservation."""
    n = len(sessions)
    active = []
    nav = 1.
    all_trades = trades.sort_values(["start", "fill_time", "code", "event_id"])
    orders = {d: list(g.itertuples(index=False)) for d, g in all_trades.groupby("start")}
    daily = []
    ledger = []
    reasons = Counter()
    index_oc = (index.C / index.O - 1).reindex(sessions).fillna(0).to_numpy()
    index_cc = index.C.pct_change(fill_method=None).reindex(sessions).fillna(0).to_numpy()
    for i in range(n):
        gross = sum(a[1] * (a[0].marks[i - a[0].start - 1] + abs(a[2])) for a in active)
        room = max(0., nav - gross)
        batch = []
        occupied = {a[0].code for a in active}
        for trade in orders.get(i, []):
            if trade.code in occupied:
                reasons["overlap"] += 1
                continue
            if constrained and trade.side < 0 and not trade.loanable:
                reasons["limit_or_lending"] += 1
                continue
            if strategy == "LSbeta" and not np.isfinite(trade.beta):
                reasons["beta_missing"] += 1
                continue
            batch.append(trade)
            occupied.add(trade.code)
        pnl = cost = entry_turnover = exit_turnover = 0.
        accepted = 0
        for trade in batch:
            hedge = -trade.side * trade.beta if strategy == "LSbeta" else 0.
            size = min(SLOT, room) / (1 + abs(hedge))
            capacity = trade.adv
            if np.isfinite(trade.bar_turnover):
                capacity = min(capacity, trade.bar_turnover) if np.isfinite(capacity) else trade.bar_turnover
            if constrained:
                size = min(size, participation * capacity / CAPITAL) if capacity > 0 else 0.
            reserved = size * (1 + abs(hedge))
            room -= reserved
            if constrained and trade.limit_day:
                reasons["limit_or_lending"] += 1
                continue
            if size <= 0:
                reasons["cash_or_capacity"] += 1
                continue
            # Transaction costs are proportional to marked notional on each side.
            slip = 0.001 * np.sqrt(size * CAPITAL / capacity) if impact and capacity > 0 else 0.
            fee = bps / 20000 + slip
            entry_turnover += size * (1 + abs(hedge))
            cost += size * (1 + abs(hedge)) * fee
            active.append((trade, size, hedge, fee))
            ledger.append((trade.event_id, trade.entry_date, trade.end_time, trade.side, size,
                           trade.closed, trade.marks[-1], trade.universe))
            accepted += 1
        nets = gross_marks = 0.
        sectors = Counter()
        remaining = []
        for trade, size, hedge, fee in active:
            offset = i - trade.start
            mark = trade.marks[offset]
            prior = trade.marks[offset - 1] if offset else 1.
            hedge_return = index_cc[i] if offset else index_oc[i]
            pnl += size * (trade.side * (mark - prior) + hedge * hedge_return)
            if trade.side < 0:
                elapsed_days = (sessions[i] - sessions[i - 1]).days if offset else 1
                cost += size * prior * borrow_bps / 10000 * elapsed_days / 365
            exposure = size * mark
            gross_marks += exposure + size * abs(hedge)
            nets += exposure * trade.side + size * hedge
            sectors[trade.sector] += exposure
            if i == trade.end and trade.closed:
                exit_turnover += exposure + size * abs(hedge)
                cost += (exposure + size * abs(hedge)) * fee
            elif i < trade.end:
                remaining.append((trade, size, hedge, fee))
        stock_gross = sum(sectors.values())
        hhi = sum((v / stock_gross) ** 2 for v in sectors.values()) if stock_gross else 0.
        daily.append(((pnl - cost) / nav, pnl / nav, cost / nav, len(active), accepted,
                      (entry_turnover + exit_turnover) / nav, gross_marks / nav, nets / nav,
                      hhi, len(orders.get(i, []))))
        nav += pnl - cost
        if nav <= 0:
            raise ValueError("Portfolio NAV exhausted")
        active = remaining
    frame = pd.DataFrame(daily, index=sessions, columns=["return", "gross_return", "cost", "positions",
                         "entries", "turnover", "gross", "net", "sector_hhi", "candidates"])
    frame["nav"] = (1 + frame["return"]).cumprod()
    fills = pd.DataFrame(ledger, columns=["event_id", "entry_date", "end_time", "side", "weight",
                                         "closed", "exit_mark", "universe"])
    return frame, fills, dict(reasons)


def performance(returns):
    if not len(returns):
        return {}
    wealth = (1 + returns).cumprod()
    peak = wealth.cummax().clip(lower=1.)
    cutoff = returns.quantile(.05)
    tail = returns.nsmallest(max(1, int(np.ceil(len(returns) * .05))))
    return {"days": len(returns), "annual": wealth.iloc[-1] ** (252 / len(wealth)) - 1,
            "sharpe": np.sqrt(252) * returns.mean() / returns.std() if returns.std() else np.nan,
            "max_dd": (wealth / peak - 1).min(), "es05": tail.mean(),
            "win": returns.gt(0).mean(), "daily_p05": cutoff, "daily_p95": returns.quantile(.95)}
