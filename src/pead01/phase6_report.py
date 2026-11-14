"""Selection, ensemble construction and reproducible Phase 6 reporting."""
from collections import Counter
from functools import lru_cache

import numpy as np
import pandas as pd

from .phase3_portfolio import performance
from .phase6_book import book
from .phase6_grid import adaptive_exit, prepare, selection, spec
from .report import pct, plot, table


def statistics(matrix, days, market):
    r = matrix[:, :, 0].astype(float)
    wealth = np.cumprod(1+r, axis=1)
    drawdown = (wealth/np.maximum(1, np.maximum.accumulate(wealth, axis=1))-1).min(axis=1)
    sd = r.std(axis=1, ddof=1)
    annual = wealth[:, -1]**(252/len(days))-1
    return pd.DataFrame(dict(
        annual=annual, sharpe=np.divide(r.mean(axis=1)*np.sqrt(252), sd,
                                       out=np.full(len(r), np.nan), where=sd>0),
        max_dd=drawdown, calmar=np.divide(annual, -drawdown, out=np.full(len(r), np.nan), where=drawdown<0),
        es=np.sort(r, axis=1)[:, :int(np.ceil(.05*len(days)))].mean(axis=1),
        fills=matrix[:, :, 4].sum(axis=1), utilization=matrix[:, :, 3].mean(axis=1),
        turnover=matrix[:, :, 2].mean(axis=1),
        beta=(r * (market.to_numpy()-market.mean())).mean(axis=1)/market.var(ddof=0)))


def rank(matrix, lo, hi, minimum):
    score = np.full(len(matrix), -np.inf)
    for start in range(0, len(matrix), 256):
        part = matrix[start:start+256, lo:hi]
        r = part[:,:,0].astype(float)
        sd = r.std(axis=1)
        np.divide(r.mean(axis=1), sd, out=score[start:start+len(r)],
                  where=(sd>0) & (part[:,:,4].sum(axis=1)>=minimum))
    ordered = np.argsort(-score, kind="stable")
    return ordered[np.isfinite(score[ordered])]


def weights(returns, method):
    n = len(returns)
    if method == "equal" or n == 1:
        return np.full(n, 1/n)
    cov = np.cov(returns) + np.eye(n)*1e-12
    diag = np.maximum(np.diag(cov), 1e-12)
    if method == "inverse":
        w = 1/np.sqrt(diag)
    else:
        cov = .5*cov + .5*np.diag(diag)
        if method == "parity":
            # Coordinate solution of a convex logarithmic risk-budget objective.
            w = 1/np.sqrt(diag)
            for _ in range(30):
                for i in range(n):
                    off = cov[i] @ w - cov[i,i]*w[i]
                    w[i] = 2/n/(np.sqrt(off*off+4*cov[i,i]/n)+off)
        else:
            expected = returns.mean(axis=1)
            w = np.maximum(np.linalg.solve(cov, expected if method == "max_sharpe" else np.ones(n)), 0)
            if method == "max_sharpe":
                # Optimize the long-only Sharpe from the clipped seed on the simplex.
                w = w/w.sum() if w.sum() else np.full(n, 1/n)
                for _ in range(40):
                    risk = max(w@cov@w, 1e-12)
                    grad = expected/np.sqrt(risk) - (expected@w)*(cov@w)/risk**1.5
                    w = np.maximum(w + .02*grad, 0)
                    w = w/w.sum() if w.sum() else np.full(n, 1/n)
    return w/w.sum() if w.sum() else np.full(n, 1/n)


