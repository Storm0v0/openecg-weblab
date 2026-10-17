"""Serve only the self-contained ECG demo; no uploads or inference endpoints."""
import argparse
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

PAGE = Path(__file__).with_name('index.html').read_bytes()
COMPRESSED_PAGE = gzip.compress(PAGE, compresslevel=6, mtime=0)


def accepts_gzip(value):
    for entry in value.split(','):
        coding, *parameters = entry.strip().split(';')
        if coding.lower() != 'gzip':
            continue
        quality = 1.0
        for parameter in parameters:
            key, separator, weight = parameter.strip().partition('=')
            if separator and key.lower() == 'q':
                try:
                    quality = float(weight)
                except ValueError:
                    quality = 0.0
        return 0 < quality <= 1
    return False


class Handler(BaseHTTPRequestHandler):
    server_version = 'ECGDemo'
    sys_version = ''

    def do_HEAD(self):
        self.respond(False)

    def do_GET(self):
        self.respond(True)

    def respond(self, body):
        path = urlsplit(self.path).path
        homepage = path in ('/', '/index.html')
        compressed = homepage and accepts_gzip(self.headers.get('Accept-Encoding', ''))
        if path == '/health':
            content, mime = b'ok\n', 'text/plain; charset=utf-8'
        elif homepage:
            content, mime = COMPRESSED_PAGE if compressed else PAGE, 'text/html; charset=utf-8'
        elif path == '/favicon.ico':
            self.send_response(204)
            self.end_headers()
            return
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if homepage:
            self.send_header('Vary', 'Accept-Encoding')
        if compressed:
            self.send_header('Content-Encoding', 'gzip')
        self.end_headers()
        if body:
            self.wfile.write(content)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='心电静态演示服务')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('端口需在 1–65535 之间')
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    print(f'演示服务已启动：{args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
