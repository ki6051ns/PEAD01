"""Aggregate Phase 8 comparisons and generate the research summary and figures."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .phase3_portfolio import performance
from .phase6_daily_wf import sharpe
from .phase7 import turnover
from .phase8_wf import conditions, schedules, windows
from .report import table

FOCUS = "neighbor_b10"
FAMILIES = ["single_b10", FOCUS, "shrink_b10", "blank_equal", "blank_shrink", "blank_dynamic"]
LABELS = ["Single", "Neighbor", "Shrink", "Blank Equal", "Blank Shrink", "Blank Dynamic"]
METHODS = {"Close→Open": "終値判定型（終値→始値）", "Close→Close": "終値判定型（終値→終値）",
           "Open→Close": "始値判定型（始値→終値）", "Open→Open": "始値判定型（始値→始値）"}


def period(daily):
    return dict(return_net=(1 + daily.net).prod()-1, sharpe=sharpe(daily.net), fills=int(daily.fills.sum()))


def summarize(daily, journal, selection, market, capital):
    turns = turnover(selection)
    quarters, full, attribution, regime, cumulative = [], [], [], [], []
    market_trend = market.C.pct_change(63).shift(1)
    for mode, frame in daily.groupby("mode", sort=True):
        frame = frame.sort_values("date").copy()
        r = frame.set_index("date").net
        nav = (1+r).cumprod()
        start_nav = nav.shift(fill_value=1)
        quarter = frame.date.dt.to_period("Q")
        q = frame.groupby(quarter).apply(lambda g: pd.Series(period(g)))
        for label, values in q.iterrows():
            quarters.append(dict(mode=mode, quarter=str(label), **values.to_dict()))
        best = q.return_net.idxmax()
        worst = q.return_net.idxmin()
        in_quarter = r.index.to_period("Q")
        q2 = in_quarter == pd.Period("2025Q2", "Q")
        log = journal.loc[journal["mode"].eq(mode)].copy()
        log["yen"] = log.net_capital * capital
        event_net = log.groupby("event").yen.sum()
        positive = event_net[event_net.gt(0)]
        top10 = positive.nlargest(10)
        q2_event = log.loc[log.date.dt.to_period("Q").eq(pd.Period("2025Q2", "Q"))].groupby("event").yen.sum()
        q2_positive = q2_event[q2_event.gt(0)]
        top10_daily = (log.loc[log.event.isin(top10.index)].assign(net=lambda g: g.gross-g.cost)
                       .groupby("date").net.sum().reindex(r.index, fill_value=0))
        full.append(dict(mode=mode, **performance(r), net_yen=(nav.iloc[-1]-1)*capital,
                         cost_yen=float((frame.set_index("date").cost*start_nav).sum()*capital),
                         fills=int(frame.fills.sum()), utilization=frame.utilization.mean(),
                         quarter_win=q.return_net.gt(0).mean(), quarter_sd=q.return_net.std(),
                         best_quarter=str(best), worst_quarter=str(worst), worst_quarter_return=q.loc[worst,"return_net"],
                         worst_quarter_yen=float((r*start_nav).loc[in_quarter==worst].sum()*capital),
                         sharpe_ex_best=sharpe(r.loc[in_quarter != best]), sharpe_ex_2025q2=sharpe(r.loc[~q2]),
                         q2_yen=float((r*start_nav).loc[q2].sum()*capital),
                         q2_top10_positive_share=q2_positive.nlargest(10).sum()/q2_positive.sum() if len(q2_positive) else np.nan,
                         top10_positive_share=top10.sum()/positive.sum() if len(positive) else np.nan,
                         sharpe_ex_top10=sharpe(r-top10_daily),
                         mean_jaccard=turns.loc[turns["mode"].eq(mode), "jaccard"].mean()))
        for dimension in ("method", "hold", "side"):
            for value, group in log.groupby(dimension):
                attribution.append(dict(mode=mode, dimension=dimension, value=METHODS.get(value, value),
                                        fills=int(group.entry.sum()), net_yen=group.yen.sum()))
        trend = market_trend.reindex(r.index)
        for label, sample in (("positive", r.loc[trend.gt(0)]), ("nonpositive", r.loc[trend.le(0)])):
            regime.append(dict(mode=mode, regime=label, **performance(sample),
                               net_yen=float((sample*start_nav.reindex(sample.index)).sum()*capital)))
        cumulative.append(nav.rename("wealth").reset_index().assign(mode=mode))
    return (pd.DataFrame(full), pd.DataFrame(quarters), turns, pd.DataFrame(attribution,
            columns=["mode","dimension","value","fills","net_yen"]), pd.DataFrame(regime), pd.concat(cumulative))


def correlations(diagnostics, minimum):
    rows = []
    if "validation_sharpe" not in diagnostics:
        return pd.DataFrame(columns=["start","blank","n","n_forward","train_validation","validation_forward"])
    for (start, blank), group in diagnostics.groupby(["start", "blank"]):
        g = group.loc[group.validation_fills.ge(minimum)].dropna(subset=["validation_sharpe"])
        forward = g.loc[g.forward_fills.gt(0)]
        def corr(left, right):
            return left.rank().corr(right.rank()) if len(left) >= 3 else np.nan
        rows.append(dict(start=start, blank=blank, n=len(g), n_forward=len(forward),
                         train_validation=corr(g.train_sharpe, g.validation_sharpe),
                         validation_forward=corr(forward.validation_sharpe, forward.forward_return)))
    return pd.DataFrame(rows)


def generate(config, source, target, summary):
    cfg = json.loads(config.read_text(encoding="utf-8-sig"))
    if json.loads((source/"status.json").read_text(encoding="utf-8"))["status"] != "completed":
        raise ValueError("Phase 8 calculations are incomplete")
    original = json.loads((source/"inputs.json").read_text(encoding="utf-8"))
    from .phase8 import digest
    if original.get(config.as_posix()) != digest(config):
        raise ValueError("Report configuration differs from source run")
    target.mkdir(parents=True, exist_ok=True)
    market = pd.read_parquet(source/"market.parquet").set_index("Date")
    dates = market.index
    catalogue = pd.read_parquet(source/"candidates.parquet").assign(
        method_ja=lambda f: f.method.map(METHODS))
    frames = {k: [] for k in ("performance","quarterly","jaccard","attribution","regimes","wealth",
                               "selection","correlations","diagnostics")}
    bounds = []
    for offset, folds in schedules(len(dates), cfg):
        for design, days, rule in conditions(cfg):
            tags = dict(offset=offset, design=design, validation_days=days, rule=rule)
            folder = source/f"{offset}_{design}_{days}_{rule}"
            history, diagnostic, daily, journal = (pd.read_parquet(folder/f"{k}.parquet")
                for k in ("selection","diagnostics","daily","journal"))
            if "validation_sharpe" in diagnostic:
                diagnostic["validation_rank"] = diagnostic.validation_sharpe.where(diagnostic.passed).groupby(
                    [diagnostic.start, diagnostic.blank]).rank(ascending=False)
            result = summarize(daily, journal, history, market, cfg["capital"])
            for key, frame in zip(frames, (*result, history.merge(catalogue, on="id", how="left"),
                                          correlations(diagnostic, cfg["min_validation_fills"]), diagnostic)):
                frames[key].append(frame.assign(**tags))
            rows = []
            for start, end in folds:
                for blank in cfg["blanks"]:
                    tr, va = windows(start, blank, days, design, max(cfg["validation_days"]))
                    rows.append((start, end, blank, tr[1], *(va or (-1, -1))))
            b = pd.DataFrame(rows, columns=["start","end","blank","train_end","val_start","val_end"])
            for name in ("start","end","train_end","val_start","val_end"):
                b[name + "_date"] = [dates[i].date() if 0 <= i < len(dates) else None for i in b[name]]
            bounds.append(b.assign(validation_days=days, offset=offset, design=design, rule=rule))
    data = {key: pd.concat(parts, ignore_index=True) for key, parts in frames.items()}
    data["boundaries"] = pd.concat(bounds, ignore_index=True)
    data["selection_weights"] = data["selection"].loc[data["selection"].weight.gt(0)]
    data["selection_mix"] = pd.concat([
        data["selection_weights"].groupby(["offset","design","validation_days","rule","mode","start", column],
            as_index=False).weight.sum().rename(columns={column: "value"}).assign(dimension=column)
        for column in ("method_ja", "direction", "hold")], ignore_index=True)
    for key, frame in data.items():
        frame.to_csv(target/f"{key}.csv", index=False, encoding="utf-8-sig", float_format="%.10g")
    for filename in ("inputs.json", "quality.json", "progress.json"):
        (target/filename).write_bytes((source/filename).read_bytes())
    (target/"config.json").write_bytes(config.read_bytes())
    figures(data, dates, target)
    write_summary(data, dates, source, summary)


def figures(data, dates, target):
    perf = data["performance"].query("offset == 0 and design == 'A'")
    def chart(name, xlabel, ylabel, draw):
        fig, ax = plt.subplots(figsize=(10, 4.5), layout="constrained")
        draw(ax)
        ax.set(xlabel=xlabel, ylabel=ylabel)
        ax.axhline(0, linewidth=.6, color="gray")
        ax.grid(alpha=.2)
        if ax.get_legend_handles_labels()[0]:
            ax.legend(frameon=False, fontsize=8, ncol=2)
        fig.savefig(target/f"{name}.png", dpi=150)
        plt.close(fig)
    def duration(ax):
        for mode, label in zip(FAMILIES, LABELS):
            rows = perf.loc[perf["mode"].eq(mode) & perf.rule.ne("screen")].sort_values("validation_days")
            ax.plot(rows.validation_days, rows.sharpe, marker="o", label=label)
    chart("01_duration", "Validation sessions", "WF Sharpe (rerank/direct)", duration)
    def lines(key, x, y, label):
        def draw(ax):
            rows = data[key].query("offset == 0 and design == 'A' and rule != 'screen' and mode == @FOCUS")
            for days, f in rows.groupby("validation_days"):
                xx = dates.take(f[x].to_numpy(dtype=int)) if x == "start" else f[x]
                ax.plot(xx, f[y], marker="o", label=f"{days} sessions")
            if x == "quarter":
                ax.tick_params(axis="x", rotation=30)
        chart(label, x, y, draw)
    lines("quarterly", "quarter", "return_net", "02_quarterly")
    lines("jaccard", "start", "jaccard", "03_jaccard")
    def scatter(ax):
        rows = data["diagnostics"].query("offset == 0 and design == 'A' and rule == 'rerank' and blank == 10 and passed and forward_fills > 0")
        for days, group in rows.groupby("validation_days"):
            ax.scatter(group.validation_sharpe, group.forward_return, s=8, alpha=.2, label=f"{days} sessions")
    chart("04_predictive", "Validation Sharpe", "Next WF block candidate return", scatter)
    def wealth(ax):
        rows = data["wealth"].query("offset == 0 and design == 'A' and validation_days == 45 and rule == 'rerank'")
        for mode, label in zip(FAMILIES, LABELS):
            f = rows.loc[rows["mode"].eq(mode)]
            ax.plot(f.date, f.wealth-1, label=label)
    chart("05_blank_ensemble", "Date", "Cumulative return (45 sessions)", wealth)


def write_summary(data, dates, source, path):
    q = json.loads((source/"quality.json").read_text(encoding="utf-8"))
    perf = data["performance"]
    base = perf.loc[perf.offset.eq(0)]
    focus = base.loc[base["mode"].eq(FOCUS)]
    primary = focus.loc[focus.design.eq("A")]
    quarter = data["quarterly"].query("offset == 0 and design == 'A' and mode == @FOCUS and rule != 'screen'")
    corr = data["correlations"].query("offset == 0 and blank == 10 and rule == 'rerank'")
    f2 = perf.loc[perf.offset.ne(0) & perf["mode"].eq(FOCUS)]
    start = int(data["boundaries"].start.min())
    def num(x):
        return f"{x:.2f}" if pd.notna(x) else "—"
    def pct(x):
        return f"{x:.2%}" if pd.notna(x) else "—"
    rows = []
    for (design, days, rule), group in base.groupby(["design","validation_days","rule"], sort=False):
        scores = group.set_index("mode").sharpe
        rows.append((design, days, rule, *(num(scores.get(mode, np.nan)) for mode in FAMILIES)))
    summary = [
        "# PEAD01 Phase 8｜内部検証期間とWFの選択安定性", "",
        "拡張学習窓で、内部検証の長さと使い方が採用候補の持続性、四半期損益、利益集中にどう影響するかを調べた。", "",
        "## データと共通期間", "",
        f"J-Quants Standardの日足は **{q['first_session']}〜{q['last_session']}、{q['sessions']:,}営業日**。"
        f"株価{q['daily_rows']:,}行・{q['price_codes']:,}コード、銘柄マスター{q['master_rows']:,}行。"
        f"決算短信は{q['first_event']}〜{q['last_event']}の{q['event_count']:,}件。"
        f"東証普通株等の既存条件を満たした{q['eligible_events']:,}件から、{q['signal_events']:,}イベントに日足シグナルを作成した。", "",
        "取得時点の株価APIが示したStandardの日次提供下限は2016-11-15。"
        "月次一括ファイルの開始月には境界より前の日付も入るが、日次提供下限で切った。"
        "データ元は[J-Quants API](https://jpx-jquants.com/en/spec/quickstart)。", "",
        f"出来高欠損{q['missing_volume']:,}行、出来高ゼロ{q['zero_volume']:,}行、異常OHLC{q['bad_ohlc']:,}行、"
        f"不正・欠損調整係数{q['invalid_factor']:,}行、観測期間内のバー欠損{q['missing_bars_inside_code_span']:,}件。"
        f"末日より前に観測が終わるコードは{q['codes_ending_before_last_session']:,}件。"
        f"旧日足との重複は{q.get('daily_overlap', {}).get('matched', 0):,}行、比較対象列に差がある行は"
        f"{q.get('daily_overlap', {}).get('changed', 0):,}行。"
        f"旧決算開示の一致キー{q.get('financial_overlap', {}).get('matched', 0):,}件のうち、"
        f"比較対象列に差がある開示は{q.get('financial_overlap', {}).get('changed', 0):,}件。"
        f"旧Phase 2イベントとの一致キーは{q.get('phase2_overlap', {}).get('matched', 0):,}件。"
        f"重複日付範囲のPhase 8側のみは{q.get('phase2_overlap', {}).get('new_only', 0):,}件、"
        f"Phase 2側のみは{q.get('phase2_overlap', {}).get('old_only', 0):,}件。"
        f"各アーカイブの端点を揃えた結果、指定範囲から除外された日数は{q.get('trimmed_sessions', 0)}営業日。"
        "診断の内訳は品質JSONに収録した。", "",
        f"全条件の共通WFは **{dates[start].date()}〜{dates[-1].date()}（{len(dates)-start}営業日）**。"
        "基準では63営業日ごとに更新し、感応度では初回更新を21営業日目に置いて以後63日ごとに更新した。"
        "WFの損益は各評価期を通じて一つの資金台帳で再生し、四半期集計は暦四半期を使う。両端に部分四半期を含む。", "",
        "Aは各条件の学習終了を可能な限り後ろに置く。Bは同一更新期・同一ブランクの学習窓を756日条件と揃え、短い内部検証は同じ終了日から遡る。"
        "Aの検証なしは学習→WFに1回、検証ありは学習→検証と検証→WFに各1回、同じ長さのブランクを置く。"
        "Bの検証なし・短期条件には学習終了を揃えるための追加空白が入る。"
        "学習・検証とも、シグナルと入口が窓内にあり、出口が終了境界より厳密に前の取引のみ採点した。"
        "この未確定損益の除外はブランク0日にも適用する。", "",
        "候補は終値判定型・始値判定型の4計測、入口・出口各2種、保有1〜40日、閾値2種、方向3種の864通り。"
        "学習は最低30約定からSharpe上位50候補。rerankは検証8約定と有限Sharpeを満たす候補を再順位付けし、"
        "screenは同じ適格条件を満たした候補の学習順位を維持する。適格候補が尽きた方式は現金となる。"
        "Single、Neighbor、Shrinkおよび均等・Shrink・Dynamicのブランクアンサンブルは日足統一版の選び方・配分を引き継ぐ。"
        "初期資本は1億円、往復費用は20bp、借株料仮定は年1%。", "",
        "## 内部検証期間と選択方式", "",
        "共通WFのSharpe。単一ブランクの3方式はPhase 7の比較で使った10日。全6ブランクの結果は詳細CSVを参照。", "",
        table(rows, ["設計","検証日","選択",*LABELS]), "",
        "## 四半期損益と選択の安定性", "",
        table([(r.validation_days, r.rule, pct(r.annual), pct(r.max_dd), r.fills, pct(r.utilization), f"{r.net_yen:,.0f}",
                pct(r.quarter_win), pct(r.quarter_sd), num(r.sharpe_ex_best), num(r.sharpe_ex_2025q2),
                pct(r.top10_positive_share), pct(r.mean_jaccard)) for r in primary.itertuples()],
              ["A検証日", "選択", "年率", "最大DD", "約定", "稼働", "純損益 円", "四半期勝率",
               "四半期σ", "最良四半期除外Sharpe", "2025Q2除外Sharpe", "上位10イベント比率", "平均Jaccard"]), "",
        table([(str(label), *(pct(g.set_index("validation_days").return_net.get(d, np.nan))
                              for d in sorted(quarter.validation_days.unique()))) for label, g in quarter.groupby("quarter")],
              ["Neighbor・A・暦四半期", *map(str, sorted(quarter.validation_days.unique()))]), "",
        "候補IDのJaccardはウェイトが正の集合で比較し、両更新期が現金のときは欠測。"
        "方式によって採用集合の大きさが異なり、Jaccardの水準にはその影響も含まれる。"
        "予測検証はブランク10日の各更新期でSpearman相関を算出し、適格な観測の中央値を示す。"
        "次期成績は候補単独の近似日次系列で、更新区間内に決済確認できた取引から算出する。"
        "途中建玉を除くため、とくに短い更新区間では長期保有候補を評価できない。", "",
        table([(d, n, len(g), int(g.n.sum()), int(g.n_forward.sum()),
                num(g.train_validation.median()), num(g.validation_forward.median()))
               for (d, n), g in corr.groupby(["design", "validation_days"])],
              ["設計", "検証日", "更新数", "検証適格候補 枠", "次期損益あり 枠", "学習順位×検証順位", "検証順位×次期損益"]), "",
        "## ブランクアンサンブルと経済的寄与", "",
    ]
    first_bounds = data["boundaries"].query("offset == 0 and start == @start and design == 'A'")
    first_days = [(days, int(group.train_end.min()), int(group.train_end.max()))
                  for days, group in first_bounds.groupby("validation_days")]
    index = summary.index("## 内部検証期間と選択方式")
    summary[index:index] = ["初回更新の拡張学習窓。範囲は6ブランクでの最短・最長の営業日数で、未確定損益の除外前の暦上の日数を示す。", "",
                            table(first_days, ["検証営業日","学習最短","学習最長"]), ""]
    for offset, g in perf.groupby("offset"):
        a = g.query("design == 'A' and rule != 'screen'")
        for mode, label in zip(FAMILIES, LABELS):
            part = a.loc[a["mode"].eq(mode)]
            if len(part):
                summary.append(f"- 更新オフセット{offset}日の{label}は、検証期間{len(part)}条件の平均Jaccard "
                               f"{pct(part.mean_jaccard.mean())}、最良四半期除外Sharpe中央値 {num(part.sharpe_ex_best.median())}。")
    baseline = "offset == 0 and design == 'A' and validation_days == 45 and rule == 'rerank' and mode == @FOCUS"
    attr = data["attribution"].query(baseline)
    regimes = data["regimes"].query(baseline)
    q2 = perf.query(baseline)
    summary += ["", "A・45日再ランキング・Neighborの約定純寄与。配分ウェイトは別表に保存し、費用控除後の帰属は実約定から日初NAVで円換算した。"
                "日次約定の相殺と統合後、台帳が採用した注文の保有・計測条件に帰属する。", "",
                table([({"method": "初動方式", "hold": "保有", "side": "売買方向"}[r.dimension],
                        {1: "ロング", -1: "ショート"}.get(r.value, r.value) if r.dimension == "side" else r.value,
                        r.fills, f"{r.net_yen:,.0f}") for r in attr.itertuples()],
                      ["軸","区分","約定","純寄与 円"]), ""]
    if len(q2):
        r = q2.iloc[0]
        method = attr.loc[attr.dimension.eq("method")].nlargest(1, "net_yen")
        if len(method):
            top = method.iloc[0]
            summary += [f"初動方式では{top.value}の純寄与が最大で、{top.net_yen:,.0f}円。"
                        f"2025Q2の純寄与は{r.q2_yen:,.0f}円で、同四半期の正寄与のうち上位10イベントは"
                        f"{pct(r.q2_top10_positive_share)}を占めた。", ""]
    summary += ["前日までのTOPIX直近63営業日騰落率で市場環境を分類した。同じ設定の日次純寄与を集計した。", "",
                table([("上昇" if r.regime == "positive" else "横ばい・下落", r.days, num(r.sharpe), f"{r.net_yen:,.0f}")
                       for r in regimes.itertuples()], ["市場環境","日数","Sharpe","純寄与 円"]), "",
                "## 結論と残課題", ""]
    joined = focus.merge(f2, on=["design","validation_days","rule","mode"], suffixes=("", "_offset"))
    for design, group in joined.groupby("design"):
        control = group.loc[group.rule.eq("direct")]
        legacy = group.loc[group.validation_days.eq(45) & group.rule.eq("rerank")]
        if control.empty:
            continue
        old = control.iloc[0]
        extended = group.loc[group.validation_days.ge(252)]
        both = extended.loc[extended.sharpe_ex_2025q2.gt(old.sharpe_ex_2025q2) &
                            extended.sharpe_ex_2025q2_offset.gt(old.sharpe_ex_2025q2_offset)]
        persistence = both.loc[both.mean_jaccard.gt(old.mean_jaccard) & both.mean_jaccard_offset.gt(old.mean_jaccard_offset)]
        summary += [f"{design}のNeighborで、長期検証{len(extended)}条件中、2025Q2除外Sharpeが検証なしを両更新日程で上回ったのは"
                    f"{len(both)}条件。そのうちJaccardも両日程で改善したのは{len(persistence)}条件。", ""]
        if len(legacy):
            old = legacy.iloc[0]
            reranked = extended.loc[extended.rule.eq("rerank")]
            above = reranked.loc[reranked.sharpe_ex_2025q2.gt(old.sharpe_ex_2025q2) &
                                  reranked.sharpe_ex_2025q2_offset.gt(old.sharpe_ex_2025q2_offset)]
            summary += [f"{design}の長期再ランキング{len(reranked)}条件のうち、2025Q2除外Sharpeが45日再ランキングを"
                        f"両日程で上回ったのは{len(above)}条件。", ""]
    leaders = []
    winners = perf.loc[perf["mode"].isin(FAMILIES) & perf.rule.ne("screen")].dropna(subset=["sharpe"])
    for (d, o), g in winners.groupby(["design", "offset"]):
        top = g.loc[g.groupby("validation_days").sharpe.idxmax()].set_index("validation_days")
        leaders.append((d, o, *(LABELS[FAMILIES.index(top.at[n,"mode"])] if n in top.index else "—"
                               for n in sorted(perf.validation_days.unique()))))
    summary += ["6方式の観測Sharpe首位を検証日数ごとに示す。最終仕様の採用判断は保留する。", "",
                table(leaders, ["設計","更新オフセット",*map(str, sorted(perf.validation_days.unique()))]), ""]
    summary += ["日足板寄せの成立はモデル上の仮定。公式停止、銘柄変更の経済的連結、上場廃止対価、個別借株の履歴は復元できていない。"
                "開示IDと当時の公表時刻を用い、同日競合や後日の再開示で過去シグナルを書き換えない。"
                "配信元の過去版スナップショットが無い期間について、事後訂正の有無を完全には検証できない。", "",
                "Phase 6・7で確認済みの2024〜2026年を含む後方検証であり、条件比較後に得たSharpeには選択バイアスがある。"
                "仕様凍結後の未観測期間で独立評価が必要。", "",
                "[詳細集計と再現手順](../reports/phase8/README.md)", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(summary), encoding="utf-8")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key, default in (("config","phase8.json"), ("source","data/phase8_run"), ("target","reports/phase8"),
                         ("summary","research/phase8_summary.md")):
        p.add_argument(f"--{key}", type=Path, default=Path(default))
    generate(**vars(p.parse_args()))