def neighborhood(specs, winner, allowed):
    best = specs[winner]
    fixed = ["family", "direction", "universe", "condition", "sizing", "exit_rule", "hedge"]
    axes = {"method": ["I5", "I15", "I30", "I60", "P5_1", "P5_5", "P5_15", "B1445", "A", "C"],
            "hold": ["1","2","3","5","10","15","20","30","40","60","90","120","close","to60"],
            "threshold": [0,.01,.03,.07], "adv": [0,1e8,1e9]}
    picked = []
    for i in allowed:
        c = specs[i]
        if any(c[k] != best[k] for k in fixed):
            continue
        distance = sum(abs(v.index(c[k])-v.index(best[k])) if c[k] in v and best[k] in v
                       else int(c[k]!=best[k])*2 for k,v in axes.items())
        if distance <= 1:
            picked.append(i)
    return picked or [winner]


def effective(returns):
    r = returns[np.std(returns, axis=1)>0]
    if len(r)<2:
        return float(len(r)), np.ones(len(r)), np.nan
    c = np.corrcoef(r)
    eig = np.linalg.eigvalsh(c).clip(0)
    return float(eig.sum()**2/(eig@eig)), eig, float(c[np.triu_indices(len(c),1)].mean())


def evaluate(data, paths_dir, events, opening, days, market, config, specs, matrix, scores, output, reports, figures,
             forward_only=False, stage=None, progress=None):
    reports.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    from .phase6_book import book

    @lru_cache(maxsize=10)
    def order_frame(m, hold, exit_rule):
        intraday = m.startswith(("I", "P5_"))
        file = "minute.parquet" if intraday else f"daily_{hold}.parquet"
        raw = pd.read_parquet(paths_dir/file, filters=[("method","==",m)])
        raw = raw.loc[raw.hold.astype(str).eq(hold)].reset_index(drop=True)
        t = prepare(raw, events, config)
        return adaptive_exit(t, exit_rule, opening, days) if exit_rule != "fixed" else t

    @lru_cache(maxsize=64)
    def candidate(i):
        c = specs[i]
        t = order_frame(c["method"], c["hold"], c["exit_rule"])
        take, side, w = selection(t, c)
        selected = t.loc[take, ["start","end","minute","exit_minute","code","sector","event_id","capacity",
                               "cost","frequency","loanable","closed","marks","beta"]].assign(hedge=c["hedge"])
        return [(row, int(s), float(weight)) for row,s,weight in zip(selected.itertuples(index=False),
                                                                    side[take], w[take])]

    def replay(selected, allocation, start=0, end=None, cost=None, collect=True):
        end = len(days) if end is None else end
        orders = [(row, side, weight*w) for ix,w in zip(selected, allocation)
                  for row,side,weight in candidate(int(ix)) if start <= row.start < end]
        return book(orders, days, config, cost, market, collect)

    if forward_only:
        cutoff = pd.Timestamp(config["research_end"])
        post = set(events.index[events.announcement_date.gt(cutoff)])
        locked = [spec("A",h,universe="topix") for h in (3,10,20)]
        locked.append(spec("P5_1","to60",adv=100000000,universe="topix"))
        by_id = {c["id"]:i for i,c in enumerate(specs)}
        rows = []
        for rule in locked:
            if rule["id"] not in by_id:
                continue
            orders = [(r,s,w) for r,s,w in candidate(by_id[rule["id"]]) if r.event_id in post]
            d,_ = book(orders,days,config,market=market)
            for day, row in zip(days[days>cutoff],d[days>cutoff]):
                rows.append((rule["id"],day,row[5],row[3],row[4]))
        pd.DataFrame(rows,columns=["id","date","net","fills","utilization"]).to_parquet(
            output/"forward_daily.parquet",index=False)
        return

    ranked = rank(matrix, 0, len(days), config["minimum_fills"])
    anchor = next(i for i,c in enumerate(specs) if c["id"]==spec("A",20,universe="topix")["id"])
    # The exact book reranks a fixed number of screening finalists.
    if stage == "walkforward":
        exact = pd.read_parquet(output/"exact_finalists.parquet")
    else:
        best_daily = []
        for i in ranked[:20]:
            if progress:
                progress(0, "finalist")
            daily, _ = replay([i], [1.], collect=False)
            best_daily.append((i, performance(pd.Series(daily[:,5]))["sharpe"]))
        exact = pd.DataFrame(best_daily, columns=["index","sharpe"]).sort_values("sharpe", ascending=False)
        exact["id"] = exact["index"].map(lambda i: specs[i]["id"])
        exact.to_parquet(output/"exact_finalists.parquet", index=False)
    winner = int(exact.iloc[0]["index"])
    groups = {"fixed": ([anchor], [1.]), "single": ([winner], [1.])}
    for k in config["top_k"]:
        chosen = ranked[:k]
        groups[f"top{k}"] = (chosen, weights(matrix[chosen,:,0], "equal"))
    near = neighborhood(specs, winner, ranked)
    groups["neighbor"] = (near, weights(matrix[near,:,0], "equal"))
    for rule in ("inverse", "shrink", "parity", "max_sharpe"):
        chosen = ranked[:10]
        groups[rule] = (chosen, weights(matrix[chosen,:,0], rule))
    metadata, portfolio, memberships, sectors = [], [], [], Counter()

    def record(name, sample, daily, selected, allocation, positions, dates):
        r = pd.Series(daily[:,5])
        info = performance(r)
        ind, _, corr = effective(matrix[np.asarray(selected, dtype=int), :, 0]) if len(selected) else (np.nan, [], np.nan)
        beta = np.cov(r, market[1,dates])[0,1]/np.var(market[1,dates])
        metadata.append(dict(method=name, sample=sample, **info, fills=int(daily[:,3].sum()),
                             utilization=float(daily[:,4].mean()), turnover=float(daily[:,2].mean()),
                             effective=ind, correlation=corr, beta=beta))
        portfolio.append(pd.DataFrame({"date": days[dates], "net": r, "gross": daily[:,0], "cost": daily[:,1],
                                       "fills": daily[:,3], "utilization": daily[:,4], "turnover": daily[:,2],
                                       "method": name, "sample": sample}))
        for i,w in zip(selected, allocation):
            memberships.append((name,sample,specs[i]["id"],w))
        for day, code, side, event, sector, exposure in positions:
            if dates[0]<=day<=dates[-1]:
                sectors[name,sample,sector] += exposure

    for name,(selected,allocation) in (groups.items() if stage != "walkforward" else ()):
        if progress:
            progress(0, name)
        daily, pos = replay(selected, allocation)
        record(name,"IS",daily,selected,allocation,pos,np.arange(len(days)))
    baseline_rows = []
    anchors = [*(spec("A",h,universe="topix") for h in (3,10,20)),
               spec("P5_1","to60",adv=100000000,universe="topix")]
    for rule in (anchors if stage != "walkforward" else ()):
        i = next(j for j,c in enumerate(specs) if c["id"]==rule["id"])
        d,_ = replay([i],[1.],collect=False)
        dates = np.arange(len(days))
        if rule["method"].startswith("P5_"):
            covered = pd.read_parquet(data/"phase4/covered_sessions.parquet").session
            dates = np.flatnonzero(days.isin(covered))
        baseline_rows.append({**rule, **performance(pd.Series(d[dates,5])),
                              "fills": int(d[dates,3].sum()), "utilization": d[dates,4].mean()})
    if baseline_rows:
        pd.DataFrame(baseline_rows).to_parquet(output/"fixed_baselines.parquet",index=False)
    sensitivity = []
    for name in (("fixed","single","top10","neighbor","shrink") if stage != "walkforward" else ()):
        for cost in (0,5,10,20,30,50):
            d,_ = replay(*groups[name],cost=cost,collect=False)
            sensitivity.append(dict(method=name,bps=cost,**performance(pd.Series(d[:,5]))))
    if sensitivity:
        pd.DataFrame(sensitivity).to_parquet(output/"cost_sensitivity.parquet",index=False)

    # Start the evaluation with cash and carry existing positions across later updates.
    cap = max(config["daily_holds"])+4
    first = int(days.searchsorted("2025-07-01"))
    schedules, traces = {}, []
    for freq in config["updates"]:
        seq = pd.Series(np.arange(first,len(days)),index=days[first:])
        spans = [(int(g.iloc[0]),int(g.iloc[-1])+1) for _,g in seq.groupby(pd.Grouper(freq=freq)) if len(g)]
        for window in config["windows"]:
            schedules[f"dynamic_{freq}_{window}"] = (spans,window,"dynamic")
        if freq=="Q":
            for rule in ("fixed","single","neighbor","shrink","inverse","parity","max_sharpe",
                         *(f"top{k}" for k in config["top_k"])):
                schedules[rule] = (spans,0,rule)
    for name,(spans,window,mode) in (schedules.items() if stage != "ensemble" else ()):
        if progress:
            progress(0, name)
        orders, chosen_all = [], Counter()
        for start,end in spans:
            # Five full sessions separate the validation marks from new orders.
            val_end = start-5
            val_start = val_end-45
            train_end = val_start-cap-5
            if train_end < 126:
                continue
            train_start = max(0,train_end-window) if window else 0
            training_rank = rank(matrix,train_start,train_end,12)[:50]
            chosen = training_rank
            # Validate only marking dates sufficiently far from entry, using the book of
            # observations already matured at the decision timestamp.
            validated = rank(matrix[chosen], val_start, val_end, 4)
            chosen = chosen[validated] if len(validated) else chosen
            if not len(chosen):
                chosen = np.array([anchor])
            if mode=="fixed":
                selected = [anchor]
            elif mode=="single":
                selected = chosen[:1]
            elif mode=="neighbor":
                selected = neighborhood(specs,int(chosen[0]),chosen)
            elif mode.startswith("top"):
                selected = chosen[:int(mode[3:])]
            else:
                selected = chosen[:10]
            sample = matrix[selected,train_start:train_end,0].astype(float)
            style = "shrink" if mode=="dynamic" else mode if mode in ("shrink","inverse","parity","max_sharpe") else "equal"
            allocation = weights(sample, style)
            if mode=="dynamic":
                recent = matrix[selected,max(train_start,train_end-63):train_end,0]
                nav = np.cumprod(1+recent,axis=1)
                dd = 1-(nav/np.maximum(1,np.maximum.accumulate(nav,axis=1))).min(axis=1)
                regime = market[1,max(0,start-20):start].sum()
                exposure = np.array([1 if specs[i]["direction"]=="long" else -1 if specs[i]["direction"]=="short" else 0 for i in selected])
                allocation *= np.exp(-10*dd+np.clip(regime*exposure,-.2,.2))
                allocation /= allocation.sum()
            for i,w in zip(selected,allocation):
                chosen_all[int(i)] += w
                train_rank = np.flatnonzero(training_rank==i)
                val_rank = np.flatnonzero(chosen==i)
                traces.append((name,days[start],days[end-1],days[train_start],days[train_end-1],
                               days[val_start],days[val_end-1],specs[i]["id"],w,
                               int(train_rank[0])+1 if len(train_rank) else None,
                               int(val_rank[0])+1 if len(val_rank) else None))
                orders.extend((row,side,weight*w) for row,side,weight in candidate(int(i)) if start<=row.start<end)
        d, pos = book(orders,days,config,market=market)
        ids = list(chosen_all)
        allocation = np.array([chosen_all[i] for i in ids])
        if len(allocation):
            allocation /= allocation.sum()
        dates=np.arange(first,len(days))
        record(name,"WF",d[dates],ids,allocation,pos,dates)
    comparison = pd.DataFrame(metadata)
    suffix = "_" + stage if stage else ""
    comparison.to_parquet(output/f"comparison{suffix}.parquet",index=False)
    streams = pd.concat(portfolio,ignore_index=True)
    streams.to_parquet(output/f"portfolios{suffix}.parquet",index=False)
    trace = pd.DataFrame(traces,columns=["method","start","end","train_start","train_end","validation_start",
                                       "validation_end","id","weight","train_rank","validation_rank"])
    if len(trace):
        trace.to_parquet(output/"selection.parquet",index=False)
        trace.groupby(["method","id"]).weight.agg(["count","sum"]).reset_index().to_parquet(
            output/"selection_frequency.parquet",index=False)
    pd.DataFrame(memberships,columns=["method","sample","id","weight"]).to_parquet(output/f"weights{suffix}.parquet",index=False)
    pd.DataFrame([(*key,value) for key,value in sectors.items()],
                 columns=["method","sample","sector","exposure"]).to_parquet(output/f"sector_exposure{suffix}.parquet",index=False)
    if stage == "walkforward":
        return
    # Pairwise constituent overlap based on individual actual fills for the IS top 10.
    constituents, actual = {}, []
    for i in ranked[:10]:
        d,h = replay([i],[1.])
        actual.append(d[:,5])
        constituents[i] = ({(x[0],x[1],x[2]) for x in h},{x[3] for x in h})
    actual=np.array(actual)
    count,eig,corr=effective(actual)
    pairs=[]
    for j,i in enumerate(ranked[:10]):
        for k,h in enumerate(ranked[:10]):
            if j>=k:
                continue
            p1,e1=constituents[i]; p2,e2=constituents[h]
            worst=actual[j]<=np.quantile(actual[j],.01)
            pairs.append((specs[i]["id"],specs[h]["id"],np.corrcoef(actual[j],actual[k])[0,1],
                          len(p1&p2)/max(1,len(p1|p2)),len(e1&e2)/max(1,len(e1|e2)),
                          (actual[k,worst]<0).mean()))
    pd.DataFrame(pairs,columns=["a","b","corr","position_overlap","event_overlap","co_loss"]).to_parquet(
        output/"dependence.parquet",index=False)
    pd.DataFrame({"eigenvalue":eig}).to_parquet(output/"eigenvalues.parquet",index=False)
    # Random sign flips of five-session aggregate returns, synchronized across candidates.
    start = np.arange(0,len(days),5)
    grouped = np.concatenate([np.add.reduceat(matrix[ranked[i:i+256],:,0].astype(float),start,axis=1)
                              for i in range(0,len(ranked),256)])
    rng = np.random.default_rng(6)
    signs = rng.choice([-1,1],size=(999,len(start)))
    observed = grouped.sum(axis=1)/np.sqrt(np.square(grouped).sum(axis=1))
    null_max = np.full(len(signs), -np.inf)
    for batch in np.array_split(grouped, max(1, int(np.ceil(len(grouped)/1000)))):
        null = (signs @ batch.T)/np.sqrt(np.square(batch).sum(axis=1))
        null_max = np.maximum(null_max, null.max(axis=1))
    pd.DataFrame({"top_candidates": [len(ranked)], "block_days": [5],
                  "max_stat": [observed.max()],
                  "max_stat_p": [(1+(null_max>=observed.max()).sum())/1000]}).to_parquet(
                      output/"screen_max_stat.parquet",index=False)
    if stage is None:
        write_reports(data,specs,scores,ranked,exact,winner,comparison,streams,count,corr,near,output,reports,figures)
    locked = {
        "research_cutoff": config["research_end"],
        "first_eligible_disclosure": "2026-11-14",
        "rules": [specs[anchor], spec("A",3,universe="topix"), spec("A",10,universe="topix"),
                  spec("P5_1","to60",adv=100000000,universe="topix")],
        "policy": "Freeze thresholds and costs from this configuration. Append a later archived snapshot, "
                  "select only post-cutoff disclosures, start with cash and report after all open trades mature.",
    }
    import json
    (output/"forward_rules.json").write_text(json.dumps(locked,indent=2,ensure_ascii=False),encoding="utf-8")


