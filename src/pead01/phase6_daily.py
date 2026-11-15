"""Independent daily-only Phase 6 rebuild; run with python -m pead01.phase6_daily."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .phase3_portfolio import performance
from .phase6_batch import atomic_json
from .phase6_daily_data import load_inputs, make_signals, paths
from .phase6_daily_wf import evaluate, replay
from .report import pct, table


def save(frame,file):
    tmp=file.with_suffix(".tmp")
    frame.to_parquet(tmp,index=False)
    tmp.replace(file)


def execute(config,output,reports,research,raw,old):
    cfg=json.loads(config.read_text(encoding="utf-8"))
    if not cfg["holds"] or any(not isinstance(h,int) or not 1<=h<=40 for h in cfg["holds"]):
        raise ValueError("Holding horizons must be within 1–40 sessions")
    output.mkdir(parents=True,exist_ok=True)
    inputs=[config,old/"events.parquet",*sorted(Path(__file__).parent.glob("phase6_daily*.py")),
            Path(__file__).with_name("phase6_book.py")]
    inputs.extend(raw/n/f"{k}.json" for n in ("daily","topix","calendar","master") for k in ("manifest","active"))
    signature={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    manifest=output/"inputs.json"
    if manifest.exists() and json.loads(manifest.read_text(encoding="utf-8"))!=signature:
        raise ValueError("Inputs changed. Use a new --output directory.")
    atomic_json(manifest,signature)
    progress=output/"progress.json"
    def checkpoint(stage):
        atomic_json(progress,dict(stage=stage,updated=datetime.now().astimezone().isoformat()))
        if (output/"pause").exists():
            raise KeyboardInterrupt("pause file present")
    files=[output/f"paths_{h}_{x}.parquet" for h in cfg["holds"] for x in ("O","C")]
    if not all(f.exists() for f in [*files,output/"market.parquet",output/"signals.parquet"]):
        checkpoint("inputs")
        events,sessions,bars,index,closes=load_inputs(raw,old,cfg,output)
        signals=make_signals(events,sessions,bars,index,closes)
        assert (signals.release<signals.signal_time).all()
        assert (signals.signal_time<signals.order_time).all() and (signals.order_time<signals.fill_time).all()
        save(index.rename_axis("Date").reset_index(),output/"market.parquet")
        save(signals,output/"signals.parquet")
        for h in cfg["holds"]:
            for x in ("O","C"):
                f=output/f"paths_{h}_{x}.parquet"
                if not f.exists():
                    frame=paths(signals,bars,sessions,closes,h,x).assign(hold=h,exit_price=x)
                    assert (frame.label_end.dropna()>frame.loc[frame.closed,"fill_time"]).all()
                    save(frame,f)
                checkpoint(f.stem)
        del bars
    market=pd.read_parquet(output/"market.parquet").set_index("Date")
    sessions=pd.DatetimeIndex(market.index)
    trades=pd.concat([pd.read_parquet(f) for f in files],ignore_index=True)
    min_start=max(cfg["windows"])+2*max(cfg["blanks"])+cfg["validation_days"]
    groups=pd.Series(np.arange(len(sessions)),index=sessions).groupby(pd.Grouper(freq="Q"))
    folds=[(int(g.iloc[0]),int(g.iloc[-1])+1) for _,g in groups if len(g) and g.iloc[0]>=min_start]
    if not folds:
        raise ValueError("No common WF folds")
    if not (output/"selection.parquet").exists():
        checkpoint("purged selection")
        catalogue,history,_=evaluate(trades,sessions,cfg,folds,output,market)
    else:
        catalogue=pd.read_parquet(output/"candidates.parquet")
        history=pd.read_parquet(output/"selection.parquet")
    first=folds[0][0]
    scenarios={"base":{},"slippage":{"slippage":.001},"cost40":{"cost":40},
               "liquidity":{"capacity_scale":.25},"miss20":{"skip_rate":.20}}
    frames=[]
    for name,kwargs in scenarios.items():
        f=output/f"wf_{name}.parquet"
        if not f.exists():
            checkpoint(name)
            daily=replay(trades,catalogue,history,sessions,cfg,contributions=True,**kwargs)
            save(daily.loc[daily.date.ge(sessions[first])],f)
        frames.append(pd.read_parquet(f).assign(scenario=name))
    wf=pd.concat(frames,ignore_index=True)
    rows=[]
    for (scenario,mode),g in wf.groupby(["scenario","mode"]):
        r=g.net
        beta=r.cov(market.C.pct_change().reindex(g.date).reset_index(drop=True).set_axis(r.index))
        beta/=market.C.pct_change().reindex(g.date).var()
        rows.append(dict(scenario=scenario,mode=mode,**performance(r),fills=int(g.fills.sum()),
                         utilization=g.utilization.mean(),turnover=g.turnover.mean(),
                         cost=g.cost.sum(),beta=beta,long_gross=g.long_gross.sum(),short_gross=g.short_gross.sum()))
    results=pd.DataFrame(rows)
    save(results,output/"summary.parquet")
    quarterly=wf.assign(quarter=wf.date.dt.to_period("Q").astype(str)).groupby(["scenario","mode","quarter"]).agg(
        net=("net",lambda s:(1+s).prod()-1),fills=("fills","sum")).reset_index()
    save(quarterly,output/"quarterly.parquet")
    cover=pd.read_parquet(output/"coverage.parquet")
    signals=pd.read_parquet(output/"signals.parquet")
    audit=pd.read_parquet(output/"interval_scores.parquet")
    write_report(reports,research,sessions,first,results,history,cover,signals,audit,catalogue,trades,quarterly)
    checkpoint("completed")


def write_report(reports,research,sessions,first,results,history,cover,signals,audit,catalogue,trades,quarterly):
    reports.mkdir(parents=True,exist_ok=True)
    research.mkdir(parents=True,exist_ok=True)
    base=results.loc[results.scenario.eq("base")].sort_values("sharpe",ascending=False)
    top=base.iloc[0]
    cash=int(history.id.eq(-1).sum())
    is_scores=audit.loc[audit.lo.eq(0)&audit.hi.eq(len(sessions))].merge(catalogue,on="id")
    best=is_scores.loc[is_scores.fills.ge(30)].nlargest(1,"sharpe")
    bins=history.loc[history.weight.gt(0)].merge(catalogue,on="id",validate="many_to_one")
    def breakdown(k):
        return table([(a,len(g),f"{g.weight.sum():.2f}") for a,g in bins.groupby(k)],
                     [k,"採用枠","配分合計"])
    sensitivity=results.loc[results["mode"].eq(top["mode"])]
    lines=["# Phase 6 日足統一の再構築","",
           f"日足は{sessions[0].date()}〜{sessions[-1].date()}の{len(sessions):,}営業日、{len(cover):,}コード。"
           f"コード観測期間内の日足欠落{int(cover.missing_inside_span.sum()):,}、出来高欠損{int(cover.no_volume.sum()):,}、"
           f"出来高ゼロ{int(cover.nontraded.sum()):,}、調整係数変化行{int(cover.adjustments.sum()):,}。",
           f"WFの共通評価区間は{sessions[first].date()}〜{sessions[-1].date()}。"
           f"候補{len(catalogue)}件。保存した候補・区間の組み合わせのpurge除外合計{int(audit.purged.sum()):,}（重複計上を含む）。"
           f"検証不適格時の現金設定{cash}方式期。","",
           "## シグナルカバレッジ","",
           table([(k,len(g),g.event_id.nunique()) for k,g in signals.groupby("method")],["計測","入口候補","イベント数"]),"",
           f"未決済を期末評価したラベルは{int((~trades.closed).sum()):,}候補経路。売買停止、値幅、欠落、調整連鎖不成立を将来への決済持越しに含める。学習・検証では決済の確認できない経路を除外。","",
           "## 一次スクリーニングIS","",
           table([(r.method,r.entry,r.hold,r.exit_price,r.direction,r.threshold,r.fills,f"{r.sharpe:.2f}")
                  for r in best.itertuples()],["計測","入口","保有","出口","方向","閾値","件数","IS Sharpe"]),"",
           "一次スクリーニングは候補ごとの日次時価評価にグロス上限を適用した近似。WFでは同時ポジションを共通台帳で再計算した。"
           "複数比較後の最高値は記述値。後続WFの選択には用いない。","",
           "## 共通期間のWF","",
           table([(r.mode,f"{r.sharpe:.2f}",pct(r.annual),pct(r.max_dd),r.fills,pct(r.utilization),
                   pct(r.turnover),pct(r.cost),f"{r.beta:.2f}",pct(r.long_gross),pct(r.short_gross))
                  for r in base.itertuples()],["方式","Sharpe","年率","DD","約定","稼働","日次回転","費用累計","β","L粗寄与","S粗寄与"]),"",
           f"観測済みのWF最高は {top['mode']}。その方式の四半期・感応度を以下に示す。"
           "全方式を見た後の比較であり、独立OOSの成績は未算出。","",
           table([(r.quarter,pct(r.net),r.fills) for r in quarterly.loc[quarterly.scenario.eq("base") & quarterly['mode'].eq(top['mode'])].itertuples()],
                 ["四半期","ネット","約定"]),"",
           table([(r.scenario,f"{r.sharpe:.2f}",pct(r.annual),pct(r.max_dd),r.fills) for r in sensitivity.itertuples()],
                 ["感応度","Sharpe","年率","DD","約定"]),"",
           "## 採用パラメータ分解",""]
    for key in ("method","entry","exit_price","hold","window","blank"):
        lines.extend([breakdown(key),""])
    lines.extend(["## 検証上の制約","",
      "寄り・引けの観測価格に注文が成立する保証はない。引け同分の開示では直前終値の順序が確定しない。"
      "取引所の売買停止原票、コード変更の経済的連結、上場廃止対価、個別借株を復元していない。"
      "制度・データ供給の違いを含む旧Phase 6の成績は移植していない。",""])
    (reports/"phase6_daily_rebuild.md").write_text("\n".join(lines),encoding="utf-8")
    (research/"phase6_daily_rebuild_summary.md").write_text(
        "# PEAD01 研究総括 | 日足統一再構築\n\n"
        f"共通WF {sessions[first].date()}〜{sessions[-1].date()}。候補{len(catalogue)}件。"
        f"探索的最高WF Sharpe {top.sharpe:.2f}、年率{pct(top.annual)}、最大DD{pct(top.max_dd)}。"
        "旧成績は別系列。独立OOSは未実施。\n\n[詳細と検証証跡](../reports/phase6_daily_rebuild.md)\n",
        encoding="utf-8")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    defaults={"config":"phase6_daily.json","output":"data/phase6_daily","reports":"reports",
              "research":"research","raw":"data/raw","old":"data/phase2"}
    for name,path in defaults.items():
        p.add_argument("--"+name,type=Path,default=Path(path))
    args=p.parse_args()
    try:
        execute(**vars(args))
    except KeyboardInterrupt:
        atomic_json(args.output/"status.json",{"status":"paused","exit":130})
        raise SystemExit(130)
    except Exception as exc:
        if args.output.exists():
            atomic_json(args.output/"status.json",{"status":"failed","exit":1,"error":str(exc)})
        raise
    atomic_json(args.output/"status.json",{"status":"completed","exit":0})
