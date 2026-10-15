"""Exercise update failures and recovery using disposable model files only."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from shapecast_linux.updates import UpdateManager,BASE,VERSION_URL,validated_files,write_json

def sha(data):return hashlib.sha256(data).hexdigest()
def manifest(name,files):
    return {'schema':1,'kind':'shapecast-pack','name':name,'version':'0.1.0',
            'files':[[path,len(data),sha(data)] for path,data in files.items()]}

class Response(io.BytesIO):
    def __init__(self,data,offset=0,slow=False):
        super().__init__(data[offset:]);self.status=206 if offset else 200
        self.headers={'Content-Range':f'bytes {offset}-{len(data)-1}/{len(data)}'};self.slow=slow
    def read(self,*args):
        if self.slow:time.sleep(.06)
        return super().read(*args)

class Transport:
    def __init__(self):self.metadata={};self.bodies={};self.offsets=[];self.slow=False
    def json(self,url):return copy.deepcopy(self.metadata[url])
    def open(self,url,offset=0):
        self.offsets.append(offset);return Response(self.bodies[url],offset,self.slow)

class Updates(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)/'native';self.pack=self.root/'profiles/native/data/packs/models'
        self.old={'models/u2net/a.onnx':b'old-A','models/u2net/b.onnx':b'old-B'}
        for relative,data in self.old.items():
            path=self.pack/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        write_json(self.pack/'pack.json',manifest('models',self.old))
        self.transport=Transport();self.new={**self.old,'models/u2net/a.onnx':b'new-A'}
        self.transport.metadata[VERSION_URL]={'version':'0.3.16','size_bytes':9,'sha256':sha(b'installer')}
        self.transport.bodies[BASE+'/dl-2c9e41/archive/Shapecast-Setup-0.3.16.exe']=b'installer'
        self.remote(self.new)
        self.manager=UpdateManager(self.root,'0.3.15',lambda:True,self.transport)
        self.manager.request_check=lambda:None
        self.manager.check()
    def tearDown(self):self.tmp.cleanup()
    def remote(self,files):
        self.transport.metadata[BASE+'/v1/models/pack.json']=manifest('models',files)
        self.transport.bodies.update({BASE+'/v1/models/'+p:data for p,data in files.items()})
    def wait(self):
        deadline=time.monotonic()+5
        while self.manager.status()['operation']['state']=='downloading':
            self.assertLess(time.monotonic(),deadline);time.sleep(.01)
        return self.manager.status()['operation']
    def ready(self):
        self.manager.download('models');self.assertEqual(self.wait()['state'],'ready')
    def assertOld(self):
        for p,data in self.old.items():self.assertEqual((self.pack/p).read_bytes(),data)

    def test_cached_release_notice_tracks_installed_upgrade_and_rollback(self):
        upgraded=UpdateManager(self.root,'0.3.16',lambda:True,self.transport)
        self.assertEqual(upgraded.catalog['software']['current'],'0.3.16')
        self.assertFalse(upgraded.catalog['software']['available'])
        rolled_back=UpdateManager(self.root,'0.3.15',lambda:True,self.transport)
        self.assertTrue(rolled_back.catalog['software']['available'])

    def test_same_version_same_size_changed_hash(self):
        item=self.manager.catalog['models'];self.assertTrue(item['available'])
        self.assertEqual(item['version'],'0.1.0');self.assertEqual(len(item['files']),1)
        self.assertEqual(item['download_bytes'],5)

    def test_download_apply_and_rollback(self):
        self.ready();self.assertOld();self.manager.apply()
        self.assertEqual((self.pack/'models/u2net/a.onnx').read_bytes(),b'new-A')
        self.assertTrue(self.manager.status()['rollback_available'])
        self.manager.rollback();self.assertOld();self.manager.check()
        self.assertTrue(self.manager.catalog['models']['available'])

    def test_hash_failure_leaves_installed_models(self):
        self.transport.bodies[BASE+'/v1/models/models/u2net/a.onnx']=b'wrong'
        self.manager.download('models');self.assertEqual(self.wait()['state'],'error');self.assertOld()

    def test_staged_tampering_is_rejected(self):
        self.ready();operation=self.manager.state['operation']
        path=self.manager.directory/'staging'/operation['fingerprint']/'files/models/u2net/a.onnx'
        path.write_bytes(b'wrong')
        with self.assertRaises(ValueError):self.manager.apply()
        self.assertOld()

    def test_duplicate_model_content_downloads_once(self):
        self.new={p:b'new-X' for p in self.old};self.remote(self.new);self.manager.check()
        self.assertEqual(self.manager.catalog['models']['download_bytes'],5)
        self.ready();self.assertEqual(len(self.transport.offsets),1)
        self.manager.apply()
        for path in self.old:self.assertEqual((self.pack/path).read_bytes(),b'new-X')

    def test_restart_recovers_interrupted_rollback(self):
        self.ready();self.manager.apply()
        backup=self.manager.directory/'backups'/self.manager.state['last_backup']
        journal=json.loads((backup/'journal.json').read_text());journal['state']='restoring'
        write_json(backup/'journal.json',journal)
        recovered=UpdateManager(self.root,'0.3.15',lambda:True,self.transport)
        self.assertOld();self.assertEqual(recovered.status()['operation']['state'],'error')

    def test_download_pause_and_resume(self):
        data=b'x'*(4*1024**2);self.new['models/u2net/a.onnx']=data;self.remote(self.new)
        self.manager.check();self.transport.slow=True;self.manager.download('models')
        time.sleep(.10);self.manager.cancel_event.set();self.assertEqual(self.wait()['state'],'paused')
        self.manager.download('models');self.assertEqual(self.wait()['state'],'ready')
        self.assertTrue(any(offset>0 for offset in self.transport.offsets));self.assertOld()

    def test_partial_apply_restores_all_files(self):
        self.new['models/u2net/b.onnx']=b'new-B';self.remote(self.new);self.manager.check();self.ready()
        from shapecast_linux import updates as linux_updates
        original=linux_updates.os.replace
        def failing(source,destination):
            if str(source).endswith('.linux-update') and str(destination).endswith('b.onnx'):
                raise OSError('Injected interrupted promotion')
            return original(source,destination)
        with patch('shapecast_linux.updates.os.replace',side_effect=failing):
            with self.assertRaises(OSError):self.manager.apply()
        self.assertOld();self.assertEqual(self.manager.state['installed'],{})

    def test_restart_recovers_interrupted_application(self):
        self.ready();self.manager.apply()
        backup=self.manager.directory/'backups'/self.manager.state['last_backup']
        journal=json.loads((backup/'journal.json').read_text());journal['state']='applying'
        write_json(backup/'journal.json',journal)
        self.manager.state['operation']['state']='applying'
        self.manager.state['installed']=journal['installed_before'];self.manager._save()
        recovered=UpdateManager(self.root,'0.3.15',lambda:True,self.transport)
        self.assertOld();self.assertEqual(recovered.status()['operation']['state'],'error')

    def test_changed_model_code_requires_review(self):
        self.new['models/hf/hub/new/snapshots/new/model.py']=b'print("unused")'
        self.remote(self.new);self.manager.check();self.ready()
        self.assertTrue(self.manager.catalog['models']['compatibility_required'])
        with self.assertRaises(ValueError):self.manager.apply()
        self.assertOld()

    def test_software_is_downloaded_but_never_executed(self):
        self.manager.download('software');self.assertEqual(self.wait()['state'],'ready')
        self.assertEqual(self.manager.software_file().read_bytes(),b'installer')
        with self.assertRaises(ValueError):self.manager.apply()
        self.assertOld()

    def test_unsafe_or_duplicate_manifest_paths_rejected(self):
        for path in ('../outside','/absolute','a/../b','a\\b','C:/outside'):
            m=manifest('models',{path:b'x'})
            with self.assertRaises(ValueError):validated_files(m,'models')
        m=manifest('models',{'a':b'x'});m['files']*=2
        with self.assertRaises(ValueError):validated_files(m,'models')

    def test_offline_check_retains_known_update(self):
        self.transport.metadata={};self.manager.check()
        self.assertTrue(self.manager.status()['available'])
        self.assertTrue(self.manager.status()['check_errors'])

    def test_unlicensed_model_download_is_rejected(self):
        self.manager.licence_valid=lambda:False
        with self.assertRaises(ValueError):self.manager.download('models')
        self.assertOld()

if __name__=='__main__':unittest.main(verbosity=2)

class LifespanTests(unittest.IsolatedAsyncioTestCase):
    async def test_automatic_checks_share_vendor_lifespan_and_stop_on_exit(self):
        from contextlib import asynccontextmanager
        from types import SimpleNamespace
        from shapecast_linux.updates import attach_update_lifespan
        events=[]
        @asynccontextmanager
        async def original(app):
            events.append('core started')
            yield {'original_state':True}
            events.append('core stopped')
        manager=SimpleNamespace(start=lambda:events.append('updates started'),stop_event=threading.Event(),cancel_event=threading.Event())
        app=SimpleNamespace(router=SimpleNamespace(lifespan_context=original))
        attach_update_lifespan(app,manager)
        async with app.router.lifespan_context(app) as state:
            self.assertTrue(state['original_state'])
            self.assertEqual(events,['core started','updates started'])
        self.assertTrue(manager.stop_event.is_set());self.assertTrue(manager.cancel_event.is_set())
        self.assertEqual(events[-1],'core stopped')

if __name__=='__main__':unittest.main()
