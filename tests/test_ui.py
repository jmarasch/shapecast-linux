import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64
from shapecast_linux.view_review import image_urls
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

    def test_native_review_assets_are_injected_and_served(self):
        # The synthetic index includes a head just as the reviewed vendor index does.
        (self.server.assets/'index.html').write_text('<title>Shapecast</title></head><body><div id="root"></div></body>')
        self.server.preview_mode=False
        html=self.request('/')[2]
        for path in ('/linux-view-review.js','/linux-view-review.css'):
            self.assertIn(path.encode(),html)
            self.assertEqual(self.request(path)[0],200)
        self.server.preview_mode=True
        self.assertNotIn(b'/linux-view-review.js',self.request('/')[2])

    def test_review_proxy_requires_token_and_forwards_only_review_routes_once(self):
        records=[]
        class Core(BaseHTTPRequestHandler):
            def answer(self):
                size=int(self.headers.get('Content-Length','0'))
                records.append((self.command,self.path,self.headers.get('Authorization'),self.rfile.read(size)))
                body=json.dumps({'content_type':'image/png','data':base64.b64encode(b'png-test-bytes').decode()}).encode() if '/image/' in self.path else b'{"reviews":[]}'
                self.send_response(200);self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            do_GET=answer
            do_POST=answer
            def log_message(self,*args):pass
        core=ThreadingHTTPServer(('127.0.0.1',0),Core)
        threading.Thread(target=core.serve_forever,daemon=True).start()
        self.server.core_port=core.server_port
        try:
            self.assertEqual(self.request('/linux-view-review-api')[0],401)
            headers={'Authorization':'Bearer fixture-token'}
            self.assertEqual(self.request('/linux-view-review-api',headers)[0],200)
            self.assertEqual(self.request('/linux-view-review-api/../license',headers)[0],404)
            self.assertEqual(self.request('/linux-view-review-api',dict(headers,Host='foreign.example'))[0],403)
            suffix='/12345678-1234-1234-1234-123456789abc/approve'
            req=urllib.request.Request(self.base+'/linux-view-review-api'+suffix,data=b'{"revision":1,"view":"left"}',
                headers={**headers,'Content-Type':'application/json'},method='POST')
            with self.opener.open(req,timeout=5) as response:self.assertEqual(response.status,200)
            self.assertEqual(len(records),2)
            self.assertEqual(records[0][1],'/v1/linux-view-reviews')
            self.assertEqual(records[1][:3],('POST','/v1/linux-view-reviews'+suffix,'Bearer fixture-token'))
            self.assertEqual(json.loads(records[1][3]),{'revision':1,'view':'left'})
            images=image_urls(self.server,{'job_id':'12345678-1234-1234-1234-123456789abc','views':[{'name':'left'}],'revision':1})
            code,image_headers,image=self.request(images['left'])
            self.assertEqual((code,image),(200,b'png-test-bytes'))
            self.assertIn('image/png',image_headers['Content-Type'])
            self.assertEqual(self.request(images['left'].replace('/image/left','/image/back'))[0],401)
            self.assertEqual(self.request(images['left'].replace('signature=','signature=bad'))[0],401)
            self.assertEqual(self.request('/linux-view-review-image/12345678-1234-1234-1234-123456789abc/image/left?expires=1&signature=bad')[0],401)
            self.assertEqual(len(records),3)
        finally:core.shutdown();core.server_close()


if __name__ == '__main__': unittest.main()
