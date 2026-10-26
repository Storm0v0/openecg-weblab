"""Build the private catalog page from frozen payloads, using only the standard library.

No inference, reconstruction, public-project writes, server operations, or Git operations
are performed. The historical two-record inference builder is a separate backup file.
"""
from pathlib import Path
from collections import Counter
import hashlib
import json
import math
import os
import re
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PUBLIC_PAGE = ROOT / '01_离线演示' / 'OpenECG_Demo.html'
PRIVATE_RESULTS = HERE / 'data/applewatch_model_results.json'
PRIVATE_CATALOG = HERE / 'data/catalog.json'
DATA_PATTERN = r'<script type="application/json" id="demo-data">([\s\S]*?)</script>'


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_frozen_records():
    public_text = PUBLIC_PAGE.read_text(encoding='utf-8')
    matches = re.findall(DATA_PATTERN, public_text)
    if len(matches) != 1:
        raise ValueError('The public page must contain exactly one frozen data block')
    public = json.loads(matches[0])
    if Counter(r.get('dataset') for r in public) != {'LUDB': 10, 'QTDB': 10}:
        raise ValueError('Expected exactly 10 LUDB and 10 QTDB frozen public records')
    private = json.loads(PRIVATE_RESULTS.read_text(encoding='utf-8'))
    catalog = json.loads(PRIVATE_CATALOG.read_text(encoding='utf-8'))
    entries = catalog['records']
    if ([r.get('id') for r in private] != [r['id'] for r in entries]
            or len(private) != catalog['privateSelectableEntries']
            or len({r['id'] for r in private}) != len(private)):
        raise ValueError('Frozen private records must match the anonymous local catalog')
    allowed = {'id','dataset','record','lead','label','fs','sourceFs','startSec','unit',
               'mode','model','raw','filtered','waves','groundTruth','rPeaks','rr',
               'metrics','pdfReconstruction','coursework'}
    for r, entry in zip(private, entries):
        if (set(r) != allowed or r['record'] != entry['record']
                or not re.fullmatch(r'[A-Z]', r['record']) or r['dataset'] != 'APPLEWATCH'):
            raise ValueError('Unexpected or non-anonymous private record metadata')
        if not (r['fs'] == 250 and r['sourceFs'] == 512
                and type(r['startSec']) in (int, float)
                and math.isfinite(r['startSec']) and r['startSec'] >= 0
                and r['lead'] == 'I' and r['unit'] == 'mV' and r['mode'] == 'precomputed'):
            raise ValueError('The frozen reconstruction metadata must not be relabelled')
        source = r['pdfReconstruction']
        window = source.get('windowSec')
        if window != entry['windowSec'] or source.get('duplicateOf') != entry.get('duplicateOf'):
            raise ValueError('Private window and duplicate provenance must match the catalog')
        if not (isinstance(window, list) and len(window) == 2
                and all(type(v) in (int, float) and math.isfinite(v) for v in window)
                and window[0] >= 0 and math.isclose(window[0], r['startSec'], abs_tol=1e-9)
                and math.isclose(window[1] - window[0], 10, abs_tol=1e-9)):
            raise ValueError('Each private record must identify its actual complete 10-second source window')
        if not (source['kind'] == 'pdf-vector-reconstruction'
                and source['nominalFs'] == 512
                and source['hasManualGroundTruth'] is False
                and 'relative mV' in source['amplitude']):
            raise ValueError('The PDF reconstruction provenance is incomplete')
        if r['groundTruth'] or r['coursework']['comparison']['rows']:
            raise ValueError('The personal records have no manual ground truth')
        for summary in r['coursework']['comparison']['summaries']:
            if summary['referenceCount'] != 0 or any(summary[k] is not None for k in
                    ('pairingRatePct','bothWithinRatePct','onsetMaeMs','offsetMaeMs',
                     'durationMaeMs','onsetBiasMs','offsetBiasMs')):
                raise ValueError('Unannotated records must remain unevaluable')
        for key in ('raw', 'filtered'):
            if len(r[key]) != 2500 or not all(math.isfinite(v) for v in r[key]):
                raise ValueError('Invalid frozen private signal')
    records = public + private
    for r in private:
        duplicate = r['pdfReconstruction'].get('duplicateOf')
        if duplicate:
            original = next((item for item in private if item['id'] == duplicate), None)
            if not original or duplicate == r['id'] or any(r[key] != original[key] for key in
                    ('raw','filtered','waves','rPeaks','rr','metrics','startSec')):
                raise ValueError('A duplicate export must retain the original waveform and results')
    if sum(not r['pdfReconstruction'].get('duplicateOf') for r in private) != catalog['uniqueMeasurements']:
        raise ValueError('Duplicate exports must not count as independent measurements')
    if len({r['id'] for r in records}) != len(records):
        raise ValueError('Record identifiers must be unique')
    return records


