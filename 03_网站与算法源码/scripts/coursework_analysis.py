"""Reproducible measurements from frozen ECG predictions; standard library only.

This is a reference-centric demonstration comparison, not a detection benchmark.
Unpaired predictions are unscored because annotation coverage is incomplete.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from bisect import bisect_left, bisect_right
from pathlib import Path
from statistics import mean, median

PROTOCOL_VERSION = "coursework-v1"
IMPLEMENTATION_REVISION = "20261018-measurement-fixes"
MATCH_CENTER_MS = 150.0
BOUNDARY_LIMITS_MS = {"P": (50.0, 50.0), "QRS": (40.0, 40.0), "T": (50.0, 100.0)}
EPS = 1e-8


def rounded(value):
    return None if value is None else round(float(value), 3)


def average(values):
    return rounded(mean(values)) if values else None


def is_finite_number(value):
    # bool is an int subclass, but is never a valid signal/time measurement.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def validate_record(record):
    if not isinstance(record, dict):
        raise ValueError("Recording must be an object")
    if not isinstance(record.get("id"), str) or not record["id"].strip():
        raise ValueError("Recording id must be a non-empty string")
    fs = record.get("fs")
    if not is_finite_number(fs) or fs <= 0:
        raise ValueError("Sampling rate must be finite and positive")
    raw = record.get("raw")
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError("Raw signal must be a non-empty array")
    if any(not is_finite_number(value) for value in raw):
        raise ValueError("Raw signal values must be finite numbers")
    if "filtered" in record:
        filtered = record["filtered"]
        if (not isinstance(filtered, (list, tuple)) or len(filtered) != len(raw)
                or any(not is_finite_number(value) for value in filtered)):
            raise ValueError("Filtered signal must contain one finite number per raw sample")
    duration = len(raw) / fs
    if not math.isfinite(duration) or not math.isfinite(duration * 1000) or duration <= 0:
        raise ValueError("Recording duration must be positive and finite in milliseconds")
    for key in ("waves", "groundTruth"):
        waves = record.get(key)
        if not isinstance(waves, (list, tuple)):
            raise ValueError(f"{key} must be an array")
        for index, wave in enumerate(waves):
            if not isinstance(wave, dict):
                raise ValueError(f"Invalid {key} wave at index {index}")
            a, b = wave.get("start"), wave.get("end")
            if (not isinstance(wave.get("type"), str) or wave["type"] not in BOUNDARY_LIMITS_MS
                    or not all(is_finite_number(x) for x in (a, b))):
                raise ValueError(f"Invalid {key} wave at index {index}")
            if not 0 <= a < b <= duration:
                raise ValueError(f"Invalid {key} interval at index {index}")
    peaks = record.get("rPeaks")
    if not isinstance(peaks, (list, tuple)):
        raise ValueError("R peaks must be an array")
    if any(not is_finite_number(t) or not 0 <= t < duration for t in peaks):
        raise ValueError("Invalid R peak")
    if any(a >= b for a, b in zip(peaks, peaks[1:])):
        raise ValueError("R peaks must be strictly increasing")
    return duration


def pair_intervals(predicted, references):
    """Order-preserving one-to-one pairing: max count, then min boundary error.

    Candidate pairs must have positive temporal overlap and centers <=150 ms
    apart. This generous association gate is separate from boundary acceptance.
    Input items are (original_index, wave_dict) sorted by start/end/index.
    """
    # Bottom-up suffix DP avoids Python's recursion limit on longer/dense
    # recordings. Only the current and following rows of states are retained.
    empty = (0, 0.0, ())
    following = [empty] * (len(references) + 1)
    for i in range(len(predicted) - 1, -1, -1):
        current = [empty] * (len(references) + 1)
        pi, p = predicted[i]
        for j in range(len(references) - 1, -1, -1):
            choices = [following[j], current[j + 1]]
            ri, r = references[j]
            center_ms = abs(p["start"] + p["end"] - r["start"] - r["end"]) * 500
            overlap = min(p["end"], r["end"]) - max(p["start"], r["start"])
            if overlap > EPS and center_ms <= MATCH_CENTER_MS + EPS:
                count, cost, pairs = following[j + 1]
                error = abs(p["start"] - r["start"]) + abs(p["end"] - r["end"])
                choices.append((count + 1, cost + error, ((pi, ri),) + pairs))
            # Deterministic ties, without reuse of any predicted or reference wave.
            current[j] = min(choices, key=lambda item: (-item[0], round(item[1], 12), item[2]))
        following = current
    return following[0][2]


def compare_annotations(record):
    rows, summaries = [], []
    for kind, (on_limit, off_limit) in BOUNDARY_LIMITS_MS.items():
        predicted = sorted(((i, w) for i, w in enumerate(record["waves"]) if w["type"] == kind),
                           key=lambda x: (x[1]["start"], x[1]["end"], x[0]))
        references = sorted(((i, w) for i, w in enumerate(record["groundTruth"]) if w["type"] == kind),
                            key=lambda x: (x[1]["start"], x[1]["end"], x[0]))
        pairs = {ri: pi for pi, ri in pair_intervals(predicted, references)}
        kind_rows, onset_errors, offset_errors, duration_errors = [], [], [], []
        for ri, ref in references:
            pi = pairs.get(ri)
            pred = record["waves"][pi] if pi is not None else None
            on = (pred["start"] - ref["start"]) * 1000 if pred else None
            off = (pred["end"] - ref["end"]) * 1000 if pred else None
            on_ok = on is not None and abs(on) <= on_limit + EPS
            off_ok = off is not None and abs(off) <= off_limit + EPS
            if pred is not None:
                onset_errors.append(on)
                offset_errors.append(off)
                duration_errors.append(off - on)
            kind_rows.append({
                "type": kind, "referenceIndex": ri + 1, "predictionIndex": pi + 1 if pi is not None else None,
                "referenceStartSec": ref["start"], "referenceEndSec": ref["end"],
                "referenceDurationMs": rounded((ref["end"] - ref["start"]) * 1000),
                "predictionStartSec": pred["start"] if pred else None,
                "predictionEndSec": pred["end"] if pred else None,
                "predictionDurationMs": rounded((pred["end"] - pred["start"]) * 1000) if pred else None,
                "onsetErrorMs": rounded(on), "offsetErrorMs": rounded(off),
                "durationErrorMs": rounded(off - on) if pred else None,
                "onsetWithinLimit": on_ok, "offsetWithinLimit": off_ok,
                "bothWithinLimits": on_ok and off_ok, "matched": pred is not None,
            })
        matched = [r for r in kind_rows if r["matched"]]
        n, m = len(references), len(matched)
        summaries.append({
            "type": kind, "referenceCount": n, "predictionCount": len(predicted), "matchedCount": m,
            "unmatchedReferenceCount": n - m, "unscoredPredictionCount": len(predicted) - m,
            "pairingRatePct": rounded(m / n * 100) if n else None,
            "onsetMaeMs": average([abs(value) for value in onset_errors]),
            "offsetMaeMs": average([abs(value) for value in offset_errors]),
            "onsetBiasMs": average(onset_errors),
            "offsetBiasMs": average(offset_errors),
            "durationMaeMs": average([abs(value) for value in duration_errors]),
            "onsetLimitMs": on_limit, "offsetLimitMs": off_limit,
            "bothWithinCount": sum(r["bothWithinLimits"] for r in kind_rows),
            # Unmatched references remain in the denominator; errors are matched-only.
            "bothWithinRatePct": rounded(sum(r["bothWithinLimits"] for r in kind_rows) / n * 100) if n else None,
        })
        rows.extend(kind_rows)
    return {
        "scope": "reference-centric-demo-only", "summaries": summaries,
        "rows": sorted(rows, key=lambda r: r["referenceIndex"]),
        "precision": None, "f1": None,
    }


def measure_qrs(record, duration):
    rows, unrounded_values = [], []
    peaks = record["rPeaks"]
    peak_memberships = [0] * len(peaks)
    memberships = []
    for index, wave in enumerate(record["waves"]):
        if wave["type"] != "QRS":
            continue
        # A boundary at the first or last sample may be clipped by the window.
        edge = wave["start"] <= EPS or wave["end"] >= duration - 1 / record["fs"] - EPS
        first_peak = bisect_left(peaks, wave["start"] - EPS)
        last_peak = bisect_right(peaks, wave["end"] + EPS)
        peak_count = last_peak - first_peak
        memberships.append((first_peak, last_peak))
        for peak_index in range(first_peak, last_peak):
            peak_memberships[peak_index] += 1
        if not edge:
            unrounded_values.append((wave["end"] - wave["start"]) * 1000)
        rows.append({
            "qrsNumber": len(rows) + 1, "predictionIndex": index + 1,
            "startSec": wave["start"], "endSec": wave["end"],
            "durationMs": rounded((wave["end"] - wave["start"]) * 1000),
            "rPeakSec": None, "rPeakCountInInterval": peak_count,
            "edgeClipped": edge, "includedInStats": not edge,
        })
    # Count every containing QRS, including intervals containing multiple peaks:
    # such an interval still makes a competing single-peak interval ambiguous.
    for row, (first_peak, last_peak) in zip(rows, memberships):
        if first_peak == last_peak:
            row["rPeakAssociation"] = "no-peak"
        elif last_peak - first_peak > 1:
            row["rPeakAssociation"] = "multiple-peaks"
        elif peak_memberships[first_peak] > 1:
            row["rPeakAssociation"] = "shared-peak"
        else:
            row["rPeakSec"] = peaks[first_peak]
            row["rPeakAssociation"] = "unique"
    values = unrounded_values
    return {"rows": rows, "summary": {
        "totalCount": len(rows), "includedCount": len(values), "edgeExcludedCount": len(rows) - len(values),
        "meanMs": average(values), "medianMs": rounded(median(values)) if values else None,
        "minMs": rounded(min(values)) if values else None, "maxMs": rounded(max(values)) if values else None,
        "sampleStepMs": rounded(1000 / record["fs"]),
    }}


def analyze_record(record):
    duration = validate_record(record)
    return {
        "protocolVersion": PROTOCOL_VERSION, "implementationRevision": IMPLEMENTATION_REVISION,
        "recordId": record["id"],
        "protocol": {"matchCenterLimitMs": MATCH_CENTER_MS, "positiveOverlapRequired": True,
                     "pairing": "same-class, order-preserving, maximum-cardinality then minimum-boundary-error",
                     "boundaryLimitsMs": {k: {"onset": v[0], "offset": v[1]} for k, v in BOUNDARY_LIMITS_MS.items()},
                     "errorSign": "prediction minus reference", "errorStatistics": "matched pairs only",
                     "acceptanceDenominator": "all reference intervals of that class, unmatched fail",
                     "unpairedPredictions": "unscored: incomplete annotation coverage; not false positives",
                     "noReferences": "not evaluable; all metrics null",
                     "qrsStatistics": "predicted intervals excluding clipped window edges; independent of R-peak linkage",
                     "rPeakAssociation": "one peak in the interval, contained by exactly one predicted QRS interval",
                     "rounding": "statistics use unrounded times; output milliseconds rounded to three decimals",
                     "scope": "curated demo comparison, not independent generalization or clinical validation"},
        "qrs": measure_qrs(record, duration), "comparison": compare_annotations(record),
    }


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=project / "public/demo")
    parser.add_argument("--output-dir", type=Path, default=project / "public/analysis")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    all_qrs, all_comparisons, all_summaries = [], [], []
    for source in sorted(args.input_dir.glob("*.json")):
        raw = source.read_bytes()
        record = json.loads(raw)
        result = analyze_record(record)
        result["sourceSha256"] = hashlib.sha256(raw).hexdigest()
        (args.output_dir / source.name).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for target, rows in ((all_qrs, result["qrs"]["rows"]), (all_comparisons, result["comparison"]["rows"]),
                             (all_summaries, result["comparison"]["summaries"])):
            target.extend({"recordId": record["id"], **row} for row in rows)
        print(record["id"], "QRS", result["qrs"]["summary"], "matched/reference",
              [(s["type"], s["matchedCount"], s["referenceCount"]) for s in result["comparison"]["summaries"]])
    if not all_summaries:
        raise SystemExit("No input records found")
    for name, rows in (("qrs_measurements.csv", all_qrs), ("reference_comparisons.csv", all_comparisons),
                       ("comparison_summary.csv", all_summaries)):
        if rows:
            write_csv(args.output_dir / name, rows, list(rows[0]))


if __name__ == "__main__":
    main()
