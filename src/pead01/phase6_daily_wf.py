"""Event-level purging and allocation for the unified daily grid."""
from itertools import product

import numpy as np
import pandas as pd

from .phase6_book import book
from .phase6_report import weights


def eligible(entry, signal, end, start_date, cutoff):
    """Strictly exclude labels with an unknown or coincident end."""
    return (entry>=start_date)&(signal>=start_date)&(entry<cutoff)&(end<cutoff)


def sharpe(x):
    sd=x.std(ddof=1) if len(x)>1 else 0
    return float(x.mean()/sd*np.sqrt(252)) if sd>0 else np.nan


def features(paths, cfg, sessions):
    n=len(paths)
    start=paths.start.to_numpy(int)
    count=np.array([len(v) for v in paths.marks])
    parent=np.repeat(np.arange(n),count)
    age=np.arange(count.sum())-np.repeat(np.cumsum(count)-count,count)
    mark=np.concatenate(paths.marks.tolist())
    previous=np.r_[1.,mark[:-1]]
    previous[age==0]=1
    day=start[parent]+age
    elapsed=np.diff(sessions.values,prepend=sessions.values[0]).astype("timedelta64[D]").astype(int)
    capacity=np.minimum(cfg["position_limit"],paths.adv.to_numpy()*cfg["participation"])/cfg["capital"]
    cost=cfg["cost_bp"]/20000
    cost_mark=cost*((age==0)+mark*((day==paths.end.to_numpy()[parent]) & paths.closed.to_numpy()[parent]))
    pnl=capacity[parent]*(mark-previous)
    expense=capacity[parent]*cost_mark
    borrow=capacity[parent]*previous*.01/365*np.where(age==0,1,elapsed[day])
    return day,parent,pnl,expense,borrow,capacity[parent]*mark


def observations(trades, cfg, sessions, cutoffs):
    """Build candidate score series only from completed trades inside each fitting interval."""
    metadata=[]
    returns={}
    traces=[]
    for (method,entry,hold,exit_price),g in trades.groupby(["method","entry","hold","exit_price"],sort=True):
        g=g.reset_index(drop=True)
        day,parent,delta,cost,borrow,exposure=features(g,cfg,sessions)
        start=g.start.to_numpy(int)
        signals=sessions.searchsorted(g.signal_time.dt.normalize())
        end=g.end.to_numpy(int)
        end=np.where(g.closed,end,len(sessions))
        gap=g.gap.to_numpy()
        for direction,threshold in product(cfg["directions"],cfg["thresholds"]):
            side=np.sign(gap)
            if direction=="long":
                side=np.maximum(side,0)
            if direction=="short":
                side=np.minimum(side,0)
            mask=(side!=0)&(np.abs(gap)>=threshold)&((side>0)|g.loanable.to_numpy(bool))
            c=len(metadata)
            metadata.append((c,method,entry,hold,exit_price,direction,threshold,int(mask.sum())))
            take=mask[parent]
            dd, pp=day[take], parent[take]
            net=delta[take]*side[pp]-cost[take]-borrow[take]*(side[pp]<0)
            gross=exposure[take]
            for lo,hi in cutoffs:
                valid=mask & eligible(start,signals,end,lo,hi)
                available=mask & (start>=lo)&(signals>=lo)&(start<hi)
                include=valid[pp]
                series=np.bincount(dd[include]-lo,net[include],minlength=hi-lo)
                scale=np.bincount(dd[include]-lo,gross[include],minlength=hi-lo)
                series=series/np.maximum(1,scale)
                returns[c,lo,hi]=series.astype("float32")
                traces.append((c,lo,hi,hi-lo,int(np.unique(dd[include]).size),int(valid.sum()),
                               int((available&~valid).sum()),sessions[start[valid].max()] if valid.any() else pd.NaT,
                               sessions[end[valid].max()] if valid.any() else pd.NaT,sharpe(series)))
    return (pd.DataFrame(metadata,columns=["id","method","entry","hold","exit_price","direction","threshold","n"]),
            returns,pd.DataFrame(traces,columns=["id","lo","hi","window_days","active_days","fills","purged",
                                               "last_entry","last_label","sharpe"]))


def fold_windows(start, window, blank, validation_days):
    end=start-blank
    vstart=end-validation_days
    tend=vstart-blank
    return (0 if not window else tend-window,tend),(vstart,end)


