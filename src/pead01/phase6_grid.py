"""Deterministic staged candidate catalogue and vectorized screening."""
from itertools import product
import hashlib
import json

import numpy as np
import pandas as pd


def spec(method, hold, family="A", direction="long", threshold=0, adv=0, universe="all",
         condition="any", sizing="equal", exit_rule="fixed", hedge=False):
    base = dict(method=method, hold=str(hold), family=family, direction=direction, threshold=threshold,
                adv=adv, universe=universe, condition=condition, sizing=sizing, exit_rule=exit_rule, hedge=hedge)
    return {**base, "id": hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()[:16]}


def catalogue(method, hold, config, sectors):
    for side, bound, adv, universe in product(
            ("long", "short", "ls", "reverse"), config["strength"], config["adv"], ("all", "topix", "non_topix")):
        family = "C" if side == "reverse" else "D" if str(hold) in ("40","60","90","120","close") else "A"
        yield spec(method, hold, family, side, bound, adv, universe)
    if hold not in ("3", "20", "60", "to60", "close"):
        return
    for side, condition in product(("long", "short", "ls"), (
            "rev_up", "rev_flat", "rev_down", "rev_conflict", "op_agree", "eps_agree",
            "op_yoy_agree", "progress_agree", "eps_rev_agree")):
        yield spec(method, hold, "B", side, condition=condition)
    for side, condition in product(("long", "short", "ls"), (
            "past_size_high", "past_size_low", "trend_up", "trend_down", "vol_high", "vol_low",
            "size_small", "size_large", "volume_high", "prints_high", "financial", "other",
            "morning", "lunch", "afternoon", "after_close", "before_open", "busy_known",
            *("sector:" + s for s in sectors))):
        yield spec(method, hold, "E", side, condition=condition)
    for sizing in ("inverse_vol", "score"):
        yield spec(method, hold, "D", "long", sizing=sizing)
    yield spec(method, hold, "A", "ls", condition="past_tail")
    if method in ("A", "C"):
        if hold == "20":
            for kind in ("stop", "trailing", "stall", "reversal"):
                yield spec(method, hold, "D", "ls", exit_rule=kind)
        yield spec(method, hold, "D", "ls", hedge=True)


def prepare(frame, events, settings):
    columns = ["security_code", "sector", "universe", "loanable", "beta", "prior_turnover", "adv20", "market_cap",
               "past_size", "market_20", "vol_20", "vol_threshold", "OP_revision_amount", "EPS_revision_amount",
               "OP_company_surprise", "EPS_company_surprise", "OP_series_surprise", "op_progress_change",
               "volume_burst_5", "first5_prints", "announcement_bucket", "known_busy"]
    t = frame.join(events[[col for col in columns if col not in frame]], on="event_id")
    t = t.rename(columns={"security_code": "code"}).reset_index(drop=True)
    t["adv"] = t.adv20.fillna(t.prior_turnover)
    t["marks"] = t.marks.map(np.asarray)
    t["last"] = t.marks.map(lambda m: m[-1])
    keys = pd.MultiIndex.from_frame(t[["event_id", "method"]])
    t["historical_rank"] = events.attrs["ranks"].reindex(keys).to_numpy()
    return t


def adaptive_exit(t, kind, opening, days):
    """Detect at a close and exit at the following available open."""
    result = t.copy()
    # Signals condition the candidate separately; the path exit follows the signal sign.
    for i, row in enumerate(t.itertuples()):
        path = row.marks
        if len(path) < 2:
            continue
        signed = np.sign(row.gap) * (path - 1)
        if kind == "stop":
            hit = signed <= -.03
        elif kind == "trailing":
            hit = np.maximum.accumulate(np.r_[0., signed])[1:] - signed >= .025
        elif kind == "stall":
            hit = np.r_[False, np.diff(signed) <= 0] & (np.arange(len(path)) >= 2)
        else:
            hit = signed < 0
        candidates = np.flatnonzero(hit[:-1])
        if not len(candidates):
            continue
        j = candidates[0]+1
        price, error, limit = opening[row.code][:, row.start+j]
        p = price / row.entry
        if not np.isfinite(p) or error != row.factor_errors or limit != 0:
            continue
        result.at[i, "marks"] = np.r_[path[:j], p]
        result.at[i, "last"] = p
        result.at[i, "end"] = row.start+j
        result.at[i, "exit_minute"] = 540
        result.at[i, "closed"] = True
        result.at[i, "exit_time"] = days[row.start+j]+pd.Timedelta(hours=9)
    return result


