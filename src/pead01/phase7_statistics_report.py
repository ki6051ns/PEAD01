"""Render public Phase 7 aggregates from the frozen evaluation panel."""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .phase7 import FOCUS
from .phase7_statistics import adoption_metrics, compute, periodic_metrics
from .report import pct, table


def composition(realized, adopted, modes, catalogue, days):
    output=[]
    for axis, columns in (("method",["method"]),("horizon",["hold"]),("method_horizon",["method","hold"])):
        buckets=catalogue[columns].astype(str).agg("/".join,axis=1).unique()
        values=pd.MultiIndex.from_product([modes,[axis],sorted(buckets)],names=["mode","axis","bucket"]).to_frame(index=False)
        for metrics in (adopted,realized):
            values=values.merge(metrics,on=["mode","axis","bucket"],how="left",validate="one_to_one")
        values=values.fillna(0)
        values["adoption_share"]=values.weight_sessions/days
        output.append(values)
    return pd.concat(output,ignore_index=True)


def family_metrics(full):
    rows=[]
    for family,g in full.groupby("family",sort=True):
        p=g.sharpe.quantile([.1,.5,.9])
        rows.append(dict(family=family,modes=len(g),finite_sharpe=int(g.sharpe.notna().sum()),
                         positive_returns=int(g.cumulative.gt(0).sum()),sharpe_p10=p.loc[.1],
                         sharpe_median=p.loc[.5],sharpe_p90=p.loc[.9],
                         cumulative_median=g.cumulative.median(),drawdown_median=g.max_dd.median(),
                         fills_median=g.fills.median(),utilization_median=g.utilization.median()))
    return pd.DataFrame(rows)


def calendar_distribution(periodic):
    rows=[]
    for (level, period), g in periodic.groupby(["level","period"],sort=True):
        p=g.cumulative.quantile([.1,.5,.9])
        rows.append(dict(level=level,period=period,days=int(g.days.iloc[0]),modes=len(g),
                         positive_modes=int(g.cumulative.gt(0).sum()),p10=p.loc[.1],
                         median=p.loc[.5],p90=p.loc[.9],sharpe_median=g.sharpe.median()))
    return pd.DataFrame(rows)


def write_csv(frame,path):
    frame.to_csv(path,index=False,float_format="%.12g",encoding="utf-8",lineterminator="\n")


def write(path,lines):
    path.write_bytes(("\n".join(lines)+"\n").encode("utf-8"))


def figures(path,composition_table,families,calendar,events):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path.mkdir(parents=True,exist_ok=True)
    fig,axes=plt.subplots(1,2,figsize=(11,4.6),constrained_layout=True)
    for axis,dimension,title in zip(axes,("method","horizon"),("Initial observation method","Holding horizon (days)")):
        g=composition_table.loc[composition_table.axis.eq(dimension)].groupby("bucket").agg(
            adopted=("adoption_share","mean"),capital=("capital_contribution","mean"))
        if dimension=="horizon":
            g=g.sort_index(key=lambda labels:labels.astype(int))
        x=np.arange(len(g))
        axis.bar(x,100*g.adopted,color="#396489",label="Mean day-weighted allocation (%)")
        other=axis.twinx()
        other.plot(x,100*g.capital,marker="o",color="#a34439",label="Mean net contribution (pp)")
        axis.set_xticks(x)
        axis.set_xticklabels(g.index,rotation=25 if dimension=="method" else 0,ha="right" if dimension=="method" else "center")
        axis.set_title(title)
        axis.legend(loc="upper left",fontsize=7)
        other.legend(loc="upper right",fontsize=7)
    fig.savefig(path/"04_method_and_horizon.png",dpi=150)
    plt.close(fig)

    fig,axes=plt.subplots(2,1,figsize=(11,7),constrained_layout=True)
    g=families.sort_values("sharpe_median")
    y=np.arange(len(g))
    axes[0].hlines(y,g.sharpe_p10,g.sharpe_p90,color="#396489")
    axes[0].scatter(g.sharpe_median,y,color="#a34439")
    axes[0].set_yticks(y)
    axes[0].set_yticklabels(g.family)
    axes[0].set(title="Full-WF Sharpe by family (median, P10–P90)",xlabel="Sharpe")
    q=calendar.loc[calendar.level.eq("month")]
    x=np.arange(len(q))
    axes[1].fill_between(x,100*q.p10.to_numpy(),100*q.p90.to_numpy(),color="#a2b7ce")
    axes[1].plot(x,100*q["median"],color="#23466a")
    axes[1].axhline(0,color=".55",linewidth=.7)
    axes[1].set_xticks(x[::3])
    axes[1].set_xticklabels(q.period.iloc[::3],rotation=25)
    axes[1].set(title="Monthly returns across 156 variants (median, P10–P90)",ylabel="Net return (%)")
    fig.savefig(path/"05_ensemble_and_periodic_performance.png",dpi=150)
    plt.close(fig)

    q=events.loc[(events.level=="quarter")&(events.period=="2025Q2")].copy()
    q["family"]=q["mode"].str.rsplit("_w",n=1).str[0]
    families=q.groupby("family").positive_share_top10.agg(
        median="median",p10=lambda x:x.quantile(.1),p90=lambda x:x.quantile(.9)).sort_values("median")
    fig,axis=plt.subplots(figsize=(8.6,4.6),constrained_layout=True)
    y=np.arange(len(families))
    axis.hlines(y,100*families.p10,100*families.p90,color="#396489")
    axis.scatter(100*families["median"],y,color="#a34439")
    axis.set_yticks(y)
    axis.set_yticklabels(families.index)
    axis.set(title="2025 Q2 | Top 10 share of positive event contributions",xlabel="Share (%)")
    fig.savefig(path/"06_q2_event_concentration.png",dpi=150)
    plt.close(fig)