def report_saved(data, output, reports, figures, config):
    reports.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    scores = pd.read_parquet(output/"candidates.parquet")
    scores = scores.reset_index(drop=True)
    exact = pd.read_parquet(output/"exact_finalists.parquet")
    winner = int(exact.iloc[0]["index"])
    ranked = scores.loc[scores.eligible].sort_values("sharpe", ascending=False, kind="stable").index.to_numpy()
    specs = scores.to_dict("records")
    def read(name):
        paths = [output/f"{name}_{stage}.parquet" for stage in ("ensemble", "walkforward")]
        if all(path.exists() for path in paths):
            return pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True)
        return pd.read_parquet(output/f"{name}.parquet")
    comparison, streams = read("comparison"), read("portfolios")
    eig = pd.read_parquet(output/"eigenvalues.parquet").eigenvalue.to_numpy()
    pairs = pd.read_parquet(output/"dependence.parquet")
    write_reports(data,specs,scores,ranked,exact,winner,comparison,streams,
                  eig.sum()**2/(eig@eig),pairs["corr"].mean(),neighborhood(specs,winner,ranked),
                  output,reports,figures)
    scores.iloc[ranked[:100]].to_csv(output/"phase6_top_candidates.csv",index=False)
    for label, sample in [("ensemble","IS"),("walkforward","WF")]:
        comparison.loc[comparison["sample"].eq(sample)].to_csv(output/f"phase6_{label}_summary.csv",index=False)
    (output/"phase6_final_summary.md").write_bytes((reports/"phase6_findings.md").read_bytes())


