"""Descriptive statistics, dependence-aware uncertainty and report figures."""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def statistics(sample, dimensions):
    long = sample.melt(id_vars=dimensions, value_vars=["total", "post", "total_excess", "post_excess"],
                       var_name="measure", value_name="return").dropna(subset=["return"])
    grouped = long.groupby(dimensions + ["measure"], observed=True)["return"]
    return grouped.agg(
        n="count", mean="mean", median="median", sd="std", win=lambda s: s.gt(0).mean(),
        p05=lambda s: s.quantile(.05), p25=lambda s: s.quantile(.25),
        p75=lambda s: s.quantile(.75), p95=lambda s: s.quantile(.95),
    ).reset_index()


def clustered_interval(sample):
    """Intercept-only Cameron–Gelbach–Miller two-way cluster variance."""
    sample = sample.dropna(subset=["post_excess"]).copy()
    n = len(sample)
    if n < 2:
        return np.nan, np.nan
    mean = sample.post_excess.mean()
    sample["residual"] = sample.post_excess - mean

    def component(keys):
        totals = sample.groupby(keys).residual.sum()
        g = len(totals)
        return totals.pow(2).sum() / n**2 * g / (g - 1) if g > 1 else np.nan

    date = "announcement_date"
    security = "security_code"
    variance = component(date) + component(security) - component([date, security])
    delta = 1.96 * np.sqrt(variance) if variance >= 0 else np.nan
    return mean - delta, mean + delta


def quintiles(values):
    labels = ["Q1", "Q2", "Q3", "Q4", "Q5"]
    bins = pd.Series(pd.NA, index=values.index, dtype="string")
    for year, series in values.groupby(values.index.year):
        valid = series.dropna()
        if len(valid) >= 5:
            bins.loc[bins.index.year == year] = pd.cut(
                series.rank(pct=True), [0, .2, .4, .6, .8, 1], labels=labels
            ).astype("string").to_numpy()
    return bins.to_numpy()