def publish(out,research,plots,source,frozen,market,catalogue,selection,realized,events):
    out.mkdir(parents=True,exist_ok=True)
    tables=out/"tables"
    tables.mkdir(exist_ok=True)
    daily_market=market.C.pct_change()
    periodic=periodic_metrics(frozen,daily_market)
    full=periodic.loc[periodic.level.eq("full")].copy()
    temporal=periodic.loc[periodic.level.ne("full")].copy()
    calendar=calendar_distribution(temporal)
    families=family_metrics(full)
    dates=pd.DatetimeIndex(sorted(frozen.date.unique()))
    comp=composition(realized,adoption_metrics(selection,catalogue),full["mode"],catalogue,len(dates))
    expected=full.set_index("mode").sort_index()
    for _, buckets in comp.groupby("axis"):
        totals=buckets.groupby("mode")[["fills","capital_contribution"]].sum()
        np.testing.assert_allclose(totals.fills,expected.fills,rtol=0,atol=0)
        np.testing.assert_allclose(totals.capital_contribution,expected.cumulative,rtol=0,atol=1e-12)
    focus_daily=frozen.loc[frozen["mode"].eq(FOCUS)]
    without_quarter=focus_daily.loc[focus_daily.date.dt.to_period("Q").ne(pd.Period("2025Q2")),"net"]
    without_sharpe=np.sqrt(252)*without_quarter.mean()/without_quarter.std()
    np.testing.assert_allclose(without_sharpe,.75,rtol=0,atol=.005)
    q2=events.loc[events.level.eq("quarter")&events.period.eq("2025Q2")].set_index("mode")
    median_share=q2.positive_share_top10.median()
    focus=q2.loc[FOCUS]
    full_ex=events.loc[events.level.eq("full")].set_index("mode")
    intervals=temporal.loc[temporal["mode"].eq(FOCUS)].set_index(["level","period"])
    multiplicity=pd.read_parquet(source/"multiplicity.parquet").set_index("mode")
    p=multiplicity.loc[FOCUS]

    for axis,name in (("method","01_method"),("horizon","02_horizon"),("method_horizon","02_method_horizon")):
        write_csv(comp.loc[comp.axis.eq(axis)],tables/f"{name}.csv")
    write_csv(full,tables/"03_ensemble_modes.csv")
    write_csv(families,tables/"03_ensemble_families.csv")
    write_csv(temporal,tables/"04_periodic_wf.csv")
    write_csv(calendar,tables/"04_periodic_distribution.csv")
    write_csv(events,tables/"05_event_concentration.csv")
    figures(plots,comp,families,calendar,events)

    dimension_tables={}
    for axis in ("method","horizon"):
        chosen=comp.loc[comp.axis.eq(axis)]
        g=chosen.groupby("bucket").agg(adopted=("adoption_share","mean"),
            contribution=("capital_contribution","mean"),fills=("fills","sum"))
        if axis=="horizon":
            g=g.sort_index(key=lambda labels:labels.astype(int))
        dimension_tables[axis]=g
    methods,horizons=dimension_tables.values()
    def compact(g):
        return table([(k,pct(r.adopted),int(r.fills),pct(r.contribution)) for k,r in g.iterrows()],
                     ["区分","平均日数加重配分","延べ新規約定","平均純寄与"])

    write(out/"phase7_method_horizon_breakdown.md",[
        "# Phase 7 初動方式と保有期間","",
        "156方式の同一資金台帳を再生。衝突時に台帳が実際に採択した価格経路へ、費用・借株料を含む損益を帰属した。",
        "初動方式は計測区間の両端を示す。保有期間は候補の計画営業日数。実際の決済は繰り越され得る。","",
        "配分は採用ウェイトを評価日数で加重した設定上の割合。約定と純寄与は別集計。",
        "純寄与は各方式のWF初期資本に対する加算可能な寄与。約定は方式間で重複する。共通資金を分割して運用した成績や単独戦略のSharpeとしては使えない。","",
        "## 初動方式","",compact(methods),"","## 保有期間","",compact(horizons),"",
        "全方式で観測されなかった区分もゼロとして平均に含める。日次寄与の分位は全516日を分母とする。","",
        "[初動CSV](tables/01_method.csv) · [保有CSV](tables/02_horizon.csv) · [交差表CSV](tables/02_method_horizon.csv) · [配分と寄与の図](../../figures/phase7/04_method_and_horizon.png)"])

    write(out/"phase7_ensemble_comparison.md",[
        "# Phase 7 アンサンブル方式の比較","",
        "9系列・156設定を共通516営業日で比較した。分位と中央値は設定間の記述統計であり、候補間の依存を含む。",
        "全期間の利益と最大DDは各方式の日次NAVから計算。年率、Sharpe、費用、グロス方向別損益、約定、資金稼働率、市場βは設定別CSVに収録した。","",
        table([(r.family,r.modes,r.positive_returns,f"{r.sharpe_p10:.2f}",f"{r.sharpe_median:.2f}",f"{r.sharpe_p90:.2f}",
                pct(r.cumulative_median),pct(r.drawdown_median)) for r in families.itertuples()],
              ["系列","設定数","累積損益が正","Sharpe P10","中央値","P90","累積中央値","最大DD中央値"]),"",
        f"全方式で累積損益が正だった設定は{int(full.cumulative.gt(0).sum())}/156。Sharpe中央値は{full.sharpe.median():.2f}。",
        "最高方式は評価後に特定した。学習窓・追加ブランクを対応させた比較は既存レポートを参照。","",
        "[156設定CSV](tables/03_ensemble_modes.csv) · [系列CSV](tables/03_ensemble_families.csv) · [比較図](../../figures/phase7/05_ensemble_and_periodic_performance.png) · [対応比較](phase7_parameter_persistence.md)"])

    by_year=calendar.loc[calendar.level.eq("year")]
    write(out/"phase7_monthly_quarterly_yearly.md",[
        "# Phase 7 月次・四半期・年次WF成績","",
        f"共通期間は {dates[0].date()}〜{dates[-1].date()}。156方式すべてに対し、月・四半期・暦年の区間内の日次純収益を複利集計した。",
        "各集計粒度を再複利した終値が日次NAV終値と一致することを各方式で検証した。2024年と2026年には端の部分期間を含む。",
        "短期間のSharpeと年率は252日換算。最大DDは区間初日のNAVを基準に区間内で算出した。","",
        table([(r.period,r.days,r.positive_modes,pct(r.p10),pct(r.median),pct(r.p90)) for r in by_year.itertuples()],
              ["暦年","営業日","プラス方式","累積P10","中央値","P90"]),"",
        "[期間×方式CSV](tables/04_periodic_wf.csv) · [期間別分布CSV](tables/04_periodic_distribution.csv) · [月次分布図](../../figures/phase7/05_ensemble_and_periodic_performance.png) · [開始日・更新日を変えた検証](phase7_wf_window_robustness.md)"])

    write(out/"phase7_event_profit_attribution.md",[
        "# Phase 7 全方式のイベント利益帰属","",
        "各方式の開始時資本を1とし、日初NAVを掛けた費用控除後損益を、同一開示の保有期間を通して合算した。",
        "正寄与の上位比率は正のイベントだけを分母とする。イベント件数・期間別・ロング／ショートの寄与をCSVに収録した。",
        "CSVは方式×期間の集計。イベント識別子・個別取引は含まない。","",
        f"2025Q2の上位10イベント比率は156方式の中央値{pct(median_share)}、{FOCUS}では{pct(focus.positive_share_top10)}。",
        f"同方式の全期間上位10イベント比率は{pct(full_ex.loc[FOCUS,'positive_share_top10'])}。",
        "上位を除く感応度は元の約定を固定して寄与を差し引いた。資金の再配分は実施していない。",
        "特定方式の銘柄・日付・業種別分解は既存の利益集中レポートを参照。","",
        "[全方式・全期間のイベント集計CSV](tables/05_event_concentration.csv) · [2025Q2の方式別分布図](../../figures/phase7/06_q2_event_concentration.png) · [最高方式の既存分解](phase7_profit_concentration.md)"])

    best_method=methods.adopted.idxmax()
    best_horizon=horizons.adopted.idxmax()
    dominant=horizons.contribution.idxmax()
    top_family=families.sort_values("sharpe_median",ascending=False).iloc[0]
    year_results="、".join(f"{r.period}年 {pct(r.median)}" for r in by_year.itertuples())
    write(research/"phase7_summary.md",[
        "# PEAD01 Phase 7 研究総括","",
        "## 1. 研究目的・データ・評価期間","",
        f"Phase 6の日足統一版864候補を用い、{dates[0].date()}〜{dates[-1].date()}の516営業日における156方式を検証した。",
        "採用履歴と価格経路を固定した台帳再生で日次の純損益・費用・約定・資金稼働率等を照合した。",
        "Phase 6は候補構築とWF評価、Phase 7は統計分解と頑健性評価を扱う。独立OOSは未実施。","",
        "## 2. 初動方式別の統計","",
        f"平均日数加重の設定配分が最も大きい初動方式は{best_method}で{pct(methods.loc[best_method,'adopted'])}。",
        "設定配分と実際の約定・損益寄与は指標を分けて集計した。 [初動方式と保有期間の詳細](../reports/phase7/phase7_method_horizon_breakdown.md)","",
        "## 3. 保有期間別の統計","",
        f"設定配分が最も大きい計画保有は{best_horizon}営業日（{pct(horizons.loc[best_horizon,'adopted'])}）。平均純寄与が最大の区分は{dominant}営業日（{pct(horizons.loc[dominant,'contribution'])}）。",
        "各方式内の候補は共通資金を使うため、この寄与から保有期間単独の期待収益は推定できない。 [保有期間の詳細](../reports/phase7/phase7_method_horizon_breakdown.md#保有期間)","",
        "## 4. アンサンブル方式別の統計","",
        f"全156設定のSharpe中央値は{full.sharpe.median():.2f}。系列内中央値が最も高かったのは{top_family.family}の{top_family.sharpe_median:.2f}（{top_family.modes}設定）。",
        "設定数は系列により異なる。 [方式比較](../reports/phase7/phase7_ensemble_comparison.md)","",
        "## 5. 月次・四半期・年次のWF成績","",
        f"方式間の暦年累積中央値は{year_results}。2024年・2026年は観測端の部分年を含む。",
        f"最高方式Neighborの2025Q2は{pct(intervals.loc[('quarter','2025Q2'),'cumulative'])}。各粒度の再複利を日次NAVと照合した。 [期間別成績](../reports/phase7/phase7_monthly_quarterly_yearly.md)","",
        "## 6. 2025Q2の収益集中","",
        f"Neighborの全期Sharpeは{full.set_index('mode').loc[FOCUS,'sharpe']:.2f}、2025Q2を除くと{without_sharpe:.2f}。",
        f"同四半期の正寄与の上位10イベント比率は{pct(focus.positive_share_top10)}で、156方式の中央値は{pct(median_share)}。",
        f"同四半期の上位10イベントの日次寄与を除いた全期Sharpeは{focus.full_sharpe_without_top10:.2f}。 [全方式の帰属](../reports/phase7/phase7_event_profit_attribution.md) · [既存の詳細分解](../reports/phase7/phase7_profit_concentration.md)","",
        "## 7. パラメータ持続性・WF期間感応度","",
        "Neighborの隣接WF更新期のJaccardは平均5.95%。中央寄りの評価窓で、既存選択を現金から再生したSharpeと再選択のSharpeは126日で0.89 → 1.04、252日で3.26 → −0.19、504日で2.08 → −0.14。",
        "再選択により更新日と採用候補が同時に変わる。 [期間感応度](../reports/phase7/phase7_wf_window_robustness.md) · [パラメータ持続性](../reports/phase7/phase7_parameter_persistence.md)","",
        "## 8. 統計的有意性・選択バイアス","",
        f"最高方式の156方式多重比較調整済みp値は10日ブロックで{p.adjusted_p_10:.3f}、40日で{p.adjusted_p_40:.3f}。",
        "最高方式は事後比較。期初採用は学習・内部検証で決定。重複窓と方式は互いに依存する。 [既存の統計検証](../reports/phase7/phase7_parameter_persistence.md)","",
        "## 9. 結論と残課題","",
        "高い観測Sharpeは収益集中と更新日の影響を受ける。初動・保有の帰属は共通資金台帳での記述分解で、各設定の効果を単独で識別していない。",
        "事前に凍結した選択規則の未観測期間評価と、取引容量の確認が残る。","",
        "[Phase 7の方法・実装・再現](../docs/phase7/methodology.md) · [Phase 6日足統一版](phase6_daily_rebuild_summary.md) · [研究全体の索引](README.md)"])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    defaults={"source":"data/phase6_daily_v4","cache":"data/phase7_statistics","config":"phase6_daily.json",
              "out":"reports/phase7","research":"research","plots":"figures/phase7"}
    for name,default in defaults.items():
        parser.add_argument("--"+name,type=Path,default=Path(default))
    args=parser.parse_args()
    publish(args.out,args.research,args.plots,args.source,*compute(args.source,args.cache,args.config))


if __name__=="__main__":
    main()
