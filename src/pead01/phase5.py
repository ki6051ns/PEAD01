"""Run the fixed Phase 5 conditional price-formation study."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .__main__ import load
from .phase2_report import common_ids
from .phase4_paths import trading_clock
from .phase5_execution import POINTS, replay
from .phase5_report import report

INFO = ["OP_series差", "EPS_series差", "OP_company差", "OP_revision_amount",
        "EPS_revision_amount", "op_progress_change", "OP_actual_cross"]


def market_features(topix, turnover):
    frame = topix.sort_index().copy()
    for n in (5, 20, 60):
        frame[f"market_{n}"] = frame.C.pct_change(n, fill_method=None)
    for n in (20, 60):
        frame[f"vol_{n}"] = frame.C.pct_change(fill_method=None).rolling(n).std()
    frame["vol_threshold"] = frame.vol_20.expanding(min_periods=120).median().shift()
    frame["market_turnover"] = turnover.reindex(frame.index)
    frame["market_turnover_change"] = frame.market_turnover / frame.market_turnover.rolling(20).mean().shift() - 1
    return frame.drop(columns="C")


def build(raw, phase2, phase3, phase4, output):
    meta = pd.read_parquet(phase4 / "path_metrics.parquet")
    events = pd.read_parquet(phase2 / "events.parquet").merge(meta, on="event_id", how="left")
    events = events.rename(columns={"initial": "phase2_initial"})
    sessions = pd.DatetimeIndex(pd.read_parquet(phase4 / "covered_sessions.parquet").session)
    events["covered"] = events.first_session.isin(sessions)
    events = events.loc[events.covered].reset_index(drop=True)
    universe = pd.read_parquet(phase3 / "signals.parquet", columns=["event_id", "universe", "membership_date", "loanable"])
    universe = universe.drop_duplicates()
    events = events.merge(universe, on="event_id", validate="one_to_one", how="left")
    if events.membership_date.gt(events.announcement_date).any():
        raise ValueError("Future TOPIX membership")
    features = pd.read_parquet(phase4 / "financial_features.parquet", columns=["event_id", *INFO])
    conflicts = pd.read_parquet(phase4 / "conflicts.parquet")
    events = events.merge(features, on="event_id", validate="one_to_one").merge(conflicts, on="event_id", validate="one_to_one")
    turnover = load(raw, "daily", ["Date", "Code", "Va"], strings=["Code"])
    market_turnover = turnover.groupby("Date").Va.sum(min_count=1)
    topix = load(raw, "topix", ["Date", "C"]).set_index("Date")
    events = events.merge(market_features(topix, market_turnover), left_on="attributes_date", right_index=True, how="left")
    days = pd.DatetimeIndex(turnover.Date.unique()).sort_values()
    dated = events.set_index("event_id")
    tape = turnover.loc[turnover.Code.isin(events.security_code)].pivot(index="Date", columns="Code", values="Va").reindex(days)
    for label, history in [("adv20", tape.rolling(20, min_periods=15).mean()),
                           ("adv20_sd", tape.rolling(20, min_periods=15).std())]:
        i = history.index.get_indexer(dated.attributes_date)
        j = history.columns.get_indexer(dated.security_code)
        events[label] = np.where((i >= 0) & (j >= 0), history.to_numpy()[i, j], np.nan)
    events["known_turnover"] = events.adv20
    events["capacity_1pct"] = events.known_turnover * .01
    events["volume_burst_5"] = events.first5_turnover / (events.adv20 / 65)
    events["initial"] = np.where(events.initial_excess.gt(0), "up",
                                 np.where(events.initial_excess.lt(0), "down", None))
    events["strength"] = pd.cut(events.initial_excess.abs(), [0, .01, .03, .07, np.inf],
                                labels=["<1%", "1-3%", "3-7%", "7%+"], right=False)
    def rank_band(values):
        return np.ceil(values.rank(pct=True) * 5).astype("Int64")
    events["size_quintile"] = events.groupby("year").market_cap.transform(rank_band)
    events["strength_quintile"] = events.groupby("year").initial_excess.transform(lambda v: rank_band(v.abs()))
    events["timing"] = events.announcement_bucket.replace({"closing_auction": "afternoon"})
    events["quarter"] = events.announcement_date.dt.to_period("Q").astype(str)
    events["regime"] = np.where(events.market_20.gt(0), "up_market",
                                np.where(events.market_20.notna(), "down_market", None))
    events["vol_regime"] = np.where(events.vol_20.gt(events.vol_threshold), "high_vol",
        np.where(events.vol_20.notna() & events.vol_threshold.notna(), "low_vol", None))
    events["cap_size"] = events["size"].astype("string")
    events["size_direction"] = events.cap_size + "|" + events.initial
    events["remaining_trading"] = 325 - trading_clock(events.first_minute)
    events["peak_elapsed"] = events.peak_minute - events.first_minute
    events["bottom_elapsed"] = events.bottom_minute - events.first_minute
    events["missing_share"] = (1 - events.observations / (events.remaining_trading + 2)).clip(0, 1)
    paths = pd.read_parquet(phase4 / "minute_paths.parquet")
    paths = paths.loc[paths.point.isin([f"wall_{n}" for n in POINTS])].copy()
    ids = common_ids(paths, "point", "additional_excess", [f"wall_{n}" for n in POINTS])
    events["common"] = events.event_id.isin(ids)
    events.to_parquet(output / "events.parquet", index=False)
    return events, paths, sessions


def run(raw, phase2, phase3, phase4, output, reports, figures, reuse_replay):
    output.mkdir(parents=True, exist_ok=True)
    source_pairs = [(phase2, "events"), (phase3, "signals"), (phase4, "financial_features"),
                    (phase4, "conflicts"), (phase4, "minute_paths"), (phase4, "path_metrics"), (phase4, "covered_sessions")]
    paths = [root / f"{name}.parquet" for root, name in source_pairs] + [phase4 / "inputs.json"]
    paths.extend(raw / dataset / f"{name}.json" for dataset in ("daily", "topix") for name in ("manifest", "active"))
    manifest = json.dumps({str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}, indent=2)
    manifest_path = output / "inputs.json"
    if reuse_replay and manifest_path.read_text(encoding="utf-8") != manifest:
        raise ValueError("Saved replay input fingerprints differ")
    events, paths, sessions = build(raw, phase2, phase3, phase4, output)
    print(f"{len(events):,} event sessions, {events.common.sum():,} common", flush=True)
    if reuse_replay:
        audit, trades = (pd.read_parquet(output / f"{name}.parquet") for name in ("audit", "fills"))
    else:
        audit, trades = replay(events, phase4)
        audit.to_parquet(output / "audit.parquet", index=False)
        trades.to_parquet(output / "fills.parquet", index=False)
        manifest_path.write_text(manifest, encoding="utf-8")
    report(events, paths, sessions, audit, trades, output, reports, figures)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option, default in [("raw", "data/raw"), ("phase2", "data/phase2"), ("phase3", "data/phase3"),
                            ("phase4", "data/phase4"), ("output", "data/phase5"), ("reports", "reports"),
                            ("figures", "figures/phase5")]:
        parser.add_argument(f"--{option}", type=Path, default=Path(default))
    parser.add_argument("--reuse-replay", action="store_true")
    run(**vars(parser.parse_args()))
