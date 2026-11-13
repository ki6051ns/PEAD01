"""Reconstruct Phase 4 from the archived financial and minute snapshots."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .__main__ import files, load
from .daily import DAILY_COLUMNS, lookup, prepare_daily
from .phase4_financial import COLUMNS, financial_features
from .phase4_paths import paths_from_files
from .phase4_report import summarize


def paired_decomposition(signals, events, prices, sessions):
    eligible = {"A", "C", "B1445", "M15"}
    s = signals.loc[signals.method.isin(eligible) & signals.universe.eq("topix") &
                    signals.entry.gt(0) & signals.initial_excess.ne(0) & signals.initial_excess.notna()].copy()
    common = s.groupby("event_id").method.nunique()
    base = s.loc[s.method.eq("A"), ["event_id", "entry_date", "signal_time", "entry", "initial_excess", "factor_errors"]]
    base = base.rename(columns=lambda c: c if c == "event_id" else f"a_{c}")
    s = s.merge(base, on="event_id").merge(events[["event_id", "security_code", "announcement_date"]],
                                           on="event_id", suffixes=("", "_event"))
    s = s.reset_index(drop=True)
    ix = sessions.get_indexer(s.a_entry_date) + 4
    s["exit_date"] = pd.Series(sessions.take(ix.clip(0, len(sessions)-1))).where(ix < len(sessions))
    end = lookup(prices, s.exit_date, s.security_code)
    valid = end.factor_errors.eq(s.factor_errors) & end.factor_errors.eq(s.a_factor_errors)
    s["gross"] = (end.close / s.entry - 1).where(valid)
    s["a_gross"] = (end.close / s.a_entry - 1).where(valid)
    direction, reference = np.sign(s.initial_excess), np.sign(s.a_initial_excess)
    s["actual"] = direction * s.gross
    s["reference"] = reference * s.a_gross
    # Symmetric attribution averages the two orders of replacing entry and sign.
    s["price_effect"] = .5 * (direction + reference) * (s.gross - s.a_gross)
    s["signal_effect"] = .5 * (direction - reference) * (s.gross + s.a_gross)
    long = direction.gt(0).astype(int)
    a_long = reference.gt(0).astype(int)
    s["long_actual"] = long * s.gross
    s["long_reference"] = a_long * s.a_gross
    s["long_price_effect"] = .5 * (long + a_long) * (s.gross - s.a_gross)
    s["long_selection_effect"] = .5 * (long - a_long) * (s.gross + s.a_gross)
    s["sign_changed"] = direction.ne(reference)
    s["counterfactual_future"] = s.a_signal_time.ge(s.fill_time)
    s["phase3_common"] = s.event_id.isin(common.index[common.eq(len(eligible))])
    complete = s.loc[s.phase3_common & s.actual.notna()].groupby("event_id").method.nunique()
    s["common"] = s.event_id.isin(complete.index[complete.eq(len(eligible))])
    return s[["event_id", "method", "security_code", "announcement_date", "exit_date", "actual", "reference",
              "price_effect", "signal_effect", "sign_changed", "counterfactual_future",
              "long_actual", "long_reference", "long_price_effect", "long_selection_effect",
              "phase3_common", "common", "bar_turnover"]]


def run(raw, expanded, phase1, phase2, phase3, output, reports, figures, reuse_paths):
    output.mkdir(parents=True, exist_ok=True)
    event = pd.read_parquet(phase2 / "events.parquet")
    fin = load(raw, "financials", COLUMNS, date_column=None, strings=COLUMNS)
    features = financial_features(fin, event)
    print(f"Financial features: {len(features):,}", flush=True)
    focus = [raw, *expanded]
    sources = [path for root in focus for path in files(root, "minute")]
    sources.sort(key=lambda p: p.name)
    provenance = {}
    for name in ("financials", "daily", "topix", "calendar"):
        provenance[name] = {
            part: json.loads((raw / name / f"{part}.json").read_text()) for part in ("active", "manifest")
        }
    for root in focus:
        provenance[root.as_posix()] = {
            "active": json.loads((root / "minute" / "active.json").read_text()),
            "manifest": json.loads((root / "minute" / "manifest.json").read_text()),
        }
    for path in [phase2 / "events.parquet", phase2 / "daily_panel.parquet",
                 phase3 / "signals.parquet", phase3 / "common_entry.parquet", phase1 / "daily_returns.parquet"]:
        provenance[path.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = output / "inputs.json"
    serialized = json.dumps(provenance, indent=2)
    if reuse_paths:
        cached = json.loads(manifest.read_text(encoding="utf-8"))
        if any(cached.get(root.as_posix()) != provenance[root.as_posix()] for root in focus):
            raise ValueError("Saved phase 4 paths refer to different minute inputs")
        for name in ("daily", "calendar"):
            if name in cached and cached[name] != provenance[name]:
                raise ValueError(f"Saved phase 4 paths refer to different {name} inputs")
        key = (phase2 / "events.parquet").as_posix()
        if cached.get(key) != provenance[key]:
            raise ValueError("Saved phase 4 paths refer to different events")
    daily = prepare_daily(load(raw, "daily", DAILY_COLUMNS, strings=["Code"]))
    trading_days = pd.DatetimeIndex(daily.index.get_level_values("Date").unique()).sort_values()
    codes = event.set_index("event_id").security_code.reindex(features.event_id).reset_index(drop=True)
    disclosure = event.set_index("event_id").announcement_date.reindex(features.event_id).reset_index(drop=True)
    levels = daily[["factor_level", "factor_errors"]]

    def units(dates):
        idx = trading_days.searchsorted(dates, side="right") - 1
        matched = pd.Series(trading_days.take(idx.clip(0, len(trading_days)-1))).where(dates.notna() & (idx >= 0))
        return lookup(levels, matched, codes)

    current_units = units(disclosure)
    for source, fields in [
        ("prior_actual_source", ["EPS_yoy", "EPS_series差", "EPS_series_surprise", "EPS_actual_cross"]),
        ("EPS_company_date", ["EPS_company差", "EPS_company_surprise"]),
        ("EPS_revision_date", ["EPS_revision_amount", "EPS_revision_rate", "EPS_revision_cross"]),
    ]:
        prior_units = units(features[source])
        same = current_units.factor_level.eq(prior_units.factor_level) & current_units.factor_errors.eq(prior_units.factor_errors)
        features.loc[~same, fields] = np.nan
    features.to_parquet(output / "financial_features.parquet", index=False)
    if reuse_paths:
        paths, meta = (pd.read_parquet(output / f"{name}.parquet") for name in ("minute_paths", "path_metrics"))
        days = set(pd.read_parquet(output / "covered_sessions.parquet").session)
    else:
        paths, meta, days = paths_from_files(event, sources, daily)
        paths.to_parquet(output / "minute_paths.parquet", index=False)
        meta.to_parquet(output / "path_metrics.parquet", index=False)
        pd.DataFrame({"session": sorted(days)}).to_parquet(output / "covered_sessions.parquet", index=False)
    manifest.write_text(serialized, encoding="utf-8")
    cal = load(raw, "calendar", ["Date", "HolDiv"], strings=["HolDiv"])
    sessions = pd.DatetimeIndex(cal.loc[cal.HolDiv.isin(["1", "2"]), "Date"]).sort_values()
    signal = pd.read_parquet(phase3 / "signals.parquet")
    paired = paired_decomposition(signal, event, daily, sessions)
    legacy = pd.read_parquet(phase3 / "common_entry.parquet")[["event_id", "method", "gross_signed"]]
    paired = paired.merge(legacy.rename(columns={"gross_signed": "phase3_actual"}),
                          on=["event_id", "method"], how="left", validate="one_to_one")
    paired.to_parquet(output / "entry_decomposition.parquet", index=False)
    phase2_daily = pd.read_parquet(phase2 / "daily_panel.parquet")
    # Day 1 is the close of the session immediately following the first reaction session.
    keys = event[["event_id", "first_session", "announcement_date", "security_code", "baseline_date"]].reset_index(drop=True)
    start = sessions.get_indexer(keys.first_session) + 1
    entry_day = pd.Series(sessions.take(start.clip(0, len(sessions)-1))).where((start > 0) & (start < len(sessions)))
    entry = lookup(daily, entry_day, keys.security_code)
    market = load(raw, "topix", ["Date", "O", "C"]).set_index("Date")
    base = lookup(daily, keys.baseline_date, keys.security_code)
    total = (entry.open / base.close - 1).where(entry.factor_errors.eq(base.factor_errors))
    open_excess = total - (market.O.reindex(entry_day).to_numpy() / market.C.reindex(keys.baseline_date).to_numpy() - 1)
    keys.assign(target_date=entry_day, total=total, total_excess=open_excess).to_parquet(
        output / "daily_next_open.parquet", index=False)
    panel = []
    for horizon in (1, 3, 5, 10, 20):
        idx = start + horizon - 1
        end_date = pd.Series(sessions.take(idx.clip(0, len(sessions) - 1))).where((idx < len(sessions)) & (start > 0))
        end = lookup(daily, end_date, keys.security_code)
        raw_return = (end.close / entry.open - 1).where(end.factor_errors.eq(entry.factor_errors) & (idx < len(sessions)))
        excess = raw_return - (market.C.reindex(end_date).to_numpy() / market.O.reindex(entry_day).to_numpy() - 1)
        panel.append(keys.assign(day=horizon, entry_date=entry_day, end_date=end_date,
                                 additional=raw_return, excess=excess))
    daily_panel = pd.concat(panel, ignore_index=True)
    daily_panel.to_parquet(output / "daily_paths.parquet", index=False)
    summarize(event, features, paths, meta, days, paired, daily_panel, phase2_daily, output, reports, figures)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option, default in [("raw", "data/raw"), ("phase1", "data/phase1"), ("phase2", "data/phase2"),
                            ("phase3", "data/phase3"), ("output", "data/phase4"), ("reports", "reports"),
                            ("figures", "figures/phase4")]:
        parser.add_argument(f"--{option}", type=Path, default=Path(default))
    parser.add_argument("--expanded", type=Path, nargs="*", default=[Path("data/phase4_raw"), Path("data/phase4_nov")])
    parser.add_argument("--reuse-paths", action="store_true")
    run(**vars(parser.parse_args()))
