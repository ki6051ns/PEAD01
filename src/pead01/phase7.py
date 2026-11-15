"""Robustness diagnostics for the frozen Phase 6 daily study."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .phase3_portfolio import performance
from .phase6_batch import atomic_json
from .phase6_daily import save
from .phase6_daily_wf import evaluate, fold_windows, replay
from .report import pct, table


FOCUS = "neighbor_w252_b10"
COMPARATORS = [FOCUS, "single_w252_b10", "blank_equal_w252", "blank_shrink_w252", "blank_dynamic_w252"]
HORIZONS = (126, 252, 504)


def windows(n, step=5):
    for length in HORIZONS:
        if length>n:
            continue
        for kind, spacing in (("nonoverlap", length), ("rolling", step)):
            positions = range(0, n-length+1, spacing)
            if kind == "rolling":
                positions = sorted(set(positions) | {n-length})
            for start in positions:
                yield kind, length, start


def window_scores(daily):
    frames = []
    for kind, length, start in windows(len(daily)):
        sample = daily.iloc[start:start+length]
        returns = sample.to_numpy()
        wealth = np.cumprod(1+returns,axis=0)
        volatility = returns.std(axis=0,ddof=1)
        sharpe = np.divide(returns.mean(axis=0)*np.sqrt(252),volatility,
                           out=np.full(returns.shape[1],np.nan),where=volatility>0)
        drawdown = (wealth/np.maximum(1.,np.maximum.accumulate(wealth,axis=0))-1).min(axis=0)
        frames.append(pd.DataFrame(dict(kind=kind,length=length,start=sample.index[0],
            end=sample.index[-1],mode=sample.columns,sharpe=sharpe,
            annual=wealth[-1]**(252/length)-1,max_dd=drawdown)))
    return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()


def turnover(selection):
    rows = []
    selected = selection.loc[selection["mode"].ne("audit")]
    for mode, periods in selected.groupby("mode"):
        previous = None
        for start, rows_at_start in periods.groupby("start"):
            current = rows_at_start.loc[rows_at_start.weight.gt(0)].groupby("id").weight.sum()
            if previous is not None:
                a, b = set(previous.index), set(current.index)
                common = len(a & b)
                # Cash gets its own weight, including a fully empty sleeve.
                change = (previous.subtract(current, fill_value=0).abs().sum()
                          + abs(previous.sum()-current.sum()))/2
                rows.append((mode, start, common/len(a) if a else np.nan,
                             common/len(a | b) if a | b else np.nan, change))
            previous = current
    return pd.DataFrame(rows,columns=["mode","start","retained","jaccard","weight_change"])


def stats_text(r):
    return (f"{r['sharpe']:.2f}",pct(r["annual"]),pct(r["max_dd"]))


def linked_journal(log, daily):
    """Start-of-day NAV weights make gross/cost contributions additive in yen."""
    out = log.copy()
    nav = (1+daily).cumprod().shift(fill_value=1.)
    out["net"] = out.gross-out.cost
    out["net_capital"] = out.net*out.date.map(nav)
    return out


def validate_journal(journal, daily):
    realized = (journal.gross-journal.cost).groupby(journal.date).sum()
    np.testing.assert_allclose(realized.reindex(daily.index,fill_value=0),daily,atol=1e-12)


def event_exclusions(journal, daily, quarter):
    ranked = journal.loc[journal.date.isin(quarter)].groupby("event").net_capital.sum().sort_values(ascending=False)
    summaries = []
    for k in (0,1,5,10):
        remove = journal.loc[journal.event.isin(ranked.head(k).index)].groupby("date").net.sum()
        reduced = daily.subtract(remove.reindex(daily.index, fill_value=0))
        summaries.append((k,(1+reduced.loc[quarter]).prod()-1,performance(reduced.loc[quarter]),
                          (1+reduced).prod()-1,performance(reduced)))
    return summaries


def trade_paths(source, catalogue):
    frames = []
    for (hold, exit_price), specs in catalogue.groupby(["hold","exit_price"]):
        paths = pd.read_parquet(source/f"paths_{hold}_{exit_price}.parquet")
        keys = specs[["method","entry"]].drop_duplicates()
        frames.append(paths.merge(keys,on=["method","entry"],sort=False,validate="many_to_one"))
    return pd.concat(frames, ignore_index=True)


def attribution(source, output, catalogue, history, sessions, cfg, daily):
    file = output/"attribution.parquet"
    if file.exists():
        return pd.read_parquet(file)
    active = history.loc[history["mode"].isin(COMPARATORS)]
    specs = catalogue.loc[catalogue.id.isin(active.id)]
    rows = []
    def record(mode):
        def append(order, day, side, gross, cost, entry):
            rows.append((mode,sessions[day],order.code,order.event_id,order.sector,side,gross,cost,entry))
        return append
    result = replay(trade_paths(source,specs),specs,active,sessions,cfg,
                    journals={mode:record(mode) for mode in COMPARATORS})
    reproduced = result.pivot(index="date",columns="mode",values="net").reindex(daily.index)
    np.testing.assert_allclose(reproduced[COMPARATORS],daily[COMPARATORS],atol=1e-12)
    log = pd.DataFrame(rows,columns=["mode","date","code","event","sector","side","gross","cost","entry"])
    frames = []
    for mode, part in log.groupby("mode"):
        validate_journal(part,daily[mode])
        frames.append(linked_journal(part,daily[mode]))
    log = pd.concat(frames,ignore_index=True)
    save(log,file)
    return log


def reselect(source, output, catalogue, history, sessions, cfg, daily):
    file = output/"reselected.parquet"
    if file.exists():
        return pd.read_parquet(file)
    paths = trade_paths(source,catalogue)
    cfg = dict(cfg, windows=[252], blanks=[10])
    first = sessions.get_loc(daily.index[0])
    schedules = {}
    for length in HORIZONS:
        spare=len(daily)-length
        for anchor, offset in (("early",0),("middle",spare//2),("late",spare)):
            start = first+offset
            end = start+length
            folds = [(lo,min(lo+63,end)) for lo in range(start,end,63)]
            if min(fold_windows(lo,252,10,cfg["validation_days"])[0][0] for lo,_ in folds)<0:
                raise ValueError("Shifted schedule requires more training data")
            schedules[length,anchor] = folds
    specs, selection, _ = evaluate(paths,sessions,cfg,
                                   sorted(set(f for folds in schedules.values() for f in folds)),output,None)
    pd.testing.assert_frame_equal(catalogue.reset_index(drop=True),specs.reset_index(drop=True))
    pieces = []
    frozen = history.loc[history["mode"].isin(COMPARATORS[:2])]
    used = set(selection.loc[selection["mode"].isin(COMPARATORS[:2]),"id"]) | set(frozen.id)
    replay_specs = specs.loc[specs.id.isin(used)]
    for (length,anchor), folds in schedules.items():
        belongs = pd.MultiIndex.from_frame(selection[["start","end"]]).isin(folds)
        selected = selection.loc[belongs & selection["mode"].isin(COMPARATORS[:2])]
        lo, hi = folds[0][0],folds[-1][1]
        controls=frozen.loc[frozen.start.lt(hi)&frozen.end.gt(lo)].copy()
        controls["start"]=controls.start.clip(lower=lo)
        controls["end"]=controls.end.clip(upper=hi)
        for policy, choices in (("refit",selected),("frozen_cash_start",controls)):
            result=replay(paths,replay_specs,choices,sessions,cfg)
            pieces.append(result.loc[result.date.ge(sessions[lo])&result.date.le(sessions[hi-1])].assign(
                length=length,anchor=anchor,policy=policy))
    results = pd.concat(pieces,ignore_index=True)
    save(results,file)
    return results


def write_reports(reports,research,output,source,daily,index,journal,scores,refit,changes):
    reports.mkdir(parents=True,exist_ok=True)
    research.mkdir(parents=True,exist_ok=True)
    rows = []
    for (length, kind, mode), sample in scores.loc[scores["mode"].isin(COMPARATORS)].groupby(
            ["length","kind","mode"]):
        x = sample.sharpe
        worst = sample.loc[x.idxmin()] if x.notna().any() else None
        rows.append((length,kind,mode,len(x),*(f"{v:.2f}" for v in x.quantile([.1,.5,.9])),
                     "-" if worst is None else f"{worst.sharpe:.2f} ({worst.start.date()})"))
    rerun = []
    controls=refit.loc[refit.policy.eq("frozen_cash_start")].set_index(["length","anchor","mode","date"]).net.sort_index()
    for (length,anchor,mode), g in refit.loc[refit.policy.eq("refit")].groupby(["length","anchor","mode"]):
        original=daily.loc[g.date,mode]
        cash=controls.loc[length,anchor,mode].reindex(g.date)
        rerun.append((length,anchor,mode,g.date.min().date(),g.date.max().date(),
                      f"{performance(original)['sharpe']:.2f}",f"{performance(cash)['sharpe']:.2f}",
                      *stats_text(performance(g.net))))
    trend=index.C.pct_change(20).shift().reindex(daily.index)
    regimes=[]
    for name, mask in (("上昇",trend.gt(0)),("下落",trend.lt(0)),("横ばい",trend.eq(0))):
        for mode in COMPARATORS:
            grouped=daily.loc[mask,mode]
            if not grouped.empty:
                regimes.append((name,mode,len(grouped),pct(grouped.mean()),
                                pct(grouped.median()),pct(grouped.quantile(.1))))
    (reports/"phase7_wf_window_robustness.md").write_text("\n".join([
        "# Phase 7 WF期間感応度","",
        f"共通基準は{daily.index[0].date()}〜{daily.index[-1].date()}の{len(daily)}営業日。"
        "保存済み日次損益を切り出し、非重複窓は初日から窓幅刻み、ローリング窓は5営業日刻みと最終窓を評価。"
        "境界に持ち越した建玉を含む。重なる評価窓は記述統計として扱う。","",
        table(rows,["営業日","窓","方式","窓数","P10","中央値","P90","最低Sharpeと窓開始日"]),"",
        "## 評価窓の開始を変更して再選択","",
        "各長さで最初・中央・最後に入る窓を定義し、そこから63営業日ごとに864候補を選択し直す。"
        "252日学習、45日内部検証、各境界10日ブランクと実際のラベル終了によるpurgeを使用。"
        "元の採用履歴を用いて現金から始める対照も再生。再選択との差には更新日の違いが含まれる。"
        "対象はSingleとNeighbor。基準損益の切り出しは156方式すべてを保存。","",
        table(rerun,["営業日","位置","方式","開始","終了","切り出しSharpe","既存選択・現金開始Sharpe","再選択Sharpe","年率","DD"]),"",
        "## 市場局面別の日次損益","",
        "前営業日までのTOPIXの20営業日騰落率の符号で区分。個別建玉の割当を変えず、該当営業日の実現損益を集計。","",
        table(regimes,["TOPIX局面","方式","営業日数","日次平均","日次中央値","日次P10"]),"",
        "独立OOSは未実施。",""]),encoding="utf-8")
    quarter=daily.index[daily.index.to_period("Q")==pd.Period("2025Q2")]
    focus=journal.loc[journal["mode"].eq(FOCUS)].copy()
    q=focus.loc[focus.date.isin(quarter)]
    exclusions=event_exclusions(focus,daily[FOCUS],quarter)
    without=daily.loc[~daily.index.isin(quarter),FOCUS]
    without_sharpe=performance(without)["sharpe"]
    if not np.isclose(without_sharpe,.75,atol=.005):
        raise ValueError("Phase 6 quarter exclusion does not reconcile")
    market=index.C.pct_change().reindex(quarter)
    beta=daily.loc[quarter,FOCUS].cov(market)/market.var()
    pieces=[]
    for mode,g in journal.groupby("mode"):
        qq=g.loc[g.date.isin(quarter)]
        positive=qq.groupby("event").net_capital.sum().clip(lower=0)
        overall=g.groupby("event").net_capital.sum().clip(lower=0)
        pieces.append((mode,qq.event.nunique(),pct(positive.nlargest(10).sum()/positive.sum()),
                       pct(overall.nlargest(10).sum()/overall.sum()),*stats_text(performance(daily[mode]))))
    split=[]
    for key, jp in (("code","銘柄"),("event","イベント"),("date","日付"),("sector","業種"),("side","方向")):
        summary=q.groupby(key,dropna=False).agg(net=("net_capital","sum"), events=("event","nunique"))
        save(summary.reset_index(),output/f"q2_by_{key}.parquet")
        ranked=summary.nlargest(10,"net")
        split.extend([f"### {jp}別 純寄与上位","",
                      table([(i if key=="event" else k.date() if key=="date" else k,
                              int(r.events),f"{r.net*1e8:,.0f}")
                             for i,(k,r) in enumerate(ranked.iterrows(),1)],[jp,"イベント数","純寄与（円）"]),""])
    (reports/"phase7_profit_concentration.md").write_text("\n".join([
        "# Phase 7 2025年第2四半期の利益集中","",
        f"対象は{FOCUS}。保存損益と同じ資金台帳を再生し、建玉の日次損益・開始／終了費用・借株料を"
        f"WF開始時の資本1億円と日初NAVで円換算。四半期のTOPIX騰落率{pct((1+market).prod()-1)}、日次β {beta:.2f}。"
        f"四半期を除いたSharpeは{without_sharpe:.2f}。","",
        "利益イベントの上位を四半期内の円建て純寄与で固定し、全期間の日次寄与を差し引いた。"
        "既存約定・資金を固定した帰属診断で、除外後に空いた枠での再配分は含めない。","",
        table([(k,pct(qr),f"{qs['sharpe']:.2f}",pct(total),f"{ts['sharpe']:.2f}")
               for k,qr,qs,total,ts in exclusions],
              ["除外件数","四半期累積","四半期Sharpe","全期累積","全期Sharpe"]),"",
        table(pieces,["方式","Q2イベント数","Q2正寄与の上位10比率","全期正寄与の上位10比率",
                      "全期Sharpe","全期年率","全期DD"]),"",
        *split,"方向は1がロング、−1がショート。イベント欄は公開用の順位。数値は費用控除後。",""]),encoding="utf-8")
    paired=[]
    for blank in (0,5,10,20,40,60):
        a,b=[f"{k}_w252_b{blank}" for k in ("neighbor","single")]
        for name,g in [("全期",daily),*daily.groupby(daily.index.to_period("Q"))]:
            n,s=(performance(g[m])["sharpe"] for m in (a,b))
            paired.append((blank,name,f"{n:.2f}",f"{s:.2f}",f"{n-s:+.2f}"))
    stability=changes.groupby("mode")[["retained","jaccard","weight_change"]].mean()
    multiplicity=pd.read_parquet(source/"multiplicity.parquet").set_index("mode")
    p=multiplicity.loc[FOCUS]
    middle=[r for r in rerun if r[1]=="middle" and r[2]==FOCUS]
    matching=[]
    for length in HORIZONS:
        g=scores.loc[scores.length.eq(length)&scores.kind.eq("rolling")]
        neighbors=g.loc[g["mode"].str.fullmatch("neighbor_w252_b[0-9]+")]
        ranks=neighbors.groupby("start").sharpe.rank(ascending=False,method="min")
        focus_rank=ranks[neighbors["mode"].eq(FOCUS)]
        matching.append((length,len(focus_rank),int(focus_rank.eq(1).sum()),f"{focus_rank.median():.1f}"))
    (reports/"phase7_parameter_persistence.md").write_text("\n".join([
        "# Phase 7 採用パラメータの持続性","",
        "隣接する実際のWF更新期を比較。同じ候補IDの重複採用は合算。継続率は前期IDを分母とし、Jaccardは和集合を分母とする。"
        "配分変化は現金を含むウェイト差の絶対値合計の半分。両期のID集合が空の場合、Jaccardは欠損。","",
        table([(m,*(pct(v) for v in stability.loc[m])) for m in COMPARATORS],
              ["方式","平均継続率","平均Jaccard","平均配分変化"]),"",
        table(matching,["ローリング窓営業日","窓数","252日Neighbor内でb10が首位","b10順位中央値"]),"",
        "252日学習のNeighborとSingleを同じブランク・四半期で比較。","",
        table(paired,["追加ブランク","比較期間","Neighbor Sharpe","Single Sharpe","差"]),"",
        f"156方式の多重比較を補正したPhase 6の最大統計ブロック検定を維持。{FOCUS}の調整pは"
        f"10日 {p.adjusted_p_10:.3f}、40日 {p.adjusted_p_40:.3f}。"
        "ローリング窓の順位は重複を含む記述値。独立OOSは未実施。",""]),encoding="utf-8")
    (research/"phase7_summary.md").write_text("\n".join([
        "# PEAD01 Phase 7 研究総括","",
        f"Phase 6 日足統一版（58343a5）の864候補を再利用。Neighborの全期Sharpeは"
        f"{performance(daily[FOCUS])['sharpe']:.2f}、2025Q2を外すと{without_sharpe:.2f}。"
        f"同四半期の正寄与の上位10イベント比率は{pieces[[r[0] for r in pieces].index(FOCUS)][2]}。"
        f"上位10イベントの日次寄与を除いた全期Sharpeは{exclusions[-1][-1]['sharpe']:.2f}。","",
        "中央寄りのWF窓でのSharpe（既存選択を現金から再生 → 再選択）は"
        +"、".join(f"{r[0]}日 {r[6]} → {r[7]}" for r in middle)+"。","",
        f"多重比較調整後のp値は10日 {p.adjusted_p_10:.3f}、40日 {p.adjusted_p_40:.3f}。"
        "最高方式の指定は事後比較。実際の期初採用は学習・内部検証の情報で決定。独立OOSは未実施。","",
        "- [評価窓の感応度](../reports/phase7_wf_window_robustness.md)",
        "- [2025Q2の利益分解](../reports/phase7_profit_concentration.md)",
        "- [採用パラメータの持続性](../reports/phase7_parameter_persistence.md)",""]),encoding="utf-8")


def figures(path,output,daily,scores,journal):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path.mkdir(parents=True,exist_ok=True)
    fig,axes=plt.subplots(3,1,figsize=(9,8),sharey=True,constrained_layout=True)
    for axis,length in zip(axes,HORIZONS):
        subset=scores.loc[scores.length.eq(length)&scores["mode"].isin(COMPARATORS)]
        for mode,group in subset.loc[subset.kind.eq("rolling")].groupby("mode"):
            axis.plot(group.start,group.sharpe,label=mode)
        dots=subset.loc[subset.kind.eq("nonoverlap")&subset["mode"].eq(FOCUS)]
        axis.scatter(dots.start,dots.sharpe,c="black",s=15,zorder=5)
        axis.axhline(0,linewidth=.7,color=".5")
        axis.set(title=f"{length} sessions | dots: non-overlapping Neighbor",ylabel="Sharpe")
    axes[0].legend(ncol=2,fontsize=7)
    fig.savefig(path/"01_wf_window_sensitivity.png",dpi=150)
    plt.close(fig)

    blanks=(0,5,10,20,40,60)
    lengths=(126,252,504,0)
    surface=np.array([[performance(daily[f"neighbor_w{w}_b{b}"])["sharpe"] for b in blanks] for w in lengths])
    correlation=np.array([[daily[f"{mode}_w{w}_b{a}"].corr(daily[f"{mode}_w{w}_b{b}"])
                           for a,b in zip(blanks,blanks[1:])]
                          for mode in ("neighbor","single") for w in lengths])
    save(pd.DataFrame(correlation,columns=[f"{a}-{b}" for a,b in zip(blanks,blanks[1:])]).assign(
        mode=np.repeat(["neighbor","single"],len(lengths)),window=list(lengths)*2),output/"adjacent_blank_correlation.parquet")
    fig,axes=plt.subplots(1,2,figsize=(10,4.5),constrained_layout=True)
    panels=[(surface,blanks,["126","252","504","Expanding"],"Neighbor WF Sharpe"),
            (correlation,[f"{a}-{b}" for a,b in zip(blanks,blanks[1:])],
             [f"{m} {w or 'exp'}" for m in ("Neighbor","Single") for w in lengths],"Adjacent-blank daily correlation")]
    for axis,(matrix,xlabels,ylabels,title) in zip(axes,panels):
        axis.imshow(matrix,cmap="coolwarm",aspect="auto")
        axis.set_xticks(range(len(xlabels)))
        axis.set_xticklabels(xlabels)
        axis.set_yticks(range(len(ylabels)))
        axis.set_yticklabels(ylabels)
        for (i,j),value in np.ndenumerate(matrix):
            axis.text(j,i,f"{value:.2f}",ha="center",va="center",fontsize=8)
        axis.set(title=title,xlabel="Additional blank (sessions)")
    fig.savefig(path/"02_blank_surface_and_correlation.png",dpi=150)
    plt.close(fig)

    fig,axes=plt.subplots(1,2,figsize=(10,4.2),constrained_layout=True)
    for mode,g in journal.loc[journal.date.dt.to_period("Q").eq(pd.Period("2025Q2"))].groupby("mode"):
        p=g.groupby("event").net_capital.sum().sort_values(ascending=False).clip(lower=0)
        axes[0].plot(np.arange(1,len(p)+1),p.cumsum()/p.sum(),label=mode)
    axes[0].set(xscale="log",ylim=(0,1.03),xlabel="Event rank",ylabel="Cumulative share of positive P&L")
    axes[0].legend(fontsize=7)
    axes[1].barh(COMPARATORS,[100*performance(daily[m])["max_dd"] for m in COMPARATORS])
    axes[1].set(xlabel="Maximum drawdown (%)",title="Common WF calendar")
    fig.savefig(path/"03_profit_concentration_and_drawdown.png",dpi=150)
    plt.close(fig)


def main(source,output,reports,research,plots):
    import hashlib

    output.mkdir(parents=True,exist_ok=True)
    cfg_path=Path("phase6_daily.json")
    cfg=json.loads(cfg_path.read_text(encoding="utf-8"))
    inputs=sorted(source.glob("*.parquet"))+[cfg_path,Path(__file__),
        Path(__file__).with_name("phase6_daily_wf.py"),Path(__file__).with_name("phase6_book.py")]
    manifest={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    manifest_path=output/"inputs.json"
    if manifest_path.exists() and json.loads(manifest_path.read_text(encoding="utf-8"))!=manifest:
        raise ValueError("Phase 7 input/code changed. Use another output directory.")
    if not manifest_path.exists() and any(output.glob("*.parquet")):
        raise ValueError("Existing Phase 7 Parquet files have no input manifest")
    atomic_json(manifest_path,manifest)
    market=pd.read_parquet(source/"market.parquet").set_index("Date")
    daily=pd.read_parquet(source/"wf_base.parquet").pivot(index="date",columns="mode",values="net")
    if daily.shape!=(516,156) or daily.isna().any().any():
        raise ValueError("Expected common 516-session Phase 6 calendar and 156 complete series")
    catalogue=pd.read_parquet(source/"candidates.parquet")
    history=pd.read_parquet(source/"selection.parquet")
    journal=attribution(source,output,catalogue,history,market.index,cfg,daily)
    refit=reselect(source,output,catalogue,history,market.index,cfg,daily)
    scores=window_scores(daily)
    changes=turnover(history)
    save(scores,output/"window_scores.parquet")
    save(changes,output/"parameter_turnover.parquet")
    write_reports(reports,research,output,source,daily,market,journal,scores,refit,changes)
    figures(plots,output,daily,scores,journal)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for name,path in {"source":"data/phase6_daily_v4","output":"data/phase7_v2","reports":"reports",
                      "research":"research","plots":"figures/phase7"}.items():
        parser.add_argument("--"+name,type=Path,default=Path(path))
    main(**vars(parser.parse_args()))
