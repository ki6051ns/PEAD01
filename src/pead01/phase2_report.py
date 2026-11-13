"""Phase 2 descriptive statistics and conditional comparisons."""
import numpy as np
import pandas as pd

from .report import clustered_interval, pct, plot, table

MEASURES = ["raw", "topix", "industry", "matched", "delayed_topix"]
POINTS = ["first_trade", "5", "15", "30", "60", "same_day_close"]


def common_ids(frame, point, value, points):
    valid = frame.loc[frame[point].isin(points) & frame[value].notna()]
    counts = valid.groupby("event_id")[point].nunique()
    return counts.index[counts.eq(len(points))]


def describe(frame, keys, measures):
    ids = ["announcement_date", "security_code"]
    rows = []
    for measure in measures:
        valid = frame.dropna(subset=[measure])
        for group, part in valid.groupby(keys, observed=True, sort=True):
            group = group if isinstance(group, tuple) else (group,)
            v = part[measure]
            lo, hi = clustered_interval(part[ids].assign(post_excess=v))
            rows.append((*group, measure, len(v), part.security_code.nunique(), part.announcement_date.nunique(),
                         v.mean(), v.median(), v.std(), v.gt(0).mean(), *v.quantile([.05, .25, .75, .95]), lo, hi))
    return pd.DataFrame(rows, columns=[*keys, "measure", "n", "securities", "dates", "mean", "median",
                                      "sd", "win", "p05", "p25", "p75", "p95", "lo", "hi"])


def regression(data, include_surprise, sample):
    numeric = ["market_cap", "prior_turnover", "momentum"]
    categories = ["sector", "year", "earnings_type", "announcement_bucket"]
    if include_surprise:
        categories += ["surprise"]
    part = data.dropna(subset=["matched", "initial", "revision", *numeric, *categories]).copy()
    part = part.loc[part.initial.isin(["up", "down"])]
    if part.empty:
        return pd.DataFrame()
    part["initial_down"] = part.initial.eq("down").astype(float)
    part["revision_up"] = part.revision.eq("up").astype(float)
    part["revision_down"] = part.revision.eq("down").astype(float)
    for kind in ["up", "down"]:
        part[f"initial_down_revision_{kind}"] = part.initial_down * part[f"revision_{kind}"]
    terms = ["initial_down", "revision_up", "revision_down",
             "initial_down_revision_up", "initial_down_revision_down"]
    design = part[terms + ["gap"] + numeric].copy()
    design[["market_cap", "prior_turnover"]] = np.log(design[["market_cap", "prior_turnover"]])
    design["constant"] = 1.
    design = design.join(pd.get_dummies(part[categories].astype(str), drop_first=True, dtype=float))
    x = design.to_numpy()
    y = part.matched.to_numpy()
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    residual = y - x @ beta
    bread = np.linalg.pinv(x.T @ x)
    scores = pd.DataFrame(x * residual[:, None])
    dates = part.announcement_date.to_numpy()
    codes = part.security_code.to_numpy()

    def cluster(keys):
        sums = scores.groupby(keys).sum().to_numpy()
        g = len(sums)
        return sums.T @ sums * g / (g - 1) if g > 1 else np.full((x.shape[1], x.shape[1]), np.nan)

    covariance = bread @ (cluster(dates) + cluster(codes) - cluster([dates, codes])) @ bread
    # For a negative initial response the upward-revision effect includes the interaction.
    contrasts = np.eye(len(design.columns))[:len(terms)]
    contrasts = np.vstack([contrasts, contrasts[1] + contrasts[3]])
    variance = np.einsum("ij,jk,ik->i", contrasts, covariance, contrasts)
    se = np.sqrt(np.where(variance >= 0, variance, np.nan))
    estimate = contrasts @ beta
    return pd.DataFrame({"term": terms + ["revision_up_given_initial_down"], "estimate": estimate,
                         "lo": estimate - 1.96 * se, "hi": estimate + 1.96 * se,
                         "n": len(part), "securities": part.security_code.nunique(),
                         "includes_surprise": include_surprise, "sample": sample})


