"""Resumable Phase 6 grid, portfolio replay and evaluation."""
import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from .phase6_inputs import attributes, daily_paths, exact_minute_paths, minute_paths
from .phase6_grid import adaptive_exit, catalogue, prepare, screen, selection, sparse_marks, spec
from .phase6_report import evaluate, report_saved, statistics


def available_specs(t, method, hold, config, sectors):
    return list(catalogue(method, hold, config, sectors if hold in ("3", "20", "to60") else []))


def chunks(paths, events, days, market, config, directory, opening, workers=1, progress=None, memory_mib=4096):
    all_specs, all_values = [], []
    sectors = sorted(events.sector.dropna().unique())
    for method, frame in paths.groupby("method"):
        hold = str(frame.hold.iloc[0])
        key = f"{method}_{hold}"
        file = directory / (key+".npz")
        specs = available_specs(frame, method, hold, config, sectors)
        if progress:
            progress(0, key)
        if file.exists():
            cached = np.load(file)
            if cached["ids"].tolist() != [c["id"] for c in specs]:
                raise ValueError("Candidate checkpoint differs from catalogue")
            values = cached["values"]
        else:
            t = prepare(frame, events, config)
            values = np.zeros((len(specs), len(days), 6))
            for exit_rule in dict.fromkeys(c["exit_rule"] for c in specs):
                part = t if exit_rule == "fixed" else adaptive_exit(t, exit_rule, opening, days)
                sparse = sparse_marks(part)
                from .phase6_batch import memory_snapshot
                rss, available = memory_snapshot()
                per_worker = max(16, int(np.ceil(len(sparse[0])*64/2**20)))
                parallel = max(1, min(workers, min(memory_mib-rss, available)//per_worker))
                jobs = [(j,c) for j,c in enumerate(specs) if c["exit_rule"] == exit_rule]
                def score(job):
                    j,c = job
                    return j, screen(part, c, sparse, days, config, market)
                with ThreadPoolExecutor(max_workers=parallel) as pool:
                    for begin in range(0,len(jobs),parallel*4):
                        for j, result in pool.map(score,jobs[begin:begin+parallel*4]):
                            values[j] = result
            pending = file.with_suffix(".tmp")
            with pending.open("wb") as stream:
                np.savez_compressed(stream, ids=np.array([c["id"] for c in specs]), values=values.astype("float32"))
            pending.replace(file)
            summary = pd.DataFrame(specs).join(statistics(values,days,pd.Series(market[1])))
            partial = file.with_suffix(".parquet")
            pending = partial.with_suffix(".tmp")
            summary.to_parquet(pending,index=False)
            pending.replace(partial)
        all_specs.extend(specs)
        all_values.append(file)
        if progress:
            progress(len(specs), key)
    return all_specs, all_values


def input_fingerprint(data, config_path):
    inputs = [config_path]
    inputs += [data / f"{file}.parquet" for file in ("phase3/signals", "phase3/summary", "phase4/financial_features",
               "phase4/minute_paths", "phase5/events", "phase5/fills", "phase5/portfolio")]
    inputs += [data / "phase4/inputs.json"]
    inputs += sorted((data / "raw").glob("*/manifest.json")) + sorted((data / "raw").glob("*/active.json"))
    return json.dumps({p.as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}, indent=2)


def run(data, config_path, output, reports, figures, forward_only=False, paths_only=False, paths_ref=None,
        stage=None, workers=1, progress=None, memory_mib=4096):
    config = json.loads(config_path.read_text())
    output.mkdir(parents=True, exist_ok=True)
    fingerprint = input_fingerprint(data,config_path)
    ck = output / "inputs.json"
    if ck.exists() and ck.read_text() != fingerprint:
        raise ValueError("Inputs or implementation changed; choose a fresh --output")
    ck.write_text(fingerprint)
    if stage == "report":
        report_saved(data,output,reports,figures,config)
        return
    grid_logic = hashlib.sha256((Path(__file__).parent / "phase6_grid.py").read_bytes()).hexdigest()[:12]
    grid_dir = output / ("grid_" + grid_logic)
    grid_dir.mkdir(exist_ok=True)
    paths_dir = output / "paths" if paths_ref is None else paths_ref
    paths_dir.mkdir(exist_ok=True)
    path_manifest = paths_dir / "inputs.json"
    if path_manifest.exists() and path_manifest.read_text() != fingerprint:
        raise ValueError("Path cache inputs differ")
    path_manifest.write_text(fingerprint)
    features_file = paths_dir / "attributes.parquet"
    ranks_file = paths_dir / "ranks.parquet"
    dates_file = paths_dir / "market.parquet"
    if dates_file.exists() and features_file.exists() and ranks_file.exists():
        events = pd.read_parquet(features_file)
        events.attrs["ranks"] = pd.read_parquet(ranks_file).set_index(["event_id","method"]).historical_rank
        topix = pd.read_parquet(dates_file)
        days = pd.DatetimeIndex(topix.index)
    else:
        signals, events, topix = attributes(data, data / "raw")
        days = daily_paths(signals, data / "raw", config, paths_dir, progress)
        saved_events = events.copy()
        saved_events.attrs = {}
        saved_events.to_parquet(features_file)
        events.attrs["ranks"].reset_index().to_parquet(ranks_file,index=False)
        pending = dates_file.with_suffix(".tmp")
        topix.reindex(days).to_parquet(pending)
        pending.replace(dates_file)
    idx = topix.reindex(days).C
    market_cc = idx.pct_change(fill_method=None).fillna(0)
    from .__main__ import load
    index_open = load(data / "raw", "topix", ["Date", "O"]).set_index("Date").O.reindex(days)
    market = np.vstack([(idx/index_open-1).fillna(0), market_cc])
    opening_frame = pd.read_parquet(paths_dir / "opening.parquet")
    opening = {c: g.set_index("Date")[["open", "factor_errors", "limit_flag"]].reindex(days).to_numpy(float).T
               for c, g in opening_frame.groupby("Code", sort=False)}
    minute_file = paths_dir / "minute.parquet"
    print_file = paths_dir / "first5.parquet"
    if not minute_file.exists():
        exact, prints = exact_minute_paths(data, days, config, progress)
        prints.rename("prints").rename_axis("event_id").reset_index().to_parquet(print_file,index=False)
        pending = minute_file.with_suffix(".tmp")
        pd.concat([exact, minute_paths(data, events, days, config)], ignore_index=True).to_parquet(pending,index=False)
        pending.replace(minute_file)
    events["first5_prints"] = pd.read_parquet(print_file).set_index("event_id").prints
    if paths_only or stage == "paths":
        return
    if stage in ("ensemble", "walkforward"):
        catalog = pd.read_parquet(output/"candidates.parquet")
        matrix = np.load(output/"screen.npy",mmap_mode="r")
        evaluate(data,paths_dir,events,opening,days,market,config,catalog.to_dict("records"),
                 matrix,catalog,output,reports,figures,stage=stage,progress=progress)
        return
    if forward_only and not events.announcement_date.gt(pd.Timestamp(config["research_end"])).any():
        pd.DataFrame(columns=["id","date","net","fills","utilization"]).to_parquet(
            output/"forward_daily.parquet",index=False)
        print("No independent forward disclosures in this snapshot.", flush=True)
        return
    specs, values = [], []
    files = [*(paths_dir / f"daily_{h}.parquet" for h in config["daily_holds"]), paths_dir / "minute.parquet"]
    if progress:
        import pyarrow.parquet as pq
        sectors = sorted(events.sector.dropna().unique())
        total = sum(len(available_specs(None,m,str(h),config,sectors))
                    for file in files for m,h in pq.read_table(file,columns=["method","hold"]).to_pandas()
                    .drop_duplicates().itertuples(index=False,name=None))
        progress(0, None, total)
    for file in files:
        for _, batch in pd.read_parquet(file).groupby("hold"):
            definitions, result = chunks(batch, events, days, market, config, grid_dir, opening, workers, progress, memory_mib)
            specs.extend(definitions)
            values.extend(result)
        print(f"Screened {file.name}: {len(specs):,} candidates total", flush=True)
    pending = output/"screen.tmp"
    matrix = np.lib.format.open_memmap(pending,mode="w+",dtype="float32",shape=(len(specs),len(days),6))
    offset = 0
    for file in values:
        with np.load(file) as saved:
            part = saved["values"]
            matrix[offset:offset+len(part)] = part
            offset += len(part)
    matrix.flush()
    catalogue_frame = pd.DataFrame(specs)
    scores = pd.concat([statistics(matrix[i:i+256],days,market_cc) for i in range(0,len(matrix),256)],
                       ignore_index=True)
    table = catalogue_frame.join(scores)
    table["eligible"] = table.fills.ge(config["minimum_fills"]) & table.sharpe.notna()
    table["ordinal"] = np.arange(len(table))
    table.to_parquet(output / "candidates.parquet", index=False)
    pd.DataFrame({"ordinal": np.arange(len(days)), "date": days}).to_parquet(output/"calendar.parquet", index=False)
    monthly = []
    for month in days.to_period("M").unique():
        mask = days.to_period("M")==month
        monthly.append(pd.DataFrame({"id": table.id, "month": str(month),
                                     "net": np.prod(1+matrix[:,mask,0].astype(float),axis=1)-1,
                                     "fills": matrix[:,mask,4].sum(axis=1)}))
    pd.concat(monthly,ignore_index=True).to_parquet(output/"candidate_monthly.parquet",index=False)
    annual = []
    for year in np.unique(days.year):
        mask=days.year==year
        annual.append(pd.DataFrame({"id": table.id, "year":year,
                                    "net": np.prod(1+matrix[:,mask,0].astype(float),axis=1)-1}))
    pd.concat(annual,ignore_index=True).to_parquet(output/"candidate_annual.parquet",index=False)
    sensitivity = []
    for bp in (0,5,10,20,30,50):
        for start in range(0,len(matrix),256):
            adjusted = matrix[start:start+256].copy()
            adjusted[:,:,0] = adjusted[:,:,1] - adjusted[:,:,5] - adjusted[:,:,2]*bp/20000
            sensitivity.append(statistics(adjusted,days,market_cc)[["annual","sharpe","max_dd"]].assign(
                id=table.id.iloc[start:start+len(adjusted)].to_numpy(),bps=bp))
    pd.concat(sensitivity,ignore_index=True).to_parquet(output/"candidate_costs.parquet",index=False)
    del matrix
    pending.replace(output/"screen.npy")
    matrix = np.load(output/"screen.npy",mmap_mode="r")
    if stage == "search":
        table.loc[table.eligible].nlargest(100,"sharpe").to_csv(output/"phase6_top_candidates.csv",index=False)
        return
    evaluate(data, paths_dir, events, opening, days, market, config, specs, matrix, scores, output, reports, figures,
             forward_only=forward_only)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name, default in [("data", "data"), ("config-path", "phase6.json"), ("output", "data/phase6_v6"),
                          ("reports", "reports"), ("figures", "figures/phase6")]:
        p.add_argument("--"+name, type=Path, default=Path(default))
    p.add_argument("--forward-only", action="store_true")
    p.add_argument("--paths-only", action="store_true")
    p.add_argument("--paths-ref", type=Path)
    p.add_argument("--mode", choices=["paths","search","ensemble","walkforward","report","all"],default="all")
    p.add_argument("--workers",type=int,default=1)
    p.add_argument("--memory-mib",type=int,default=4096)
    p.add_argument("--resume",action="store_true")
    p.add_argument("--adopt-existing",action="store_true")
    from .phase6_batch import execute
    raise SystemExit(execute(run,vars(p.parse_args())))
