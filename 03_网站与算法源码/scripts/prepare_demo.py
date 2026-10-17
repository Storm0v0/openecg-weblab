"""Generate the catalog's fixed ECG demos, or leave the previous output set intact.

Heavy inference dependencies are imported only after input preflight. The JSON
payloads keep the original scientific pipeline and schema. Reproduction metadata
is written separately to public/generation_manifest.json, outside demo/*.json.
Use --new-only to validate and preserve existing JSON bytes, including the four
original demos, while generating only missing catalog entries.
"""
import argparse
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
from datetime import datetime, timezone
from coursework_analysis import is_finite_number, validate_record
from demo_catalog import RECORDS, ORIGINAL_RECORD_IDS

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source-data"
OUT = ROOT / "public" / "demo"
MODEL_LABEL = "openecg 0.11.0 / v56c int8"  # Existing display label, not runtime verification.


def load_dependencies():
    import numpy as np
    import wfdb
    from scipy.signal import butter, filtfilt, iirnotch, resample_poly
    from openecg.deploy import Inference
    from openecg.qrs import detect_qrs
    return SimpleNamespace(np=np, wfdb=wfdb, butter=butter, filtfilt=filtfilt,
                           iirnotch=iirnotch, resample_poly=resample_poly,
                           Inference=Inference, detect_qrs=detect_qrs)


def filter_ecg(signal, fs: int, dependencies=None):
    dep = dependencies or load_dependencies()
    baseline = dep.filtfilt(*dep.butter(2, 0.5, btype="highpass", fs=fs), signal)
    bandpassed = dep.filtfilt(*dep.butter(3, [0.5, 40], btype="bandpass", fs=fs), baseline)
    return dep.filtfilt(*dep.iirnotch(50, 30, fs), bandpassed)


def annotation_spans(base: Path, extension: str, start: int, end: int, fs: int, dependencies=None):
    dep = dependencies or load_dependencies()
    ann = dep.wfdb.rdann(str(base), extension)
    spans, onset, kind = [], None, None
    for sample, symbol in zip(ann.sample, ann.symbol):
        if symbol == "(":
            onset, kind = int(sample), None
        elif symbol.lower() in {"p", "t"}:
            kind = symbol.upper()
        elif symbol in {"N", "L", "R", "V", "A", "Q", "F", "j", "e"}:
            kind = "QRS"
        elif symbol == ")" and onset is not None and kind is not None:
            if onset >= start and sample < end:
                spans.append({"type": kind, "start": round((onset-start)/fs, 4), "end": round((sample-start)/fs, 4)})
            onset, kind = None, None
    return spans


def make_demo(dataset: str, record: str, lead: str, annotation: str, start_sec: int,
              label: str, detector, source=SOURCE, dependencies=None):
    """Return a payload; publication happens only when all records succeed."""
    dep = dependencies or load_dependencies()
    np = dep.np
    base = Path(source) / dataset / record
    rec = dep.wfdb.rdrecord(str(base))
    source_fs = int(rec.fs)
    start = start_sec * source_fs
    end = start + 10 * source_fs
    signal = rec.p_signal[start:end, [name.lower() for name in rec.sig_name].index(lead.lower())]
    if signal.size != 10 * source_fs or not np.isfinite(signal).all():
        raise ValueError(f"Invalid window: {base}")
    raw = dep.resample_poly(signal, 250, source_fs) if source_fs != 250 else signal
    clean = filter_ecg(raw, 250, dependencies=dep)
    waves = [{"type": b.name, "start": round(b.start/250, 4), "end": round(b.end/250, 4)}
             for b in detector.predict(clean)[0]]
    peaks = dep.detect_qrs(clean, fs=250)
    rr = np.diff(peaks) / 250
    hr = 60 / rr if rr.size else np.array([])
    record_id = f"{dataset}-{record}"
    return {
        "id": record_id, "dataset": dataset.upper(), "record": record, "lead": lead,
        "label": label, "fs": 250, "sourceFs": source_fs, "startSec": start_sec,
        "unit": "mV", "mode": "precomputed", "model": MODEL_LABEL,
        "raw": np.round(raw, 5).tolist(), "filtered": np.round(clean, 5).tolist(),
        "waves": waves, "groundTruth": annotation_spans(base, annotation, start, end, source_fs, dependencies=dep),
        "rPeaks": np.round(peaks / 250, 4).tolist(),
        "rr": np.round(rr, 4).tolist(),
        "metrics": {"averageHr": round(float(np.mean(hr)), 1) if hr.size else None,
                    "minHr": round(float(np.min(hr)), 1) if hr.size else None,
                    "maxHr": round(float(np.max(hr)), 1) if hr.size else None,
                    "meanRr": round(float(np.mean(rr)), 3) if rr.size else None,
                    "rPeakCount": len(peaks)},
    }


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_snapshot(source):
    """Require each expected record and hash its local WFDB companion files."""
    source = Path(source)
    missing, paths = [], set()
    for dataset, record, _lead, annotation, _start, _label in RECORDS:
        base = source / dataset / record
        for extension in ("hea", "dat", annotation):
            path = base.with_suffix(f".{extension}")
            if not path.is_file():
                missing.append(str(path))
        paths.update(path for path in base.parent.glob(f"{record}.*") if path.is_file())
    if missing:
        raise FileNotFoundError("Required source files are missing:\n" + "\n".join(missing))
    return [{"path": path.relative_to(source).as_posix(), "bytes": path.stat().st_size,
             "sha256": sha256_file(path)} for path in sorted(paths)]


