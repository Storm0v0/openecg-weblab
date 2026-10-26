"""Build and verify the 25-record edition; no server or remote publication."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def run(parts):
    subprocess.run([str(p) for p in parts],cwd=ROOT,check=True)


def main():
    node = shutil.which('node')
    if not node:
        raise SystemExit('Node.js is required for the interaction checks')
    for name in ('test_coursework_analysis.py','test_prepare_demo.py'):
        run([sys.executable,ROOT/'03_网站与算法源码/scripts'/name])
    run([sys.executable,HERE/'build_demo.py'])
    run([node,'--check',HERE/'app.js'])
    run([node,HERE/'verify.cjs'])
    run([node,ROOT/'01_离线演示/verify.cjs','--expected-per-source=10'])
    write_manifest()
    print('PASS: 25-record build, interaction checks, algorithm checks and release checksums.')


def write_manifest():
    files = [ROOT/'.gitattributes',ROOT/'.gitignore',ROOT/'README.md']
    for folder in ('01_离线演示','02_华为云部署','03_网站与算法源码','04_完整演示','docs'):
        files.extend(path for path in (ROOT/folder).rglob('*') if path.is_file()
                     and '__pycache__' not in path.parts
                     and path.suffix not in {'.pyc','.pyo','.pdf','.tmp'}
                     and not path.name.startswith('replay-'))
    files = sorted(set(files),key=lambda p:p.relative_to(ROOT).as_posix())
    rows = [{'path':path.relative_to(ROOT).as_posix(),'bytes':path.stat().st_size,
             'sha256':hashlib.sha256(path.read_bytes()).hexdigest()} for path in files]
    checksums=''.join(f"{row['sha256']}  {row['path']}\n" for row in rows)
    (ROOT/'SHA256SUMS').write_text(checksums,encoding='utf-8',newline='\n')
    checksum_path=ROOT/'SHA256SUMS'
    rows.append({'path':'SHA256SUMS','bytes':checksum_path.stat().st_size,
                 'sha256':hashlib.sha256(checksum_path.read_bytes()).hexdigest()})
    manifest={'schema':'openecg-private-25-record-release-v1','recordCount':25,
        'sourceCounts':{'LUDB':10,'QTDB':10,'APPLEWATCH':5},
        'entryPoint':'04_完整演示/OpenECG_Demo.html','visibility':'private',
        'modelInferenceExecuted':False,'files':rows}
    (ROOT/'release-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')


if __name__ == '__main__':
    main()
