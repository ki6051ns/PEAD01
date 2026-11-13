"""Conditional price paths, attribution, and equal-sample prediction comparisons."""
import numpy as np
import pandas as pd

from .phase2_report import common_ids, describe
from .report import pct, plot, table

POINTS = ["wall_5", "wall_15", "wall_30", "wall_60", "wall_120"]
FEATURES = ["OP_revision_amount", "OP_company差", "OP_series差", "EPS_company差",
            "Sales_revision_amount", "OdP_revision_amount"]


def direction(values):
    return np.select([values.gt(0), values.lt(0), values.eq(0)], ["positive", "negative", "flat"], default="unknown")


def models(frame, target, inputs_at_five):
    cols = ["initial_excess", "first5_turnover", "OP_series_surprise", "OP_revision_rate",
            "market_cap", "prior_turnover", "sector", target]
    if not inputs_at_five:
        cols = [c for c in cols if c not in ("initial_excess", "first5_turnover")]
    data = frame.dropna(subset=cols).copy()
    data = data.loc[data.market_cap.gt(0) & data.prior_turnover.gt(0)]
    data["size"] = np.log(data.market_cap)
    data["liquidity"] = np.log(data.prior_turnover)
    data["volume"] = np.log1p(data.first5_turnover if inputs_at_five else data.prior_turnover)
    sector = pd.get_dummies(data.sector, dtype=float, drop_first=True)
    controls = pd.concat([data[["size", "liquidity"]], sector], axis=1)
    rows = []
    for year in sorted(data.announcement_date.dt.year.unique()):
        test = data.announcement_date.dt.year.eq(year)
        cutoff = pd.Timestamp(year=int(year), month=1, day=1) - pd.Timedelta(days=7)
        train = data.announcement_date.lt(cutoff)
        if train.sum() < 100 or not test.any():
            continue
        y = data[target]
        base = np.square(y[test] - y[train].mean()).mean()
        price_fields = ["initial_excess", "volume"] if inputs_at_five else []
        for method, fields in [
            ("information", ["OP_series_surprise", "OP_revision_rate"]),
            ("price" if inputs_at_five else "pre_event_controls", price_fields),
            ("combined", ["OP_series_surprise", "OP_revision_rate", *price_fields]),
        ]:
            if not inputs_at_five and method == "combined":
                continue
            x = pd.concat([data[fields], controls], axis=1)
            lower, upper = x[train].quantile(.01), x[train].quantile(.99)
            # Do not clip rare sector dummy values to zero.
            bounded = fields + ["size", "liquidity"]
            x[bounded] = x[bounded].clip(lower[bounded], upper[bounded], axis=1)
            x["intercept"] = 1.
            estimate = np.linalg.lstsq(x.loc[train].to_numpy(), y[train], rcond=None)[0]
            pred = x.loc[test].to_numpy() @ estimate
            residual = y[test].to_numpy() - pred
            rows.append((year, method, int(train.sum()), int(test.sum()), np.sqrt(np.square(residual).mean()),
                         1 - np.square(residual).mean() / base, np.mean(np.sign(pred) == np.sign(y[test]))))
    return pd.DataFrame(rows, columns=["year", "model", "train", "test", "rmse", "r2_oos", "sign_accuracy"]).assign(
        target="continuation" if inputs_at_five else "initial")


def compact(frame, keys, values=("mean", "median", "lo", "hi")):
    return table([[r[k] for k in keys] + [r["n"], *[pct(r[v]) for v in values]]
                  for r in frame.to_dict("records")], [*keys, "n", *values])