def compact(stats, keys):
    return table([tuple(row[k] for k in keys) + (row["n"], row["securities"], pct(row["mean"]),
                  pct(row["median"]), f'{pct(row["lo"])} ～ {pct(row["hi"])}')
                  for row in stats.to_dict("records")],
                 [*keys, "件数", "銘柄数", "平均", "中央値", "95%区間"])


def conditional_finding(joint, coeff, paths):
    cells = joint.set_index(["initial", "revision"])["mean"]
    terms = coeff.loc[coeff["sample"].eq("full")].set_index("term")
    comparable = coeff.loc[coeff["sample"].eq("surprise_observed") & ~coeff.includes_surprise].set_index("term")
    detailed = coeff.loc[coeff.includes_surprise].set_index("term")
    delayed = paths.loc[paths.day.eq(5) & paths["sample"].eq("common")
                        & paths.measure.eq("delayed_topix")].set_index("initial")
    def cell(initial, revision):
        return pct(cells.get((initial, revision), np.nan))

    def contrast(model, term):
        row = model.loc[term]
        return f'{pct(row.estimate)}（{pct(row.lo)} ～ {pct(row.hi)}）'

    return [
        f"初動負では上方修正 {cell('down', 'up')}、据え置き {cell('down', 'flat')}、"
        f"下方修正 {cell('down', 'down')}。初動正では順に {cell('up', 'up')}、"
        f"{cell('up', 'flat')}、{cell('up', 'down')}。いずれもDay 5のマッチ後平均。",
        "据え置きに対する上方修正の条件付き差は、初動正で "
        f"{contrast(terms, 'revision_up')}、初動負で {contrast(terms, 'revision_up_given_initial_down')}。"
        "事前会社予想と実績の差が取れる共通集合での初動負の差は、実績差調整前 "
        f"{contrast(comparable, 'revision_up_given_initial_down')}、調整後 "
        f"{contrast(detailed, 'revision_up_given_initial_down')}。括弧内は近似95%区間。",
        f"翌々営業日始値まで待った場合、初動負群のDay 5平均TOPIX超過は {pct(delayed.at['down', 'mean'])}。"
        "始値を観測した後の約定条件を検討する際は、こちらの期間の結果も参照する。",
    ]


