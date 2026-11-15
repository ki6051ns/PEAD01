"""Run resumable daily-only Phase 8 comparisons and audit the shared ledger."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from .__main__ import files
from .phase6_batch import atomic_json
from .phase6_daily import save
from .phase6_daily_data import make_signals, paths
from .phase6_daily_wf import replay
from .phase7 import linked_journal, validate_journal
from .phase8_data import inputs
from .phase8_wf import conditions, intervals, schedules, score_paths, select


@contextmanager
def exclusive(path):
    with path.open("a+b") as lock:
        if os.name == "nt":
            import msvcrt
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def digest(path):
    with path.open("rb") as stream:
        checksum = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def provenance(config, raw, old_raw, old_events):
    modules = ("__main__", "daily", "events", "phase6_batch", "phase6_book", "phase6_daily",
               "phase6_daily_data", "phase6_daily_wf", "phase6_report", "phase7",
               "phase8", "phase8_data", "phase8_wf")
    sources = [config, *(Path(__file__).with_name(name + ".py") for name in modules)]
    if old_events:
        sources.append(old_events)
    for archive in filter(None, (raw, old_raw)):
        for dataset in ("daily", "financials", "master", "topix", "calendar"):
            sources.extend(archive / dataset / name for name in ("active.json", "manifest.json"))
            # Verify actual snapshot payloads, even on resume.
            files(archive, dataset)
    return {p.as_posix(): digest(p) for p in sources}


def progress(out, stage, **details):
    atomic_json(out/"progress.json", dict(stage=stage, utc=datetime.now(timezone.utc).isoformat(), **details))
    print(stage, details, flush=True)
    if (out/"pause").exists():
        raise KeyboardInterrupt("pause file present")


def prepare(cfg, raw, old_raw, old_events, out, pairs):
    if all((out/f"paths_{h}_{p}.parquet").exists() for h, p in pairs) and (out/"quality.json").exists():
        return
    progress(out, "input audit and disclosures")
    events, sessions, bars, market, closes, quality = inputs(raw, old_raw, old_events, cfg)
    signals = make_signals(events, sessions, bars, market, closes)
    if signals.empty:
        raise ValueError("No eligible daily signals")
    if not ((signals.release < signals.signal_time) & (signals.signal_time < signals.order_time)
            & (signals.order_time < signals.fill_time)).all():
        raise ValueError("Release/signal/order/fill chronology failed")
    save(market.reset_index(), out/"market.parquet")
    save(signals, out/"signals.parquet")
    quality.update(first_session=str(sessions[0].date()), last_session=str(sessions[-1].date()),
                   sessions=len(sessions), signal_rows=len(signals), signal_events=signals.event_id.nunique(),
                   signals_by_method={str(k): int(v) for k, v in signals.groupby("method").size().items()})
    atomic_json(out/"quality.json", quality)
    for hold, price in pairs:
        name = f"paths_{hold}_{price}"
        target = out/f"{name}.parquet"
        if not target.exists():
            frame = paths(signals, bars, sessions, closes, hold, price).assign(hold=hold, exit_price=price)
            if not frame.loc[frame.closed, "label_end"].gt(frame.loc[frame.closed, "fill_time"]).all():
                raise ValueError(f"{name}: invalid label chronology")
            save(frame, target)
        progress(out, name)


def score_all(out, pairs, cfg, sessions, ranges):
    catalogue, audit, streams, forward_paths = [], [], {}, []
    first_id = 0
    wf_first = min(start for _, folds in schedules(len(sessions), cfg) for start, _ in folds)
    for hold, price in pairs:
        tag = f"{hold}_{price}"
        spec_file = out/f"candidates_{tag}.parquet"
        score_file = out/f"scores_{tag}.parquet"
        stream_file = out/f"streams_{tag}.npz"
        wf_file = out/f"wf_paths_{tag}.parquet"
        if not all(f.exists() for f in (spec_file, score_file, stream_file, wf_file)):
            progress(out, f"scoring {tag}")
            frame = pd.read_parquet(out/f"paths_{tag}.parquet")
            specs, scores, ret = score_paths(frame, cfg, sessions, ranges, first_id)
            save(specs, spec_file)
            save(scores, score_file)
            pending = stream_file.with_suffix(".tmp.npz")
            np.savez(pending, **{"_".join(map(str, k)): v for k, v in ret.items()})
            pending.replace(stream_file)
            frame = frame.loc[frame.start.ge(wf_first)].copy()
            # The journal records the dominant filled order selected by the shared book.
            frame["event_id"] += "|" + frame.method + "|" + frame.hold.astype(str)
            save(frame, wf_file)
        specs = pd.read_parquet(spec_file)
        catalogue.append(specs)
        audit.append(pd.read_parquet(score_file))
        with np.load(stream_file) as saved:
            streams.update({tuple(map(int, k.split("_"))): saved[k] for k in saved.files})
        forward_paths.append(pd.read_parquet(wf_file))
        first_id += len(specs)
    return pd.concat(catalogue, ignore_index=True), pd.concat(audit, ignore_index=True), streams, pd.concat(forward_paths, ignore_index=True)


def replay_condition(trades, specs, selection, sessions, cfg):
    logs = []
    def recorder(mode):
        def record(order, day, side, gross, cost, entry):
            logs.append((mode, day, order.event_id, side, gross, cost, entry))
        return record
    active = set(selection.loc[selection.weight.gt(0), "id"])
    specs = specs.loc[specs.id.isin(active)]
    daily = replay(trades, specs, selection, sessions, cfg,
                   journals={m: recorder(m) for m in selection["mode"].unique()})
    daily = daily.loc[daily.date.ge(sessions[selection.start.min()])].copy()
    log = pd.DataFrame(logs, columns=["mode", "day", "tag", "side", "gross", "cost", "entry"])
    log = log.astype({"gross": float, "cost": float, "entry": bool})
    log["date"] = sessions.take(log.day.to_numpy(dtype=int))
    log[["event", "method", "hold"]] = pd.DataFrame(
        [tag.rsplit("|", 2) for tag in log.tag], index=log.index, columns=range(3))
    log = log.drop(columns=["tag", "day"])
    log["net_capital"] = np.nan
    for mode, series in daily.groupby("mode"):
        events = log.loc[log["mode"].eq(mode)]
        expected = series.set_index("date").net
        validate_journal(events, expected)
        if int(events.entry.sum()) != int(series.fills.sum()):
            raise ValueError(f"{mode}: journal fill count differs from the book")
        if len(events):
            log.loc[events.index, "net_capital"] = linked_journal(events, expected).net_capital
    return daily, log


def execute(config, raw, old_raw, old_events, out):
    cfg = json.loads(config.read_text(encoding="utf-8-sig"))
    if not cfg["holds"] or any(not isinstance(h, int) or not 1 <= h <= 40 for h in cfg["holds"]):
        raise ValueError("Holding horizons must be within 1–40 sessions")
    signature = provenance(config, raw, old_raw, old_events)
    manifest = out/"inputs.json"
    if manifest.exists() and json.loads(manifest.read_text(encoding="utf-8")) != signature:
        raise ValueError("Inputs or code changed. Use a new --out directory.")
    atomic_json(manifest, signature)
    pairs = [(h, p) for h in sorted(set(cfg["holds"])) for p in ("O", "C")]
    prepare(cfg, raw, old_raw, old_events, out, pairs)
    sessions = pd.DatetimeIndex(pd.read_parquet(out/"market.parquet").Date)
    grids = list(schedules(len(sessions), cfg))
    ranges = sorted(set().union(*(intervals(folds, cfg) for _, folds in grids)))
    specs, scores, streams, trades = score_all(out, pairs, cfg, sessions, ranges)
    available = set(trades[["method", "entry", "hold", "exit_price"]].itertuples(index=False, name=None))
    # Keep all catalogue candidates, including those with no eligible trade in the WF.
    missing = specs.loc[~specs.iloc[:, 1:5].apply(tuple, axis=1).isin(available)]
    if not missing.empty:
        # Retain the corresponding historical rows so Phase 6 replay can locate the empty WF slice.
        for (h, p), group in missing.groupby(["hold", "exit_price"]):
            frame = pd.read_parquet(out/f"paths_{h}_{p}.parquet")
            fallback = frame.merge(group[["method", "entry"]].drop_duplicates(), on=["method", "entry"])
            trades = pd.concat([trades, fallback.drop_duplicates(["method", "entry"])], ignore_index=True)
    save(specs, out/"candidates.parquet")
    save(scores, out/"interval_scores.parquet")
    score_index = {key: frame.sort_values("id").set_index("id") for key, frame in scores.groupby(["lo", "hi"])}
    completed = []
    for offset, folds in grids:
        for design, days, rule in conditions(cfg):
            name = f"{offset}_{design}_{days}_{rule}"
            folder = out/name
            folder.mkdir(exist_ok=True)
            if not (folder/"done.json").exists():
                progress(out, "WF replay", condition=name, completed=completed)
                history, diagnostics = select(specs, score_index, streams, folds, cfg, design, days, rule)
                daily, journal = replay_condition(trades, specs, history, sessions, cfg)
                for frame, file in ((history,"selection"), (diagnostics,"diagnostics"),
                                    (daily,"daily"), (journal,"journal")):
                    save(frame, folder/f"{file}.parquet")
                atomic_json(folder/"done.json", dict(offset=offset, design=design, days=days, rule=rule))
            completed.append(name)
    progress(out, "completed", completed=completed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("phase8.json"))
    parser.add_argument("--raw", type=Path, default=Path("data/phase8_raw"))
    parser.add_argument("--old-raw", type=Path, default=Path("data/raw"))
    parser.add_argument("--old-events", type=Path, default=Path("data/phase2/events.parquet"))
    parser.add_argument("--no-overlap", action="store_true", help="Skip overlap audit when the Phase 2/old archive is unavailable")
    parser.add_argument("--out", type=Path, default=Path("data/phase8_run"))
    args = parser.parse_args()
    if args.no_overlap:
        args.old_raw = args.old_events = None
    del args.no_overlap
    args.out.mkdir(parents=True, exist_ok=True)
    with exclusive(args.out/"run.lock"):
        try:
            execute(**vars(args))
        except KeyboardInterrupt:
            atomic_json(args.out/"status.json", {"status": "paused"})
            raise SystemExit(130)
        except Exception as exc:
            atomic_json(args.out/"status.json", {"status": "failed", "error": str(exc)})
            raise
        atomic_json(args.out/"status.json", {"status": "completed"})
