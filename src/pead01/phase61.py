"""Replay frozen Phase 6 orders under cash and credit constraints."""
import argparse
from collections import defaultdict
from functools import lru_cache
import hashlib
from itertools import product
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .phase3_portfolio import performance
from .phase6_batch import atomic_json
from .phase6_grid import adaptive_exit, prepare, selection
from .phase6_report import weights

METHODS = ("single", "neighbor", "dynamic_M_252", "fixed")
CAPITAL = 100_000_000
GRID = list(product((1, 2, 3, 5, 10), (1, 1.5, 2, 2.5, 3), (.05, .10, .20, .30, .50)))


def simulate(orders, days, policy, rates, restrictions, market):
    pending = defaultdict(lambda: defaultdict(list))
    for trade, sleeve in orders:
        row, _, _ = trade
        pending[row.start][row.minute, row.code].append((trade, sleeve))
    active = {}
    equity = float(CAPITAL)
    result = []
    for i, day in enumerate(days):
        previous_equity = equity
        multiplier, leverage, scale, allocation = policy[i]
        cash_only, interest, borrow, fee_multiplier = rates
        loan_fee = funding = fees = 0.
        fills = blocked = 0
        # Entries use the last available mark of carried positions.
        def value(item):
            row, side, size, mark, haircut, hedge = item
            return size * (mark + abs(hedge))

        gross = sum(map(value, active.values()))
        peak = gross
        locked = sum(value(p) * p[4] for p in active.values())
        maintenance = gross > 0 and equity < .20 * gross
        restricted = restrictions.get(day, {})
        def mark(code, exiting):
            nonlocal equity, gross, locked, fees
            row, side, size, old, haircut, hedge = active[code]
            price = row.marks[i-row.start]
            equity += side * size * (price-old)
            if hedge:
                equity += size * hedge * market[i, int(i != row.start)]
            if exiting:
                fee = size * (price + abs(hedge)) * row.cost/20000 * fee_multiplier
                equity -= fee
                fees += fee
                gross -= value(active[code])
                locked -= value(active[code]) * haircut
                del active[code]
            else:
                active[code] = row, side, size, price, haircut, hedge

        elapsed = (day-days[i-1]).days if i else 0
        for row, side, size, price, haircut, hedge in active.values():
            funding += size * (int(side > 0) + max(hedge, 0)) * interest * elapsed/365
            loan_fee += size * price * borrow * elapsed/365 if side < 0 else 0.
        equity -= funding + loan_fee
        exits = sorted((p[0].exit_minute, code) for code,p in active.items()
                       if p[0].end == i and p[0].closed)
        j = 0
        for (minute, code), batch in sorted(pending.get(i, {}).items()):
            while j<len(exits) and exits[j][0] < minute:
                mark(exits[j][1], True)
                j += 1
            weighted = [(row, side, w*allocation.get(sleeve, 0))
                        for (row, side, w), sleeve in batch if allocation.get(sleeve, 0)>0]
            demand = sum(side*w for row,side,w in weighted
                         if not cash_only or (side > 0 and not row.hedge))
            side = np.sign(demand)
            if code in active or not side:
                continue
            haircut = 1. if cash_only else max(.30, restricted.get(code, .30))
            if maintenance or haircut >= 1 and not cash_only:
                blocked += 1
                continue
            row = max((x for x in weighted if x[1] == side and (not cash_only or not x[0].hedge)),
                      key=lambda x: x[2])[0]
            hedge = -side * row.beta if row.hedge else 0.
            unit = 1+abs(hedge)
            fee_rate = row.cost/20000 * fee_multiplier
            size = min(row.capacity*CAPITAL, 1e6*multiplier*min(abs(demand),1)*scale,
                       (equity*leverage-gross)/(unit*(1+leverage*fee_rate)),
                       (equity-locked)/(unit*(haircut+fee_rate)))
            if size <= 0:
                blocked += 1
                continue
            active[code] = row, side, size, 1., haircut, hedge
            gross += size*unit
            peak = max(peak,gross)
            locked += size*unit*haircut
            fee = size*unit*fee_rate
            equity -= fee
            fees += fee
            fills += 1
            if row.end == i and row.closed:
                exits.append((row.exit_minute, code))
                exits[j:] = sorted(exits[j:])
        marked_gross = sum(p[2] * (p[0].marks[i-p[0].start] + abs(p[5])) for p in active.values())
        peak = max(peak, marked_gross)
        for code in list(active):
            row = active[code][0]
            mark(code, row.end == i and row.closed)
        closing = sum(map(value, active.values()))
        if equity <= 0:
            raise ValueError("Credit equity exhausted")
        result.append((day,equity,equity/previous_equity-1,peak/previous_equity,peak,closing,
                       max(0.,equity-sum(value(p)*p[4] for p in active.values())),
                       fills,blocked,maintenance,fees,funding,loan_fee))
    return pd.DataFrame(result,columns=["date","nav","return","utilization","peak_yen","closing_yen",
                          "free_collateral","fills","blocked","maintenance","fees","funding","borrow"])


