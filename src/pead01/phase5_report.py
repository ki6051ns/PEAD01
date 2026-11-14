"""Build Phase 5 tables and reports from fixed analysis conditions."""
from math import erfc, sqrt

import numpy as np
import pandas as pd

from .phase2_report import describe
from .phase4_report import direction, save
from .phase5_execution import COSTS, DELAYS, POINTS, portfolio
from .phase5_stats import blocks, fixed_effects, matched_size
from .report import pct, plot, table

DIMENSIONS = ["universe", "size", "size_quintile", "liquidity", "sector", "timing", "regime",
              "vol_regime", "busy", "year", "quarter", "strength_quintile", "strength", "all"]
INFO = ["OP_series差", "EPS_series差", "OP_company差", "OP_revision_amount", "EPS_revision_amount",
        "op_progress_change", "OP_actual_cross", "op_eps_conflict", "op_revision_actual_conflict"]


def compact(df, cols, estimates):
    return table([[r[k] for k in cols] + [r["n"], r["securities"], *[pct(r[k]) for k in estimates]]
                  for r in df.to_dict("records")], [*cols, "n", "銘柄", *estimates])


def execution(trades, events, sessions, output):
    trade = trades.merge(events, on="event_id", validate="many_to_one")
    if not (trade.signal_minute.lt(trade.entry_minute) & trade.entry_minute.lt(trade.exit_minute)).all():
        raise ValueError("Execution chronology")
    trade["gross"] = np.sign(trade.initial_excess) * (trade.exit / trade.entry - 1)
    trade["liquid_topix"] = trade.universe.eq("topix") & trade.adv20.ge(1e8)
    complete = trade.groupby("event_id").delay.nunique()
    trade["common_delay"] = trade.event_id.isin(complete.index[complete.eq(len(DELAYS))])
    rows, daily = [], []
    subsets = {"all": trade, "liquid_topix": trade.loc[trade.liquid_topix],
               "non_topix": trade.loc[trade.universe.eq("non_topix")],
               "strong_liquid_topix": trade.loc[trade.liquid_topix & trade.initial_excess.abs().ge(.03)]}
    for universe, subset in subsets.items():
        for delay in DELAYS:
            for side in ("up", "down"):
                part = subset.loc[subset.delay.eq(delay) & subset.initial.eq(side)]
                part = part.loc[part.known_turnover.gt(0)]
                if side == "down":
                    part = part.loc[part.loanable.eq(True)]
                for rate in (.001, .01):
                    gross_ledger = portfolio(part, sessions, 0, rate)
                    for cost in COSTS:
                        ledger = gross_ledger.assign(net=gross_ledger.gross - gross_ledger.deployed / 1e8 * cost / 10000)
                        total = ledger.net.sum()
                        cumulative = ledger.net.cumsum()
                        dd = (cumulative - cumulative.cummax().clip(lower=0)).min()
                        rows.append((universe, delay, side, cost, rate, len(part), int(ledger.fills.sum()),
                                     part.security_code.nunique(), part.gross.mean(), part.gross.mean()-cost/10000,
                                     part.loc[part.common_delay, "gross"].mean()-cost/10000,
                                     int(part.common_delay.sum()), total, dd, ledger.deployed.sum(),
                                     ledger.net.sum()*1e8/ledger.deployed.sum() if ledger.deployed.sum() > 0 else np.nan))
                        daily.append(ledger.assign(universe=universe, delay=delay, side=side, cost=cost, rate=rate))
    summary = pd.DataFrame(rows, columns=["universe", "delay", "side", "cost", "rate", "n", "fills",
                                          "securities", "gross", "net", "common_net", "common_n",
                                          "portfolio", "dd", "deployed", "capital_weighted_net"])
    daily = pd.concat(daily, ignore_index=True)
    keys = ["universe", "delay", "side", "cost", "rate"]
    annual = daily.assign(year=daily.date.dt.year).groupby(keys+["year"])[["net", "fills"]].sum().reset_index()
    annual.to_parquet(output / "execution_year.parquet", index=False)
    daily.to_parquet(output / "portfolio.parquet", index=False)
    summary.to_parquet(output / "execution_summary.parquet", index=False)
    return summary, annual


