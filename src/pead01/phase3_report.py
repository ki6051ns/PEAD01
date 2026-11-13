"""Out-of-sample comparisons and research artifacts."""
import numpy as np
import pandas as pd

from .phase3_portfolio import performance
from .report import pct, plot, table


def walk_forward(daily):
    base = daily.loc[daily.method.eq("A") & daily.universe.eq("topix") & daily.bps.eq(20)
                     & daily["mode"].eq("screened") & daily.rule.eq("sign") & daily.hold.gt(0)]
    rows = []
    for strategy, group in base.groupby("strategy"):
        matrix = group.pivot(index="date", columns="hold", values="return").sort_index()
        for year in sorted(matrix.index.year.unique()):
            actual = matrix.loc[matrix.index.year == year]
            rows.append(dict(strategy=strategy, year=year, method="fixed", hold=3,
                             **performance(actual[3])))
            prior = matrix.loc[matrix.index.year < year]
            if year < 2024 or len(prior) < 300:
                continue
            validation_start = pd.Timestamp(year=year - 1, month=1, day=1)
            training = prior.loc[prior.index < validation_start].iloc[:-25]
            validation = prior.loc[prior.index >= validation_start].iloc[25:-25]
            for mode in ("expanding", "rolling"):
                train = training.iloc[-504:] if mode == "rolling" else training
                if len(train) < 180 or len(validation) < 100 or len(actual) <= 25:
                    continue
                rank = train.mean().div(train.std()).dropna().sort_values(ascending=False)
                choices = rank.index[:2]
                validation_scores = validation[choices].mean().div(validation[choices].std()).dropna()
                if validation_scores.empty:
                    continue
                selected = validation_scores.idxmax()
                rows.append(dict(strategy=strategy, year=year, method=mode, hold=selected,
                                 **performance(actual[selected].iloc[25:])))
                rows.append(dict(strategy=strategy, year=year, method="fixed_same_days_" + mode, hold=3,
                                 **performance(actual[3].iloc[25:])))
    return pd.DataFrame(rows)


def summary_table(frame, keys):
    headers = [*keys, "約定", "年率", "Sharpe", "最大DD", "日次ES 5%", "日次勝率"]
    rows = []
    for r in frame.to_dict("records"):
        rows.append([r[k] for k in keys] + [r.get("fills", "—"), pct(r["annual"]),
                    f'{r["sharpe"]:.2f}', pct(r["max_dd"]), pct(r["es05"]), pct(r["win"])])
    return table(rows, headers)


