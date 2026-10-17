"""Build, check and package the static ECG release without network access.

Run this file from any working directory. Python 3 and Node.js must be available.
This command regenerates analysis/HTML files and the deployment ZIP, but does
not install a server, contact Huawei Cloud or upload anything to GitHub.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile


OFFLINE = Path(__file__).resolve().parent
ROOT = OFFLINE.parent
SOURCE = ROOT / "03_网站与算法源码"
sys.path.insert(0, str(SOURCE / "scripts"))
from demo_catalog import RECORDS
DEPLOY = ROOT / "02_华为云部署"
ZIP_NAME = "OpenECG_Huawei_Deploy.zip"
ZIP_FOLDER = "OpenECG_Huawei_Deploy"
PACKAGE_FILES = ("index.html", "server.py", "install.sh", "部署说明.md", "verify_server.py")
MANIFEST = ROOT / "静态发布清单_20261018.json"
PRESERVATION_MANIFESTS = (
    ROOT / "05_交接说明" / "10_扩充前十四条保护清单_20261018.json",
    SOURCE / "public" / "preservation_14_records_manifest.json",
)
GENERATION_HISTORY = SOURCE / "public" / "generation_history" / "generation_14_records_20261018.json"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def run(command, cwd):
    print("RUN:", subprocess.list2cmdline([str(part) for part in command]), flush=True)
    subprocess.run([str(part) for part in command], cwd=cwd, check=True)


def atomic_write(path, content):
    """Replace one file only after its temporary sibling has been fully written."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{path.name}.", suffix=".tmp",
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def verify_zip(path, expected):
    with zipfile.ZipFile(path) as bundle:
        names = bundle.namelist()
        if len(names) != len(expected) or set(names) != set(expected):
            raise RuntimeError("Deployment ZIP contains missing, duplicate or non-whitelisted paths")
        if bundle.testzip() is not None:
            raise RuntimeError("Deployment ZIP integrity check failed")
        for name, digest in expected.items():
            if sha256(bundle.read(name)) != digest:
                raise RuntimeError(f"Deployment ZIP hash mismatch: {name}")


