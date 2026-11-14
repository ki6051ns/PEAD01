"""Snapshot authorized J-Quants bulk files through the existing CLI."""
import argparse
import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

ENDPOINTS = {
    "financials": "/fins/summary",
    "daily": "/equities/bars/daily",
    "master": "/equities/master",
    "topix": "/indices/bars/daily/topix",
    "calendar": "/markets/calendar",
    "minute": "/equities/bars/minute",
}


def cli(*args, cwd=None):
    for attempt in range(3):
        result = subprocess.run(["jquants", *args], cwd=cwd, capture_output=True)
        if result.returncode == 0:
            return result.stdout.decode("utf-8-sig")
        if b"429" not in result.stderr or attempt == 2:
            raise RuntimeError(f"J-Quants command failed: {args[0]} ({result.returncode})")
        time.sleep(60 * (attempt + 1))


def acquire(root, start, end, datasets):
    for name in datasets:
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        manifest_file = folder / "manifest.json"
        manifest = json.loads(manifest_file.read_text()) if manifest_file.exists() else {}
        listing = json.loads(cli("--output", "json", "bulk", "list", "--endpoint",
                                 ENDPOINTS[name], "--from", start, "--to", end))
        if not listing:
            raise ValueError(f"No bulk files listed for {name}")
        active = []
        for item in listing:
            key = item["Key"]
            filename = Path(key).name
            target = folder / filename
            active.append(filename)
            old = manifest.get(filename, {})
            if not (target.exists() and old.get("LastModified") == item["LastModified"]
                    and target.stat().st_size == item["Size"]
                    and hashlib.sha256(target.read_bytes()).hexdigest() == old.get("sha256")):
                with TemporaryDirectory(dir=folder) as scratch:
                    cli("bulk", "get", "--key", key, "--download", cwd=scratch)
                    downloaded = Path(scratch) / filename
                    if downloaded.stat().st_size != item["Size"]:
                        raise ValueError(f"Unexpected file size: {filename}")
                    digest = hashlib.sha256(downloaded.read_bytes()).hexdigest()
                    downloaded.replace(target)
                manifest[filename] = {**item, "sha256": digest,
                                      "retrieved_utc": datetime.now(timezone.utc).isoformat()}
                pending = manifest_file.with_suffix(".tmp")
                pending.write_text(json.dumps(manifest, indent=2))
                pending.replace(manifest_file)
        (folder / "active.json").write_text(json.dumps(active))
        print(f"{name}: {len(active)} files", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/raw"))
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument("datasets", nargs="+", choices=ENDPOINTS)
    args = parser.parse_args()
    acquire(args.root, args.start, args.end, args.datasets)
