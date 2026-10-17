"""Download missing demo WFDB files directly from PhysioNet and verify SHA-256.

Existing files are verified and never replaced. New files are downloaded into a
temporary file in their target directory and published only after hash/size
checks succeed. A failed run may retain verified additions, but never modifies
any existing source file. Requires only the Python standard library.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urlsplit

from demo_catalog import RECORDS, ORIGINAL_RECORD_IDS, WINDOW_SELECTION

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source-data"
MANIFEST = ROOT / "public" / "source_manifest.json"
OFFICIAL = {
    "ludb": {"base": "https://physionet.org/files/ludb/1.0.1/", "prefix": "data/", "version": "1.0.1"},
    "qtdb": {"base": "https://physionet.org/files/qtdb/1.0.0/", "prefix": "", "version": "1.0.0"},
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def persistent_fetch(url):
    """Fetch ranges on up to four persistent HTTPS connections."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "physionet.org":
        raise ValueError("Only official PhysioNet HTTPS URLs are allowed")
    request_path = parsed.path + (("?" + parsed.query) if parsed.query else "")
    chunk_size = 16384
    cache = Path(tempfile.gettempdir()) / "openecg-source-download-cache" / sha256(url.encode("utf-8"))
    cache.mkdir(parents=True, exist_ok=True)

    def connection():
        return http.client.HTTPSConnection(parsed.hostname, timeout=30)

    def get_part(conn, start, end):
        cache_path = cache / f"{start}-{end}.json"
        if cache_path.is_file():
            try:
                saved = json.loads(cache_path.read_text("utf-8"))
                payload = bytes.fromhex(saved["hex"])
                total = int(saved["total"])
                if saved["sha256"] == sha256(payload) and len(payload) == min(end, total - 1) - start + 1:
                    return payload, total
            except (ValueError, KeyError, TypeError):
                pass
            cache_path.unlink(missing_ok=True)
        conn.request("GET", request_path, headers={"Range": f"bytes={start}-{end}", "User-Agent": "OpenECG-WebLab-coursework/1.0"})
        response = conn.getresponse()
        header = response.getheader("Content-Range", "")
        match = re.fullmatch(r"bytes\s+(\d+)-(\d+)/(\d+)", header.strip())
        payload = response.read()
        if response.status != 206 or not match:
            raise ValueError(f"Invalid official range response: {url} ({response.status})")
        actual_start, actual_end, total = map(int, match.groups())
        if (actual_start, actual_end) != (start, min(end, total - 1)) or len(payload) != actual_end - actual_start + 1:
            raise ValueError(f"Invalid official range bounds/size: {url}")
        with tempfile.NamedTemporaryFile(prefix=cache_path.name, suffix=".tmp", dir=cache, delete=False) as stream:
            staged_cache = Path(stream.name)
            stream.write(json.dumps({"total": total, "hex": payload.hex(), "sha256": sha256(payload)}).encode("utf-8"))
        try:
            os.replace(staged_cache, cache_path)
        finally:
            staged_cache.unlink(missing_ok=True)
        return payload, total

    initial = connection()
    try:
        first, total = get_part(initial, 0, chunk_size - 1)
        offsets = list(range(chunk_size, total, chunk_size))

        def worker(params):
            index, assigned = params
            conn = initial if index == 0 else connection()
            parts = []
            try:
                for offset in assigned:
                    for attempt in range(3):
                        try:
                            part, part_total = get_part(conn, offset, offset + chunk_size - 1)
                            if part_total != total:
                                raise ValueError("Official file size changed during download")
                            parts.append((offset, part))
                            print(f"range_verified: {url.rsplit('/',1)[-1]} {offset}-{offset + len(part) - 1}/{total}", flush=True)
                            break
                        except Exception:
                            conn.close()
                            if attempt == 2:
                                raise
                            conn = connection()
                return parts
            finally:
                conn.close()

        assignments = [(index, offsets[index::4]) for index in range(min(4, len(offsets)))]
        with ThreadPoolExecutor(max_workers=4) as pool:
            groups = list(pool.map(worker, assignments))
        all_parts = sorted((part for group in groups for part in group), key=lambda part: part[0])
        payload = first + b"".join(part for _offset, part in all_parts)
        if len(payload) != total:
            raise ValueError(f"Reassembled HTTP range length mismatch: {url}")
        return payload, total
    finally:
        initial.close()


