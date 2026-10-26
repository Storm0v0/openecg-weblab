"""Local-only extraction of displayed Apple Watch PDF vector curves.

This is not a HealthKit/raw-sample decoder. Inputs are supplied explicitly;
no source PDF or identifying text is copied into the output directory.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import pymupdf as fitz

FS = 512
PT_PER_MM = 72 / 25.4
PT_PER_SEC = PT_PER_MM * 25
PT_PER_MV = PT_PER_MM * 10


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(path: Path, alias: str) -> tuple[dict, dict]:
    doc = fitz.open(path)
    assert len(doc) == 1
    page = doc[0]
    footer = page.get_text()
    for marker in ("25 mm/s", "10 mm/mV", "512Hz"):
        assert marker in footer, f"Expected explicit calibration marker: {marker}"
    drawings = page.get_drawings()
    gray_vertical = set()
    red_paths = []
    calibration = []
    for drawing in drawings:
        color = drawing.get("color")
        if color and color[0] > .7 and color[1] < .1 and color[2] < .2:
            assert all(item[0] == "l" for item in drawing["items"])
            red_paths.append(drawing)
        if color and min(color) > .7 and max(color) - min(color) < .01:
            for item in drawing["items"]:
                if item[0] == "l":
                    a, b = item[1:]
                    if abs(a.x - b.x) < 1e-5 and abs(a.y - b.y) > 50:
                        gray_vertical.add(tuple(sorted((float(a.y), float(b.y)))))
        if color and max(color) < .5 and len(drawing["items"]) == 5:
            calibration.append(drawing)
    bands = sorted(gray_vertical)
    assert len(bands) == 3 and len(calibration) == 1
    cal = calibration[0]
    reference_y0 = cal["rect"].y1
    origin_x = cal["rect"].x0
    measured_calibration_height = cal["rect"].height
    assert abs(measured_calibration_height - PT_PER_MV) < 1e-3
    grouped = [[] for _ in bands]
    for drawing in red_paths:
        centre_y = (drawing["rect"].y0 + drawing["rect"].y1) / 2
        row = next(i for i, (lo, hi) in enumerate(bands) if lo <= centre_y <= hi)
        grouped[row].append(drawing)
    segments = []
    geometry = []
    vector_hasher = hashlib.sha256()
    line_count = 0
    for row, paths in enumerate(grouped):
        points = []
        for drawing in paths:
            for _, a, b in drawing["items"]:
                line_count += 1
                if not points:
                    points.append(a)
                else:
                    assert abs(points[-1].x - a.x) < 1e-6
                    assert abs(points[-1].y - a.y) < 1e-6
                assert b.x > a.x
                points.append(b)
        row_reference_y = reference_y0 + bands[row][0] - bands[0][0]
        indices = [round((point.x - origin_x) / PT_PER_SEC * FS) for point in points]
        assert indices == list(range(indices[0], indices[0] + len(points)))
        assert 0 <= indices[0] <= indices[-1] < FS * 10
        residual = max(abs(point.x - (origin_x + index * PT_PER_SEC / FS)) for point, index in zip(points, indices))
        # The PDF uses rounded drawing constants; allow <0.015 nominal sample
        # of coordinate disagreement, and record the measured value explicitly.
        assert residual / PT_PER_SEC * FS < .015
        signal = [(row_reference_y - point.y) / PT_PER_MV for point in points]
        assert all(math.isfinite(v) for v in signal)
        reconstruction_error_y = max(abs((row_reference_y - voltage * PT_PER_MV) - point.y)
                                     for voltage, point in zip(signal, points))
        assert reconstruction_error_y < 1e-9
        absolute_start = row * FS * 10 + indices[0]
        vector = [[point.x, point.y] for point in points]
        vector_hasher.update(json.dumps(vector, separators=(",", ":")).encode())
        segments.append({"startSample": absolute_start, "startSec": absolute_start / FS,
                         "sampleCount": len(points), "signal": signal})
        geometry.append({"row": row + 1, "pathCount": len(paths), "pointCount": len(points),
                         "xMinPt": points[0].x, "xMaxPt": points[-1].x,
                         "gridBandYPt": list(bands[row]), "referenceYPt": row_reference_y,
                         "maxVoltageRoundTripResidualPt": reconstruction_error_y,
                         "maxNominalSampleGridResidualPt": residual,
                         "maxNominalSampleGridResidualSamples": residual / PT_PER_SEC * FS})
    # Some reports end before the nominal third row is full. Describe the
    # actual coverage instead of requiring or manufacturing 30 seconds.
    missing = []
    cursor = 0
    for segment in segments:
        assert segment['startSample'] >= cursor
        if segment['startSample'] > cursor:
            missing.append({'startSampleInclusive': cursor,
                            'endSampleExclusive': segment['startSample']})
        cursor = segment['startSample'] + segment['sampleCount']
    if cursor < 30 * FS:
        missing.append({'startSampleInclusive': cursor, 'endSampleExclusive': 30 * FS})
    assert sum(s['sampleCount'] for s in segments) + sum(
        r['endSampleExclusive']-r['startSampleInclusive'] for r in missing) == 30 * FS
    payload = {"schema": 1, "recordId": alias, "sourceKind": "pdf-vector-reconstruction",
               "fs": FS, "units": "mV-relative", "lead": "I-like wearable single lead",
               "nominalDisplayedDurationSec": 30, "availablePointCount": sum(s["sampleCount"] for s in segments),
               "missingSampleRanges": missing,
               "amplitudeReference": "PDF calibration baseline plus row displacement; arbitrary DC reference, not verified absolute electrode voltage",
               "groundTruth": [], "hasManualGroundTruth": False, "segments": segments}
    audit = {"recordId": alias, "sourcePdfSha256": digest(path), "sourcePdfBytes": path.stat().st_size,
             "pages": len(doc), "embeddedFiles": doc.embfile_count(), "hasXmp": bool(doc.get_xml_metadata()),
             "calibrationEvidence": {"footer": "25 mm/s; 10 mm/mV; lead I; 512Hz",
                 "ptPerSecond": PT_PER_SEC, "ptPerMv": PT_PER_MV,
                 "measuredOneMvPulseHeightPt": measured_calibration_height,
                 "pulseHeightDifferencePt": measured_calibration_height - PT_PER_MV},
             "waveformPathCount": len(red_paths), "waveformLineSegmentCount": line_count,
             "waveformPointCount": payload["availablePointCount"], "waveformVectorSha256": vector_hasher.hexdigest(),
             "rows": geometry,
             "limitations": ["PDF displayed-vector reconstruction, not original HealthKit samples",
                 *[f"Nominal samples {r['startSampleInclusive']} to {r['endSampleExclusive']} "
                   f"({r['startSampleInclusive']/FS} to {r['endSampleExclusive']/FS} s) are absent; not interpolated or zero-filled"
                   for r in missing],
                 "No independent manual P/QRS/T or R-peak labels",
                 "Relative amplitude with an arbitrary DC reference; no validated absolute zero",
                 "Reported grid residual measures PDF coordinate consistency, not physiological or diagnostic accuracy"]}
    return payload, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('--record', required=True, choices=list('ABCDE'))
    parser.add_argument('--start', type=int, default=10)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Choose a new output path')
    payload, _ = extract(args.source, 'record_'+args.record)
    start = args.start*FS
    points = {s['startSample']+i:v for s in payload['segments'] for i,v in enumerate(s['signal'])}
    try:
        signal = [points[i] for i in range(start,start+10*FS)]
    except KeyError as exc:
        raise ValueError('The selected 10-second window includes missing PDF points') from exc
    output = {'id':'applewatch-'+args.record.lower(),'sourceKind':'pdf-vector-reconstruction',
              'fs':FS,'unit':'mV-relative','windowSec':[args.start,args.start+10],'signal':signal}
    args.output.write_text(json.dumps(output,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print('Extracted one complete 10-second window: '+str(args.output))


if __name__ == '__main__':
    main()
