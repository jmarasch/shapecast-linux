import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from shapecast_linux.job_controls import is_hidden, KEY, adapt_queue_bundle
from unittest.mock import patch
import hashlib
from shapecast_linux.ui_server import make_ui


class VisibilityTests(unittest.TestCase):
    def test_only_terminal_jobs_can_be_hidden(self):
        for status in ('queued', 'awaiting_selection', 'generating_shape', 'texturing'):
            self.assertFalse(is_hidden(SimpleNamespace(status=status, params={KEY: True})))
        for status in ('complete', 'failed', 'cancelled'):
            self.assertTrue(is_hidden(SimpleNamespace(status=status, params={KEY: True})))
            for params in (None, {}, {KEY: False}, {KEY: 'true'}):
                self.assertFalse(is_hidden(SimpleNamespace(status=status, params=params)))


class QueueBundleTests(unittest.TestCase):
    def test_unreviewed_bundle_is_unchanged(self):
        sample=b'console.log("synthetic unreviewed app")'
        self.assertEqual(adapt_queue_bundle(sample),sample)

    def test_reviewed_bundle_gets_stable_page_and_row_attributes(self):
        sample=b'function xL(){return c.jsxs("div",{className:"page"})}function vL({job:a}){return c.jsxs("div",{className:"row"})}'
        adapt_queue_bundle.cache_clear()
        try:
            with patch('shapecast_linux.job_controls.QUEUE_BUNDLE_SHA256', hashlib.sha256(sample).hexdigest()):
                result=adapt_queue_bundle(sample)
            self.assertIn(b'"data-linux-queue-page":true',result)
            self.assertIn(b'"data-linux-queue-job":a.id,"data-linux-queue-status":a.status',result)
            self.assertNotIn(b'data-linux-queue',sample)
        finally:adapt_queue_bundle.cache_clear()


class JobProxyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        assets = Path(self.temp.name)
        (assets/'index.html').write_text('<title>Shapecast</title></head><body></body>')
        (assets/'extraction-manifest.json').write_text('{"assets": []}')
        self.ui = make_ui(assets, 'test-token', lambda: {})
        self.records = []
        records = self.records
        class Core(BaseHTTPRequestHandler):
            def answer(self):
                records.append((self.command, self.path, self.headers.get('Authorization'),
                    self.rfile.read(int(self.headers.get('Content-Length', '0')))))
                body = b'{"jobs":[],"total":0,"queued_ids":[]}'
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
            do_GET = do_POST = answer
            def log_message(self, *args): pass
        self.core = ThreadingHTTPServer(('127.0.0.1', 0), Core)
        self.ui.core_port = self.core.server_port
        for server in (self.ui, self.core): threading.Thread(target=server.serve_forever, daemon=True).start()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        for server in (self.ui, self.core): server.shutdown(); server.server_close()
        self.temp.cleanup()

    def request(self, suffix='', body=None, auth=True, headers=None):
        request = urllib.request.Request('http://127.0.0.1:'+str(self.ui.server_port)+'/linux-jobs-api'+suffix,
            data=json.dumps(body).encode() if body is not None else None,
            headers={**({'Authorization':'Bearer test-token'} if auth else {}), **(headers or {})})
        try:
            with self.opener.open(request, timeout=5) as response: return response.status, response.read()
        except urllib.error.HTTPError as error:
            with error: return error.code, error.read()

    def test_scoped_authenticated_listing(self):
        self.assertEqual(self.request(auth=False)[0], 401)
        self.assertEqual(self.request('?offset=50&hidden=1')[0], 200)
        self.assertEqual(self.records[0][:3], ('GET','/v1/linux-jobs?offset=50&hidden=1','Bearer test-token'))
        for suffix in ('/../license','?target=http://example.com','/clear','?offset=-1&hidden=0'):
            self.assertEqual(self.request(suffix)[0], 404)
        self.assertEqual(len(self.records), 1)

    def test_mutations_scoped_and_cross_origin_rejected(self):
        identifier = '12345678-1234-1234-1234-123456789abc'
        self.assertEqual(self.request('/clear-finished', {})[0], 200)
        for action in ('hide','restore','dismiss'):
            self.assertEqual(self.request('/'+identifier+'/'+action, {})[0], 200)
        self.assertEqual(self.request('/'+identifier+'/delete', {})[0], 404)
        self.assertEqual(self.request('/clear', {})[0], 404)
        self.assertEqual(self.request('/'+identifier+'/cancel', {})[0], 404)
        self.assertEqual(self.request('/clear-finished', {}, headers={'Origin':'https://foreign.example'})[0], 403)
        self.assertEqual(self.request(headers={'Host':'foreign.example'})[0], 403)
        self.assertEqual(json.loads(self.records[0][3]), {})
        self.assertEqual(len(self.records), 4)

    def test_assets_injected(self):
        with self.opener.open('http://127.0.0.1:'+str(self.ui.server_port)) as response:
            html = response.read()
        for asset in ('linux-jobs.js','linux-jobs.css'):
            self.assertIn(asset.encode(), html)
            with self.opener.open('http://127.0.0.1:'+str(self.ui.server_port)+'/'+asset) as response:
                self.assertEqual(response.status, 200)


if __name__ == '__main__': unittest.main()
