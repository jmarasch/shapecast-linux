import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from shapecast_linux.ui_server import make_ui


class BrowserHostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        assets = Path(self.temp.name)
        (assets/'index.html').write_text('<title>Shapecast</title><body><div id="root"></div></body>')
        (assets/'app.js').write_text('console.log("synthetic fixture")')
        (assets/'extraction-manifest.json').write_text(json.dumps({'assets':[{'path':'/index.html'}, {'path':'/app.js'}]}))
        self.server = make_ui(assets, 'fixture-token', lambda: {'cuda':{'devices':None}, 'missing_models':[]}, preview_mode=True)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = 'http://127.0.0.1:'+str(self.server.server_port)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.temp.cleanup()

    def request(self, path, headers=None):
        try:
            with self.opener.open(urllib.request.Request(self.base+path, headers=headers or {}), timeout=5) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            with error:
                return error.code, error.headers, error.read()

    def test_adapter_and_private_routes(self):
        code, headers, html = self.request('/')
        self.assertEqual(code, 200)
        self.assertIn(b'/linux-bridge.js', html)
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        self.assertEqual(self.request('/preview')[0], 200)
        self.assertEqual(self.request('/setup')[0], 200)
        self.assertEqual(self.request('/native-status')[0], 401)
        self.assertEqual(self.request('/native-status', {'Authorization':'Bearer fixture-token'})[0], 200)

    def test_host_and_traversal_rejected(self):
        self.assertEqual(self.request('/', {'Host':'foreign.example'})[0], 403)
        for path in ('/../session.json','/%2e%2e/session.json','/extraction-manifest.json','/unknown.js'):
            with self.subTest(path=path): self.assertEqual(self.request(path)[0], 404)


if __name__ == '__main__': unittest.main()