def fetch(url, attempts=3):
    for attempt in range(attempts):
        try:
            return persistent_fetch(url)
        except Exception as exc:
            if attempt == attempts - 1:
                raise
            print(f"Retrying missing HTTP ranges for {url}: {type(exc).__name__}; completed chunks remain cached", flush=True)
            time.sleep(attempt + 1)


def checksum_index(dataset):
    url = OFFICIAL[dataset]["base"] + "SHA256SUMS.txt"
    payload, _ = fetch(url)
    parsed = {}
    for line in payload.decode("utf-8").splitlines():
        digest, name = line.split(maxsplit=1)
        if len(digest) != 64:
            raise ValueError(f"Malformed official checksum line: {line}")
        parsed[name.lstrip("*")] = digest.lower()
    return parsed, {"url": url, "sha256": sha256(payload), "bytes": len(payload)}


def ensure_file(item):
    target, url, expected = item
    existed = target.is_file()
    if existed:
        payload = target.read_bytes()
        content_length = None
    else:
        payload, content_length = fetch(url)
    digest = sha256(payload)
    if digest != expected:
        raise ValueError(f"SHA-256 does not match PhysioNet: {target.name}; retained existing file if any")
    if not existed:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(prefix=target.name + ".", suffix=".download", dir=target.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            # Never replace a file that appeared while this request was running.
            if target.exists():
                if sha256(target.read_bytes()) != digest:
                    raise FileExistsError(f"Concurrent source differs: {target}")
            else:
                os.link(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return {"path": target.relative_to(SOURCE).as_posix(), "url": url,
            "bytes": len(payload), "sha256": digest, "official_sha256": expected,
            "checksum_verified": True, "http_content_length": content_length,
            "action": "verified_existing" if existed else "downloaded_verified"}


def download_sources(manifest=MANIFEST):
    indexes = {dataset: checksum_index(dataset) for dataset in OFFICIAL}
    items = []
    for dataset, record, _lead, annotation, _start, _label in RECORDS:
        info = OFFICIAL[dataset]
        for extension in ("hea", "dat", annotation):
            name = f"{record}.{extension}"
            remote_path = info["prefix"] + name
            if remote_path not in indexes[dataset][0]:
                raise FileNotFoundError(f"Official checksum missing: {remote_path}")
            items.append((SOURCE / dataset / name, info["base"] + remote_path,
                          indexes[dataset][0][remote_path]))
    files = []
    for item in items:
        entry = ensure_file(item)
        files.append(entry)
        print(f"{entry['action']}: {entry['path']} ({entry['bytes']} bytes)", flush=True)
    report = {
        "schema_version": 1,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": "PhysioNet (official source only)",
        "transport": "Official versioned HTTPS URLs via four persistent range connections with an atomic per-chunk TEMP cache; retries request only missing ranges. Every Content-Range, byte count, complete size and final SHA-256 is verified; at most four range requests concurrently.",
        "verification": "All source files match the official versioned SHA256SUMS.txt; existing files were not replaced.",
        "original_record_ids": list(ORIGINAL_RECORD_IDS),
        "record_count": len(RECORDS),
        "records": [{"id": f"{d}-{r}", "dataset": d, "version": OFFICIAL[d]["version"], "record": r,
                     "lead": l, "annotation": a, "start_sec": s, "duration_sec": 10}
                    for d, r, l, a, s, _label in RECORDS],
        "window_selection": WINDOW_SELECTION,
        "official_checksum_manifests": {d: data[1] for d, data in indexes.items()},
        "files": files,
    }
    manifest = Path(manifest)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=manifest.name + ".", suffix=".tmp", dir=manifest.parent, delete=False) as stream:
        staged = Path(stream.name)
        stream.write((json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    try:
        os.replace(staged, manifest)
    finally:
        staged.unlink(missing_ok=True)
    print(f"Verified {len(files)} files for {len(RECORDS)} records; wrote {manifest}")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args()
    download_sources(args.manifest)