def package_versions():
    versions = {"python": sys.version.split()[0]}
    for name in ("openecg", "numpy", "scipy", "wfdb", "onnxruntime", "tflite-runtime"):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "unknown"
    return versions


def model_provenance(detector):
    """Hash only model file paths exposed by the actual instantiated detector.

    Do not infer an active model from arbitrary files found in a package/cache.
    Some runtimes load bytes and expose no filename; that is explicitly unknown.
    """
    path_names = ("model_path", "model_file", "onnx_path", "weights_path", "checkpoint_path", "path",
                  "_model_path", "_model_file", "_onnx_path", "_weights_path")
    object_names = ("model", "session", "sess", "ort_session", "predictor", "detector")
    candidates = [("detector", detector)]
    attrs = vars(detector) if hasattr(detector, "__dict__") else {}
    candidates.extend((f"detector.{name}", attrs[name]) for name in object_names if name in attrs)
    files, seen = [], set()
    for origin, obj in candidates:
        values = vars(obj) if hasattr(obj, "__dict__") else {}
        for name in path_names:
            value = values.get(name)
            if not isinstance(value, (str, os.PathLike)):
                continue
            path = Path(value).expanduser()
            # OpenECG 0.11.0 Inference passes its .path directly to TFLite.
            # Do not treat an arbitrary generic path as a model artifact.
            if name == "path" and path.suffix.lower() not in (".tflite", ".onnx", ".pt", ".pth"):
                continue
            if not path.is_absolute():
                path = Path.cwd() / path
            if not path.is_file() or path.resolve() in seen:
                continue
            seen.add(path.resolve())
            files.append({"attribute": f"{origin}.{name}", "filename": path.name,
                          "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    return {"status": "identified" if files else "unknown", "files": files,
            "reason": None if files else "The instantiated detector exposes no identifiable model file path; model hash is unknown."}


def publish_staged(entries, stage_dir, replace_file=None):
    """Atomic file replacements with rollback on a caught publication failure.

    Multiple paths cannot be replaced atomically as one filesystem operation.
    This rolls back ordinary exceptions; a process/power loss can interrupt the
    group. Backups are retained if rollback itself fails, for manual recovery.
    """
    replace_file = replace_file or os.replace
    backups, committed = {}, []
    for index, (_staged, target) in enumerate(entries):
        if target.exists():
            backup = Path(stage_dir) / f"backup-{index}"
            shutil.copy2(target, backup)
            backups[target] = backup
        else:
            backups[target] = None
    try:
        for staged, target in entries:
            replace_file(staged, target)
            committed.append(target)
    except Exception as exc:
        rollback_errors = []
        for target in reversed(committed):
            try:
                backup = backups[target]
                if backup is None:
                    target.unlink(missing_ok=True)
                else:
                    replace_file(backup, target)
            except Exception as rollback_exc:
                rollback_errors.append(f"{target}: {rollback_exc}")
        if rollback_errors:
            raise RuntimeError(f"Publication failed ({exc}); rollback incomplete. Preserve recovery directory {stage_dir}: "
                               + "; ".join(rollback_errors)) from exc
        raise RuntimeError(f"Publication failed; previous outputs restored: {exc}") from exc


def record_parameters(params):
    return {"dataset": params[0], "record": params[1], "lead": params[2],
            "annotation": params[3], "startSec": params[4], "durationSec": 10,
            "outputFs": 250}


def preserved_snapshot(out):
    """Fail closed on partial/corrupt existing outputs before loading a model."""
    preserved = {}
    for params in RECORDS:
        record_id = f"{params[0]}-{params[1]}"
        path = out / f"{record_id}.json"
        if not path.is_file():
            if record_id in ORIGINAL_RECORD_IDS:
                raise FileNotFoundError(f"--new-only requires the original frozen record: {path}")
            continue
        try:
            content = path.read_bytes()
            payload = json.loads(content)
            validate_record(payload)
            expected = {"id": record_id, "dataset": params[0].upper(), "record": params[1],
                        "lead": params[2], "startSec": params[4], "fs": 250,
                        "mode": "precomputed", "unit": "mV"}
            if any(payload.get(name) != value for name, value in expected.items()):
                raise ValueError("record id or catalog parameters do not match")
            required = {"filtered", "sourceFs", "label", "model", "rr", "metrics"}
            if not required.issubset(payload) or len(payload["raw"]) != 2500:
                raise ValueError("missing fields or incomplete ten-second signal")
            if (not is_finite_number(payload["sourceFs"]) or payload["sourceFs"] <= 0
                    or any(not isinstance(payload[key], str) or not payload[key].strip()
                           for key in ("label", "model"))):
                raise ValueError("invalid source sampling rate, label, or model metadata")
            metric_keys = {"rPeakCount", "averageHr", "minHr", "maxHr", "meanRr"}
            if (not isinstance(payload["rr"], list)
                    or len(payload["rr"]) != max(0, len(payload["rPeaks"]) - 1)
                    or any(not is_finite_number(value) or value <= 0 for value in payload["rr"])
                    or not isinstance(payload["metrics"], dict)
                    or not metric_keys.issubset(payload["metrics"])
                    or payload["metrics"].get("rPeakCount") != len(payload["rPeaks"])):
                raise ValueError("incomplete beat measurements")
            if any(value is not None and not is_finite_number(value)
                   for key, value in payload["metrics"].items() if key in metric_keys):
                raise ValueError("invalid beat measurements")
            json.dumps(payload, allow_nan=False)
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f"Invalid existing frozen JSON; refusing --new-only: {path}: {exc}") from exc
        preserved[record_id] = {"path": f"{out.name}/{path.name}", "bytes": len(content),
                                "sha256": hashlib.sha256(content).hexdigest(),
                                "recordParameters": record_parameters(params)}
    return preserved