def write_reports(data,specs,scores,ranked,exact,winner,comparison,streams,count,corr,near,output,reports,figures):
    from .phase4_report import save
    historical=pd.read_parquet(data/"phase3/summary.parquet")
    base=historical.loc[(historical.method=="A")&(historical.hold==20)&(historical.universe=="topix")&
                        (historical.strategy=="L")&(historical.bps==20)&(historical.rule=="sign")&
                        (historical["mode"]=="screened")].iloc[0]
    ix=comparison.set_index(["sample","method"])
    rows=[]
    for name in ("fixed","single","top10","neighbor","shrink","dynamic_M_252"):
        wf=ix.loc[("WF",name)]
        ins=ix.loc[("IS",name),"sharpe"] if ("IS",name) in ix.index else np.nan
        rows.append((name,f"{ins:.2f}" if np.isfinite(ins) else "—",f"{wf.sharpe:.2f}",pct(wf.annual),
                     pct(wf.max_dd),f"{wf.effective:.1f}",wf.fills,pct(wf.utilization)))
    overview=table(rows,["方式","IS Sharpe","WF Sharpe","WF年率","WF最大DD","実効数","WF約定","WF稼働"])
    anchors=pd.read_parquet(output/"fixed_baselines.parquet")
    fixed_wf = ix.loc[("WF","fixed"),"sharpe"]
    single_wf = ix.loc[("WF","single"),"sharpe"]
    top_wf = ix.loc[("WF","top10"),"sharpe"]
    dynamic_wf = ix.loc[("WF","dynamic_M_252"),"sharpe"]
    save(reports/"phase6_findings.md",["# PEAD01 Phase 6","",
         f"旧固定20日ロングのSharpeは{base.sharpe:.2f}。"
         f"候補{len(specs):,}件の一次スクリーニング最高は{scores.sharpe.iloc[ranked[0]]:.2f}。"
         f"上位20件の制約付き再評価の最高は{exact.sharpe.iloc[0]:.2f}。","",overview,"",
         "## 固定条件の再計算","",
         table([(r.method,r.hold,r.fills,r.days,f"{r.sharpe:.2f}",pct(r.annual),pct(r.max_dd))
                for r in anchors.itertuples()],["入口","保有","約定","営業日","Sharpe","年率","最大DD"]),"",
         f"固定に対するWF Sharpe差は単独 {single_wf-fixed_wf:+.2f}、Top-10 {top_wf-fixed_wf:+.2f}、"
         f"月次252日動的 {dynamic_wf-fixed_wf:+.2f}。","",
         "すべて2026年11月13日以前の観測済み期間。独立OOS成績は欠損。"
         "候補数による選択バイアスと、実際の約定・費用の不確実性を含む。"])
    top=[]
    for n in (10,100,1000):
        s=scores.sharpe.iloc[ranked[:n]]
        top.append((n,len(s),f"{s.min():.2f}",f"{s.median():.2f}",f"{s.max():.2f}"))
    family = pd.DataFrame({"family": [c["family"] for c in specs],
                           "sharpe": scores.sharpe.to_numpy()}).iloc[ranked].groupby("family").sharpe.agg(["size","max"])
    save(reports/"phase6_grid_search.md",["# 単独探索","",
         table(top,["上位","件数","下限","中央値","最高"]),"",
         table([(k,int(r["size"]),f"{r['max']:.2f}") for k,r in family.iterrows()],["系列","適格件数","一次最高"]),"",
         "制約付き最高候補", "",str(specs[winner]),"",
         table([(specs[i]["method"],specs[i]["hold"],specs[i]["threshold"],specs[i]["adv"],
                 f"{scores.sharpe.iloc[i]:.2f}",int(scores.fills.iloc[i])) for i in near],
               ["近傍入口","保有","初動","ADV","一次Sharpe","件数"])])
    save(reports/"phase6_ensemble.md",["# アンサンブル","","",overview,"",
         f"一次上位10条件の個別制約付き系列の実効数 {count:.2f}、平均相関 {corr:.2f}。"
         "ポジション・イベントのJaccard重複、損失下位1%の同時損失は dependence.parquet。"])
    wf=comparison.loc[comparison["sample"].eq("WF")]
    save(reports/"phase6_walkforward.md",["# Walk-forward","",
         table([(r.method,r.days,r.fills,f"{r.sharpe:.2f}",pct(r.annual),pct(r.max_dd),pct(r.utilization))
                for r in wf.itertuples()],["方式","評価日","約定","Sharpe","年率","最大DD","稼働率"]),"",
         "固定・単独・アンサンブルは共通評価期間。切替後に新規に入ったポジションだけに新配分を適用する。"
         "既存ポジションは元の条件で決済する。完全な未観測OOSは未実施。"])
    net=streams.loc[streams["sample"].eq("WF")].copy()
    net["year"]=net.date.dt.year
    net["month"]=net.date.dt.strftime("%Y-%m")
    for period in ("year","month"):
        net.groupby(["method",period]).agg(net=("net",lambda x: (1+x).prod()-1),fills=("fills","sum"),
                                            utilization=("utilization","mean")).reset_index().to_parquet(
            output/f"wf_{period}.parquet",index=False)
    save(reports/"phase6_overfitting.md",["# 過剰最適化","",overview,"",
         f"制約付き最高ISと期間逐次選択のSharpe差は {exact.sharpe.iloc[0]-ix.loc[('WF','single'),'sharpe']:.2f}。"
         "候補ごとの順位は学習窓と評価期間で変動する。DSRは未算出。",
         f"5営業日ブロックの共通符号反転による一次候補全体の最大統計量の近似p値は "
         f"{pd.read_parquet(output/'screen_max_stat.parquet').max_stat_p.iloc[0]:.3f}。"
         "ブロックの対称性を仮定し、長期の保有重複を完全には調整できない。"])
    picture=net.loc[net.method.isin(["fixed","single","top10","dynamic_M_252"])].pivot(
        index="date",columns="method",values="net")
    plot(figures/"01_walkforward.png",(1+picture).cumprod()-1,"Walk-forward | cumulative net return","line")