def write_reports(events, old, panel, minute, output, reports, figures):
    reports.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    data = panel.merge(events, on="event_id", validate="many_to_one")
    original = old.merge(events[["event_id", "initial", "revision", "announcement_bucket",
                                 "daily_entry_date", "next_open_date"]], on="event_id")
    count = original.groupby(["horizon", "announcement_bucket"]).agg(
        eligible=("event_id", "size"), total=("total_excess", "count"), post=("post_excess", "count"),
        after_gap=("after_gap_excess", "count")).reset_index()
    count.to_parquet(output / "phase1_audit.parquet", index=False)
    paths = []
    for measure in MEASURES:
        horizons = [3, 5, 10, 20] if measure == "delayed_topix" else [1, 3, 5, 10, 20]
        ids = common_ids(data, "day", measure, horizons)
        for scope, subset in [("available", data), ("common", data.loc[data.event_id.isin(ids)])]:
            paths.append(describe(subset, ["day", "initial"], [measure]).assign(sample=scope))
            paths.append(describe(subset.assign(initial="all"), ["day", "initial"], [measure]).assign(sample=scope))
    paths = pd.concat(paths, ignore_index=True)
    paths.to_parquet(output / "paths.parquet", index=False)
    subsets = []
    for dimension in ["initial_q5", "initial_q10", "revision_rate_q", "revision_amount_q", "size",
                      "liquidity", "sector", "year", "earnings_type", "announcement_bucket", "busy", "surprise"]:
        keys = ["day", dimension] if dimension.endswith(("_q", "q5", "q10")) else ["day", "initial", dimension]
        stats = describe(data.dropna(subset=[dimension]), keys, ["topix", "matched"])
        subsets.append(stats.rename(columns={dimension: "bucket"}).assign(
            dimension=dimension, bucket=stats[dimension].astype(str)))
    pd.concat(subsets, ignore_index=True).to_parquet(output / "stratified.parquet", index=False)
    paired = data.dropna(subset=["raw", "topix", "industry", "matched"])
    joint = describe(paired, ["day", "initial", "revision"], MEASURES[:4])
    joint.to_parquet(output / "joint.parquet", index=False)
    comparison = describe(paired, ["day", "initial"], MEASURES[:4])
    revision = describe(paired, ["day", "revision"], MEASURES[:4])
    decomposition = pd.concat([comparison.assign(signal="initial", bucket=comparison.initial).drop(columns="initial"),
                               revision.assign(signal="revision", bucket=revision.revision).drop(columns="revision")])
    decomposition.to_parquet(output / "decomposition.parquet", index=False)
    d5 = data.loc[data.day.eq(5)]
    observable = d5.dropna(subset=["surprise"])
    coeff = pd.concat([regression(d5, False, "full"), regression(observable, False, "surprise_observed"),
                       regression(observable, True, "surprise_observed")], ignore_index=True)
    coeff.to_parquet(output / "conditional_regression.parquet", index=False)
    tails = []
    for name, group in d5.groupby("initial"):
        valid = group.dropna(subset=["matched"]).assign(abs_return=lambda d: d.matched.abs())
        extreme = valid.nlargest(20, "abs_return").copy()
        extreme["contribution_to_mean"] = extreme.matched / len(valid)
        tails.append(extreme[["event_id", "initial", "matched", "contribution_to_mean"]])
    tails = pd.concat(tails)
    tails.to_parquet(output / "outliers.parquet", index=False)
    minute_stats = []
    for scope, points in [("available", POINTS), ("through_60", POINTS[:-1]), ("through_close", POINTS)]:
        ids = common_ids(minute, "horizon", "post", points)
        part = minute if scope == "available" else minute.loc[minute.event_id.isin(ids)]
        minute_stats.append(describe(part, ["timing", "horizon"], ["total", "post"]).assign(sample=scope))
    minute_stats = pd.concat(minute_stats)
    minute_stats.to_parquet(output / "minute_summary.parquet", index=False)
    first = minute.loc[minute.horizon.eq("first_trade")].set_index("event_id").total
    intraday = minute.assign(first_move=minute.event_id.map(first))
    intraday["first_direction"] = np.where(intraday.first_move.lt(0), "down",
        np.where(intraday.first_move.gt(0), "up", None))
    intraday = intraday.loc[intraday.event_id.isin(common_ids(minute, "horizon", "post", POINTS[:-1]))]
    reversal = describe(intraday, ["timing", "first_direction", "horizon"], ["post"])
    reversal.to_parquet(output / "minute_initial_direction.parquet", index=False)
    delays = minute.loc[minute.horizon.eq("first_trade")].groupby("timing").elapsed_minutes.agg(
        n="count", median="median", p95=lambda s: s.quantile(.95)).reset_index()
    delays.to_parquet(output / "minute_delay.parquet", index=False)

    legacy = original.loc[original.horizon.eq("5")]
    audit = []
    for label, pre, post in [
        ("全体", legacy.post_excess, d5.topix),
        ("初動負", legacy.loc[legacy.initial.eq("down"), "after_gap_excess"], d5.loc[d5.initial.eq("down"), "topix"]),
        ("上方修正", legacy.loc[legacy.revision.eq("up"), "post_excess"], d5.loc[d5.revision.eq("up"), "topix"]),
    ]:
        audit.append((label, int(pre.count()), pct(pre.mean()), int(post.count()), pct(post.mean())))
    prior_day5 = legacy.set_index("event_id").target_date
    valid_marks = d5.end_date.notna()
    changed = d5.loc[valid_marks, "event_id"].map(prior_day5).ne(d5.loc[valid_marks, "end_date"]).sum()
    next_open = original.loc[original.horizon.eq("next_open")]
    no_window = original.loc[original.horizon.eq("1") & original.target_date.lt(original.daily_entry_date)]
    flags = original.pivot(index="event_id", columns="horizon", values="post_excess").notna()
    crossing = int((flags["3"] & ~flags["1"]).sum())
    lost = int((flags["1"] & ~flags["3"]).sum())
    topix_common = paths.loc[paths["sample"].eq("common") & paths.measure.eq("topix")]
    matched_common = paths.loc[paths["sample"].eq("common") & paths.measure.eq("matched")]
    joint5 = joint.loc[joint.day.eq(5) & joint.measure.eq("matched")]
    rate = next(s for s in subsets if s.dimension.eq("revision_rate_q").all())
    amount = next(s for s in subsets if s.dimension.eq("revision_amount_q").all())
    q10 = next(s for s in subsets if s.dimension.eq("initial_q10").all())
    strata = pd.concat(subsets, ignore_index=True)
    repro = strata.loc[strata.dimension.isin(["year", "size", "liquidity", "sector", "busy"])
                       & strata.day.eq(5) & strata.measure.eq("matched") & strata.initial.eq("down")]
    breadth = repro.loc[repro.n.ge(100)].groupby("dimension")["mean"].agg(
        groups="count", negative=lambda x: x.lt(0).sum()
    )

    findings = [
        "# PEAD01 Phase 2 結果", "", "## Phase 1監査", "",
        f"翌営業日始値の追加超過は{next_open.post_excess.count():,}件。寄り前発表のみ当日始値が先に到来し、翌営業日始値までの区間を持つ。"
        "総反応は翌営業日始値までを測り、初動にはその超過リターンを使用する。",
        f"Day 1とDay 3はそれぞれ{flags['1'].sum():,}件と{flags['3'].sum():,}件。"
        f"Day 1の終値が起点より先に来る{len(no_window):,}件が構造上欠損。Day 3のみ{crossing:,}件、Day 1のみ{lost:,}件で、"
        "各終点の取引・価格欠損も差に含む。場中発表のDay 1は当日引け、追加の起点は翌営業日始値だった。",
        "引け同分と引け後の最初の対象セッションは翌営業日。寄り前開示は当日始値が旧起点。日足始値はその日の最初の約定で、09:00の約定には限られない。"
        "分足は同一開示分を除いた正の出来高の最初のバー。初動符号は翌始値観測後に判明する。", "",
        f"Phase 2では翌営業日始値に揃え、Day 5の終点日が変わった観測候補は{changed:,}件。Phase 1の結果は保存した。", "",
        table(audit, ["Day 5", "Phase 1件数", "Phase 1平均", "Phase 2件数", "Phase 2平均"]), "",
        "## 仮説AとB", "", "### 初動別の共通サンプル", "",
        compact(topix_common, ["day", "initial"]), "",
        "### マッチ後の共通サンプル", "",
        compact(matched_common, ["day", "initial"]), "",
        "### 初動10分位のDay 5", "",
        compact(q10.loc[q10.day.eq(5) & q10.measure.eq("matched")], ["bucket"]), "",
        "### 負の初動群のDay 5の再現範囲", "",
        table([(k, r.groups, r.negative) for k, r in breadth.iterrows()],
              ["属性", "100件以上の区分数", "マッチ後平均が負の区分数"]), "",
        "### 翌々営業日始値からの感応度", "",
        compact(paths.loc[paths.measure.eq("delayed_topix") & paths["sample"].eq("common")],
                ["day", "initial"]), "",
        "### 初動と予想修正を組み合わせたDay 5", "",
        "同日・同業種・規模・流動性で選んだ対照銘柄との差。", "",
        compact(joint5, ["initial", "revision"]), "",
        *conditional_finding(joint5, coeff, paths), "",
        "### 上方修正率の分位", "",
        compact(rate.loc[rate.day.eq(5) & rate.measure.eq("matched")], ["bucket"]), "",
        "### 上方修正額の分位", "",
        compact(amount.loc[amount.day.eq(5) & amount.measure.eq("matched")], ["bucket"]), "",
        "## 仮説C", "",
        "2026年8〜10月。through_60は最初の約定から60分までが共通の集合、through_closeは当日引けも揃う集合。"
        "総反応は発表前の基準価格を確定できた部分集合。", "",
        table([(r.timing, r.n, f"{r.median:.0f}", f"{r.p95:.0f}") for r in delays.itertuples()],
              ["発表区分", "件数", "初回約定までの中央値（分）", "95%点（分）"]), "",
        compact(minute_stats, ["sample", "timing", "horizon", "measure"]), "",
        "### 最初の約定までの反応方向と60分後", "",
        compact(reversal.loc[reversal.horizon.eq("60")], ["timing", "first_direction"]), "",
        "集計には、当日引けを持てない引け後発表がある。分足は約定足の観測価格で、注文の執行を再現していない。", "",
        "## 結論とPhase 3", "",
        "負の初動後の相対下落は業種・規模・流動性の調整後も残った。共通TOPIXサンプルではDay 1からDay 3に下落が広がり、Day 5以降は平均で縮小した。"
        "Phase 3では、始値を確認した後の価格、空売り規制・借株・費用を入れて残存幅を検証する。",
        "上方修正と正の初動が重なると上昇継続が観測された。修正率の五分位は単調に上昇せず、初動と属性を調整した修正差の区間にはゼロが入る。"
        "上方修正の独立した効果は確定できなかった。初動正かつ下方修正の群は平均と中央値が大きく乖離しており、尾部と同時開示を調べる余地がある。",
        "共通分足では場中・昼休みと引け後で反応の方向が異なる時間軸がある。短期リバーサルを検証するには初動方向別で複数期間の共通集合を作り、ティックと板で約定条件を調べる。",
        "Value、銘柄別借株、日次の厳密な寄り成立時刻、配当込み収益は未調整。初動条件で同じ始値に入る集計は観測上の比較。",
    ]
    (reports / "phase2_findings.md").write_text("\n\n".join(line for line in findings if line), encoding="utf-8")

    coverage = d5.groupby("initial").agg(events=("event_id", "size"), selected=("control", "count"),
                                         returns=("matched", "count")).reset_index()
    coverage["unmatched"] = coverage.events - coverage.selected
    coverage.to_parquet(output / "matching_coverage.parquet", index=False)
    factor = [
        "# Phase 2 ファクター分解", "",
        "## Day 5 の同一サンプル比較", "",
        compact(decomposition.loc[decomposition.day.eq(5)], ["signal", "bucket", "measure"]), "",
        "## マッチングの成立数", "",
        table(coverage.itertuples(index=False, name=None), list(coverage.columns)), "",
        "## Day 5 極端値の寄与", "",
        table([(k, pct(g.contribution_to_mean.sum())) for k, g in tails.groupby("initial")],
              ["初動", "絶対値上位20件の平均への符号付き寄与"]), "",
        "## 初動・修正方向と属性を同時に比較", "",
        "目的変数はマッチ後Day 5。初動正・据え置きを基準とする。Momentumは事前60営業日価格リターン。"
        "区間は銘柄・開示日の2方向クラスタ。同一対照の再利用による依存は残る。Valueは未調整。", "",
        table([(r.sample, r.includes_surprise, r.term, r.n, pct(r.estimate), pct(r.lo), pct(r.hi))
               for r in coeff.itertuples(index=False)], ["集合", "実績差調整", "項", "件数", "係数", "下限", "上限"]), "",
        "規模・業種・流動性・決算期・年・集中日・発表時刻の個別集計は stratified.parquet。", "",
    ]
    (reports / "phase2_factor_decomposition.md").write_text("\n".join(factor), encoding="utf-8")
    plot(figures / "01_common_paths.png", topix_common.pivot(index="day", columns="initial", values="mean"),
         "Common event sample | TOPIX-adjusted returns", "line")
    plot(figures / "02_initial_revision.png", joint5.pivot(index="initial", columns="revision", values="mean"),
         "Day 5 matched return | initial reaction and guidance revision")
    plot(figures / "03_benchmarks.png",
         comparison.loc[comparison.day.eq(5)].pivot(index="initial", columns="measure", values="mean"),
         "Day 5 | same events across benchmarks")
    minute_order = ["first_trade", "5", "15", "30", "60"]
    minute_plot = minute_stats.loc[minute_stats["sample"].eq("through_60") & minute_stats.measure.eq("post")]
    if len(minute_plot):
        plot(figures / "04_intraday.png",
             minute_plot.pivot(index="horizon", columns="timing", values="mean").reindex(minute_order),
             "First trade to 60 minutes | common events", "line")


def rebuild_reports(baseline, output, reports, figures):
    """Re-render the analysis from the saved event-level panels."""
    events, panel, minute = (pd.read_parquet(output / f"{name}.parquet")
                             for name in ["events", "daily_panel", "minute_panel"])
    old = pd.read_parquet(baseline / "daily_returns.parquet")
    write_reports(events, old, panel, minute, output, reports, figures)
