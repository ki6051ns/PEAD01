"""Windows batch lifecycle, durable checkpoints and compact progress."""
import contextlib
import ctypes
from ctypes import wintypes
from datetime import datetime
import json
import os
import time
import traceback
from pathlib import Path

STAGES = ("paths", "search", "ensemble", "walkforward", "report")


class Counters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in ("peak", "working", "peak_paged", "paged",
                                             "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile")]


class MemoryStatus(ctypes.Structure):
    _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD)] + [
        (name, ctypes.c_ulonglong) for name in ("total", "available", "pagefile", "available_pagefile",
                                               "virtual", "available_virtual", "extended")]


def memory_snapshot():
    if os.name != "nt":
        return 0, 4096
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    get_info = ctypes.windll.psapi.GetProcessMemoryInfo
    get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    get_info(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
    memory = MemoryStatus()
    memory.length = ctypes.sizeof(memory)
    kernel.GlobalMemoryStatusEx(ctypes.byref(memory))
    return int(counters.working // 2**20), int(memory.available // 2**20)


def atomic_json(path, content):
    pending = path.with_suffix(".tmp")
    pending.write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")
    pending.replace(path)


def run_stages(run, options, mode, resume, update, markers):
    for stage in STAGES if mode == "all" else (mode,):
        marker = markers / f"{stage}.json"
        if resume and marker.exists():
            update(stage=stage, last_batch="checkpoint")
            continue
        update(stage=stage, last_batch=None, **({"complete":0, "total":None} if stage == "search" else {}))
        run(**options, stage=stage)
        atomic_json(marker, {"finished": datetime.now().astimezone().isoformat()})


def execute(run, options):
    output = options["output"]
    output.mkdir(parents=True, exist_ok=True)
    logs = output / "logs"
    logs.mkdir(exist_ok=True)
    mode = options.pop("mode")
    adopt = options.pop("adopt_existing")
    resume = options.pop("resume")
    memory = options.pop("memory_mib")
    requested = options.pop("workers")
    if requested < 1 or memory < 256:
        raise SystemExit("--workers must be positive; --memory-mib must be at least 256")
    rss, available = memory_snapshot()
    recommended = max(1, min(os.cpu_count() or 1, max(0, min(available, memory-rss))//256))
    workers = min(requested, recommended)
    started = time.monotonic()
    state = dict(started=datetime.now().astimezone().isoformat(), status="running", errors=0,
                 complete=0, total=None, requested_workers=requested, workers=workers,
                 recommended_workers=recommended, memory_budget_mib=memory)
    progress = output / "phase6_progress.json"
    checkpoints = output / "checkpoints"
    checkpoints.mkdir(exist_ok=True)

    def update(**changes):
        state.update(changes)
        state["rss_mib"], state["available_mib"] = memory_snapshot()
        state["conditions_per_second"] = round(state["complete"] / max(1, time.monotonic()-started), 2)
        state["progress_pct"] = round(100*state["complete"]/state["total"], 2) if state["total"] else None
        atomic_json(progress,state)

    def batch(count, key, total=None):
        update(complete=state["complete"]+count, last_batch=key,
               total=total if total is not None else state["total"])
        if (output/"phase6.pause").exists():
            raise KeyboardInterrupt("Cooperative pause")

    original = options["config_path"].read_bytes()
    import hashlib
    source = options["data"]
    files = [*sorted(source.glob("phase[345]/*.parquet")), *sorted(source.glob("raw/*/*.json")),
             source/"phase4/inputs.json"]
    digest = hashlib.sha256(original)
    for path in files:
        digest.update(path.as_posix().encode())
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(2**20), b""):
                digest.update(chunk)
    for path in sorted(Path(__file__).parent.glob("phase6*.py")):
        digest.update(path.read_bytes())
    markers = checkpoints / digest.hexdigest()[:16]
    markers.mkdir(exist_ok=True)
    lock = output/"phase6.lock"
    # OS releases the exclusive byte lock when the process exits.
    with lock.open("a+b") as guard:
        if os.name == "nt":
            import msvcrt
            guard.seek(0)
            try:
                msvcrt.locking(guard.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                print("status=already_running errors=1")
                return 1
        update()
        print(f"start={state['started']} workers={workers} recommended_workers={recommended}", flush=True)
        options.update(workers=workers,progress=batch,memory_mib=memory)
        forwarded = options["paths_only"] or options["forward_only"]
        code = 0
        with (logs/"phase6_run.log").open("a",encoding="utf-8") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            try:
                if adopt:
                    import pandas as pd
                    from .phase6 import input_fingerprint
                    if (output/"inputs.json").read_text() != input_fingerprint(options["data"], options["config_path"]):
                        raise ValueError("Existing results use different inputs")
                    grid = hashlib.sha256((Path(__file__).parent/"phase6_grid.py").read_bytes()).hexdigest()[:12]
                    import numpy as np
                    found = pd.read_parquet(output/"candidates.parquet", columns=["id"])
                    ids = []
                    for item in (output/("grid_"+grid)).glob("*.npz"):
                        with np.load(item) as chunk:
                            ids.extend(chunk["ids"].tolist())
                    if sorted(ids) != sorted(found.id):
                        raise ValueError("Existing result catalogue differs from current checkpoint grid")
                    samples = pd.read_parquet(output/"comparison.parquet",columns=["sample"])
                    if set(samples["sample"]) != {"IS","WF"}:
                        raise ValueError("Existing ensemble or walk-forward results are incomplete")
                    for name in ("portfolios", "fixed_baselines", "exact_finalists", "eigenvalues",
                                 "dependence", "screen_max_stat", "selection"):
                        pd.read_parquet(output/f"{name}.parquet").shape
                    for stage in STAGES[:-1]:
                        atomic_json(markers/f"{stage}.json", {"adopted": True})
                    resume = True
                    update(complete=len(found), total=len(found))
                if forwarded:
                    run(**options)
                else:
                    run_stages(run,options,mode,resume,update,markers)
                update(status="completed",exit_code=0)
            except KeyboardInterrupt:
                code = 130
                update(status="paused",exit_code=code)
            except Exception as exc:
                code = 1
                traceback.print_exc()
                update(status="failed",exit_code=code,errors=1,error=f"{type(exc).__name__}: {exc}")
        print(f"status={state['status']} complete={state['complete']} total={state['total']} "
              f"progress_pct={state['progress_pct']} speed={state['conditions_per_second']} errors={state['errors']}")
        return code