def frozen_orders(root, data, days):
    from .phase6_inputs import attributes
    saved = root/"paths"
    if (saved/"attributes.parquet").exists():
        events = pd.read_parquet(saved/"attributes.parquet")
        events.attrs["ranks"] = pd.read_parquet(saved/"ranks.parquet").set_index(["event_id","method"]).historical_rank
    else:
        _, events, _ = attributes(data,data/"raw")
    events["first5_prints"] = pd.read_parquet(saved/"first5.parquet").set_index("event_id").prints
    trace = pd.read_parquet(root/"selection.parquet")
    trace = trace.loc[trace.method.isin(METHODS)]
    specs = pd.read_parquet(root/"candidates.parquet").set_index("id")
    opening = None

    @lru_cache(maxsize=8)
    def build(identifier):
        nonlocal opening
        c = specs.loc[identifier].to_dict()
        method = c["method"]
        name = "minute" if method.startswith(("I","P5_")) else f"daily_{c['hold']}"
        raw = pd.read_parquet(saved/f"{name}.parquet",filters=[("method","==",method)])
        t = prepare(raw.loc[raw.hold.astype(str).eq(c["hold"])],events,{})
        if c["exit_rule"]!="fixed":
            if opening is None:
                opening = {code:g.set_index("Date")[["open","factor_errors","limit_flag"]].reindex(days).to_numpy(float).T
                           for code,g in pd.read_parquet(saved/"opening.parquet").groupby("Code")}
            t = adaptive_exit(t,c["exit_rule"],opening,days)
        mask, side, w = selection(t,c)
        columns = ["start","end","minute","exit_minute","code","capacity","cost","closed","marks","beta",
                   "loanable","frequency","event_id","sector"]
        return list(zip(t.loc[mask,columns].assign(hedge=c["hedge"]).itertuples(index=False),side[mask],w[mask]))

    result = []
    for identifier,g in trace.groupby("id",sort=False):
        orders = build(identifier)
        for record in g.itertuples():
            lo,hi = days.searchsorted(record.start),days.searchsorted(record.end,side="right")
            result.extend(((row,side,w*record.weight),record.method) for row,side,w in orders if lo<=row.start<hi)
    return result


def pareto(frame):
    metrics = frame[["sharpe", "annual", "max_dd", "utilization"]].to_numpy()
    valid = np.isfinite(metrics).all(axis=1)
    return [bool(valid[i] and not ((metrics >= row).all(axis=1) &
                                   (metrics > row).any(axis=1) & valid).any())
            for i, row in enumerate(metrics)]


def tune(history, target, reference):
    active = history.utilization.mean()
    return min(1., target/active) if reference and active > 0 else 1.