def rebuild_zip():
    destination = DEPLOY / ZIP_NAME
    expected = {f"{ZIP_FOLDER}/{name}": sha256((DEPLOY / name).read_bytes()) for name in PACKAGE_FILES}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{ZIP_NAME}.", suffix=".tmp",
                                         dir=DEPLOY, delete=False) as stream:
            temporary = Path(stream.name)
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=9) as bundle:
            for name in PACKAGE_FILES:
                # Fixed timestamps and permissions make identical inputs produce
                # identical archives on Windows and Linux.
                info = zipfile.ZipInfo(f"{ZIP_FOLDER}/{name}", date_time=(2026, 10, 18, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                bundle.writestr(info, (DEPLOY / name).read_bytes(), compresslevel=9)
        verify_zip(temporary, expected)
        os.replace(temporary, destination)
        verify_zip(destination, expected)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return expected


def verify_preserved_fourteen():
    """Protect the 14 prior predictions, analyses and 42 WFDB files by bytes.

    The handoff guard is used in the working tree; the public guard is its
    path/hash-only projection used by an independently prepared repository.
    """
    prefixes = {"03_网站与算法源码/public/demo/": 14,
                "03_网站与算法源码/public/analysis/": 14,
                "03_网站与算法源码/source-data/": 42}
    for manifest_path in PRESERVATION_MANIFESTS:
        if not manifest_path.is_file():
            continue
        entries = json.loads(manifest_path.read_text(encoding="utf-8"))["files"]
        names = [entry["path"] for entry in entries]
        if len(entries) != 70 or len(set(names)) != 70:
            raise RuntimeError(f"Prior-record preservation manifest must cover 70 distinct files: {manifest_path.name}")
        if any(sum(name.startswith(prefix) for name in names) != count for prefix, count in prefixes.items()):
            raise RuntimeError(f"Prior-record preservation manifest has an unexpected scope: {manifest_path.name}")
        for entry in entries:
            path = (ROOT / entry["path"]).resolve()
            if not path.is_relative_to(ROOT) or not path.is_file():
                raise RuntimeError(f"Missing or escaped protected file: {entry['path']}")
            content = path.read_bytes()
            if len(content) != entry["bytes"] or sha256(content) != entry["sha256"]:
                raise RuntimeError(f"Previously frozen 14-record scientific file changed: {entry['path']}")


def verify_analysis_binding():
    """Bind the displayed measurements to their frozen inputs and saved outputs."""
    text = (OFFLINE / "OpenECG_Demo.html").read_text(encoding="utf-8")
    match = re.search(r'<script type="application/json" id="demo-data">([\s\S]*?)</script>', text)
    if match is None:
        raise RuntimeError("Embedded demo data not found")
    records = json.loads(match.group(1))
    expected_ids = [f"{params[0]}-{params[1]}" for params in RECORDS]
    if [record["id"] for record in records] != expected_ids:
        raise RuntimeError(f"Expected all {len(expected_ids)} distinct embedded catalog records in catalog order")
    if len(records) != 20 or any(sum(record["dataset"] == dataset for record in records) != 10 for dataset in ("LUDB", "QTDB")):
        raise RuntimeError("This release requires ten LUDB and ten QTDB records")
    for embedded in records:
        data = dict(embedded)
        analysis = data.pop("coursework")
        name = data["id"] + ".json"
        source = (SOURCE / "public/demo" / name).read_bytes()
        saved = json.loads((SOURCE / "public/analysis" / name).read_bytes())
        digest = saved.pop("sourceSha256")
        if data != json.loads(source) or digest != sha256(source) or analysis != saved:
            raise RuntimeError(f"Source/analysis/embedded data mismatch: {name}")
    provenance_path = SOURCE / "public/source_manifest.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    expected_sources = {f"{dataset}/{record}.{extension}" for dataset, record, _lead, annotation, _start, _label in RECORDS
                        for extension in ("dat", "hea", annotation)}
    source_rows = provenance["files"]
    if (provenance["record_count"] != len(RECORDS) or len(source_rows) != len(expected_sources)
            or {item["path"] for item in source_rows} != expected_sources):
        raise RuntimeError("Official source manifest does not match the demo catalog")
    for item in source_rows:
        content = (SOURCE / "source-data" / item["path"]).read_bytes()
        if (not item["checksum_verified"] or len(content) != item["bytes"]
                or sha256(content) != item["sha256"] or item["sha256"] != item["official_sha256"]):
            raise RuntimeError(f"Official source checksum mismatch: {item['path']}")
    generation_path = SOURCE / "public/generation_manifest.json"
    if generation_path.is_file():
        generation = json.loads(generation_path.read_text(encoding="utf-8"))
        outputs = generation["outputs"]
        if len(outputs) != len(expected_ids) or {item["path"] for item in outputs} != {f"demo/{rid}.json" for rid in expected_ids}:
            raise RuntimeError("Model generation manifest does not cover every catalog output")
        for item in outputs:
            content = (SOURCE / "public" / item["path"]).read_bytes()
            if len(content) != item["bytes"] or sha256(content) != item["sha256"]:
                raise RuntimeError(f"Frozen model output hash mismatch: {item['path']}")
    original_manifest = ROOT / "文件清单.json"
    if original_manifest.is_file():
        entries = json.loads(original_manifest.read_text(encoding="utf-8"))["files"]
        for entry in entries:
            if entry["path"].startswith(("03_网站与算法源码/public/demo/", "03_网站与算法源码/source-data/")):
                if sha256((ROOT / entry["path"]).read_bytes()) != entry["sha256"]:
                    raise RuntimeError(f"Frozen scientific input changed: {entry['path']}")
    verify_preserved_fourteen()


def write_manifest(zip_entries):
    files = {OFFLINE / name for name in ("release_static.py", "build_demo.py", "template.html",
                                         "base.css", "app.js", "verify.cjs", "OpenECG_Demo.html")}
    files.update(DEPLOY / name for name in (*PACKAGE_FILES, ZIP_NAME))
    files.update(SOURCE / "scripts" / name for name in ("coursework_analysis.py", "test_coursework_analysis.py"))
    files.update(path for name in ("prepare_demo.py", "test_prepare_demo.py", "demo_catalog.py", "download_demo_sources.py")
                 if (path := SOURCE / "scripts" / name).is_file())
    files.add(SOURCE / "docs" / "定量对照协议.md")
    files.add(SOURCE / "README.md")
    for optional in (ROOT / "00_先读_交接入口.md",
                     ROOT / "05_交接说明" / "source_snapshot.json",
                     ROOT / "05_交接说明" / "07_静态演示优化与验收_20261018.md",
                     ROOT / "05_交接说明" / "08_发布准备与稳健性完善_20261018.md",
                     ROOT / "05_交接说明" / "09_十四条演示与自动展示_20261018.md",
                     ROOT / "05_交接说明" / "11_二十条演示优化与发布_20261018.md",
                     OFFLINE / "prepare_github.py", SOURCE / "docs" / "GitHub发布结构.md",
                     SOURCE / "public" / "generation_manifest.json",
                     SOURCE / "public" / "source_manifest.json",
                     SOURCE / "public" / "model_replay_audit.json",
                     GENERATION_HISTORY, *PRESERVATION_MANIFESTS):
        if optional.is_file():
            files.add(optional)
    for pattern in ("public/demo/*.json", "public/analysis/*.json", "public/analysis/*.csv"):
        files.update(SOURCE.glob(pattern))
    for dataset, record, _lead, annotation, _start, _label in RECORDS:
        files.update(SOURCE / "source-data" / dataset / f"{record}.{extension}"
                     for extension in ("dat", "hea", annotation))
    entries = []
    for path in sorted(files, key=lambda item: item.relative_to(ROOT).as_posix()):
        content = path.read_bytes()
        entries.append({"path": path.relative_to(ROOT).as_posix(), "bytes": len(content), "sha256": sha256(content)})
    payload = {
        "releaseDate": "2026-10-18", "scope": "static precomputed demo only",
        "status": "local release checks passed; not evidence of browser or public deployment acceptance",
        "checks": ["coursework known-answer tests", "analysis regeneration", "static HTML build",
                   "simulated DOM checks", "frozen input/analysis/HTML binding", "official source checksum manifest binding",
                   "model generation output hash binding", "prior 14-record byte preservation guard",
                   "loopback HTTP checks", "deployment ZIP whitelist and hashes"],
        "homepageSha256": sha256((OFFLINE / "OpenECG_Demo.html").read_bytes()),
        "zipEntriesSha256": zip_entries, "files": entries,
    }
    atomic_write(MANIFEST, (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def main():
    verify_preserved_fourteen()
    node = shutil.which("node")
    if node is None:
        raise SystemExit("Node.js was not found on PATH. Install Node.js before running this release command.")
    for name in PACKAGE_FILES:
        if name != "index.html" and not (DEPLOY / name).is_file():
            raise SystemExit(f"Missing deployment input: {name}")
    run([sys.executable, SOURCE / "scripts" / "test_coursework_analysis.py"], SOURCE)
    optional_tests = SOURCE / "scripts" / "test_prepare_demo.py"
    if optional_tests.is_file():
        run([sys.executable, optional_tests], SOURCE)
    run([sys.executable, SOURCE / "scripts" / "coursework_analysis.py"], SOURCE)
    run([sys.executable, OFFLINE / "build_demo.py"], OFFLINE)
    run([node, OFFLINE / "verify.cjs", "--expected-per-source=10"], OFFLINE)
    verify_analysis_binding()
    homepage = (OFFLINE / "OpenECG_Demo.html").read_bytes()
    atomic_write(DEPLOY / "index.html", homepage)
    if (DEPLOY / "index.html").read_bytes() != homepage:
        raise RuntimeError("Offline and deployment HTML differ")
    run([sys.executable, DEPLOY / "verify_server.py"], DEPLOY)
    zip_entries = rebuild_zip()
    if zip_entries[f"{ZIP_FOLDER}/index.html"] != sha256(homepage):
        raise RuntimeError("Packaged homepage differs from the offline demo")
    write_manifest(zip_entries)
    print(f"PASS: static release, deployment archive and SHA-256 manifest: {MANIFEST}")


if __name__ == "__main__":
    main()