def reports(signals, summary, daily, oos, report_dir, figures, common):
    report_dir.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    core = summary.loc[summary.bps.eq(20) & summary["mode"].eq("screened") & summary.rule.eq("sign")]
    base = core.loc[core.method.eq("A") & core.universe.eq("topix") & core.hold.eq(3)]
    by_strategy = base.set_index("strategy")
    comparative = core.loc[core.hold.eq(3) & core.strategy.isin(["L", "S", "LS"])]
    opening = comparative.loc[comparative.method.isin(["A", "C"])]
    intraday = comparative.loc[~comparative.method.isin(["A", "C"]) & comparative.universe.eq("topix")]
    oos_fixed = oos.loc[oos.method.eq("fixed") & oos.year.ge(2024)]
    overview = []
    for strategy in ["L", "S", "LS", "LSbeta"]:
        r = by_strategy.loc[strategy]
        overview.append(f"- {strategy} は約定 {int(r.fills):,} 件、年率 {pct(r.annual)}、最大DD {pct(r.max_dd)}。")
    shortlist = oos_fixed.groupby("strategy").annual.agg(lambda v: int(v.gt(0).sum()))
    universe = signals.drop_duplicates("event_id").groupby("universe", dropna=False).agg(
        events=("event_id", "size"), securities=("security_code", "nunique"),
        median_turnover=("prior_turnover", "median"), lending_proxy=("loanable", "mean"))
    change = opening[opening.method.eq("A") & opening.strategy.eq("LS")].set_index("universe").annual
    shared = common.groupby("method").gross_signed.agg(["size", "mean"]) if len(common) else pd.DataFrame()
    minute_coverage = signals.loc[signals.method.str.startswith(("B", "M"))].groupby(
        ["method", "announcement_bucket"]
    ).event_id.count().rename("events").reset_index()
    long, short, mixed = (by_strategy.loc[name] for name in ["L", "S", "LS"])
    stronger = "ロング" if long.annual > short.annual else "ショート"
    lines = [
        "# PEAD01 Phase 3 結果", "",
        "## 固定ルールの絶対収益", "",
        "A方式、TOPIX分類、3営業日、往復20bp、1億円、前営業日売買代金の1%上限。ショートは貸借区分で絞り、年1%の借株費用を仮定した。", "",
        *overview, "",
        f"この固定設定の年率は{stronger}側が高い。LSの日次ESは {pct(mixed.es05)}、Lは {pct(long.es05)}、Sは {pct(short.es05)}。"
        f"LSの平均保有は {mixed.mean_positions:.1f} 銘柄、日次新規は {mixed.mean_entries:.1f} 件、平均グロスは {pct(mixed.mean_gross)}。",
        f"A方式LSの年率は東証普通株 {pct(change.get('all'))}、TOPIX {pct(change.get('topix'))}、非構成 {pct(change.get('non_topix'))}。", "",
        "負の初動後に観測した相対下落を、翌営業日以降に建てるショートの絶対収益へ転換できなかった。"
        "LSは日次の下方尾部を縮小した一方、累積損失は拡大し、ロング単独より最大DDが深かった。", "",
        "## エントリー比較", "",
        summary_table(opening, ["method", "universe", "strategy"]), "",
        "Bと分足は2026年8〜10月の探索。現物TOPIX分足の代わりに1306 ETFを比較に使用した。下表の短期年率は期間の異なるA/Cと直接比較できない。", "",
        summary_table(intraday, ["method", "strategy"]), "",
        "### 同じイベントでの比較", "",
        "A・C・B1445・M15が全て算出できたTOPIXイベント。各方式の符号で売買した場合のコスト・貸借控除前の銘柄単位損益。",
        table([(method, int(r["size"]), pct(r["mean"])) for method, r in shared.iterrows()],
              ["方式", "共通件数", "平均損益"]), "",
        "## 期間外と次の研究", "",
        "2024年以降の固定ルールで年率が正だった年数は " +
        "、".join(f"{k} {v}/{oos_fixed.year.nunique()}" for k, v in shortlist.items()) + "。",
        "各年はPhase 2で既に観察した期間に含まれる。独立した未観測期間での再検証が必要。",
        "ウォークフォワードの設定選択後も、ショートとロング・ショートに持続的な利益は確認できなかった。"
        "短期の引けロングには検証を続ける余地がある。", "",
        f"Phase 4では年率が高かった{stronger}側を優先し、同じイベントでの注文遅延・執行損失と、利用可能な板・借株履歴で収益の残存を検証する。", "",
        "## ユニバース", "",
        table([(str(k), int(r.events), int(r.securities), f"{r.median_turnover:,.0f}", pct(r.lending_proxy))
               for k, r in universe.iterrows()], ["構成区分", "イベント", "銘柄", "前営業日売買代金中央値 円", "貸借割合"]), "",
    ]
    (report_dir / "phase3_findings.md").write_text("\n".join(lines), encoding="utf-8")
    execution = signals.assign(signal_ok=np.isfinite(signals.initial_excess), fill_ok=signals.entry.gt(0)).groupby("method").agg(
        candidates=("event_id", "size"), signals=("signal_ok", "sum"), prices=("fill_ok", "sum"),
        limit=("limit_day", "sum"), rejected_clock=("clock_rejected", "sum"))
    (report_dir / "phase3_execution.md").write_text("\n".join([
        "# Phase 3 執行", "",
        table(execution.reset_index().itertuples(index=False, name=None),
              ["方式", "候補", "初動算出", "価格あり", "値幅フラグ", "時刻順序不成立"]), "",
        "日足寄り・引けは観測価格。寄り成立時刻、板、注文優先順位、空売り価格規制、逆日歩、現物当日の配当相当額は復元していない。"
        "売買単位・買戻し時の個別貸株料は未反映。",
        "分足はシグナル確定後、次の1分足以降の正の出来高と想定容量を要求した。Bは15:30の約定足を要求した。小口配分、スプレッドとインパクトは仮定。",
        "",
        table(minute_coverage.itertuples(index=False, name=None), ["方式", "発表時刻区分", "件数"]), "",
        "退出が不成立のときは5営業日の範囲で再試行し、未決済は期末まで保有して最後の観測価格で評価した。",
        "貸借区分は取引候補のスクリーニング。理論シナリオも別途保存した。", "",
    ]), encoding="utf-8")
    sensitivity = summary.loc[summary.method.eq("A") & summary.hold.eq(3) & summary.universe.eq("topix")]
    (report_dir / "phase3_portfolio.md").write_text("\n".join([
        "# Phase 3 ポートフォリオ", "", "## 保有期間", "",
        summary_table(core.loc[core.method.eq("A") & core.universe.eq("topix")], ["hold", "strategy"]), "",
        "hold 0 は固定の方向別保有（ロング5日・ショート3日）。", "",
        "## コスト・容量・条件の感応度", "",
        summary_table(sensitivity, ["strategy", "bps", "rule", "mode"]), "",
        "日次損益、グロス・ネット、売買回転、業種集中度は daily.parquet。集計指標は summary.parquet。", "",
        table([(r.strategy, f"{r.mean_positions:.1f}", f"{r.mean_entries:.1f}", pct(r.mean_gross),
                pct(r.mean_net), pct(r.mean_turnover), f"{r.mean_sector_hhi:.3f}", int(r.open_at_end))
               for r in base.itertuples(index=False)],
              ["戦略", "平均保有", "平均新規", "グロス", "ネット", "日次回転", "業種HHI", "未決済"]), "",
    ]), encoding="utf-8")
    (report_dir / "phase3_oos.md").write_text("\n".join([
        "# Phase 3 Walk-forward", "",
        "固定3日と、学習Sharpe上位2候補から直近1年の検証Sharpeで1案を選ぶローリング・拡張方式。"
        "直前25営業日をpurgeし、次区間冒頭25日をembargo。日次系列は各ルールの継続運用で、比較時にポジションを再初期化しない。", "",
        summary_table(oos, ["year", "method", "strategy", "hold"]), "",
        "2026年は11月まで。Phase 2で閲覧済みの期間なので、カレンダー分割を使った擬似OOS。", "",
    ]), encoding="utf-8")
    path = daily.loc[daily.method.eq("A") & daily.hold.eq(3) & daily.universe.eq("topix")
                     & daily.bps.eq(20) & daily.rule.eq("sign") & daily["mode"].eq("screened")]
    plot(figures / "01_equity.png", path.pivot(index="date", columns="strategy", values="nav") - 1,
         "A | TOPIX universe | cumulative net return", "line")
    plot(figures / "02_holding.png",
         core.loc[core.method.eq("A") & core.universe.eq("topix") & core.hold.gt(0)]
         .pivot(index="hold", columns="strategy", values="annual"),
         "A | TOPIX universe | annualized return by holding days")
