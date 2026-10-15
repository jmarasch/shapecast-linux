import io,json,tempfile,unittest
from pathlib import Path
from argparse import Namespace
from unittest.mock import patch
from shapecast_linux.common import private_json,sha256
from shapecast_linux.models import selected_files,transfer,destination,install_models
from shapecast_linux.native import patch_engine,configure

class NativeTests(unittest.TestCase):
    def test_native_selection_omits_windows_runtimes(self):
        files=[['python/python.exe',1,'a'*64],['engine/hy3dpaint/a.py',1,'b'*64],['engine/hy3dpaint/kernel.pyd',1,'c'*64]]
        data={'schema':1,'kind':'shapecast-pack','name':'engine','files':files}
        self.assertEqual(set(selected_files('engine',data)),{'engine/hy3dpaint/a.py'})

    def test_download_requires_licence_before_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);private_json(root/'install.json',{'schema':1})
            args=Namespace(install_root=root,packs='models',source=None)
            with patch('shapecast_linux.models.require_licence',side_effect=ValueError('activation required')),patch('shapecast_linux.models.fetch_json') as fetch:
                with self.assertRaises(ValueError):install_models(args)
                fetch.assert_not_called()

    def test_bad_model_download_preserves_installed_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'model';p.write_bytes(b'old')
            with patch('urllib.request.urlopen',side_effect=lambda *a,**k:io.BytesIO(b'bad')),patch('time.sleep'):
                with self.assertRaises(ValueError):transfer('https://example.invalid/model',p,3,'0'*64)
            self.assertEqual(p.read_bytes(),b'old')

    def test_model_targets_cannot_follow_external_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp)/'root';r.mkdir();(r/'models').symlink_to(Path(tmp)/'outside',target_is_directory=True)
            with self.assertRaises(ValueError):destination(r,'engine2','models/dinov3.gguf')

    def test_native_configuration_preserves_quality_and_removes_exe_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);p=r/'profiles/native/data/settings.json'
            private_json(p,{'mesh_engine':'engine1','image_host_exe':'C:\\python.exe'})
            private_json(r/'runtimes/quality/linux-runtime-ready.json',{'installed':True})
            (r/'engines').mkdir();(r/'engines/quality-python').write_text('fixture')
            result=configure(r);data=json.loads(p.read_text())
            self.assertEqual(data['mesh_engine'],'engine1');self.assertIsNone(data['image_host_exe'])
            self.assertEqual(data['gpu_host_exe'],str(r/'engines/quality-python'))
            self.assertFalse(data['allow_preview_generation']);self.assertTrue(result['quality_available'])

    def test_quality_without_fast_selects_installed_engine(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);private_json(r/'profiles/native/data/settings.json',{'mesh_engine':'engine2'})
            private_json(r/'runtimes/quality/linux-runtime-ready.json',{'installed':True})
            (r/'engines').mkdir();(r/'engines/quality-python').write_text('fixture')
            configure(r)
            self.assertEqual(json.loads((r/'profiles/native/data/settings.json').read_text())['mesh_engine'],'engine1')

    def test_fast_selection_keeps_quality_host_for_ui_engine_switches(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);p=r/'profiles/native/data/settings.json'
            private_json(p,{'mesh_engine':'engine2'})
            private_json(r/'runtimes/quality/linux-runtime-ready.json',{'installed':True})
            (r/'engines').mkdir();(r/'engines/quality-python').write_text('fixture')
            binary=r/'components/cuda/trellis-cli';binary.parent.mkdir(parents=True);binary.write_text('fixture')
            configure(r);data=json.loads(p.read_text())
            self.assertEqual(data['mesh_engine'],'engine2')
            self.assertEqual(data['gpu_host_exe'],str(r/'engines/quality-python'))

    def test_download_resumes_at_verified_range(self):
        import hashlib
        data=b'complete model payload'
        class Response(io.BytesIO):
            status=206
            headers={'Content-Range':'bytes 7-21/22'}
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'model';p.with_name('model.part').write_bytes(data[:7])
            with patch('urllib.request.urlopen',return_value=Response(data[7:])) as opened:
                transfer('https://example.invalid/model',p,len(data),hashlib.sha256(data).hexdigest())
            self.assertEqual(p.read_bytes(),data)
            self.assertEqual(opened.call_args.args[0].headers['Range'],'bytes=7-')

    def test_rig_weight_updates_reach_private_runtime_copy(self):
        from shapecast_linux.updates import UpdateManager
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);(r/'engines/rig').mkdir(parents=True)
            manager=UpdateManager(r,'0.3.17',lambda:True)
            paths=manager._destinations('rig','rig-pack/checkpoints/skin.ckpt')
            self.assertIn(r/'engines/rig/checkpoints/skin.ckpt',paths)

    def test_vendor_layout_change_refuses_source_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);p=r/'hy3dpaint/utils/multiview_utils.py';p.parent.mkdir(parents=True);p.write_text('unsupported source')
            with self.assertRaises(ValueError):patch_engine(r)

if __name__=='__main__':unittest.main()
