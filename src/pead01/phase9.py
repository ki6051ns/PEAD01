"""Phase 9 fixed-WF learning-window experiment using saved Phase 8 price paths."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from itertools import product
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .phase6_batch import atomic_json
from .phase6_daily import save
from .phase6_daily_wf import replay, sharpe
from .phase7 import validate_journal
from .phase8 import digest, exclusive, progress
from .phase8_wf import HISTORY, PARAMETERS, choose, score_paths

FOCUS = "neighbor_w252_b10"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def bounds(sessions, cfg):
    start, last = sessions.get_indexer([cfg["first_wf"], cfg["last_wf"]])
    if start < 0 or last != len(sessions)-1 or last-start+1 != cfg["wf_sessions"]:
        raise ValueError("The Phase 8 calendar does not match the fixed Phase 9 WF")
    stops = [*range(start, last+1, cfg["update_days"]), last+1]
    return list(zip(stops, stops[1:]))


def training_interval(start, days, blank, validation=0):
    end = start-blank
    if validation:
        end -= validation+blank
    lo = end-days if days else 0
    if lo < 0 or end <= lo:
        raise ValueError(f"Insufficient training history: {days=} {blank=} {validation=} {start=}")
    return lo, end


def histories(specs, scores, series, folds, cfg, windows, blanks, label, validation=0, dynamic=False):
    records = []
    candidates = specs.set_index("id")[PARAMETERS]
    for days, (start, end) in product(windows, folds):
        winners = []
        for blank in blanks:
            t = training_interval(start, days, blank, validation)
            v = (start-blank-validation, start-blank)
            _, best = choose(scores[t], scores[v] if validation else None,
                             "rerank" if validation else "direct", cfg)
            if len(best):
                winner = best[0]
                near = candidates.loc[best].ne(candidates.loc[winner]).sum(axis=1).le(1)
                neighbors = best[near.to_numpy()]
                winners.append((blank, winner, t))
            else:
                neighbors = []
            if not dynamic:
                for style, selected in (("single", best[:1]), ("neighbor", neighbors)):
                    mode = f"{label}_{style}_{days}"
                    for c in selected if len(selected) else [-1]:
                        records.append((start, end, blank, mode, c, 1/len(selected) if c >= 0 else 0.))
        if dynamic:
            mode = f"{label}_blank_dynamic_{days}"
            if not winners:
                records.append((start, end, -1, mode, -1, 0.))
                continue
            # The last 63 common dates are sufficient for the existing Dynamic weights.
            hi = min(t[1] for _, _, t in winners)
            lo = max(hi-63, *(t[0] for _, _, t in winners))
            stats = []
            for _, c, (left, right) in winners:
                tail = series[c, left, right]
                tail_start = right-len(tail)
                stats.append(sharpe(tail[lo-tail_start:hi-tail_start]))
            weights = np.exp(np.clip(np.nan_to_num(stats), -3, 3))
            for (blank, c, _), weight in zip(winners, weights/weights.sum()):
                records.append((start, end, blank, mode, c, weight))
    return pd.DataFrame(records, columns=HISTORY)


def score_file(task):
    file, candidate_ids, ranges, cfg, sessions, tails_needed, target = task
    if target.exists():
        return
    trades = pd.read_parquet(file)
    specs, audit, streams = score_paths(trades, cfg, sessions, ranges, 0)
    ids = specs.merge(candidate_ids, on=PARAMETERS, validate="one_to_one").set_index("id").id_original
    if len(ids) != len(candidate_ids):
        raise ValueError(f"Candidate grid changed in {file.name}")
    audit["tail"] = [streams[c, lo, hi][-123:] if (lo, hi) in tails_needed else None
                     for c, lo, hi in audit[["id","lo","hi"]].itertuples(index=False, name=None)]
    audit["id"] = audit.id.map(ids)
    save(audit, target)
    print(f"Scored {file.stem}", flush=True)


def tagged_paths(source, specs, first):
    if specs.empty:
        return pd.DataFrame(columns=PARAMETERS[:4])
    frames = []
    for (hold, price), g in specs.groupby(["hold", "exit_price"], sort=False):
        frame = pd.read_parquet(source/f"paths_{hold}_{price}.parquet")
        frame = frame.merge(g[["method","entry"]].drop_duplicates(), on=["method","entry"], sort=False)
        active = frame.loc[frame.start.ge(first)]
        # The shared replay groups paths by candidate shape before slicing the WF.
        # Retain a pre-WF representative when a fitted shape has no WF events.
        keys = ["method", "entry"]
        inactive = frame.loc[frame.start.lt(first)].drop_duplicates(keys)
        inactive = inactive.merge(active[keys].drop_duplicates(), how="left", on=keys, indicator=True)
        frame = pd.concat([active, inactive.loc[inactive._merge.eq("left_only")].drop(columns="_merge")])
        frame["event_id"] += "|" + frame.method + "|" + frame.hold.astype(str)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def run_book(trades, specs, selection, sessions, cfg):
    events = []
    def journal(mode):
        def record(row, day, side, gross, cost, entry):
            action = "entry" if entry else "exit" if row.closed and day == row.end else "mark"
            minute = row.minute if entry else row.exit_minute if action == "exit" else -1
            mark = row.marks[-1] if action == "exit" else 1.
            events.append((mode, day, row.start, row.minute, minute, row.code, row.event_id,
                           side, action, gross, cost, mark))
        return record
    chosen = specs.loc[specs.id.isin(selection.loc[selection.weight.gt(0), "id"])]
    day = replay(trades, chosen, selection, sessions, cfg,
                 journals={mode: journal(mode) for mode in selection["mode"].unique()})
    day = day.loc[day.date.ge(sessions[selection.start.min()])].reset_index(drop=True)
    day["nav"] = day.groupby("mode").net.transform(lambda s: (1+s).cumprod())*cfg["capital"]
    day["start_nav"] = day.groupby("mode").nav.shift().fillna(cfg["capital"])
    day["pnl_yen"] = day.start_nav*day.net
    day["cost_yen"] = day.start_nav*day.cost
    log = pd.DataFrame(events, columns=["mode","day","start","entry_minute","minute","code",
                                       "tag","side","action","gross","cost","mark"])
    log = log.astype({"gross": float, "cost": float})
    log["date"] = sessions.take(log.day.to_numpy(dtype=int))
    log["entry_date"] = sessions.take(log.start.to_numpy(dtype=int))
    log[["event_id","method","hold"]] = pd.DataFrame([tag.rsplit("|", 2) for tag in log.tag],
                                                     index=log.index, columns=range(3))
    log = log.drop(columns=["day","start","tag"]).merge(day[["mode","date","start_nav"]],
                                                        on=["mode","date"], validate="many_to_one")
    log["pnl_yen"] = (log.gross-log.cost)*log.start_nav
    log["cost_yen"] = log.cost*log.start_nav
    log["timestamp"] = (log.date + pd.to_timedelta(log.minute, unit="min")).where(log.minute.ge(0))
    executions = log.loc[log.action.ne("mark")].copy()
    key = ["mode","code","entry_date","entry_minute"]
    opening = executions.loc[executions.action.eq("entry")].set_index(key).cost_yen
    executions["notional_yen"] = executions.set_index(key).index.map(opening) * executions.mark / (cfg["cost_bp"]/20000)
    for mode, g in day.groupby("mode"):
        rows = log.loc[log["mode"].eq(mode)]
        validate_journal(rows, g.set_index("date").net)
        assert rows.action.eq("entry").sum() == g.fills.sum()
    return day, log, executions


def session_positions(old, new, folds):
    first = new.get_indexer(old.take([l for l, _ in folds]))
    last = new.get_indexer(old.take([r-1 for _, r in folds]))
    if min(first.min(), last.min()) < 0:
        raise ValueError("Old WF dates are absent from the Phase 8 calendar")
    mapped = list(zip(first, last+1))
    if any(not old[a:b].equals(new[c:d]) for (a,b), (c,d) in zip(folds,mapped)):
        raise ValueError("Old and new sessions differ inside a legacy WF block")
    return mapped


def reconcile_inputs(source, legacy, first):
    a = pd.read_parquet(legacy/"market.parquet").set_index("Date")
    b = pd.read_parquet(source/"market.parquet").set_index("Date").loc[a.index.min():a.index.max()]
    pd.testing.assert_frame_equal(a, b, check_exact=True)
    market_rows_equal = len(a)
    keys = ["event_id","method","entry"]
    fields = ["fill_time","gap","loanable","adv"]
    old, new = (pd.read_parquet(folder/"signals.parquet", columns=keys+fields)
                .loc[lambda f: f.fill_time.ge(first)].set_index(keys, verify_integrity=True)
                for folder in (legacy, source))
    common = old.index.intersection(new.index)
    a, b = old.loc[common], new.loc[common]
    differs = ~np.isclose(a.gap, b.gap, atol=1e-12, rtol=0)
    differs |= a.loanable.ne(b.loanable) | a.fill_time.ne(b.fill_time) | a.adv.ne(b.adv)
    return {"market_rows_equal": market_rows_equal,
            "legacy_signals": len(old), "phase8_signals": len(new),
            "matching_signal_keys": len(common), "changed_matching_signals": int(differs.sum())}


def execute(config, source, legacy, out, workers):
    cfg = read_json(config)
    phase8 = read_json(Path("phase8.json"))
    upstream = read_json(source/"inputs.json")
    if read_json(source/"status.json")["status"] != "completed":
        raise ValueError("The Phase 8 cache is incomplete")
    if upstream.get("phase8.json") != digest(Path("phase8.json")):
        raise ValueError("Phase 8 settings differ from the cached price paths")
    specs = pd.read_parquet(source/"candidates.parquet")
    old_specs = pd.read_parquet(legacy/"candidates.parquet")
    if set(specs[PARAMETERS].itertuples(index=False, name=None)) != set(old_specs[PARAMETERS].itertuples(index=False, name=None)):
        raise ValueError("Legacy and Phase 8 candidate universes differ")
    if len(specs) != 864 or specs.duplicated(PARAMETERS).any():
        raise ValueError("Expected the existing 864-candidate grid")
    old_cfg = read_json(Path("phase6_daily.json"))
    keys = ("capital","position_limit","participation","cost_bp","min_train_fills","min_validation_fills")
    if any(old_cfg[key] != phase8[key] for key in keys):
        raise ValueError("The legacy and Phase 8 book or scoring settings differ")

    sessions = pd.DatetimeIndex(pd.read_parquet(source/"market.parquet").Date)
    old_sessions = pd.DatetimeIndex(pd.read_parquet(legacy/"market.parquet").Date)
    folds = bounds(sessions, cfg)
    old_all = pd.read_parquet(legacy/"selection.parquet")
    old_picks = old_all.loc[old_all["mode"].eq(FOCUS), HISTORY].copy()
    native = list(old_picks[["start","end"]].drop_duplicates().itertuples(index=False, name=None))
    mapped = session_positions(old_sessions, sessions, native)
    days, blank, v = cfg["training_days"], cfg["blank"], cfg["legacy_validation_days"]
    blanks = phase8["blanks"]
    tails = {training_interval(s, d, b) for (s, _), d, b in product(folds, days, blanks)}
    base_ranges = {rng for (s, _) in folds+mapped for rng in
                   (training_interval(s, 252, blank, v), (s-blank-v, s-blank))}
    ranges = sorted(tails | base_ranges)

    pairs = [(int(h), str(p)) for h, p in specs[["hold","exit_price"]].drop_duplicates().itertuples(index=False)]
    paths = [source/f"paths_{h}_{p}.parquet" for h,p in pairs]
    files = [config, Path("phase8.json"), Path("phase6_daily.json"), *paths,
             *[source/x for x in ("market.parquet","candidates.parquet","inputs.json","interval_scores.parquet",
                                  "signals.parquet","0_A_0_direct/daily.parquet")],
             *[legacy/x for x in ("market.parquet","candidates.parquet","selection.parquet",
                                  "wf_base.parquet","interval_scores.parquet","signals.parquet")],
             *sorted(legacy.glob("paths_*.parquet")),
             *[Path(__file__).with_name(name+".py") for name in
               ("phase9","phase8_wf","phase6_daily_wf","phase6_book","phase7")]]
    signature = {f.as_posix(): digest(f) for f in files}
    manifest = out/"inputs.json"
    if manifest.exists() and read_json(manifest) != signature:
        raise ValueError("Inputs changed, use a new --out")
    atomic_json(manifest, signature)
    population = reconcile_inputs(source, legacy, old_sessions[native[0][0]])

    progress(out, "history confirmed", training_available=folds[0][0]-blank, max_fixed=max(days),
             first_wf=str(sessions[folds[0][0]].date()))
    cached = source/"interval_scores.parquet"
    # Phase 8 scores can be reused for matching intervals unless Dynamic needs a return tail.
    cached_audit = pd.read_parquet(cached)
    cached_ranges = set(cached_audit[["lo","hi"]].itertuples(index=False, name=None))
    primary_ranges = {training_interval(s, d, blank) for (s, _), d in product(folds, days)}
    primary_scores = score_batch("primary", primary_ranges, primary_ranges, cached_audit, cached_ranges,
                                 specs, pairs, phase8, sessions, source, out, workers)
    primary = histories(specs, index_scores(primary_scores), {}, folds, phase8, days, [blank], "primary")
    save_replay("primary", primary, source, specs, sessions, phase8, out)
    primary_daily = pd.read_parquet(out/"primary_daily.parquet")
    phase8_daily = pd.read_parquet(source/"0_A_0_direct/daily.parquet")
    for style in ("single", "neighbor"):
        p9 = primary_daily.loc[primary_daily["mode"].eq(f"primary_{style}_0"), ["date","net"]].reset_index(drop=True)
        p8 = phase8_daily.loc[phase8_daily["mode"].eq(f"{style}_b{blank}"), ["date","net"]].reset_index(drop=True)
        pd.testing.assert_frame_equal(p9, p8, check_exact=True)

    # Score the fixed-blank intervals only once. Dynamic reuses those already computed tails.
    remainder = set(ranges)-primary_ranges
    extra = score_batch("references", remainder, tails, cached_audit, cached_ranges,
                        specs, pairs, phase8, sessions, source, out, workers)
    audit = pd.concat([primary_scores, extra], ignore_index=True)
    series = {(c,l,r): data for c,l,r,data in audit[["id","lo","hi","tail"]].itertuples(index=False, name=None)
              if isinstance(data, np.ndarray)}
    all_scores = audit.drop(columns="tail")
    scores = index_scores(all_scores)
    save(all_scores, out/"interval_scores.parquet")

    reference = histories(specs, scores, series, folds, phase8, days, blanks, "reference", dynamic=True)
    control = histories(specs, scores, series, folds, phase8, [252], [blank], "control", validation=v)
    native_new = histories(specs, scores, series, mapped, phase8, [252], [blank], "legacy_calendar", validation=v)
    native_new = native_new.loc[native_new["mode"].eq("legacy_calendar_neighbor_252")]
    for name, h in (("reference",reference), ("control",control), ("legacy_calendar",native_new)):
        save_replay(name, h, source, specs, sessions, phase8, out)

    progress(out, "legacy ledger reconciliation")
    old_audit = pd.read_parquet(legacy/"interval_scores.parquet")
    old_scores = {key:g.sort_values("id").set_index("id") for key,g in old_audit.groupby(["lo","hi"])}
    rebuilt = histories(old_specs, old_scores, {}, native, old_cfg, [252], [blank], "archived", validation=v)
    rebuilt = rebuilt.loc[rebuilt["mode"].eq("archived_neighbor_252")]
    old_picks["mode"] = "archived_neighbor_252"
    fields = ["start","end","id","weight"]
    pd.testing.assert_frame_equal(rebuilt[fields].reset_index(drop=True), old_picks[fields].reset_index(drop=True),
                                  check_dtype=False)
    trades = tagged_paths(legacy, old_specs.loc[old_specs.id.isin(rebuilt.id)], rebuilt.start.min())
    bundle = run_book(trades, old_specs, rebuilt, old_sessions, old_cfg)
    expected = pd.read_parquet(legacy/"wf_base.parquet").loc[lambda f: f["mode"].eq(FOCUS)].reset_index(drop=True)
    actual = bundle[0]
    pd.testing.assert_series_equal(actual.date, expected.date)
    metrics = ["gross","cost","turnover","fills","utilization","net"]
    np.testing.assert_allclose(actual[metrics], expected[metrics], atol=1e-12, rtol=0)
    output_group(out, "archived", bundle, rebuilt, old_specs, old_sessions)
    fields = ["update_date", *PARAMETERS, "weight"]
    original = pd.read_parquet(out/"archived_selection.parquet")[fields].dropna()
    revised = pd.read_parquet(out/"legacy_calendar_selection.parquet")[fields].dropna()
    by_fold = original.merge(revised, on=fields, how="outer", indicator=True)
    changed_folds = by_fold.loc[by_fold._merge.ne("both"), "update_date"].nunique()
    atomic_json(out/"verification.json", {"legacy_ledger_equal": True, "legacy_selection_equal": True,
                "phase8_expanding_daily_equal": True,
                "candidates": len(specs), "primary_conditions": primary["mode"].nunique(),
                "first_training_available": folds[0][0]-blank, "common_sessions": cfg["wf_sessions"],
                "legacy_calendar_changed_selection_folds": changed_folds, **population})
    progress(out, "completed")


def score_batch(label, ranges, tails, cached, cached_ranges, specs, pairs, cfg, sessions, source, out, workers):
    reusable = (ranges-tails) & cached_ranges
    needed = sorted(ranges-reusable)
    tasks = []
    for hold, price in pairs:
        ids = specs.loc[specs.hold.eq(hold) & specs.exit_price.eq(price), ["id",*PARAMETERS]]
        ids = ids.rename(columns={"id":"id_original"})
        tasks.append((source/f"paths_{hold}_{price}.parquet", ids, needed, cfg, sessions,
                      tails, out/f"scores_{label}_{hold}_{price}.parquet"))
    progress(out, f"scoring {label}")
    with ProcessPoolExecutor(max_workers=workers) as pool:
        list(pool.map(score_file, tasks))
    new = pd.concat([pd.read_parquet(t[-1]) for t in tasks], ignore_index=True)
    old = cached.loc[[r in reusable for r in cached[["lo","hi"]].itertuples(index=False, name=None)]]
    result = pd.concat([new, old], ignore_index=True)
    if not result.last_label.lt(result.hi).all():
        raise ValueError("Found a label at or beyond the training cutoff")
    return result


def index_scores(audit):
    return {key:g.sort_values("id").set_index("id") for key,g in audit.groupby(["lo","hi"])}


def save_replay(name, selection, source, specs, sessions, cfg, out):
    if not (out/f"{name}_done.json").exists():
        progress(out, name)
        trades = tagged_paths(source, specs.loc[specs.id.isin(selection.id)], selection.start.min())
        output_group(out, name, run_book(trades, specs, selection, sessions, cfg), selection, specs, sessions)


def output_group(out, name, bundle, selection, specs, sessions):
    for suffix, f in zip(("daily", "journal", "executions"), bundle):
        save(f, out/f"{name}_{suffix}.parquet")
    chosen = selection.merge(specs[["id",*PARAMETERS]], on="id", how="left", validate="many_to_one")
    chosen["update_date"] = sessions.take(chosen.start.to_numpy())
    chosen["last_wf_date"] = sessions.take(chosen.end.to_numpy()-1)
    save(chosen, out/f"{name}_selection.parquet")
    atomic_json(out/f"{name}_done.json", {"completed": True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name, default in (("config","phase9.json"), ("source","data/phase8_run"),
                          ("legacy","data/phase6_daily_v4"), ("out","data/phase9_run")):
        parser.add_argument("--"+name, type=Path, default=Path(default))
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    with exclusive(args.out/"run.lock"):
        try:
            execute(**vars(args))
        except KeyboardInterrupt:
            atomic_json(args.out/"status.json", {"status":"paused"})
            raise SystemExit(130)
        except Exception as exc:
            atomic_json(args.out/"status.json", {"status":"failed", "error":str(exc)})
            raise
        atomic_json(args.out/"status.json", {"status":"completed"})
