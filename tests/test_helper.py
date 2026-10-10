import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shapecast_linux.common import core_environment, private_json, relative_path, sha256, verify_vendor
from shapecast_linux.installer import extract_tar, download, install
from shapecast_linux.server import profile_settings


class HelperTests(unittest.TestCase):
    def test_archive_paths(self):
        self.assertEqual(relative_path('a\\b.pyc'), Path('a/b.pyc'))
        for name in ('../out', 'a/../../out', '/tmp/out', 'C:\\out', '\\\\server\\out', ''):
            with self.subTest(name=name), self.assertRaises(ValueError):
                relative_path(name)

    def test_tar_traversal_and_links(self):
        for kind in ('traversal', 'symlink', 'hardlink', 'device'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); archive = root/'bad.tar'
                with tarfile.open(archive, 'w') as writer:
                    entry = tarfile.TarInfo('../outside' if kind == 'traversal' else 'inside')
                    if kind == 'symlink': entry.type = tarfile.SYMTYPE; entry.linkname = '../outside'
                    elif kind == 'hardlink': entry.type = tarfile.LNKTYPE; entry.linkname = '../outside'
                    elif kind == 'device': entry.type = tarfile.CHRTYPE
                    writer.addfile(entry)
                with self.assertRaises(ValueError): extract_tar(archive, root/'result')
                self.assertFalse((root/'outside').exists())

    def test_tar_allows_internal_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); archive = root/'ok.tar'
            with tarfile.open(archive, 'w') as writer:
                file = tarfile.TarInfo('folder/data'); file.size = 4
                writer.addfile(file, io.BytesIO(b'test'))
                link = tarfile.TarInfo('folder/sub/link'); link.type = tarfile.SYMTYPE; link.linkname = '../data'
                writer.addfile(link)
            extract_tar(archive, root/'result')
            self.assertEqual((root/'result/folder/sub/link').read_bytes(), b'test')

    def test_private_atomic_state(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp)/'data/session.json'
            private_json(file, {'token': 'example'})
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(file.read_text()), {'token': 'example'})
            private_json(file, {'token': 'replacement'})
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)

    def test_profiles_ignore_inherited_preview_flags(self):
        with patch.dict(os.environ, {'SHAPECAST_FAKE_STAGES':'true', 'SHAPECAST_ALLOW_PREVIEW_GENERATION':'true'}):
            native = core_environment('/tmp/fixture', 'native')
            preview = core_environment('/tmp/fixture', 'preview')
        self.assertNotEqual(native['SHAPECAST_DATA_DIR'], preview['SHAPECAST_DATA_DIR'])
        self.assertNotIn('SHAPECAST_ALLOW_PREVIEW_GENERATION', native)
        self.assertNotIn('SHAPECAST_FAKE_STAGES', native)

    def test_preview_permission_stays_in_preview(self):
        class Settings:
            def model_copy(self, update): return update
        settings = Settings(); root = Path('/tmp/fixture')
        for mode in ('native', 'preview'):
            settings.data_dir = root/'profiles'/mode/'data'
            settings.library_dir = root/'profiles'/mode/'library'
            changes = profile_settings(settings, root, mode)
            self.assertEqual(changes['allow_preview_generation'], mode == 'preview')
        settings.data_dir = root/'profiles/native/data'
        with self.assertRaises(ValueError): profile_settings(settings, root, 'preview')

    def test_integrity_detects_modified_vendor_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); core = root/'vendor/packages/core.pyc'; core.parent.mkdir(parents=True)
            core.write_bytes(b'fixture only')
            private_json(root/'vendor/integrity.json', {'files':[['python/Lib/site-packages/core.pyc', core.stat().st_size, sha256(core)]]})
            private_json(root/'vendor/ui/extraction-manifest.json', {'assets':[]})
            self.assertEqual(verify_vendor(root), (1, 0))
            core.write_bytes(b'altered core')
            with self.assertRaises(ValueError): verify_vendor(root)

    def test_bad_download_is_not_installed(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch('urllib.request.urlopen', return_value=io.BytesIO(b'wrong component')):
                with self.assertRaises(ValueError):
                    download({'url':'https://example.invalid/archive.tar', 'sha256':'0'*64}, temp)
            self.assertEqual(list(Path(temp).iterdir()), [])

    def test_unknown_installer_fails_before_extraction(self):
        with tempfile.TemporaryDirectory() as temp:
            from argparse import Namespace
            root = Path(temp); installer = root/'installer.exe'; installer.write_bytes(b'fixture')
            args = Namespace(install_root=root/'runtime', installer=installer)
            with patch('shapecast_linux.installer.extract_installer') as extraction:
                with self.assertRaises(ValueError): install(args)
                extraction.assert_not_called()
            self.assertFalse(args.install_root.exists())


if __name__ == '__main__': unittest.main()
