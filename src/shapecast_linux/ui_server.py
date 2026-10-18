"""Serve the privately recovered interface with a Linux browser connection adapter."""
import json
import mimetypes
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .common import WEB
from .view_review import PROXY_PATH, IMAGE_PATH, proxy_review
CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "connect-src 'self' http://127.0.0.1:* blob:; img-src 'self' blob: data:; "
       "font-src 'self' data:; media-src 'self' blob:; worker-src 'self' blob:; "
       "form-action 'none'; frame-ancestors 'none'; base-uri 'none'")

class Page(BaseHTTPRequestHandler):
    def do_POST(self):
        if urlsplit(self.path).path.startswith(PROXY_PATH):
            proxy_review(self)
        else:
            self.send_error(405)

    def do_GET(self):
        # Reject DNS rebinding and arbitrary Host headers even on the loopback listener.
        if self.headers.get('Host') not in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}:
            self.send_error(403)
            return
        path = unquote(urlsplit(self.path).path)
        if path.startswith((PROXY_PATH, IMAGE_PATH)):
            proxy_review(self)
            return
        if path == '/native-status':
            supplied = self.headers.get('Authorization', '').removeprefix('Bearer ').strip()
            if not secrets.compare_digest(supplied, self.server.launch_token):
                self.send_error(401)
                return
            self.reply(json.dumps({**self.server.native_status(), 'preview_mode': self.server.preview_mode}).encode(), 'application/json')
            return
        if path == '/preview' and self.server.preview_mode:
            self.reply((WEB/'preview.html').read_bytes(), 'text/html; charset=utf-8', CSP.replace("script-src 'self'", "script-src 'self' 'unsafe-inline'"))
            return
        if path == '/setup':
            html = (WEB/'setup.html').read_bytes()
            self.reply(html, 'text/html; charset=utf-8', "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self' http://127.0.0.1:*; form-action 'none'; frame-ancestors 'none'; base-uri 'none'")
            return
        if path in ('/', '/index.html'):
            html = (self.server.assets/'index.html').read_text()
            html = html.replace('<title>Shapecast</title>', '<title>Shapecast — Linux</title><script src="/linux-bridge.js"></script><link rel="stylesheet" href="/linux-shell.css"><link rel="stylesheet" href="/linux-updates.css">')
            if not self.server.preview_mode:
                html=html.replace('</head>','<script src="/linux-updates.js" defer></script><script src="/linux-view-review.js" defer></script><link rel="stylesheet" href="/linux-view-review.css"></head>')
            html = html.replace('<body>', '<body><nav id="linux-toolbar" aria-label="Linux runtime"><span>Native Linux runtime · Your vendor licence and models required</span><a id="linux-setup" href="/setup">Linux setup</a></nav>')
            if self.server.preview_mode:
                html = html.replace('Native Linux runtime · Your vendor licence and models required', 'Placeholder test profile · Results are sample models, not AI output')
                html = html.replace('<a id="linux-setup"', '<a id="linux-preview" href="/preview">Test previews</a><a id="linux-setup"')
            self.reply(html.encode(), 'text/html; charset=utf-8', CSP)
            return
        if path in ('/linux-bridge.js', '/linux-shell.css','/linux-updates.js','/linux-updates.css', '/linux-view-review.js', '/linux-view-review.css'):
            file = WEB/path[1:]
        elif path in self.server.asset_paths:
            file = (self.server.assets/path[1:]).resolve()
            if not file.is_relative_to(self.server.assets.resolve()):
                self.send_error(404)
                return
        else:
            self.send_error(404)
            return
        if not file.is_file():
            self.send_error(404)
            return
        mime = mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
        self.reply(file.read_bytes(), mime, CSP)

    def reply(self, body, mime, csp=None):
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if csp:
            self.send_header('Content-Security-Policy', csp)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def make_ui(assets, token, status, preview_mode=False):
    server = ThreadingHTTPServer(('127.0.0.1', 0), Page)
    server.assets = Path(assets).resolve()
    server.asset_paths = {e['path'] for e in json.loads((server.assets/'extraction-manifest.json').read_text())['assets']}
    server.launch_token = token
    server.native_status = status
    server.preview_mode = preview_mode
    return server
