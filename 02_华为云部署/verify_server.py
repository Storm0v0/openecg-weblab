"""Local HTTP checks, including measurement UI; no external traffic or install."""
import gzip
import runpy
import threading
import urllib.error
import urllib.request
from pathlib import Path

def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    root = Path(__file__).resolve().parent
    page = (root / 'index.html').read_bytes()
    text = page.decode('utf-8')
    for marker in ['id="qrs-heading"', 'id="comparison-heading"', 'id="export-qrs"',
                   'id="export-summary"', 'id="export-comparison"', '"coursework":',
                   '"qrs":', '"comparison":']:
        require(marker in text, f'Measurement/comparison feature missing: {marker}')
    module = runpy.run_path(str(root / 'server.py'))
    server = module['ThreadingHTTPServer'](('127.0.0.1', 0), module['Handler'])
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f'http://127.0.0.1:{server.server_port}'
    # Avoid sending even a loopback check to a machine's configured HTTP proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        for path in ['/', '/index.html', '/?demo=1']:
            with opener.open(base + path, timeout=10) as response:
                require(response.status == 200, f'Homepage status: {path}')
                require(response.read() == page, f'Homepage content mismatch: {path}')
                require(response.headers.get_content_type() == 'text/html', 'Wrong homepage content type')
                require(response.headers.get('X-Content-Type-Options') == 'nosniff', 'Missing nosniff header')
        with opener.open(base + '/health', timeout=10) as response:
            require(response.read() == b'ok\n', 'Health response mismatch')
        with opener.open(urllib.request.Request(base + '/', method='HEAD'), timeout=10) as response:
            require(not response.read(), 'HEAD returned a body')
            require(int(response.headers['Content-Length']) == len(page), 'HEAD content length mismatch')
        for encoding, compressed in [('gzip, deflate', True), ('gzip;q=0', False), ('gzip;q=0.0, deflate', False)]:
            request = urllib.request.Request(base + '/', headers={'Accept-Encoding': encoding})
            with opener.open(request, timeout=10) as response:
                content = response.read()
                require(response.headers.get('Vary') == 'Accept-Encoding', 'Missing compression variant header')
                require((response.headers.get('Content-Encoding') == 'gzip') == compressed, 'Wrong compression negotiation')
                require((gzip.decompress(content) if compressed else content) == page, 'Compressed homepage mismatch')
                require(int(response.headers['Content-Length']) == len(content), 'Encoded content length mismatch')
                if compressed:
                    require(len(content) < len(page), 'Compression did not reduce homepage size')
        for path in ['/server.py', '/install.sh', '/../server.py']:
            try:
                with opener.open(base + path, timeout=10):
                    raise RuntimeError(f'Non-public file was exposed: {path}')
            except urllib.error.HTTPError as exc:
                require(exc.code == 404, f'Expected 404: {path}')
                exc.close()
        print('PASS: measurement/comparison markers, homepage, gzip negotiation, health, HEAD and route isolation')
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


if __name__ == '__main__':
    main()