def evaluate(trades, sessions, cfg, folds, output, market):
    ranges={(0,len(sessions))}
    for start,_ in folds:
        for w,b in product(cfg["windows"],cfg["blanks"]):
            ranges.update(fold_windows(start,w,b,cfg["validation_days"]))
    catalogue,ret,audit=observations(trades,cfg,sessions,sorted(ranges))
    catalogue.to_parquet(output/"candidates.parquet",index=False)
    audit.to_parquet(output/"interval_scores.parquet",index=False)
    by_interval={k:g.set_index("id") for k,g in audit.groupby(["lo","hi"])}
    timeline=[]
    for start,end in folds:
        for window in cfg["windows"]:
            blocks=[]
            for blank in cfg["blanks"]:
                tr,va=fold_windows(start,window,blank,cfg["validation_days"])
                train=by_interval[tr]
                val=by_interval[va]
                good=train.loc[train.fills.ge(cfg["min_train_fills"])].dropna(subset=["sharpe"])
                shortlist=good.nlargest(50,"sharpe").index
                check=val.loc[shortlist]
                best=check.loc[check.fills.ge(cfg["min_validation_fills"])].dropna(subset=["sharpe"])
                best=best.sort_values("sharpe",ascending=False,kind="stable").index.tolist()
                for c in catalogue.id:
                    timeline.append((start,end,window,blank,"audit",c,0.,c in shortlist,c in best))
                label=f"w{window}_b{blank}"
                if not best:
                    for mode in ("single","top","neighbor","shrink","max_sharpe","dynamic"):
                        timeline.append((start,end,window,blank,mode+"_"+label,-1,0.,False,False))
                    continue
                winner=best[0]
                top=best[:cfg["top_k"]]
                t=np.array([ret[(c,*tr)] for c in top])
                row=catalogue.iloc[winner]
                neighbors=[c for c in best if
                           sum(catalogue.iloc[c][k]!=row[k] for k in
                               ("method","entry","hold","exit_price","threshold","direction"))<=1]
                # Dynamic allocation updates on each WF boundary using recent purged training returns.
                dynamic=weights(t[:,-min(63,t.shape[1]):],"shrink")
                picks={"single":([winner],[1.]),"top":(top,np.ones(len(top))/len(top)),
                       "neighbor":(neighbors,np.ones(len(neighbors))/len(neighbors)),
                       "shrink":(top,weights(t,"shrink")),"max_sharpe":(top,weights(t,"max_sharpe")),
                       "dynamic":(top,dynamic)}
                for mode,(ids,weight) in picks.items():
                    for c,v in zip(ids,weight):
                        timeline.append((start,end,window,blank,mode+"_"+label,c,float(v),True,True))
                blocks.append((blank,winner,tr))
            for mode in ("equal","shrink","dynamic"):
                name=f"blank_{mode}_w{window}"
                if not blocks:
                    timeline.append((start,end,window,-1,name,-1,0.,False,False))
                    continue
                # A common calendar training interval makes cross-blank covariance comparable.
                lo=max(t[0] for _,_,t in blocks)
                hi=min(t[1] for _,_,t in blocks)
                streams=np.array([ret[(c,*t)][lo-t[0]:hi-t[0]] for _,c,t in blocks])
                allocation=weights(streams,"shrink") if mode=="shrink" else np.ones(len(blocks))/len(blocks)
                if mode=="dynamic":
                    scores=np.array([sharpe(s[-63:]) for s in streams])
                    allocation=np.exp(np.clip(np.nan_to_num(scores),-3,3))
                    allocation/=allocation.sum()
                for (blank,c,_),w in zip(blocks,allocation):
                    timeline.append((start,end,window,blank,name,c,float(w),True,True))
    history=pd.DataFrame(timeline,columns=["start","end","window","blank","mode","id","weight","shortlisted","validated"])
    history.to_parquet(output/"selection.parquet",index=False)
    return catalogue,history,by_interval[(0,len(sessions))]


def replay(trades, catalogue, history, sessions, cfg, cost=None, capacity_scale=1.,
           slippage=0., skip_rate=0., contributions=False, journals=None):
    from collections import namedtuple
    import hashlib
    rowtype=namedtuple("Order","start end minute exit_minute code sector event_id capacity cost frequency "
                               "loanable closed marks beta hedge")
    pairs={}
    fields=["method","entry","hold","exit_price"]
    grouped=trades.groupby(fields,sort=False).indices
    choices_by_id=dict(tuple(history.loc[history.weight.gt(0)].groupby("id",sort=False)))
    for spec in catalogue.itertuples(index=False):
        choices=choices_by_id.get(spec.id)
        if choices is None:
            continue
        group=trades.take(grouped[tuple(getattr(spec,k) for k in fields)])
        group=group.loc[group.gap.abs().ge(spec.threshold)]
        for (start,end), memberships in choices.groupby(["start","end"],sort=False):
            subset=group.loc[group.start.ge(start)&group.start.lt(end)]
            sleeves=[(pairs.setdefault(c.mode,[]),c.weight) for c in memberships.itertuples(index=False)]
            for p in subset.itertuples(index=False):
                side=int(np.sign(p.gap))
                if not side or (spec.direction=="long" and side<0) or (spec.direction=="short" and side>0):
                    continue
                if skip_rate and int.from_bytes(hashlib.sha256(p.event_id.encode()).digest()[:4],"big")/2**32<skip_rate:
                    continue
                marks=p.marks
                if slippage:
                    marks=marks/(1+side*slippage)
                    if p.closed:
                        marks[-1]*=1-side*slippage
                row=rowtype(p.start,p.end,p.fill_time.hour*60+p.fill_time.minute,p.exit_minute,p.code,
                            p.sector,p.event_id,p.adv*cfg["participation"]/cfg["capital"]*capacity_scale,
                            cfg["cost_bp"],"daily",p.loanable,p.closed,marks,0.,False)
                for orders,weight in sleeves:
                    orders.append((row,side,weight))
    out=[]
    for mode in sorted(set(history["mode"])-{"audit"}):
        sides=np.zeros((len(sessions),2))
        result,_=book(pairs.get(mode,[]),sessions,cfg,cost_override=cost,collect=False,
                      contributions=sides if contributions else None,
                      journal=journals.get(mode) if journals is not None else None)
        daily=pd.DataFrame(result,columns=["gross","cost","turnover","fills","utilization","net"])
        if contributions:
            # Use identical shared-ledger fills and sizing, including cash/netting effects.
            daily[["long_gross","short_gross"]]=sides
        out.append(daily.assign(date=sessions,mode=mode))
    return pd.concat(out,ignore_index=True)
