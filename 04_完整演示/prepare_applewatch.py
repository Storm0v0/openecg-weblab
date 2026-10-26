"""Reproduce one selected Apple Watch input with the existing OpenECG pipeline.

Writes only the explicitly requested output path. The frozen examples are read
for record metadata; the stored model results are not overwritten.
"""
import argparse
import copy
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'03_网站与算法源码/scripts'))
from prepare_demo import load_dependencies, filter_ecg, model_provenance
from coursework_analysis import analyze_record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--record', required=True, choices=list('ABCDE'))
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Choose a new output path')
    source = json.loads((HERE/f'data/inputs/anonymous-{args.record.lower()}.json').read_text(encoding='utf-8'))
    frozen = json.loads((HERE/'data/anonymous_records.json').read_text(encoding='utf-8'))
    record = copy.deepcopy(next(r for r in frozen if r['record'] == args.record))
    assert source['id'] == record['id'] and source['fs'] == 512
    assert source['sourceKind'] == 'pdf-vector-reconstruction'
    assert source['windowSec'] == record['pdfReconstruction']['windowSec']
    dep = load_dependencies()
    np = dep.np
    signal = np.asarray(source['signal'],dtype=np.float64)
    assert signal.shape == (5120,) and np.isfinite(signal).all()
    detector = dep.Inference()
    fingerprint = model_provenance(detector)
    assert any(f['sha256'] == '2e130ed795491764ffa4f7eff5decc06a4531ac69e1cab51bfbffa714bc0b3fb'
               for f in fingerprint['files'])
    raw = dep.resample_poly(signal,250,512)
    clean = filter_ecg(raw,250,dependencies=dep)
    record['raw'] = np.round(raw,5).tolist()
    record['filtered'] = np.round(clean,5).tolist()
    record['waves'] = [{'type':b.name,'start':round(b.start/250,4),'end':round(b.end/250,4)}
                       for b in detector.predict(clean)[0]]
    peaks = dep.detect_qrs(clean,fs=250)
    rr = np.diff(peaks)/250
    hr = 60/rr if rr.size else np.array([])
    record['rPeaks'] = np.round(peaks/250,4).tolist()
    record['rr'] = np.round(rr,4).tolist()
    record['metrics'] = {'averageHr':round(float(np.mean(hr)),1) if hr.size else None,
        'minHr':round(float(np.min(hr)),1) if hr.size else None,
        'maxHr':round(float(np.max(hr)),1) if hr.size else None,
        'meanRr':round(float(np.mean(rr)),3) if rr.size else None,'rPeakCount':len(peaks)}
    record['coursework'] = analyze_record(record)
    args.output.write_text(json.dumps(record,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'record':record['id'],'model':fingerprint,'matchesFrozenResult':
        record == next(r for r in frozen if r['record'] == args.record)},ensure_ascii=False))


if __name__ == '__main__':
    main()
