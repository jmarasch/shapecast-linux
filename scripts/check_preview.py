#!/usr/bin/env python3
"""Opt-in live integration test; creates one placeholder in the preview library."""
import argparse
import json
import struct
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from shapecast_linux.common import default_root, read_install, verify_vendor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-root', type=Path, default=default_root())
    args = parser.parse_args()
    root, config = read_install(args.install_root)
    verify_vendor(root)
    state = json.loads((root/'profiles/preview/session.json').read_text())
    headers = {'Authorization':'Bearer '+state['token'], 'Content-Type':'application/json'}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base = 'http://127.0.0.1:'+str(int(state['core_port']))
    ui = 'http://127.0.0.1:'+str(int(state['ui_port']))

    def request(url, payload=None, auth=True):
        body = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=body, headers=headers if auth else {})
        with opener.open(req, timeout=90) as response:
            value = response.read()
            return json.loads(value) if 'application/json' in response.headers.get('Content-Type','') else value

    status = request(ui+'/native-status')
    if status.get('preview_mode') is not True:
        raise RuntimeError('Refusing to create a test in a non-preview session.')
    for url in (base+'/v1/system', ui+'/native-status'):
        try: request(url, auth=False)
        except urllib.error.HTTPError as error:
            if error.code != 401: raise
        else: raise RuntimeError('Unauthenticated request was accepted.')
    for url, extra, expected in (
        (ui+'/', {'Host':'foreign.example'}, 403),
        (ui+'/%2e%2e/session.json', {}, 404),
        (base+'/v1/system', {'Origin':'https://foreign.example', **headers}, 403),
    ):
        try: opener.open(urllib.request.Request(url, headers=extra), timeout=10)
        except urllib.error.HTTPError as error:
            if error.code != expected: raise
        else: raise RuntimeError('Loopback security check failed.')
    job = request(base+'/v1/jobs', {'prompt':'Community helper placeholder check', 'kind':'prop', 'variants':1, 'rig':False})
    picked = False; deadline = time.monotonic()+90
    while time.monotonic() < deadline:
        job = request(base+'/v1/jobs/'+job['id'])
        if job['status'] == 'awaiting_selection' and not picked:
            variants = request(base+'/v1/jobs/'+job['id']+'/variants')
            request(base+'/v1/jobs/'+job['id']+'/select-variant', {'file_id':variants[0]['id']})
            picked = True
        if job['status'] in ('complete','failed','cancelled'): break
        time.sleep(.3)
    if job['status'] != 'complete': raise RuntimeError('Placeholder job did not complete.')
    assets = request(base+'/v1/assets')
    asset = next(a for a in assets if a['job_id'] == job['id'])
    detail = request(base+'/v1/assets/'+asset['id'])
    final = next(f for f in detail['files'] if f['file_kind'] == 'final_glb')
    glb = request(base+'/v1/files/'+final['id']+'/download')
    if glb[:4] != b'glTF' or struct.unpack_from('<I', glb, 8)[0] != len(glb):
        raise RuntimeError('Downloaded placeholder is not a valid GLB container.')
    exported = request(base+'/v1/assets/'+asset['id']+'/export', {'formats':['glb','obj','stl']})
    manifest = exported['manifest']
    if manifest.get('errors') or set(manifest['formats']) != {'glb','obj','stl'}:
        raise RuntimeError('One or more Blender exports failed.')
    folder = Path(exported['folder']).resolve()
    if not folder.is_relative_to((root/'profiles/preview/library').resolve()):
        raise RuntimeError('Exports are outside the preview library.')
    for name, entry in manifest['formats'].items():
        content = (folder/entry['file']).read_bytes()
        if len(content) != entry['bytes']: raise RuntimeError('Export file size did not match.')
        if name == 'glb' and content[:4] != b'glTF': raise RuntimeError('Export is not a GLB.')
        if name == 'obj' and b'\nv ' not in content: raise RuntimeError('OBJ lacks vertices.')
        if name == 'stl' and len(content) != 84+50*struct.unpack_from('<I',content,80)[0]:
            raise RuntimeError('STL triangle data is incomplete.')
    if not manifest['mesh_integrity']['watertight']: raise RuntimeError('Placeholder export is not watertight.')
    print('PASS: placeholder job, GLB download, Blender GLB/OBJ/STL files and watertight mesh.')
    print('PASS: API authentication, UI authentication, Host, Origin and traversal checks.')
    print('Real AI generation was not tested. The sample remains in the preview library.')


if __name__ == '__main__': main()
