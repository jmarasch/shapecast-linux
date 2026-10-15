import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from shapecast_linux.common import LOCK, private_json
from shapecast_linux.installer import update_vendor
from shapecast_linux.native import patch_cuda_headers,install_topology


class InstallUpdateTests(unittest.TestCase):
    def fixture(self, root):
        private_json(root/'install.json', {'schema':1,'core_version':'0.3.16','cuda':None})
        (root/'vendor').mkdir();(root/'vendor/old').write_text('original')
        private_json(root/'profiles/native/data/settings.json', {'mesh_engine':'engine1'})
        p=root/'profiles/native/data/license.dat';p.write_text('synthetic fixture only')
        (root/'profiles/native/library').mkdir();(root/'profiles/native/library/asset').write_text('keep')
        installer=root/'setup.exe';installer.write_text('synthetic installer')
        return Namespace(install_root=root,installer=installer)

    def test_reviewed_software_update_preserves_profile_and_vendor_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);args=self.fixture(r)
            def prepare(installer, stage, node):
                p=stage/'vendor';p.mkdir();(p/'new').write_text('new');return p
            with patch('shapecast_linux.session_control.existing_url',return_value=None),patch('shapecast_linux.installer.sha256',return_value=LOCK['shapecast']['installer_sha256']),patch('shutil.which',return_value='/synthetic/node'),patch('shapecast_linux.installer.prepare_vendor',side_effect=prepare):
                update_vendor(args)
            self.assertEqual((r/'vendor/new').read_text(),'new')
            backup=next((r/'backups').iterdir())
            self.assertEqual((backup/'vendor/old').read_text(),'original')
            self.assertEqual((backup/'native/license.dat').read_text(),'synthetic fixture only')
            self.assertEqual((r/'profiles/native/library/asset').read_text(),'keep')
            self.assertEqual(json.loads((r/'install.json').read_text())['core_version'],LOCK['shapecast']['core_version'])

    def test_failed_update_restores_original_vendor_and_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);args=self.fixture(r)
            def prepare(installer, stage, node):
                p=stage/'vendor';p.mkdir();return p
            with patch('shapecast_linux.session_control.existing_url',return_value=None),patch('shapecast_linux.installer.sha256',return_value=LOCK['shapecast']['installer_sha256']),patch('shutil.which',return_value='/synthetic/node'),patch('shapecast_linux.installer.prepare_vendor',side_effect=prepare),patch('shutil.move',side_effect=OSError('synthetic storage failure')):
                with self.assertRaises(OSError):update_vendor(args)
            self.assertEqual((r/'vendor/old').read_text(),'original')
            self.assertEqual(json.loads((r/'install.json').read_text())['core_version'],'0.3.16')
            self.assertEqual((r/'profiles/native/library/asset').read_text(),'keep')

    def test_private_cuda_header_patch_is_host_detected_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);p=r/'include/crt/math_functions.h';p.parent.mkdir(parents=True)
            original='extern __DEVICE_FUNCTIONS_DECL__ __device_builtin__ double rsqrt(double x);\n'
            p.write_text(original)
            patch_cuda_headers(r,'old system math')
            self.assertEqual(p.read_text(),original)
            host='extern double rsqrt(double __x) noexcept (true);'
            patch_cuda_headers(r,host);patch_cuda_headers(r,host)
            self.assertIn('rsqrt(double x) noexcept(true);',p.read_text())
            self.assertEqual(p.with_suffix('.h.original').read_text(),original)

    def test_official_remesher_help_exit_255_is_accepted_only_with_valid_help(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);p=r/'components/instant-meshes/Instant Meshes'
            p.parent.mkdir(parents=True);p.write_text('synthetic executable')
            with patch('subprocess.run',return_value=Namespace(returncode=255,stdout='Syntax: Instant Meshes --faces',stderr='')):
                self.assertEqual(install_topology(r,r/'cache'),p)
            with patch('subprocess.run',return_value=Namespace(returncode=1,stdout='',stderr='missing shared library')):
                with self.assertRaises(ValueError):install_topology(r,r/'cache')

if __name__=='__main__':unittest.main()