def selection(t, c):
    gap = t.gap.to_numpy()
    sign = np.sign(gap)
    direction = c["direction"]
    side = (sign if direction == "ls" else -sign if direction == "reverse"
            else (sign > 0).astype(int) if direction == "long" else -(sign < 0).astype(int))
    mask = (np.abs(gap) >= c["threshold"]) & t.adv.ge(c["adv"]).to_numpy() & (side != 0)
    mask &= (side > 0) | t.loanable.eq(True).to_numpy()
    if c["universe"] != "all":
        mask &= t.universe.eq(c["universe"]).to_numpy()
    condition = c["condition"]
    if condition in ("volume_high", "prints_high"):
        mask &= t.method.str.startswith(("P5_", "I")).to_numpy()
    if condition.startswith("sector:"):
        mask &= t.sector.eq(condition[7:]).to_numpy()
    elif condition in ("rev_up", "rev_flat", "rev_down"):
        mask &= np.sign(t.OP_revision_amount).eq({"rev_up": 1, "rev_flat": 0, "rev_down": -1}[condition]).to_numpy()
    elif condition == "rev_conflict":
        mask &= np.sign(t.OP_revision_amount).eq(-sign).to_numpy()
    elif condition.endswith("_agree"):
        col = {"op_agree": "OP_company_surprise", "eps_agree": "EPS_company_surprise",
               "op_yoy_agree": "OP_series_surprise", "progress_agree": "op_progress_change",
               "eps_rev_agree": "EPS_revision_amount"}[condition]
        mask &= np.sign(t[col]).eq(sign).to_numpy()
    elif condition != "any":
        tests = {
            "past_size_high": lambda: t.past_size.ge(.8), "past_size_low": lambda: t.past_size.le(.2),
            "size_small": lambda: t.market_cap.lt(3e10), "size_large": lambda: t.market_cap.ge(1e12),
            "trend_up": lambda: t.market_20.gt(0), "trend_down": lambda: t.market_20.lt(0),
            "vol_high": lambda: t.vol_20.gt(t.vol_threshold), "vol_low": lambda: t.vol_20.le(t.vol_threshold),
            "volume_high": lambda: t.volume_burst_5.ge(2), "prints_high": lambda: t.volume_burst_5.notna()
                & t.gap.notna() & t.first5_prints.ge(4),
            "financial": lambda: t.sector.isin(["銀行業", "保険業", "その他金融業"]),
            "other": lambda: ~t.sector.isin(["銀行業", "保険業", "その他金融業"]),
            "busy_known": lambda: t.known_busy,
            "past_tail": lambda: (t.historical_rank.ge(.9) & (sign > 0)) | (t.historical_rank.le(.1) & (sign < 0)),
        }
        mask &= (tests[condition]() if condition in tests else t.announcement_bucket.eq(condition)).to_numpy()
    if c["hedge"]:
        mask &= np.isfinite(t.beta)
    if c["family"] == "B":
        # End-of-day API timing is unknown; intraday observations are theoretical.
        mask &= t.method.isin(["A", "C"]).to_numpy()
    weight = np.ones(len(t))
    if c["sizing"] == "score":
        weight = np.clip(np.abs(gap)/.05, .1, 1)
    if c["sizing"] == "inverse_vol":
        weight = np.where(t.vol_20.gt(0), np.clip(.01/t.vol_20, .1, 1), 0.)
    return mask & (weight > 0), side.astype(int), weight


def screen(t, c, increments, days, settings, market):
    mask, side, weights = selection(t, c)
    idx = np.flatnonzero(mask)
    size = np.minimum(t.capacity.to_numpy()[idx], settings["position_limit"]/settings["capital"]*weights[idx])
    start = t.start.to_numpy()[idx]
    end = t.end.to_numpy()[idx]
    axis, delta, parent, marked = increments
    # Aggregate sparse marks before applying a day-level gross-cap screen.
    cap = np.zeros(len(t))
    cap[idx] = size
    selected = mask[parent]
    axis, delta, parent, marked = axis[selected], delta[selected], parent[selected], marked[selected]
    component = cap[parent]
    gross = np.bincount(axis, component * marked, minlength=len(days))
    pnl = np.bincount(axis, delta * component * side[parent], minlength=len(days))
    if c["hedge"]:
        beta = t.beta.fillna(0).to_numpy()
        hedge = -side[parent] * beta[parent] * component
        first = axis == t.start.to_numpy()[parent]
        pnl += np.bincount(axis, hedge * np.where(first, market[0, axis], market[1, axis]), minlength=len(days))
        gross += np.bincount(axis, np.abs(hedge), minlength=len(days))
    fee = t.cost.to_numpy()[idx]/20000
    last = t["last"].to_numpy()[idx]
    closed = t.closed.to_numpy()[idx]
    turn = np.bincount(start, size, minlength=len(days)) + np.bincount(end, size*last*closed, minlength=len(days))
    costs = np.bincount(start, size*fee, minlength=len(days)) + np.bincount(end, size*last*fee*closed, minlength=len(days))
    prior_marks = marked - delta
    borrow_days = np.r_[1, np.diff(days.values).astype("timedelta64[D]").astype(int)]
    borrow = np.bincount(axis, component * prior_marks * (side[parent] < 0) * borrow_days[axis] * .01/365,
                         minlength=len(days)) if t.frequency.iloc[0] == "daily" else np.zeros(len(days))
    scale = 1/np.maximum(1., gross)
    return np.column_stack([(pnl-borrow-costs)*scale, pnl*scale, turn*scale, gross*scale,
                            np.bincount(start, minlength=len(days)), borrow*scale])


def sparse_marks(t):
    lengths = np.array([len(m) for m in t.marks])
    parent = np.repeat(np.arange(len(t)), lengths)
    age = np.arange(lengths.sum()) - np.repeat(np.cumsum(lengths)-lengths, lengths)
    axis = t.start.to_numpy()[parent]+age
    mark = np.concatenate(t.marks.to_list())
    lag = np.r_[1., mark[:-1]]
    lag[age == 0] = 1.
    return axis, mark-lag, parent, mark
