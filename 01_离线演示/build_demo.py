"""Rebuild the single HTML demo using only Python's standard library."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEMO = ROOT.parent / '03_网站与算法源码' / 'public' / 'demo'
sys.path.insert(0, str(DEMO.parents[1] / 'scripts'))
from coursework_analysis import analyze_record
from demo_catalog import RECORDS
names = [f'{params[0]}-{params[1]}' for params in RECORDS]
records = [json.loads((DEMO / (name + '.json')).read_text(encoding='utf-8')) for name in names]
for record in records:
    record['coursework'] = analyze_record(record)
text = (ROOT / 'template.html').read_text(encoding='utf-8')
text = text.replace('/*__BASE_CSS__*/', (ROOT / 'base.css').read_text(encoding='utf-8'))
text = text.replace('/*__DEMO_DATA__*/', json.dumps(records, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/'))
text = text.replace('/*__APP_JS__*/', (ROOT / 'app.js').read_text(encoding='utf-8'))
out = ROOT / 'OpenECG_Demo.html'
out.write_text(text, encoding='utf-8')
print(out)
