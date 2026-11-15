"""Summarize Phase 9's fixed learning-window experiment."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
import numpy as np
import pandas as pd

from .phase3_portfolio import performance
from .phase6_daily_wf import replay, sharpe
from .phase9 import PARAMETERS, digest, read_json, tagged_paths
from .report import table

LABELS = {"neighbor": "Neighbor", "single": "Single", "blank_dynamic": "Blank Dynamic"}
GROUPS = ["primary", "reference", "control", "archived", "legacy_calendar"]


def stats(frame):
    if frame.empty:
        raise ValueError("No observations in performance period")
    r = frame.net
    return {**performance(r), "return": float((1+r).prod()-1),
            "pnl_yen": frame.pnl_yen.sum(), "cost_yen": frame.cost_yen.sum(),
            "fills": int(frame.fills.sum()), "utilization": frame.utilization.mean()}


def measure(days):
    full, quarter, year = [], [], []
    for mode, g in days.groupby("mode", sort=False):
        g = g.sort_values("date")
        q = g.date.dt.to_period("Q")
        y = g.date.dt.to_period("Y")
        quarters = {str(period): stats(rows) for period, rows in g.groupby(q)}
        best = max(quarters, key=lambda p: quarters[p]["return"])
        q2 = g.loc[q.eq(pd.Period("2025Q2","Q"))]
        full.append(dict(mode=mode, **stats(g), sharpe_ex_2025q2=sharpe(g.loc[~g.index.isin(q2.index), "net"]),
                         best_quarter=best, sharpe_ex_best=sharpe(g.loc[q.astype(str).ne(best), "net"]),
                         pnl_2025q2_yen=q2.pnl_yen.sum(), return_2025q2=stats(q2)["return"] if len(q2) else np.nan))
        quarter.extend(dict(mode=mode, quarter=period, **values) for period, values in quarters.items())
        year.extend(dict(mode=mode, year=str(period), **stats(rows)) for period, rows in g.groupby(y))
    return map(pd.DataFrame, (full, quarter, year))


def modes(cfg):
    return [(style, window, f"{'reference' if style == 'blank_dynamic' else 'primary'}_{style}_{window}")
            for style in LABELS for window in cfg["training_days"]]


def heatmap(result, cfg, file):
    names = list(LABELS)
    windows = cfg["training_days"]
    matrix = result.set_index("mode").sharpe.reindex([m for _, _, m in modes(cfg)]).to_numpy().reshape(len(names), len(windows))
    extent = max(2.01, float(np.nanmax(np.abs(matrix))))
    fig, ax = plt.subplots(figsize=(11, 3.6), layout="constrained")
    im = ax.imshow(matrix, norm=TwoSlopeNorm(vmin=-extent, vcenter=0, vmax=extent), cmap="RdBu")
    for (i,j), value in np.ndenumerate(matrix):
        label = "n/a" if np.isnan(value) else f"{value:.2f}" + (" **" if value >= 2 else " *" if value >= 1.5 else "")
        if value >= 1.5:
            ax.add_patch(plt.Rectangle((j-.48, i-.48), .96, .96, fill=False, lw=2.4, edgecolor="#e6aa24"))
        ax.text(j, i, label, va="center", ha="center", color="white" if abs(value) > .66*extent else "#121a25")
    ax.set_xticks(range(len(windows)), [f"{n:,}" if n else "Expanding" for n in windows])
    ax.set_yticks(range(len(names)), [LABELS[n] for n in names])
    ax.set_xlabel("Training sessions  |  * Sharpe >= 1.5   ** Sharpe >= 2.0")
    ax.set_title("WF Sharpe by training window")
    fig.colorbar(im, ax=ax, shrink=.8, label="Annualized Sharpe")
    fig.savefig(file, dpi=160)
    plt.close(fig)


def label(days):
    return f"{days:,}日" if days else "拡張"


def number(v):
    return f"{v:.2f}" if pd.notna(v) else "—"


def percent(v):
    return f"{v:.2%}" if pd.notna(v) else "—"


def money(v):
    return f"{v:,.0f}"


def write_summary(path, cfg, result, quarters, years, legacy, verification):
    r = result.set_index("mode")
    lengths = cfg["training_days"]
    primary = result.loc[result["mode"].str.startswith("primary_")].copy()
    main = primary.loc[primary.sharpe.idxmax()]
    _, style, w = main["mode"].split("_")
    style = LABELS[style]
    w = int(w)
    q2 = primary.loc[primary.pnl_2025q2_yen.idxmax()]
    q2_style, q2_window = q2["mode"].split("_")[1:]
    extrema = sum(primary.sharpe.ge(1.5))
    records = []
    for days in lengths:
        n, s = (r.loc[f"primary_{name}_{days}"] for name in ("neighbor","single"))
        records.append((label(days), number(n.sharpe), number(s.sharpe), percent(n.annual), percent(s.annual),
                        percent(n.max_dd), percent(s.max_dd), money(n.pnl_yen), money(s.pnl_yen)))
    trend = []
    for name in ("neighbor", "single"):
        fixed = [r.at[f"primary_{name}_{day}", "sharpe"] for day in lengths if day]
        rho = pd.Series(fixed).rank().corr(pd.Series(range(len(fixed))))
        trend.append((LABELS[name], number(rho), "はい" if all(a >= b for a,b in zip(fixed,fixed[1:])) else "いいえ"))
    worst_after = primary.loc[primary.sharpe_ex_best.idxmax()]
    reference = result.loc[result.group.eq("reference")]
    top_reference = reference.loc[reference.sharpe.idxmax()]
    old_shared, new_old_dates, new_dates, no_validation = legacy.sharpe.iloc[[1,3,6,7]]
    lines = [
        "# PEAD01 Phase 9｜学習期間とWF Sharpe", "",
        f"主要14条件の最高は **{style}・{label(w)}、WF Sharpe {number(main.sharpe)}**。"
        f"Sharpe 1.5以上は{extrema}条件、2.0以上は{int(primary.sharpe.ge(2).sum())}条件。"
        "学習期間を振った結果は既観測の共通WFにおける探索成績。", "",
        "## 共通条件", "",
        f"Phase 8のJ-Quants日足と価格経路を再利用。{cfg['first_wf']}〜{cfg['last_wf']}の{cfg['wf_sessions']}営業日を"
        f"63営業日ごとに更新した。初回の学習利用可能期間はブランク10日控除後に"
        f"{verification['first_training_available']:,}営業日あり、1,512日条件も指定どおり計算した。"
        "拡張学習は2016-11-15から累積。主要条件は内部検証0日、ブランク10日、864候補から学習Sharpe上位50を使う。"
        "学習窓内にシグナル・入口を含み、出口が終了境界より厳密に前の取引を採点する。"
        "Singleは首位、Neighborは首位と条件差1軸以内の候補を均等配分する。共通資金台帳、1億円、往復20bp、建玉・約定・流動性制約を維持した。", "",
        "## 学習期間別のWF", "",
        table(records,["学習期間","Neighbor Sharpe","Single Sharpe","Neighbor 年率","Single 年率",
                       "Neighbor 最大DD","Single 最大DD","Neighbor 累積純損益 円","Single 累積純損益 円"]), "",
        table(trend,["方式","固定6窓の学習日数とSharpeの順位相関","単調に低下"]), "",
        "参考のBlank Dynamicは複数ブランクの各首位を、共通学習期間の直近63日の成績で配分。主要14条件とは別枠で評価した。", "",
        table([(label(d),number(r.at[f"reference_blank_dynamic_{d}","sharpe"]),
                number(r.at[f"reference_blank_dynamic_{d}","sharpe_ex_2025q2"])) for d in lengths],
              ["学習期間","Blank Dynamic Sharpe","2025Q2除外Sharpe"]), "",
        "[学習期間別Sharpeヒートマップ](../reports/phase9/01_sharpe_heatmap.png)", "",
        "## Phase 7基準線との照合", "",
        table([(x.comparison,x.first,x.last,x.days,number(x.sharpe),percent(x.return_net),
                number(x.sharpe_ex_2025q2)) for x in legacy.itertuples(index=False)],
              ["条件","開始","終了","営業日","Sharpe","純リターン","2025Q2除外Sharpe"]), "",
        "Phase 7のオリジナルは保存スコアから採用候補を再選択し、当時の価格経路で日次の粗損益・費用・回転・約定・稼働率・純損益を全日照合した。"
        "共通504日への切り出しは元台帳の建玉を引き継ぐ。Phase 8データ側も元のWF更新日で2024-10-01から再生し、同じ範囲に切り出した。"
        f"旧データとPhase 8では候補パラメータ集合・資金台帳設定・重複する市場{verification['market_rows_equal']:,}行が一致した。"
        f"元のWF期間における取引シグナルは旧{verification['legacy_signals']:,}行、新{verification['phase8_signals']:,}行。"
        f"一致キー{verification['matching_signal_keys']:,}行のうち、約定時刻・相対初動・事前売買代金・貸借可否に差があったのは"
        f"{verification['changed_matching_signals']:,}行。旧更新日における採用候補と配分が変わったのは"
        f"{verification['legacy_calendar_changed_selection_folds']}期。"
        "Phase 8データの注文入力を旧候補順に揃えると、旧台帳の日次純リターンと数値誤差内で一致した。"
        "共通台帳は、同じ銘柄・時刻・方向で配分が同値の場合、最初の注文の価格経路を採るため、候補順に感応する。"
        "Phase 8データ内の45日検証ありと検証なしの比較は、"
        "主に検証工程と、それにともなう学習終了日の移動を含む。252日窓の長さとPhase 9の更新日は共通。", "",
        f"旧台帳の共通504日Sharpeは{number(old_shared)}。Phase 8データで旧日程を使うと{number(new_old_dates)}だが、"
        f"45日検証を維持してPhase 9日程・現金開始にすると{number(new_dates)}。"
        f"同じPhase 9日程で検証を省くと{number(no_validation)}だった。"
        "元の2.00からの乖離には、評価開始時の建玉と採用候補を更新する日程の違いが含まれる。", "",
        "## 四半期・年次と利益集中", "",
    ]
    for name in ("neighbor","single"):
        subset = quarters.loc[quarters["mode"].str.startswith(f"primary_{name}_")]
        grid = subset.pivot(index="quarter",columns="mode",values="return")
        lines += [f"### {LABELS[name]}の四半期純リターン", "",
                  table([(q, *(percent(row[f"primary_{name}_{d}"]) for d in lengths)) for q,row in grid.iterrows()],
                        ["四半期",*map(label,lengths)]), ""]
    y = years.loc[years.year.isin(["2025","2026"])].set_index(["mode","year"])
    lines += [table([(LABELS[name], label(d), money(r.at[m,"pnl_2025q2_yen"]), number(r.at[m,"sharpe_ex_2025q2"]), r.at[m,"best_quarter"],
                      number(r.at[m,"sharpe_ex_best"]), percent(y.at[(m,"2025"),"return"]),
                      percent(y.at[(m,"2026"),"return"])) for name,d,m in modes(cfg)],
                    ["方式","学習","2025Q2純損益 円","2025Q2除外Sharpe","最良四半期","最良四半期除外Sharpe","2025年","2026年途中"]), "",
              f"主要14条件で2025Q2の円寄与が最大だったのは{LABELS[q2_style]}・{label(int(q2_window))}の"
              f"{money(q2.pnl_2025q2_yen)}円（四半期純リターン{percent(q2.return_2025q2)}）。"
              "四半期の率は期初に再基準化した複利。円寄与は元の資金台帳から加算した。", "",
              "## Phase 10への引き継ぎ", "",
              f"{style}・{label(w)}を観測Sharpeの首位として持ち越し、同方式の252日と拡張窓を事前対照にする。"
              f"最良四半期除外Sharpeの首位は{LABELS[worst_after['mode'].split('_')[1]]}・"
              f"{label(int(worst_after['mode'].split('_')[-1]))}（{number(worst_after.sharpe_ex_best)}）。"
              f"参考枠からはBlank Dynamic・{label(int(top_reference.training_days))}（{number(top_reference.sharpe)}）を別枠で追試する。"
              "共通日付を保ちながら評価期間を延ばし、2025Q2への依存と独立期間での再現性を確認する。"
              "学習期間と配分方式の採用判断はその評価まで保留する。日付付きのNAV・純損益・採用履歴・約定は保存済み。", "",
              "[詳細集計・再現手順](../reports/phase9/README.md)", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def replay_old_order(source, phase8, legacy):
    """Keep the selection and price paths fixed and restore legacy order priority."""
    selection = pd.read_parquet(source/"legacy_calendar_selection.parquet")
    archived = pd.read_parquet(source/"archived_daily.parquet")
    old = pd.read_parquet(legacy/"candidates.parquet")
    new = pd.read_parquet(phase8/"candidates.parquet")
    specs = old[PARAMETERS].merge(new, on=PARAMETERS, sort=False, validate="one_to_one")
    specs = specs.loc[specs.id.isin(selection.id)]
    sessions = pd.DatetimeIndex(pd.read_parquet(phase8/"market.parquet").Date)
    paths = tagged_paths(phase8, specs, selection.start.min())
    cfg = read_json(Path("phase8.json"))
    daily = replay(paths, specs, selection, sessions, cfg)
    daily = daily.loc[daily.date.ge(archived.date.min())].reset_index(drop=True)
    pd.testing.assert_series_equal(daily.date, archived.date)
    daily["mode"] = "legacy_order_neighbor_252"
    daily["nav"] = (1+daily.net).cumprod()*cfg["capital"]
    daily["start_nav"] = daily.nav.shift(fill_value=cfg["capital"])
    daily["pnl_yen"] = daily.start_nav*daily.net
    daily["cost_yen"] = daily.start_nav*daily.cost
    return daily, float(np.abs(daily.net-archived.net).max())


def generate(config, source, target, summary, phase8, legacy):
    cfg = read_json(config)
    if read_json(source/"status.json")["status"] != "completed" or read_json(source/"inputs.json").get(config.as_posix()) != digest(config):
        raise ValueError("Run is incomplete or its Phase 9 config differs")
    target.mkdir(parents=True, exist_ok=True)
    aligned, max_error = replay_old_order(source, phase8, legacy)
    existing = [pd.read_parquet(source/f"{g}_daily.parquet") for g in GROUPS]
    daily = pd.concat([*existing, aligned], ignore_index=True)
    full, quarters, years = measure(daily)
    comparison = []
    for mode, name, shared in [
        ("archived_neighbor_252","Phase 7・旧データ・元期間",False),
        ("archived_neighbor_252","Phase 7・旧データ・共通日付切り出し",True),
        ("legacy_calendar_neighbor_252","Phase 8データ・旧更新日・元期間",False),
        ("legacy_calendar_neighbor_252","Phase 8データ・旧更新日・共通日付切り出し",True),
        ("legacy_order_neighbor_252","Phase 8データ・旧更新日と旧候補順・元期間",False),
        ("legacy_order_neighbor_252","Phase 8データ・旧更新日と旧候補順・共通日付切り出し",True),
        ("control_neighbor_252","A・Phase 9更新日・45日検証",True),
        ("primary_neighbor_252","B・Phase 9更新日・検証なし",True),
    ]:
        part = daily.loc[daily["mode"].eq(mode)]
        if shared:
            part = part.loc[part.date.between(cfg["first_wf"], cfg["last_wf"])]
        result, _, _ = measure(part)
        record = result.rename(columns={"return":"return_net"}).iloc[0].to_dict()
        comparison.append(dict(comparison=name, first=part.date.min().date(), last=part.date.max().date(), **record))
    legacy = pd.DataFrame(comparison)
    compare = full.merge(pd.DataFrame(modes(cfg), columns=["method","training_days","mode"]), on="mode")
    compare["group"] = np.where(compare.method.eq("blank_dynamic"), "reference", "primary")
    compare["sharpe_ge_1_5"] = compare.sharpe.ge(1.5)
    compare["sharpe_ge_2"] = compare.sharpe.ge(2)
    for file, f in (("performance",compare), ("quarterly",quarters), ("annual",years), ("phase7_reconciliation",legacy)):
        f.to_csv(target/f"{file}.csv", index=False, encoding="utf-8-sig", float_format="%.10g")
    # The raw order ledger and dated NAV remain local. Copy byte-for-byte so all report
    # exports can be evaluated over alternate periods without rebuilding decisions.
    from shutil import copyfile
    for group in GROUPS:
        for suffix in ("daily","executions","selection"):
            file = f"{group}_{suffix}.parquet"
            copyfile(source/file, target/file)
    verification = read_json(source/"verification.json")
    verification["legacy_order_max_daily_net_difference"] = max_error
    (target/"verification.json").write_text(json.dumps(verification, indent=2)+"\n", encoding="utf-8")
    aligned.to_parquet(target/"legacy_order_daily.parquet", index=False)
    copyfile(source/"inputs.json", target/"inputs.json")
    heatmap(compare, cfg, target/"01_sharpe_heatmap.png")
    write_summary(summary, cfg, compare, quarters, years, legacy, verification)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key, value in (("config","phase9.json"), ("source","data/phase9_run"), ("target","reports/phase9"),
                       ("summary","research/phase9_summary.md"), ("phase8","data/phase8_run"),
                       ("legacy","data/phase6_daily_v4")):
        p.add_argument("--"+key, type=Path, default=Path(value))
    generate(**vars(p.parse_args()))