def run(root, data, output, regulation_file, check_only=False):
    from .__main__ import load
    from .phase6_book import book

    output.mkdir(parents=True, exist_ok=True)
    paths = [Path(__file__), root/"selection.parquet", root/"candidates.parquet", root/"calendar.parquet",
             root/"inputs.json"]
    portfolio_path = root/"portfolios.parquet" if (root/"portfolios.parquet").exists() else root/"portfolios_walkforward.parquet"
    paths.append(portfolio_path)
    paths += [Path(__file__).with_name(name) for name in ("phase6_grid.py","phase6_inputs.py","phase6_book.py","phase6_report.py")]
    paths += sorted((data/"raw").glob("*/manifest.json")) + sorted((data/"raw").glob("*/active.json"))
    for name in ("phase3/signals", "phase4/financial_features", "phase4/minute_paths", "phase5/events"):
        paths.append(data/f"{name}.parquet")
    paths += sorted((root/"paths").glob("*.parquet"))
    if regulation_file:
        paths.append(regulation_file)
    digest = hashlib.sha256()
    for path in paths:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(2**20), b""):
                digest.update(chunk)
    manifest = output/"inputs.json"
    signature = {"sha256": digest.hexdigest()}
    if manifest.exists() and json.loads(manifest.read_text()) != signature:
        raise ValueError("Input changed. Choose a new output directory.")
    atomic_json(manifest, signature)
    days = pd.DatetimeIndex(pd.read_parquet(root/"calendar.parquet").date)
    observed = pd.read_parquet(portfolio_path)
    wf = observed.loc[observed["sample"].eq("WF") & observed.method.isin(METHODS)]
    baseline = wf.pivot(index="date",columns="method",values="net").sort_index()
    anchor = days.get_loc(baseline.index.min())
    source = frozen_orders(root,data,days)
    topix = load(data/"raw","topix",["Date","O","C"]).set_index("Date").reindex(days)
    market = np.column_stack([(topix.C/topix.O-1).fillna(0),topix.C.pct_change(fill_method=None).fillna(0)])
    restrictions = {}
    if regulation_file:
        rules = pd.read_csv(regulation_file,dtype={"code":str},parse_dates=["effective","until","known"])
        if rules[["effective","until","known","initial_margin","code"]].isna().any().any() or (
            rules.effective.gt(rules.until) | ~rules.initial_margin.between(.30,1)
        ).any():
            raise ValueError("Invalid historical restriction rows")
        for r in rules.itertuples():
            for day in days[(days>=max(r.effective,r.known+pd.Timedelta(days=1))) & (days<=r.until)]:
                by_code = restrictions.setdefault(day,{})
                by_code[r.code] = max(by_code.get(r.code,.30),r.initial_margin)
    reconciliation = []
    for sleeve in METHODS:
        orders = [trade for trade,m in source if m==sleeve]
        old, _ = book(orders,days,{"capital":CAPITAL,"position_limit":1e6},market=market.T,collect=False)
        diff = old[anchor:,5] - baseline[sleeve].reindex(days[anchor:]).to_numpy()
        reconciliation.append((sleeve,float(np.max(np.abs(diff)))))
    pd.DataFrame(reconciliation,columns=["method","max_daily_difference"]).to_csv(output/"baseline_check.csv",index=False)
    if any(not np.isfinite(diff) or diff > 1e-8 for _,diff in reconciliation):
        raise ValueError("Phase 6 replay differs from saved daily returns; see baseline_check.csv")
    if check_only:
        return

    spans = [g.index for _,g in baseline.groupby(baseline.index.to_period("Q"))]
    # Fixed alternatives are diagnostic; the adaptive policy is selected only from matured historical trades.
    recipes = [(m,"equal") for m in METHODS] + [("composite",k) for k in ("equal","inverse","shrink")]
    rate_cases = {"standard":(False,.028,.01,1.), "no_funding":(False,0.,.01,1.),
                  "stress":(False,.05,.03,1.5), "cash":(True,0.,0.,1.)}
    rows = []
    total = len(recipes)*len(GRID) + len(recipes)*len(rate_cases)
    progress = output/"progress.json"

    def allocations(sleeve, kind, idx):
        if sleeve != "composite":
            return {sleeve:1.}
        names = METHODS[:3]
        historical = baseline.reindex(days[anchor:max(anchor,idx-125)])[list(names)]
        w = weights(historical.to_numpy().T,kind) if len(historical)>=40 else np.ones(3)/3
        return dict(zip(names,w))

    def produce(sleeve, kind, schedule, scenario):
        policy = [(1,1.,1.,{}) for _ in days]
        for idx,end,m,l,target,scale in schedule:
            allocation = allocations(sleeve,kind,idx)
            for j in range(idx,end):
                policy[j] = (m,1. if scenario=="cash" else l,scale,allocation)
        return simulate(source,days,policy,rate_cases[scenario],restrictions,market).iloc[anchor:].reset_index(drop=True)

    def checkpoint(key, compute):
        path = output/f"{key}.parquet"
        if not path.exists():
            pending = path.with_suffix(".tmp")
            compute().to_parquet(pending,index=False)
            pending.replace(path)
        return pd.read_parquet(path)

    def record(key, frame, **params):
        metrics = performance(frame["return"])
        monthly = frame.groupby(frame.date.dt.to_period("M"))["return"].apply(lambda v:(1+v).prod()-1)
        rows.append(dict(id=key,**params,**metrics,
                         calmar=metrics["annual"]/-metrics["max_dd"] if metrics["max_dd"]<0 else np.nan,
                         utilization=frame.utilization.mean(),util_p95=frame.utilization.quantile(.95),
                         peak_yen=frame.peak_yen.max(),fills=frame.fills.sum(),
                         margin_days=frame.maintenance.sum(),positive_months=monthly.gt(0).mean(),
                         funding=frame.funding.sum(),borrow=frame.borrow.sum(),fees=frame.fees.sum()))
        atomic_json(progress,{"status":"running","complete":len(rows),"total":total})

    for sleeve,kind in recipes:
        parameters = []
        for k,(m,l,target) in enumerate(GRID):
            key = f"{sleeve}_{kind}_{k}"
            # Calibrate target scaling using only previously available Phase 6 utilization.
            def nominal():
                schedule = []
                past = wf.loc[wf.method.eq(sleeve if sleeve!="composite" else "single")].set_index("date")
                for span in spans:
                    idx,end = days.get_loc(span[0]),days.get_loc(span[-1])+1
                    history = past.loc[past.index<days[max(0,idx-124)]].copy()
                    history["utilization"] *= m
                    schedule.append((idx,end,m,l,target,tune(history,target,True)))
                return produce(sleeve,kind,schedule,"standard")
            frame = checkpoint(key,nominal)
            parameters.append((m,l,target,frame))
            record(key,frame,method=sleeve,allocation=kind,scenario="standard",evaluation="fixed_grid",
                   multiplier=m,leverage=l,target=target)
        selected = []
        for span in spans:
            idx,end = days.get_loc(span[0]),days.get_loc(span[-1])+1
            limit = days[max(0,idx-124)]
            past = [(m,l,target,frame.loc[frame.date.lt(limit)]) for m,l,target,frame in parameters]
            eligible = [(performance(h["return"])["sharpe"],m,l,target,h) for m,l,target,h in past
                        if len(h)>=40 and h.fills.sum()>=20 and h["return"].std()>0]
            if eligible:
                _,m,l,target,h = max(eligible,key=lambda row:row[0])
                reference = wf.loc[wf.method.eq(sleeve if sleeve!="composite" else "single") & wf.date.lt(limit)].copy()
                reference["utilization"] *= m
                scale = tune(reference,target,True)
            else:
                m,l,target,scale = 1,1.,.05,1.
            selected.append((idx,end,m,l,target,scale))
        pd.DataFrame(selected,columns=["start_index","end_exclusive","multiplier","leverage","target","scale"]).to_parquet(
            output/f"policy_{sleeve}_{kind}.parquet",index=False)
        for scenario in rate_cases:
            key = f"{sleeve}_{kind}_selected_{scenario}"
            frame = checkpoint(key,lambda:produce(sleeve,kind,selected,scenario))
            record(key,frame,method=sleeve,allocation=kind,scenario=scenario,evaluation="selected")
            monthly = frame.assign(month=frame.date.dt.strftime("%Y-%m")).groupby("month")["return"].apply(
                lambda v:(1+v).prod()-1)
            monthly.rename("return").reset_index().to_parquet(output/f"monthly_{key}.parquet",index=False)
    summary = pd.DataFrame(rows)
    summary["pareto"] = False
    for _, group in summary.groupby(["evaluation","scenario"]):
        summary.loc[group.index,"pareto"] = pareto(group)
    summary["annual_under_1pct"] = summary.annual.lt(.01)
    summary.to_parquet(output/"summary.parquet",index=False)
    summary.loc[summary.pareto].sort_values("sharpe",ascending=False).to_csv(output/"pareto.csv",index=False)
    atomic_json(progress,{"status":"completed","complete":len(rows),"total":total})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase6",type=Path,default=Path("data/phase6_v6"))
    parser.add_argument("--data",type=Path,default=Path("data"))
    parser.add_argument("--output",type=Path,default=Path("data/phase61"))
    parser.add_argument("--regulations",type=Path)
    parser.add_argument("--check-only",action="store_true")
    args = parser.parse_args()
    try:
        run(args.phase6,args.data,args.output,args.regulations,args.check_only)
    except KeyboardInterrupt:
        atomic_json(args.output/"status.json",{"status":"paused","exit":130})
        raise SystemExit(130)
    except Exception as exc:
        atomic_json(args.output/"status.json",{"status":"failed","exit":1,"error":str(exc)})
        raise
    atomic_json(args.output/"status.json",{"status":"completed","exit":0})


if __name__ == "__main__":
    main()