def verify_preserved(out, preserved):
    for record_id, item in preserved.items():
        path = out / f"{record_id}.json"
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            raise RuntimeError(f"Existing frozen JSON changed during generation: {record_id}")


def generate_demos(source=SOURCE, out=OUT, dependency_loader=None, demo_builder=None,
                   versions_provider=None, replace_file=None, new_only=False):
    source, out = Path(source), Path(out)
    inputs = source_snapshot(source)  # Fail before importing or constructing a model.
    preserved = preserved_snapshot(out) if new_only else {}
    generated_params = [p for p in RECORDS if f"{p[0]}-{p[1]}" not in preserved]
    if generated_params:
        dep = (dependency_loader or load_dependencies)()
        detector = dep.Inference()
        model_info = model_provenance(detector)
    else:
        dep, detector = None, None
        model_info = {"status": "not-run", "files": [], "reason": "Every catalog entry was preserved; no model was constructed."}
    builder = demo_builder or make_demo
    payloads = []
    for params in generated_params:
        payload = builder(*params, detector=detector, source=source, dependencies=dep)
        if payload.get("id") != f"{params[0]}-{params[1]}":
            raise ValueError(f"Unexpected output record id for {params[:2]}")
        payloads.append(payload)
    if source_snapshot(source) != inputs:
        raise RuntimeError("Source files changed during generation; previous outputs kept.")
    verify_preserved(out, preserved)
    if not generated_params:
        # This is verification only. In particular, do not replace a previous
        # manifest containing evidence of actual inference with a no-model run.
        # When no old manifest exists, do not manufacture one either.
        return {"schemaVersion": 2, "status": "verified-no-op",
                "publicationPerformed": False, "mode": "new-only",
                "recordCount": len(RECORDS), "generatedCount": 0,
                "preservedCount": len(preserved), "preservedExisting": list(preserved.values()),
                "generatedRecordParameters": [], "modelAppliesToRecordIds": [],
                "model": model_info, "sources": inputs,
                "outputs": [{key: value for key, value in item.items() if key != "recordParameters"}
                            for item in preserved.values()],
                "publication": "No files were written. Existing inference provenance, if present, was preserved byte for byte."}
    # No public JSON is written until every fixed record has generated successfully.
    out.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".prepare-demo-", dir=out.parent))
    preserve_stage = False
    try:
        entries, generated_outputs = [], {}
        for index, payload in enumerate(payloads):
            staged = stage / f"record-{index}.json"
            staged.write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False), encoding="utf-8")
            target = out / f"{payload['id']}.json"
            entries.append((staged, target))
            generated_outputs[payload["id"]] = {"path": f"{out.name}/{target.name}", "bytes": staged.stat().st_size,
                                                "sha256": sha256_file(staged)}
        outputs = [{key: value for key, value in (preserved.get(f"{p[0]}-{p[1]}") or generated_outputs[f"{p[0]}-{p[1]}"]).items()
                    if key != "recordParameters"} for p in RECORDS]
        manifest = {"schemaVersion": 2, "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
                    "status": "complete", "recordCount": len(RECORDS),
                    "publicationPerformed": True,
                    "mode": "new-only" if new_only else "all",
                    "generatedCount": len(generated_params), "preservedCount": len(preserved),
                    "preservedExisting": list(preserved.values()),
                    "generatedRecordParameters": [record_parameters(p) for p in generated_params],
                    "modelAppliesToRecordIds": list(generated_outputs),
                    "generatorSha256": sha256_file(__file__),
                    "catalogSha256": sha256_file(Path(__file__).with_name("demo_catalog.py")),
                    "packages": (versions_provider or package_versions)(),
                    "payloadModelLabel": MODEL_LABEL,
                    "payloadModelLabelIsRuntimeVerification": False,
                    "model": model_info, "sources": inputs, "outputs": outputs,
                    "recordParameters": [record_parameters(p) for p in RECORDS],
                    "publication": "Each file uses atomic replace; caught failures roll back the group. Process/power-loss atomicity across the group is not guaranteed."}
        staged_manifest = stage / "manifest.json"
        staged_manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        entries.append((staged_manifest, out.parent / "generation_manifest.json"))
        verify_preserved(out, preserved)
        try:
            publish_staged(entries, stage, replace_file=replace_file)
        except RuntimeError as exc:
            preserve_stage = "rollback incomplete" in str(exc)
            raise
    finally:
        if not preserve_stage:
            # Cleanup is confined to the exact staging directory created above.
            # Resolve it before recursive deletion, including on Windows.
            resolved_stage = stage.resolve()
            if resolved_stage.parent != out.parent.resolve() or not resolved_stage.name.startswith(".prepare-demo-"):
                raise RuntimeError(f"Unsafe staging cleanup target; preserved: {resolved_stage}")
            shutil.rmtree(stage)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--new-only", action="store_true",
                        help="Keep all valid existing catalog JSON bytes; require all four original frozen records; generate missing records only")
    args = parser.parse_args(argv)
    try:
        manifest = generate_demos(new_only=args.new_only)
    except Exception as exc:
        print(f"ERROR: demo generation failed: {exc}", file=sys.stderr)
        return 1
    if manifest.get("publicationPerformed") is False:
        print(f"Verified {manifest['recordCount']} existing records. No model was run and no files were written; existing generation_manifest.json and inference provenance, if present, were preserved.")
        return 0
    print(f"Published catalog of {manifest['recordCount']} records: generated {manifest['generatedCount']}, preserved {manifest['preservedCount']}; public/generation_manifest.json updated.")
    if manifest["model"]["status"] == "unknown":
        print("NOTE: active model file hash is unknown; see generation_manifest.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