def table(rows, header):
    return "\n".join(["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * len(header)) + " |"]
                     + ["| " + " | ".join(map(str, row)) + " |" for row in rows])


def pct(number):
    return f"{100 * number:.2f}%" if pd.notna(number) else "—"


def plot(path, values, title, kind="bar"):
    fig, ax = plt.subplots(figsize=(9, 4.5), layout="constrained")
    if not values.dropna(how="all").empty:
        values.mul(100).plot(ax=ax, kind=kind, color=["#146d78", "#da8338", "#354f79", "#895175"],
                             rot=35 if kind == "bar" else 0)
    if kind == "barh":
        ax.axvline(0, color="#555", linewidth=.7)
        ax.set(xlabel="Mean return (%)", ylabel="", title=title)
        ax.invert_yaxis()
    else:
        ax.axhline(0, color="#555", linewidth=.7)
        ax.set(ylabel="Mean return (%)", xlabel="", title=title)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def summarize(events, returns, minute, bad_minutes, output, figures, report):
    figures.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    universe = events.loc[events.universe_status.eq("tse_common")].copy()
    clean = universe.loc[~universe.repeat_period & ~universe.same_day_multiple].copy()
    clean["year"] = clean.announcement_date.dt.year
    clean["size"] = pd.cut(clean.market_cap, [0, 30e9, 100e9, 500e9, 1e12, np.inf],
                           labels=["<30bn", "30–100bn", "100–500bn", "500bn–1tn", "≥1tn"])
    clean["price_band"] = pd.cut(clean.prior_price, [0, 500, 2000, 5000, np.inf],
                                 labels=["<500", "500–2,000", "2,000–5,000", "≥5,000"])
    clean["turnover_band"] = pd.cut(clean.prior_turnover, [0, 1e7, 1e8, 1e9, np.inf],
                                    labels=["<10m", "10–100m", "100m–1bn", "≥1bn"])
    clean["yoy_profit"] = sign(clean.op_yoy)
    clean["revision"] = sign(clean.forecast_revision)
    clean["market_regime"] = sign(clean.prior_market_return)
    clean["busy_date"] = clean.announcement_date.map(universe.groupby("announcement_date").size()).ge(100)
    clean["initial_gap"] = sign(clean.event_id.map(returns.loc[returns.horizon.eq("next_open")].set_index("event_id").total_excess))
    dated = clean.set_index("announcement_date")
    clean["op_surprise_quintile"] = quintiles(dated.company_surprise_op)
    clean["eps_surprise_quintile"] = quintiles(dated.company_surprise_eps)
    sample = returns.merge(clean, on="event_id", validate="many_to_one")
    # Initial gap groups are only meaningful for marks strictly after the gap.
    initial_sample = sample.loc[sample.after_gap.notna()].copy()
    initial_sample[["total", "total_excess"]] = np.nan
    initial_sample["post"] = initial_sample.after_gap
    initial_sample["post_excess"] = initial_sample.after_gap_excess
    groups = ["year", "sector", "size", "price_band", "turnover_band", "earnings_type",
              "announcement_bucket", "busy_date", "market_regime", "initial_gap", "yoy_profit",
              "revision", "op_surprise_quintile", "eps_surprise_quintile"]
    summary = statistics(sample, ["horizon"])
    summary.to_parquet(output / "daily_summary.parquet", index=False)
    grouped = {}
    for group in groups:
        grouped[group] = statistics(initial_sample if group == "initial_gap" else sample, ["horizon", group])
    pd.concat([frame.rename(columns={group: "bucket"}).assign(group=group, bucket=frame[group].astype(str))
               for group, frame in grouped.items()], ignore_index=True).to_parquet(output / "group_summary.parquet", index=False)

    focus = sample[sample.horizon.eq("5")]
    extremes = focus.loc[focus.post_excess.notna()].assign(abs_return=lambda d: d.post_excess.abs())
    extremes = extremes.nlargest(20, "abs_return").copy()
    extremes["contribution_to_mean"] = extremes.post_excess / focus.post_excess.count()
    extremes[["event_id", "security_code", "announcement_date", "post_excess", "contribution_to_mean",
              "entry_limit_flag", "target_limit_flag"]].to_parquet(output / "outliers.parquet", index=False)
    coverage = sample.groupby("horizon")[["total", "post", "total_excess", "post_excess"]].count()
    coverage.to_parquet(output / "coverage.parquet")
    order = ["next_open", "1", "3", "5", "10", "20"]
    path = summary.pivot(index="horizon", columns="measure", values="mean").reindex(order)
    # The next-open post return exists only for the separate pre-open disclosure subset.
    path.loc["next_open", ["post", "post_excess"]] = np.nan
    path = path.rename(index={"next_open": "Next open"}, columns={
        "post": "Post-entry", "post_excess": "Post-entry vs TOPIX",
        "total": "Total reaction", "total_excess": "Total reaction vs TOPIX",
    }).rename_axis(columns=None)
    plot(figures / "01_event_study.png", path,
         "Earnings event study | price and TOPIX-adjusted returns", "line")
    for file, group, title in [
        ("02_surprise", "op_surprise_quintile", "Company guidance surprise | operating profit"),
        ("03_size", "size", "Market capitalization | JPY"),
        ("04_sector", "sector", "TSE sectors | 12 largest by coverage"),
        ("05_timing", "announcement_bucket", "Disclosure timing"),
        ("06_year", "year", "Announcement year"),
    ]:
        data = grouped[group].loc[lambda d: d.horizon.eq("5") & d.measure.eq("post_excess")]
        if group == "sector":
            data = data.nlargest(12, "n")
            data[group] = data[group].map(lambda label: ENGLISH_SECTORS.get(label, label))
        plot(figures / f"{file}.png", data.set_index(group)[["mean"]].rename(columns={"mean": "D5 post, excess"}),
             title, kind="barh" if group == "sector" else "bar")

    minute_clean = minute.merge(clean[["event_id", "announcement_bucket"]], on="event_id") if len(minute) else minute
    minute_summary = pd.DataFrame()
    if len(minute_clean):
        minute_summary = minute_clean.groupby("horizon").agg(n=("post", "count"), total_n=("total", "count"),
                                                               total=("total", "mean"), post=("post", "mean"))
        minute_summary.to_parquet(output / "minute_summary.parquet")
    quality = {
        "statements": len(events), "tse_common": len(universe), "main_sample": len(clean),
        "unmatched_universe": int(events.universe_status.eq("unmatched").sum()),
        "repeat_period": int(universe.repeat_period.sum()),
        "multiple_statements": int(universe.same_day_multiple.sum()),
        "unknown_time": int(clean.announcement_datetime.isna().sum()),
        "daily_bad_ohlc_marks": int(sample.target_bad_ohlc.eq(True).sum()),
        "daily_missing_marks": int(sample.target_missing_bar.sum()),
        "daily_no_trade_marks": int(sample.target_no_trade.sum()),
        "minute_excluded_bars": bad_minutes,
        "abs_post_excess_over_50pct_d5": int(focus.post_excess.abs().gt(.5).sum()),
    }
    (output / "quality.json").write_text(json.dumps(quality, indent=2))
    lines = [
        "# PEAD01 Phase 1 基礎結果", "",
        f"開示日 {events.announcement_date.min():%Y-%m-%d}〜{events.announcement_date.max():%Y-%m-%d}。"
        f"財務諸表開示 {len(events):,} 件、東証普通株 {len(universe):,} 件、基礎集計 {len(clean):,} 件。"
        f"銘柄マスタ未照合 {quality['unmatched_universe']:,} 件。"
        f"同一期間の再開示 {quality['repeat_period']:,} 件と同日複数短信 {quality['multiple_statements']:,} 件は、重複を含めて基礎集計から除外した。", "",
        "## 日次リターン", "",
        "総反応は発表前の日足終値を基準にする。追加反応は発表後に丸ごと観察できる最初の営業日の始値を基準にする。"
        "超過は同じ始終点のTOPIX価格リターンとの差。2方向クラスタ区間は開示日と銘柄を使用した近似95%区間。", "",
    ]
    daily_rows = []
    for horizon in order:
        part = sample[sample.horizon.eq(horizon)]
        lo, hi = clustered_interval(part)
        daily_rows.append((horizon, f"{part.total.count():,}", pct(part.total.mean()),
                           f"{part.post_excess.count():,}", pct(part.post_excess.mean()),
                           pct(part.post_excess.median()), f"{pct(lo)} ～ {pct(hi)}"))
    lines += [table(daily_rows, ["観測点", "総反応 n", "平均総反応", "追加超過 n", "平均追加超過",
                                  "中央値", "クラスタ区間"]), "",
              f"Day 5 追加超過の絶対値50%超は {quality['abs_post_excess_over_50pct_d5']} 件。"
              f"絶対値上位20件の平均への符号付き寄与は {pct(extremes.contribution_to_mean.sum())}。", ""]
    for group, title in [("year", "開示年"), ("size", "時価総額（円）"), ("sector", "業種（観測数上位12）"),
                         ("announcement_bucket", "発表時刻"), ("op_surprise_quintile", "会社予想比の営業利益差")]:
        results = grouped[group].loc[lambda d: d.horizon.eq("5") & d.measure.eq("post_excess")]
        if group == "sector":
            results = results.nlargest(12, "n")
        lines += [f"### {title}の Day 5 追加超過", "",
                  table([(r[group], f"{r.n:,}", pct(r["mean"]), pct(r["median"]))
                         for _, r in results.iterrows()], ["区分", "件数", "平均", "中央値"]), ""]
    lines += ["## 分足", ""]
    if len(minute_clean):
        lines += [f"実測できた最初の取引がある開示は {minute_clean.event_id.nunique():,} 件。"
                  f"対象銘柄・セッションで時刻または価格・出来高の検査から外れたバーは {bad_minutes:,} 本。", "",
                  table([(h, int(r.n), int(r.total_n), pct(r.total), pct(r.post))
                         for h, r in minute_summary.iterrows()], ["観測点", "追加 n", "総反応 n", "平均総反応", "平均追加"]), ""]
    else:
        lines += ["分足の観測値は得られなかった。", ""]
    lines += ["## カバレッジと解釈", "",
              f"集計対象の時刻欠損 {quality['unknown_time']:,} 件、時価総額欠損 {clean.market_cap.isna().sum():,} 件、"
              f"会社予想比の営業利益差の欠損 {clean.company_surprise_op.isna().sum():,} 件。"
              "日次の分位点・標準偏差・勝率・全グループ、分足集計と個別極端値寄与は `data/phase1/` に保存した。", "",
              f"日次観測点の価格バー欠落または出来高不明 {quality['daily_missing_marks']:,}、"
              f"出来高ゼロ {quality['daily_no_trade_marks']:,}、OHLC異常 {quality['daily_bad_ohlc_marks']:,}。"
              "欠落には観測期間末の右打ち切りも含む。", "",
              "分足は取得した月の範囲に限る。市場コンセンサス・銘柄別保有者比率・分足市場調整・配当込み収益は未集計。"
              "OHLCVからは注文の約定確率、板の厚さ、取引停止や特別気配の正確な時刻を復元できない。", "",
              "[初回分析の解釈と次の研究仮説](phase1_findings.md)", ""]
    report.write_text("\n".join(lines), encoding="utf-8")


def sign(values):
    return pd.Series(np.select([values.gt(0), values.lt(0), values.eq(0)], ["up", "down", "flat"],
                               default=None), index=values.index, dtype="string")


ENGLISH_SECTORS = {
    "情報･通信業": "Information & communication", "情報・通信業": "Information & communication",
    "サービス業": "Services", "卸売業": "Wholesale", "その他製品": "Other products",
    "小売業": "Retail", "電気機器": "Electric appliances", "機械": "Machinery", "化学": "Chemicals",
    "建設業": "Construction", "不動産業": "Real estate", "食料品": "Foods", "金属製品": "Metal products",
    "陸運業": "Land transport", "銀行業": "Banks", "輸送用機器": "Transport equipment",
}
