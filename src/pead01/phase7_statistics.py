"""Aggregate the frozen daily Phase 6 study without reranking candidates."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .phase3_portfolio import performance
from .phase6_batch import atomic_json
from .phase6_daily import save
from .phase6_daily_wf import replay
from .phase7 import FOCUS, linked_journal, trade_paths, validate_journal
from .report import pct, table


FREQUENCIES = {"month":"M", "quarter":"Q", "year":"Y"}
METRICS = ("gross","cost","turnover","fills","utilization","net","long_gross","short_gross")


def periods(dates):
    yield "full","all",dates
    for label, freq in FREQUENCIES.items():
        for period in dates.to_period(freq).unique():
            yield label,str(period),dates[dates.to_period(freq)==period]


def ensemble_family(mode):
    return mode.rsplit("_w",1)[0]


def daily_metrics(net, market=None):
    result=performance(net)
    result["cumulative"]=(1+net).prod()-1
    result["daily_median"]=net.median()
    if market is not None:
        aligned=market.reindex(net.index)
        result["beta"]=net.cov(aligned)/aligned.var() if aligned.var()>0 else np.nan
    return result


def periodic_metrics(frozen, market):
    rows=[]
    for mode, frame in frozen.groupby("mode",sort=True):
        frame=frame.set_index("date").sort_index()
        net=frame.net
        reconstructed={}
        for level, period, dates in periods(net.index):
            sample=frame.loc[dates]
            stats=daily_metrics(sample.net,market)
            rows.append(dict(mode=mode,family=ensemble_family(mode),level=level,period=period,
                             start=dates[0],end=dates[-1],**stats,fills=int(sample.fills.sum()),
                             utilization=sample.utilization.mean(),turnover=sample.turnover.mean(),
                             cost_sum=sample.cost.sum(),long_gross_sum=sample.long_gross.sum(),
                             short_gross_sum=sample.short_gross.sum()))
            if level!="full":
                reconstructed.setdefault(level,[]).append(stats["cumulative"])
        for returns in reconstructed.values():
            np.testing.assert_allclose(np.prod(1+np.array(returns)),(1+net).prod(),rtol=0,atol=1e-12)
    return pd.DataFrame(rows)


def event_metrics(journal, net):
    rows=[]
    for level, period, dates in periods(net.index):
        sample=journal.loc[journal.date.isin(dates)]
        by_event=sample.groupby("event").net_capital.sum().sort_values(ascending=False)
        positive=by_event.loc[by_event.gt(0)]
        row=dict(level=level,period=period,events=len(by_event),positive_events=len(positive),
                 negative_events=int(by_event.lt(0).sum()),capital_contribution=by_event.sum(),
                 long_capital=sample.loc[sample.side.gt(0),"net_capital"].sum(),
                 short_capital=sample.loc[sample.side.lt(0),"net_capital"].sum())
        for k in (1,5,10):
            top=positive.head(k)
            row[f"positive_share_top{k}"]=top.sum()/positive.sum() if len(positive) else np.nan
            if level=="full" or (level=="quarter" and period=="2025Q2"):
                # Fix original fills and measure perturbation of daily return contributions.
                impact=journal.loc[journal.event.isin(top.index)].groupby("date").net.sum()
                reduced=net-impact.reindex(net.index,fill_value=0.)
                row[f"period_return_without_top{k}"]=(1+reduced.loc[dates]).prod()-1
                row[f"period_sharpe_without_top{k}"]=performance(reduced.loc[dates])["sharpe"]
                row[f"full_sharpe_without_top{k}"]=performance(reduced)["sharpe"]
        rows.append(row)
    return pd.DataFrame(rows)


def realized_metrics(journal, net):
    groups=(
        ("method",["method"]),("horizon",["hold"]),("method_horizon",["method","hold"]),
    )
    rows=[]
    for axis, fields in groups:
        for key, sample in journal.groupby(fields[0] if len(fields)==1 else fields,sort=True):
            component=sample.groupby("date").net.sum().reindex(net.index,fill_value=0.)
            fills=sample.loc[sample.entry]
            row=dict(axis=axis,bucket="/".join(map(str,key)) if isinstance(key,tuple) else str(key),
                     fills=len(fills),events=sample.event.nunique(),active_days=sample.date.nunique(),
                     long_fills=int(fills.side.gt(0).sum()),short_fills=int(fills.side.lt(0).sum()),
                     capital_contribution=sample.net_capital.sum(),daily_avg=component.mean(),
                     daily_volatility=component.std(),daily_p05=component.quantile(.05),
                     daily_p50=component.median(),daily_p95=component.quantile(.95))
            rows.append(row)
    return pd.DataFrame(rows)


def adoption_metrics(selection,catalogue):
    chosen=selection.loc[selection.weight.gt(0)].merge(catalogue,on="id",validate="many_to_one")
    chosen["exposure"]=chosen.weight*(chosen.end-chosen.start)
    pieces=[]
    for axis, fields in (("method",["method"]),("horizon",["hold"]),("method_horizon",["method","hold"])):
        totals=chosen.groupby(["mode",*fields]).agg(
            adoption_slots=("id","size"),weight_sessions=("exposure","sum")).reset_index()
        totals["axis"]=axis
        totals["bucket"]=totals[fields].astype(str).agg("/".join,axis=1)
        pieces.append(totals.drop(columns=fields))
    return pd.concat(pieces,ignore_index=True)


def attribution(source, cache, frozen, catalogue, selection, market, config):
    paths=[cache/f"{name}.parquet" for name in ("realized","events","replay_verified")]
    if all(path.exists() for path in paths):
        return tuple(pd.read_parquet(path) for path in paths[:2])
    sessions=market.index
    modes=sorted(frozen["mode"].unique())
    streams={m:g.set_index("date").net.sort_index() for m,g in frozen.groupby("mode")}
    selected=selection.loc[selection["mode"].isin(modes)]
    specs=catalogue.loc[catalogue.id.isin(selected.id)]
    trades=trade_paths(source,specs)
    # Replay uses event_id only as journal metadata when skip_rate is zero.
    # Each actual fill retains the path preferred by the original order ledger.
    trades["event_id"]=trades.event_id+"|"+trades.method+"|"+trades.hold.astype(str)
    completed=[]
    chunks=[]
    event_chunks=[]
    active=None
    buffer=[]

    def flush():
        if active is None:
            return
        log=pd.DataFrame(buffer,columns=["date","tag","side","gross","cost","entry"])
        net=streams[active]
        log=log.loc[log.date.isin(net.index)].copy()
        log[["event","method","hold"]]=log.tag.str.rsplit("|",n=2,expand=True)
        log["hold"]=log.hold.astype(int)
        validate_journal(log,net)
        linked=linked_journal(log,net)
        np.testing.assert_allclose(linked.net_capital.sum(),(1+net).prod()-1,atol=1e-12)
        chunks.append(realized_metrics(linked,net).assign(mode=active))
        event_chunks.append(event_metrics(linked,net).assign(mode=active))
        completed.append(active)
        buffer.clear()

    def callback(mode):
        def append(order, day, side, gross, cost, entry):
            nonlocal active
            if mode!=active:
                flush()
                active=mode
            buffer.append((sessions[day],order.event_id,side,gross,cost,entry))
        return append

    reproduced=replay(trades,specs,selected,sessions,config,contributions=True,
                      journals={mode:callback(mode) for mode in modes})
    flush()
    keys=["mode","date"]
    comparable=reproduced.merge(frozen,on=keys,suffixes=("_replay","_source"),validate="one_to_one")
    if len(comparable)!=len(frozen):
        raise ValueError("Incomplete portfolio replay")
    for metric in METRICS:
        np.testing.assert_allclose(comparable[metric+"_replay"],comparable[metric+"_source"],rtol=0,atol=1e-12)
    for mode in sorted(set(modes)-set(completed)):
        if streams[mode].ne(0).any():
            raise ValueError(f"No journal for {mode}")
        empty=pd.DataFrame(columns=["date","event","net_capital","side","net"])
        event_chunks.append(event_metrics(empty,streams[mode]).assign(mode=mode))
    realized=pd.concat(chunks,ignore_index=True)
    events=pd.concat(event_chunks,ignore_index=True)
    save(realized,paths[0])
    save(events,paths[1])
    save(pd.DataFrame({"mode":modes,"days":[len(streams[m]) for m in modes]}),paths[2])
    return realized,events


def load_inputs(source):
    frozen=pd.read_parquet(source/"wf_base.parquet").sort_values(["mode","date"])
    market=pd.read_parquet(source/"market.parquet").set_index("Date")
    if frozen.duplicated(["mode","date"]).any() or len(frozen)!=156*516:
        raise ValueError("Unexpected Phase 6 evaluation panel")
    daily=frozen.pivot(index="date",columns="mode",values="net")
    if daily.shape!=(516,156) or daily.isna().any().any():
        raise ValueError("Phase 6 must have a common finite evaluation period")
    return frozen,market,pd.read_parquet(source/"candidates.parquet"),pd.read_parquet(source/"selection.parquet")


def compute(source,cache,config_path):
    cache.mkdir(parents=True,exist_ok=True)
    files=[*sorted(source.glob("paths_*.parquet")),source/"wf_base.parquet",source/"market.parquet",
           source/"candidates.parquet",source/"selection.parquet",source/"multiplicity.parquet",
           config_path,Path(__file__),Path(__file__).with_name("phase6_daily_wf.py"),
           Path(__file__).with_name("phase6_book.py")]
    manifest={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    signature=cache/"inputs.json"
    if signature.exists() and json.loads(signature.read_text(encoding="utf-8"))!=manifest:
        raise ValueError("Input or code changed. Use a fresh output cache.")
    atomic_json(signature,manifest)
    frozen,market,catalogue,selection=load_inputs(source)
    config=json.loads(config_path.read_text(encoding="utf-8"))
    realized,events=attribution(source,cache,frozen,catalogue,selection,market,config)
    return frozen,market,catalogue,selection,realized,events