def atomic_text(path, content):
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
            dir=HERE, prefix='.local-preview-', suffix='.tmp', delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(content)
    try:
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main():
    records = load_frozen_records()
    template = (HERE / 'template.html').read_text(encoding='utf-8')
    app = (HERE / 'app_template.js').read_text(encoding='utf-8')
    css = (HERE / 'base.css').read_text(encoding='utf-8')
    for token in ('/*__BASE_CSS__*/', '/*__DEMO_DATA__*/', '/*__APP_JS__*/'):
        if template.count(token) != 1:
            raise ValueError('Private template placeholder mismatch: ' + token)
    payload = json.dumps(records, ensure_ascii=False, separators=(',', ':'),
                         allow_nan=False).replace('</', '<\\/')
    html = template.replace('/*__BASE_CSS__*/', css)
    html = html.replace('/*__DEMO_DATA__*/', payload).replace('/*__APP_JS__*/', app)
    if json.loads(re.findall(DATA_PATTERN, html)[0]) != records:
        raise ValueError('Embedding must preserve every frozen value')
    for forbidden in (r'<script[^>]+src=', r'<link[^>]+href=', r'@import',
                      r'fetch\(', r'XMLHttpRequest', r'WebSocket', r'type=["\']file["\']'):
        if re.search(forbidden, html):
            raise ValueError('The private page must remain self-contained and offline')
    atomic_text(HERE / 'app.js', app)
    atomic_text(HERE / 'OpenECG_Demo.html', html)
    audit = {
        'scope': 'private local preview only', 'recordCount': len(records),
        'sourceCounts': dict(Counter(r['dataset'] for r in records)),
        'privateUniqueMeasurements': json.loads(PRIVATE_CATALOG.read_text(encoding='utf-8'))['uniqueMeasurements'],
        'defaultRecord': 'applewatch-a', 'modelInferenceExecuted': False,
        'privateSourceWindowsSec': {r['id']: r['pdfReconstruction']['windowSec']
                                    for r in records if r['dataset'] == 'APPLEWATCH'},
        'frozenValuesPreserved': True,
        'publicPayloadSource': '01_离线演示/OpenECG_Demo.html',
        'publicPayloadSourceSha256': sha256(PUBLIC_PAGE),
        'privatePayloadSource': 'data/applewatch_model_results.json',
        'privatePayloadSourceSha256': sha256(PRIVATE_RESULTS),
        'publishedToCloud': False, 'uploadedToGitHub': False,
        'outputs': {name: sha256(HERE/name) for name in ('app.js', 'OpenECG_Demo.html')},
    }
    atomic_text(HERE / 'build_manifest.json',
                json.dumps(audit, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': 'built private local preview', 'recordCount': len(records),
                     'sourceCounts': audit['sourceCounts'], 'defaultRecord': 'applewatch-a',
                     'inferenceExecuted': False, 'output': 'OpenECG_Demo.html'},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