def report(events, paths, sessions, audit, trades, output, reports, figures):
    reports.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    frame = paths.merge(events.drop(columns="initial_excess"), on="event_id", validate="many_to_one")
    frame = frame.loc[frame.initial.notna()].copy()
    frame["signed"] = frame.additional_excess * np.sign(frame.initial_excess)
    frame["continuation"] = frame.signed.gt(0).where(frame.signed.notna()).astype(float)
    frame["reversal"] = frame.signed.lt(0).where(frame.signed.notna()).astype(float)
    frame["all"] = "tse_common"
    stats = []
    for name, subset in [("available", frame), ("common", frame.loc[frame.common])]:
        for dimension in DIMENSIONS:
            observed = subset.dropna(subset=[dimension])
            out = describe(observed, ["point", "initial", dimension], ["additional_excess", "signed"])
            probabilities = observed.groupby(["point", "initial", dimension], observed=True)[
                ["continuation", "reversal", "half_retrace", "cross_base"]].mean().reset_index()
            out = out.merge(probabilities, on=["point", "initial", dimension], validate="many_to_one")
            out = out.rename(columns={dimension: "bucket"}).assign(sample=name, dimension=dimension)
            out["bucket"] = out.bucket.astype(str)
            stats.append(out)
    summary = pd.concat(stats, ignore_index=True)
    summary.to_parquet(output / "conditional.parquet", index=False)
    base = frame.loc[frame.point.eq("wall_60")].dropna(subset=["signed"])
    cells = pd.concat([describe(base, ["initial", "strength", key], ["signed"]).rename(columns={key: "bucket"})
                       .assign(dimension=key) for key in ("size", "liquidity")])
    cells["bucket"] = cells.bucket.astype(str)
    cells.to_parquet(output / "strength_matched_cells.parquet", index=False)
    regression = pd.concat([fixed_effects(base, dim, "signed") for dim in
                            ("size", "liquidity", "sector", "regime", "timing", "size_direction")])
    regression.to_parquet(output / "regression.parquet", index=False)
    matches = matched_size(base)
    matches.to_parquet(output / "matched_size.parquet", index=False)
    matched = describe(matches.assign(group="matched"), ["group", "initial"], ["difference"])
    block = []
    tails = []
    for (side, concentrated), group in base.groupby(["initial", "busy"]):
        lo, hi = blocks(group, "signed")
        block.append((side, concentrated, len(group), group.signed.mean(), lo, hi))
        outliers = group.signed.abs().nlargest(20).index
        tails.append((side, concentrated, group.loc[outliers, "signed"].sum()/len(group)))
    block_frame = pd.DataFrame(block, columns=["side", "busy", "n", "mean", "lo", "hi"])
    block_frame.to_parquet(output / "bootstrap.parquet", index=False)
    pd.DataFrame(tails, columns=["side", "busy", "tail_contribution"]).to_parquet(output / "tails.parquet", index=False)
    annual = base.groupby(["initial", "year", "security_code"]).signed.agg(["mean", "size"]).reset_index()
    annual.to_parquet(output / "security_year.parquet", index=False)
    security_check = annual.loc[annual["size"].ge(3)].groupby(["initial", "year"])["mean"].agg(
        securities="count", median="median", positive=lambda x: x.gt(0).mean()).reset_index()
    security_check.to_parquet(output / "security_recurrence.parquet", index=False)
    tests = regression.reset_index(drop=True)
    # Recover normal-approximation p values from the existing two-sided intervals.
    se = (tests.hi - tests.lo) / 3.92
    tests["p"] = [erfc(abs(effect / error) / sqrt(2)) if error > 0 else np.nan
                  for effect, error in zip(tests.estimate, se)]
    ranked = tests.p.dropna().sort_values()
    tests.loc[ranked.index, "holm_p"] = (ranked * np.arange(len(ranked), 0, -1)).cummax().clip(upper=1)
    tests.to_parquet(output / "multiple_comparisons.parquet", index=False)
    interactions = pd.concat([
        describe(base, ["initial", "regime", dimension], ["signed"])
        .rename(columns={dimension: "bucket"}).assign(dimension=dimension)
        for dimension in ("size", "sector")
    ], ignore_index=True)
    interactions["bucket"] = interactions.bucket.astype(str)
    interactions.to_parquet(output / "regime_interactions.parquet", index=False)
    attr = events.assign(initial_abs=events.initial_excess.abs()).groupby(["common", "timing"], observed=True).agg(
        n=("event_id", "size"), securities=("security_code", "nunique"), cap=("market_cap", "median"),
        adv=("adv20", "median"), strength=("initial_abs", "median"), delay=("first_delay_minutes", "median"),
        remaining=("remaining_trading", "median")).reset_index()
    attr.to_parquet(output / "selection.parquet", index=False)
    metrics = ["initial_excess", "peak_elapsed", "bottom_elapsed", "missing_share", "volume_burst_5",
               "capacity_1pct", "first_delay_minutes", "remaining_trading"]
    profile = []
    for k in ("size", "liquidity", "sector", "timing", "regime", "vol_regime", "universe"):
        part = events.loc[events.first_minute.notna()].copy()
        part["initial_excess"] = part.initial_excess.abs()
        by = part.groupby(k, observed=True)
        profile.append(by[metrics].median().assign(n=by.event_id.size(), securities=by.security_code.nunique(),
            mean_abs=by.initial_excess.mean(), up_share=by.initial.apply(lambda v: v.eq("up").mean()))
            .reset_index().rename(columns={k: "bucket"}).assign(dimension=k))
    profile = pd.concat(profile, ignore_index=True)
    profile["bucket"] = profile.bucket.astype(str)
    profile.to_parquet(output / "profiles.parquet", index=False)
    reasons = audit.groupby(["horizon", "reason"]).size().rename("n").reset_index()
    boundary = events.loc[events.first_session.eq(sessions.max()) & ~events.common, "event_id"].size
    reasons.to_parquet(output / "missing_by_reason.parquet", index=False)
    audit.merge(events[["event_id", "timing", "sector", "universe"]], on="event_id").groupby(
        ["horizon", "reason", "timing", "sector", "universe"], observed=True).size().rename("n").reset_index().to_parquet(
            output / "missing_by_attributes.parquet", index=False)
    info = []
    for name in INFO:
        category = direction(base[name]) if pd.api.types.is_numeric_dtype(base[name]) and not name.endswith("conflict") else base[name].fillna("unknown").astype(str)
        part = base.assign(info=category)
        raw = describe(part, ["initial", "info"], ["signed"]).assign(feature=name)
        keys = ["sector", "timing", "size", "initial", "strength"]
        # Leave out the event's own return from its reference cell.
        grouped = part.groupby(keys, observed=True).signed
        n = grouped.transform("count")
        part["adjusted"] = (part.signed - (grouped.transform("sum") - part.signed)/(n-1)).where(n.ge(10))
        adjusted = describe(part, ["initial", "info"], ["adjusted"]).assign(feature=name)
        info.extend([raw, adjusted])
    information = pd.concat(info)
    information.to_parquet(output / "information.parquet", index=False)
    economic, oos = execution(trades, events, sessions, output)
    selected = summary.loc[summary.point.eq("wall_60") & summary.measure.eq("signed") & summary["sample"].eq("available")]
    general = summary.loc[summary.dimension.eq("all") & summary.measure.eq("signed") & summary.point.ne("wall_5")]
    for scope in ("available", "common"):
        values = general.loc[general["sample"].eq(scope)].pivot(index="point", columns="initial", values="mean")
        plot(figures / f"01_momentum_{scope}.png", values.reindex([f"wall_{x}" for x in POINTS[1:]]),
             f"Directional excess | {scope}", "line")
    sz = selected.loc[selected.dimension.eq("size")]
    plot(figures / "02_size.png", sz.pivot(index="bucket", columns="initial", values="mean"),
         "60-minute directional excess | market cap")
    screen = economic.loc[economic.cost.eq(10) & economic.rate.eq(.01)]
    holdout = oos.loc[oos.cost.eq(10) & oos.rate.eq(.01) & oos.delay.eq(1)]
    selection = events.groupby("common")[["market_cap", "adv20"]].median()
    common_text = (
        f"共通集合の時価総額中央値は{selection.at[True, 'market_cap']/1e8:,.0f}億円、"
        f"共通外は{selection.at[False, 'market_cap']/1e8:,.0f}億円。"
        f"事前ADV中央値はそれぞれ{selection.at[True, 'adv20']/1e6:,.0f}百万円と"
        f"{selection.at[False, 'adv20']/1e6:,.0f}百万円。"
    )
    ledger_table = table([(r.universe, r.delay, r.side, r.n, r.fills, pct(r.net), pct(r.common_net),
                           pct(r.capital_weighted_net), pct(r.portfolio), pct(r.dd)) for r in screen.itertuples()],
                         ["対象", "遅延分", "初動", "候補", "約定", "平均ネット", "共通ネット", "元本加重", "累積損益", "最大DD"])
    adjusted = regression.loc[regression.dimension.isin(["size", "liquidity"])]
    size_table = table([(r.dimension,r.term,r.n,pct(r.estimate),pct(r.lo),pct(r.hi)) for r in adjusted.itertuples()],
                       ["属性", "基準との差", "件数", "差", "下限", "上限"])
    liquid_long = economic.loc[economic.universe.eq("liquid_topix") & economic.side.eq("up")
                               & economic.rate.eq(.01)].set_index(["delay", "cost"])
    one = liquid_long.loc[(1, 10)]
    net_20 = liquid_long.loc[(1, 20), "net"]
    save(reports / "phase5_size_liquidity.md", [
        "# 時価総額と流動性", "", "60分時点の方向付き超過。", "",
        compact(selected.loc[selected.dimension.isin(["size", "liquidity", "size_quintile"])],
                ["dimension", "bucket", "initial"], ["mean", "median", "lo", "hi", "reversal"]), "",
        "## 初動・属性を同時に調整", "", size_table, "",
        "## 同日・同業種・類似流動性での対応比較", "",
        compact(matched, ["initial"], ["mean", "lo", "hi"]), "",
        "初動強度帯ごとの規模・流動性集計は strength_matched_cells.parquet。"
        "無約定率、ピーク・ボトム時間、ADV容量の中央値は profiles.parquet。"])
    save(reports / "phase5_sector_regime.md", [
        "# 業種・市場環境・発表時刻", "",
        compact(selected.loc[selected.dimension.isin(["regime", "vol_regime", "busy", "timing"])],
                ["dimension", "bucket", "initial"], ["mean", "lo", "hi", "continuation", "reversal"]), "",
        "## 業種別", "",
        compact(selected.loc[selected.dimension.eq("sector")],
                ["bucket", "initial"], ["mean", "lo", "hi"]), "",
        "## 決算集中日ブロック", "",
        table([(r.side, r.busy, r.n, pct(r.mean), pct(r.lo), pct(r.hi)) for r in block_frame.itertuples()],
              ["方向", "集中日", "件数", "平均", "下限", "上限"]), "",
        "業種・規模等の調整係数は regression.parquet。月をまたぐ保有重複とは異なり、60分試算は当日中に終了する。"])
    save(reports / "phase5_conditional_returns.md", [
        "# 情報との相互作用・費用控除後の試算", "",
        compact(information.loc[information.measure.eq("adjusted") & information.feature.isin(
            ["OP_company差", "OP_revision_amount", "op_eps_conflict"])],
            ["feature", "info", "initial"], ["mean", "lo", "hi"]), "",
        "## 遅延・容量・費用", "", ledger_table, "",
        "## 固定条件の年別成績と2026年時系列評価", "",
        table([(r.universe, r.side, r.year, int(r.fills), pct(r.net)) for r in holdout.itertuples()],
              ["対象", "方向", "年", "約定", "累積損益"]), "",
        "2024・2025・2026年の固定条件結果は execution_year.parquet。5・20・30bpおよび0.1%参加率は execution_summary.parquet。"
        "売買代金上限と借株候補は事前情報。価格は分足約定の観測値で、板と受注を再現していない。"])
    save(reports / "phase5_findings.md", [
        "# Phase 5 結果", "",
        "## 結論とPhase 6", "",
        "初動強度・流動性・業種・年・発表時刻・市場局面を調整した60分の規模差は、全規模帯で近似95%区間がゼロを含んだ。"
        "同日対応は正負で結果が異なり、規模だけによる一貫した効果は確認できなかった。",
        "正の初動後、前営業日の売買代金が1000万円未満の群では60分の平均が反対方向に動いた。"
        "業種・時刻・市場環境には記述上の差があるが、補正後の回帰では独立した効果を確認できなかった。"
        "営業利益予想修正と初動の不一致も、同業種等で調整した群の区間がゼロを含んだ。",
        f"事前ADV1億円以上のTOPIXロングは、1分遅延・10bpで1件平均{pct(one.net)}、"
        f"固定資本の累積損益{pct(one.portfolio)}。20bpでは1件平均{pct(net_20)}。"
        "Phase 6ではこのロングを、未観測期間と約定容量を用いた検証に進める。"
        "取引実績や独立OOSによる裏付けはまだない。", "",
        f"分足初回約定 {events.first_minute.count():,}件、Phase 4と同じ5〜120分共通集合 {events.common.sum():,}件。"
        f"符号が確定した共通集合 {int((events.common & events.initial.notna()).sum()):,}件。", "",
        "## 各時点の全観測と共通集合", "",
        compact(general, ["sample", "point", "initial"], ["mean", "median", "lo", "hi", "reversal"]), "",
        "## 120分の欠損内訳", "",
        table(reasons.loc[reasons.horizon.eq(120), ["reason", "n"]].itertuples(index=False, name=None),
              ["理由", "件数"]), "",
        f"最終収録営業日で共通集合に入らなかったイベントは{boundary:,}件。"
        "60・120分は同一セッション内の観測なので、日をまたぐ打ち切りを立会時間不足と混同しない。", "",
        "## 共通集合と脱落集合", "",
        common_text, "",
        table([(r.common, r.timing, r.n, f"{r.cap/1e9:.1f}", f"{r.adv/1e6:.1f}",
                pct(r.strength), f"{r.remaining:.0f}") for r in attr.itertuples()],
              ["共通", "発表時刻", "件数", "時価総額中央値 十億円", "ADV中央値 百万円", "初動絶対値中央値", "残り立会分"]), "",
        "## 調整後の規模差", "", size_table, "",
        "## 銘柄単位の再現性", "",
        table([(r.initial, r.year, r.securities, pct(r.median), pct(r.positive))
               for r in security_check.itertuples()],
              ["初動", "年", "3件以上の銘柄", "銘柄平均の中央値", "平均が正の銘柄割合"]), "",
        "## 費用・遅延試算", "", ledger_table, "",
        f"分析した一変量区分は{len(DIMENSIONS)}系列、情報指標は{len(INFO)}系列、"
        f"執行シナリオは{len(economic)}。回帰係数{len(ranked)}件のHolm補正後5%通過は"
        f"{tests.holm_p.lt(.05).sum()}件。表の区間は未調整。", "",
        "[規模・流動性](phase5_size_liquidity.md) · [業種・市場](phase5_sector_regime.md) · [条件付き損益](phase5_conditional_returns.md)"])