def save(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def summarize(events, features, paths, meta, days, paired, daily, phase2_daily, output, reports, figures):
    reports.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    events = events.merge(features, on="event_id", validate="one_to_one")
    events["timing"] = events.announcement_bucket.replace({"closing_auction": "afternoon"})
    events["year"] = events.announcement_date.dt.year
    events["month"] = events.announcement_date.dt.strftime("%Y-%m")
    minute = paths.merge(events, on="event_id", validate="many_to_one")
    minute["initial"] = direction(minute.initial_excess)
    minute["magnitude"] = pd.cut(minute.initial_excess.abs(), [0, .01, .03, .07, np.inf],
                                 labels=["<1%", "1–3%", "3–7%", ">7%"], include_lowest=True)
    minute["signed"] = np.sign(minute.initial_excess) * minute.additional_excess
    complete = common_ids(minute, "point", "additional_excess", POINTS)
    common = minute.loc[minute.event_id.isin(complete) & minute.point.isin(POINTS)]
    price_stats = pd.concat([
        describe(frame, ["point", dimension], ["additional_excess", "signed"]).assign(
            sample=scope, dimension=dimension).rename(columns={dimension: "bucket"})
        for scope, frame in [("available", minute), ("common", common)]
        for dimension in ["initial", "magnitude", "timing", "busy", "year", "month"]
    ], ignore_index=True)
    price_stats["bucket"] = price_stats.bucket.astype(str)
    price_stats.to_parquet(output / "price_summary.parquet", index=False)
    reversals = common.groupby(["point", "initial"])[["opposite", "half_retrace", "cross_base"]].mean().reset_index()
    reversals.to_parquet(output / "reversal.parquet", index=False)
    metrics = meta.merge(events[["event_id", "timing", "busy"]], on="event_id")
    metrics["initial"] = direction(metrics.initial_excess)
    metrics["peak_elapsed"] = metrics.peak_minute - metrics.first_minute
    metrics["bottom_elapsed"] = metrics.bottom_minute - metrics.first_minute
    path_vars = ["favorable", "adverse", "first_delay_minutes", "peak_elapsed", "bottom_elapsed",
                 "volume_60_share", "turnover_60_share", "longest_missing_trading_minutes"]
    path_sizes = metrics.groupby(["timing", "initial", "busy"])[path_vars].median().reset_index()
    path_sizes.to_parquet(output / "path_group_metrics.parquet", index=False)
    session_bounds = pd.DatetimeIndex(sorted(days))
    covered = events.loc[events.first_session.isin(pd.DatetimeIndex(sorted(days)))]
    coverage = events.groupby("year").agg(events=("event_id", "size"), securities=("security_code", "nunique"))
    coverage["covered_session"] = covered.groupby("year").size()
    coverage["first_trade"] = events.loc[events.event_id.isin(meta.event_id)].groupby("year").size()
    coverage["old_first_trade"] = events.loc[events.event_id.isin(meta.event_id) &
        events.first_session.between("2026-08-01", "2026-10-31")].groupby("year").size()
    coverage = coverage.fillna(0).astype(int).reset_index()
    coverage.to_parquet(output / "coverage.parquet", index=False)
    tax = []
    for f in FEATURES:
        events[f + "_direction"] = direction(events[f])
        counts = events.groupby([f + "_direction", "year"]).event_id.size().rename("n").reset_index()
        tax.append(counts.rename(columns={f+"_direction": "direction"}).assign(feature=f))
    taxonomy = pd.concat(tax)
    events["op_eps_conflict"] = ((events.OP_company差 * events.EPS_company差 < 0)
                                  .where(events.OP_company差.notna() & events.EPS_company差.notna()))
    events["op_revision_actual_conflict"] = ((events.OP_revision_amount * events.OP_series差 < 0)
                                  .where(events.OP_revision_amount.notna() & events.OP_series差.notna()))
    taxonomy.to_parquet(output / "taxonomy.parquet", index=False)
    events[["event_id", "op_eps_conflict", "op_revision_actual_conflict"]].to_parquet(output / "conflicts.parquet", index=False)
    longer = daily.merge(meta[["event_id", "initial_excess"]], on="event_id").merge(
        events[["event_id", *FEATURES]], on="event_id")
    all_daily = phase2_daily.merge(events[["event_id", "gap", "announcement_date", "security_code", *FEATURES]], on="event_id")
    groups = []
    for f in FEATURES:
        for scope, frame, k, v, initial in [
            ("minute_all", minute, "point", "additional_excess", "initial_excess"),
            ("minute_common", common, "point", "additional_excess", "initial_excess"),
            ("following_session", longer, "day", "excess", "initial_excess"),
            ("phase2_all", all_daily, "day", "topix", "gap"),
        ]:
            part = frame.assign(info=direction(frame[f]), initial=direction(frame[initial]))
            sums = describe(part, [k, "info", "initial"], [v]).rename(columns={k: "point"})
            skew = part.groupby([k, "info", "initial"])[v].skew().rename("skew").reset_index().rename(columns={k: "point"})
            groups.append(sums.merge(skew, on=["point", "info", "initial"]).assign(feature=f, sample=scope))
    joint = pd.concat(groups)
    joint["point"] = joint.point.astype(str)
    joint.to_parquet(output / "interaction.parquet", index=False)
    fit = pd.concat([
        models(minute.loc[minute.point.eq("wall_60")].merge(meta[["event_id", "first5_turnover"]], on="event_id"),
               "additional_excess", True),
        models(minute.loc[minute.point.eq("wall_5")], "excess", False),
    ], ignore_index=True)
    fit.to_parquet(output / "forecast_comparison.parquet", index=False)
    paired = paired.assign(difference=paired.actual-paired.reference)
    assert np.allclose(paired.difference, paired.price_effect+paired.signal_effect, equal_nan=True)
    stats = describe(paired.loc[paired.common], ["method"], ["actual", "difference", "price_effect", "signal_effect"])
    all_avg = paired.groupby("method").actual.mean()
    same_avg = paired.loc[paired.common].groupby("method").actual.mean()
    coverage_effect = (all_avg-same_avg).rename("coverage_shift").reset_index()
    legacy = paired.loc[paired.common].groupby("method").phase3_actual.mean()
    legacy_delta = legacy - legacy.get("A", np.nan)
    common_delta = same_avg - same_avg["A"]
    exit_shift = (legacy_delta-common_delta).rename("legacy_exit_relative").reset_index()
    stats.merge(coverage_effect, on="method").merge(exit_shift, on="method").to_parquet(
        output / "attribution_summary.parquet", index=False)
    path = price_stats.loc[price_stats.dimension.eq("initial") & price_stats["sample"].eq("common") &
                           price_stats.measure.eq("signed") & price_stats.bucket.isin(["positive", "negative"])]
    plot(figures / "01_price_path.png", path.pivot(index="point", columns="bucket", values="mean").reindex(POINTS),
         "Momentum after the first five minutes | same event sample", "line")
    plot(figures / "02_entry_attribution.png",
         stats.loc[stats.measure.isin(["price_effect", "signal_effect"])].pivot(index="method", columns="measure", values="mean"),
         "Common exit | entry price and signal attribution")
    grouped = stats.pivot(index="method", columns="measure", values="mean")
    longs = paired.loc[paired.common].copy()
    longs["long_difference"] = longs.long_actual - longs.long_reference
    assert np.allclose(longs.long_difference, longs.long_price_effect + longs.long_selection_effect)
    long_stats = describe(longs, ["method"], ["long_actual", "long_difference", "long_price_effect",
                                             "long_selection_effect"])
    long_stats.to_parquet(output / "long_attribution.parquet", index=False)
    long_summary = long_stats.pivot(index="method", columns="measure", values="mean")
    benchmark = fit.loc[fit.target.eq("continuation")].pivot(index="year", columns="model", values="r2_oos")
    gain_years = int((benchmark["combined"] > benchmark["price"]).sum()) if "combined" in benchmark else 0
    tail = path.loc[path.point.eq("wall_120")].set_index("bucket")
    early = path.loc[path.point.eq("wall_15")].set_index("bucket")
    positives = ", ".join(f"{name} {pct(row['mean'])}" for name, row in tail.iterrows())
    initial_window = ", ".join(f"{name} {pct(row['mean'])}" for name, row in early.iterrows())
    overview = table([(k, pct(r.actual), pct(r.difference), pct(r.price_effect), pct(r.signal_effect),
                       pct(all_avg[k]-same_avg[k]), pct(legacy.get(k, np.nan)),
                       pct(legacy_delta[k]-common_delta[k])) for k, r in grouped.iterrows()],
                     ["方式", "平均", "Aとの差", "価格", "符号", "範囲差", "旧決済の平均", "旧決済による対A差"])
    save(reports / "phase4_findings.md", [
        "# PEAD01 Phase 4 結果", "",
        f"分足の最初の約定がある{len(meta):,}件。従来の2026年8〜10月は{coverage.old_first_trade.sum():,}件。"
        f"5〜120分まで市場代理調整値が揃う共通集合は{len(complete):,}件。", "",
        f"分足の収録日は {session_bounds.min():%Y-%m-%d}〜{session_bounds.max():%Y-%m-%d} の"
        f"{len(session_bounds):,}営業日。日次の財務・価格パネルより対象期間が短い。", "",
        "## 初動後の方向付きリターン", "", compact(path, ["point", "bucket"]), "",
        f"初動5分から15分への方向付き平均は {initial_window}。120分時点は {positives}。"
        "正なら初動と同方向、負なら反対方向への平均変化。", "",
        f"60分予測で情報を価格モデルに追加したとき、OOS R²が改善した年は{gain_years}/{len(benchmark)}。"
        "各年の誤差と符号精度は相互作用レポートに記載した。", "",
        "## Phase 3の早期エントリー分解", "",
        f"Phase 3の4方式共通候補は{paired.loc[paired.phase3_common, 'event_id'].nunique()}件。"
        f"統一決済日で価格が揃う比較は{paired.loc[paired.common, 'event_id'].nunique()}件。"
        "比較の決済はAの建日を含む5営業日目の同一終値。範囲差は各方式の利用可能標本平均から共通標本平均を引いた値。", "",
        overview, "",
        "### ロングのみの分解", "",
        "各方式で初動が正ならロング、負なら現金。現金を0として共通イベント全体で平均する。", "",
        table([(k, pct(r.long_actual), pct(r.long_difference), pct(r.long_price_effect),
                pct(r.long_selection_effect)) for k, r in long_summary.iterrows()],
              ["方式", "平均", "Aとの差", "価格寄与", "選別寄与"]), "",
        "価格効果はシグナルを固定する反実仮想を含む。Aのシグナルが早期価格の後に判明する行は台帳に明示している。"
        "当該反実仮想を執行成績に使わない。Phase 3の公表値は方式別の決済日を含んでいた。", "",
        "## Phase 5の検証対象", "",
        "初動の極端度と時価総額・流動性を揃え、前場と引け後で反転確率が変わるかを検証する。"
        "決算情報の方向が互いに衝突する場合の反応は、業種と発表時刻を揃えて比較する。"
        "早期価格の改善は、同じ決済時刻と実際の約定数量が確認できるサンプルで再検証する。", "",
        "[分足](phase4_intraday_price_discovery.md) · [決算分類](phase4_event_taxonomy.md) · [情報と価格の相互作用](phase4_signal_interaction.md)",
    ])
    save(reports / "phase4_intraday_price_discovery.md", [
        "# 分足価格形成", "", table(coverage.itertuples(index=False, name=None), list(coverage)), "",
        "## 共通集合での反転", "",
        table([(r.point,r.initial,pct(r.opposite),pct(r.half_retrace),pct(r.cross_base)) for r in reversals.itertuples()],
              ["時点", "初動", "追加が逆向き", "初動を半分以上打ち消す", "発表前価格を横切る"]), "",
        "立会分は昼休みとプレクロージングを除く。ピーク・ボトム、順行幅・逆行幅、売買代金集中度、無約定継続は事後的な経路統計。"
        "時刻・月・集中日別の数値は price_summary.parquet と path_group_metrics.parquet に保存した。",
    ])
    agg = taxonomy.groupby(["feature", "direction"]).n.sum().unstack(fill_value=0)
    save(reports / "phase4_event_taxonomy.md", [
        "# 決算イベントの情報分類", "",
        table([(k, *r.tolist()) for k,r in agg.iterrows()], ["指標", *agg.columns.tolist()]), "",
        f"営業利益とEPSの会社予想差が逆方向の件数は {int(events.op_eps_conflict.eq(True).sum()):,}。"
        f"営業利益の通期予想修正と前年同期差が逆方向の件数は {int(events.op_revision_actual_conflict.eq(True).sum()):,}。", "",
        "累計実績、前年比、営業利益率、事前予想に対する進捗率、黒字赤字転換、予想修正額・率を保存した。"
        "市場コンセンサス、自己株取得、減損・特別損益、一過性、セグメント、予想取り下げは欠損。"
        "公開TDnetは31日、東証上場会社情報サービスは過去10年の閲覧を提供する。原文による個別分類は0件。"
        "同時刻件数は財務サマリーに含まれる開示に限る。 [JPX TDnet](https://www.jpx.co.jp/equities/listing/disclosure/tdnet/index.html)",
    ])
    subset = joint.loc[joint.feature.eq("OP_revision_amount") & joint["sample"].eq("minute_all") &
                       joint.point.eq("wall_60") & joint.initial.isin(["positive", "negative"])]
    analyses = joint.loc[joint.feature.isin(["OP_company差", "OP_series差", "EPS_company差"]) &
                         joint["sample"].eq("minute_all") & joint.point.eq("wall_60") &
                         joint["info"].isin(["positive", "negative"]) & joint.initial.isin(["positive", "negative"])]
    save(reports / "phase4_signal_interaction.md", [
        "# 決算情報と初動の組み合わせ", "", "## 60分後の追加超過と営業利益予想修正", "",
        compact(subset, ["info", "initial"]), "",
        "## 会社予想差・前年同期間差", "",
        compact(analyses, ["feature", "info", "initial"]), "",
        "## 同じ5分時点・同じ集合で60分までを予測", "",
        table([(r.target,r.year,r.model,r.train,r.test,pct(r.rmse),f"{r.r2_oos:.4f}",pct(r.sign_accuracy)) for r in fit.itertuples()],
              ["予測対象","年","モデル","学習","評価","RMSE","OOS R²","符号正解率"]), "",
        "3モデルは同じ対象と業種・規模・流動性の調整を使用。財務情報モデルはTDnet開示時点で取得できたと仮定した理論比較。"
        "実際のJ-Quants配信時刻は確認できない。continuationは5分から60分、initialは発表前から5分。"
        "initialでは5分時点の価格を説明変数に入れず、事前属性のみのモデルと比較した。",
    ])
