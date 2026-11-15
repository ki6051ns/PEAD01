"""Selection-bias diagnostics from saved unified-daily WF results."""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .report import pct, table


def block_max_test(matrix, block, draws=1999, seed=61):
    n=len(matrix)
    observed=matrix.mean(axis=0)
    centered=matrix-observed
    rng=np.random.default_rng(seed)
    starts=rng.integers(0,n,size=(draws,int(np.ceil(n/block))))
    indices=((starts[:,:,None]+np.arange(block))%n).reshape(draws,-1)[:,:n]
    simulated=np.array([centered[i].mean(axis=0) for i in indices])
    se=simulated.std(axis=0,ddof=1)
    mask=se>0
    if not mask.any():
        return np.full(matrix.shape[1],np.nan)
    null=(simulated[:,mask]/se[mask]).max(axis=1)
    p=np.full(matrix.shape[1],np.nan)
    p[mask]=(1+(null[:,None]>=observed[mask]/se[mask]).sum(axis=0))/(draws+1)
    return p


def main(output,reports):
    wf=pd.read_parquet(output/"wf_base.parquet")
    daily=wf.pivot(index="date",columns="mode",values="net").sort_index()
    if daily.isna().any().any():
        raise ValueError("WF evaluation calendar differs by mode")
    market=pd.read_parquet(output/"market.parquet",columns=["Date"]).Date
    if not daily.index.equals(pd.DatetimeIndex(market[market.ge(daily.index[0])])):
        raise ValueError("WF is missing market sessions")
    if not np.allclose(wf.net, wf.long_gross+wf.short_gross-wf.cost):
        raise ValueError("Directional P&L and costs do not reconcile")
    path_count=0
    for file in sorted(output.glob("paths_*.parquet")):
        trades=pd.read_parquet(file,columns=["start","target","hold","end","closed","release",
                                            "signal_time","order_time","fill_time","label_end"])
        closed=trades.closed
        if not ((trades.hold.between(1,40)).all()
                and (trades.target-trades.start).eq(trades.hold).all()
                and trades.loc[closed,"end"].ge(trades.loc[closed,"target"]).all()
                and (trades.release<trades.signal_time).all()
                and (trades.signal_time<trades.order_time).all()
                and (trades.order_time<trades.fill_time).all()
                and (trades.loc[closed,"fill_time"]<trades.loc[closed,"label_end"]).all()
                and trades.loc[~closed,"label_end"].isna().all()):
            raise ValueError(f"Invalid timing or holding horizon in {file.name}")
        path_count+=len(trades)
    if not path_count:
        raise ValueError("No checked trade paths")
    audits=pd.read_parquet(output/"interval_scores.parquet")
    boundaries=pd.to_datetime(audits.hi.map(market))
    dated=audits.last_label.notna() & boundaries.notna()
    if not audits.loc[dated,"last_label"].lt(boundaries[dated]).all():
        raise ValueError("A fitted label overlaps a later interval")
    selected=pd.read_parquet(output/"selection.parquet")
    allocations=selected.loc[selected.weight.gt(0)].groupby(["start","mode"]).weight.sum()
    if not np.allclose(allocations,1):
        raise ValueError("Sleeve weights differ from unit portfolio capital")
    result=pd.DataFrame({"mode":daily.columns,"mean":daily.mean().to_numpy()})
    for block in (10,40):
        result[f"adjusted_p_{block}"]=block_max_test(daily.to_numpy(),block)
    result.to_parquet(output/"multiplicity.parquet",index=False)
    summary=pd.read_parquet(output/"summary.parquet").query('scenario=="base"').set_index("mode")
    best=summary.sharpe.idxmax()
    all_results=result.set_index("mode")
    families=summary.assign(family=summary.index.str.extract(r"(.+)_w\d+")[0].to_numpy())
    by_family=families.groupby("family").sharpe.agg(["size","median","max"])
    side_by_side=summary.loc[summary.index.str.startswith("neighbor_"),"sharpe"]
    single=summary.loc[side_by_side.index.str.replace("neighbor_","single_",regex=False),"sharpe"]
    paired=(side_by_side.to_numpy()-single.to_numpy())
    paired=paired[np.isfinite(paired)]
    winner=daily[best]
    quarter=winner.index.to_period("Q")
    largest=winner.groupby(quarter).apply(lambda s:(1+s).prod()-1).idxmax()
    without=winner[quarter!=largest]
    reduced_sharpe=without.mean()/without.std(ddof=1)*np.sqrt(252)
    catalogue=pd.read_parquet(output/"candidates.parquet")
    picks=selected.loc[selected["mode"].eq(best)&selected.weight.gt(0)].merge(catalogue,on="id")
    exposures=[]
    for field in ("method","entry","hold","exit_price","direction","threshold"):
        for key,part in picks.groupby(field):
            exposures.append((field,key,pct(part.weight.sum()/picks.weight.sum())))
    text=["# 日足統一版 選択バイアスと期間集中","",
          f"実データの{path_count:,}候補経路で時刻順序、計画保有上限、決済終点を検査した。"
          "学習ラベルの終了境界、配分合計、共通WF営業日、方向別粗損益と費用の日次照合も確認した。","",
          f"同じ{len(daily)}営業日で評価した{len(daily.columns)}方式。"
          "個別の方式について、帰無仮説下の日次平均をゼロに中心化し、各方式に同じ循環移動ブロックを適用した。"
          "全方式の最大標準化平均を帰無分布とし、探索後の多重比較を調整する。独立OOSの代替にはならない。","",
          table([(mode,f"{summary.at[mode,'sharpe']:.2f}",pct(row['mean']),
                   f"{row.adjusted_p_10:.3f}",f"{row.adjusted_p_40:.3f}")
                 for mode,row in all_results.loc[summary.sharpe.nlargest(12).index].iterrows()],
                ["方式","観測WF Sharpe","日次平均","調整p 10日","調整p 40日"]),"",
          "## 方式内の分布と対応比較","",
          table([(name,int(r["size"]),f"{r['median']:.2f}",f"{r['max']:.2f}")
                 for name,r in by_family.iterrows()],
                ["方式系列","設定数","WF Sharpe中央値","最高WF Sharpe"]),"",
          f"学習窓と追加ブランクを揃えた{len(paired)}組のうち、NeighborのSharpeがSingleを上回ったのは"
          f"{int((paired>0).sum())}組、差の中央値は{np.median(paired):+.2f}。","",
          f"最高Sharpe {best} の最良四半期は{largest}。この四半期を除外したSharpeは{reduced_sharpe:.2f}。"
          "これは成績集中を見るための事後診断。四半期損益の全件は[主レポート](phase6_daily_rebuild.md)を参照。"
          "短期・長期ブロックの結果の差は保持期間重複に対する感応度。"
          "パラメータを見直した後の検証には、別途未観測期間が必要。","",
          "## 最高Sharpe方式の採用配分","",
          "採用時の配分を四半期ごとに合計して正規化。建玉や損益の実現寄与は主レポートに記載。","",
          table(exposures,["属性","条件","配分構成比"]),""]
    (reports/"phase6_daily_validation.md").write_text("\n".join(text),encoding="utf-8")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=Path("data/phase6_daily_v2"))
    parser.add_argument("--reports",type=Path,default=Path("reports"))
    main(**vars(parser.parse_args()))
