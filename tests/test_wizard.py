import json
import os
from argparse import Namespace
from contextlib import contextmanager
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock,patch

from shapecast_linux.common import LOCK,private_json
from shapecast_linux.wizard import Wizard,create_launchers,desktop_quote,path_answer,setup


class WizardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'private install'
        private_json(self.root/'install.json',{'schema':1,'core_version':LOCK['shapecast']['core_version']})
        self.args=Namespace(install_root=self.root,installer=None,cxx=None,no_browser=True)
    def tearDown(self):self.tmp.cleanup()
    def wizard(self,answers):
        answer=iter(answers)
        return Wizard(self.args,input_fn=lambda _:next(answer),output=lambda _:None)
    def run_wizard(self,wizard):
        with patch('shapecast_linux.wizard.verify_vendor'),patch('shapecast_linux.wizard.active_sessions',return_value=False),patch('shapecast_linux.wizard.gpu_info',return_value='Synthetic NVIDIA GPU'),patch.object(wizard,'prerequisites'):
            return wizard.run()

    def test_preview_setup_never_calls_licensing_models_or_gpu_setup(self):
        w=self.wizard(['','4','y','n','n']);w.command=Mock()
        with patch('shapecast_linux.wizard.license_status') as licence:
            self.assertEqual(self.run_wizard(w),0);licence.assert_not_called()
        w.command.assert_called_once_with('doctor','--mode','preview')
        self.assertEqual(json.loads((self.root/'setup-state.json').read_text())['stage'],'complete')
        self.assertIn('launch --mode preview',(self.root/'bin/start-shapecast').read_text())

    def test_native_setup_imports_selected_packs_before_runtime_and_checks(self):
        w=self.wizard(['','2','y','2','/synthetic/vendor packs','n','n']);w.command=Mock()
        with patch('shapecast_linux.wizard.license_status',return_value={'ok':True}):self.run_wizard(w)
        self.assertEqual(w.command.call_args_list[0].args,('models','--packs','models,engine,rig','--source',Path('/synthetic/vendor packs')))
        self.assertEqual(w.command.call_args_list[1].args,('runtime','--components','quality,image,rig,topology','--engine','quality'))
        self.assertEqual(w.command.call_args_list[2].args,('doctor','--mode','native'))

    def test_waiting_for_email_saves_resume_state_and_never_installs_models(self):
        w=self.wizard(['','1','y','later']);w.command=Mock();events=[]
        @contextmanager
        def session(root):
            events.append('started')
            try:yield 'http://127.0.0.1:12345/setup#synthetic'
            finally:events.append('stopped')
        with patch('shapecast_linux.wizard.license_status',return_value={'ok':False,'message':'Awaiting licence'}),patch('shapecast_linux.wizard.activation_session',session):
            self.run_wizard(w)
        self.assertEqual(events,['started','stopped']);w.command.assert_not_called()
        state=json.loads((self.root/'setup-state.json').read_text())
        self.assertEqual(state['stage'],'activation');self.assertEqual(state['preset'],'1')
        self.assertFalse((self.root/'bin/start-shapecast').exists())

    def test_activation_failure_never_becomes_permission_to_download(self):
        w=self.wizard(['check','later']);events=[]
        @contextmanager
        def session(root):
            try:yield 'http://127.0.0.1:12345/setup#synthetic'
            finally:events.append('closed')
        with patch('shapecast_linux.wizard.license_status',return_value={'ok':False,'message':'Not activated'}),patch('shapecast_linux.wizard.activation_session',session):
            self.assertFalse(w.activate())
        self.assertEqual(events,['closed'])

    def test_model_failure_stops_before_runtime_installation(self):
        w=self.wizard(['','2','y','1']);w.command=Mock(side_effect=ValueError('synthetic download error'))
        with patch('shapecast_linux.wizard.license_status',return_value={'ok':True}):
            with self.assertRaisesRegex(ValueError,'synthetic'):self.run_wizard(w)
        self.assertEqual(w.command.call_count,1)
        self.assertEqual(json.loads((self.root/'setup-state.json').read_text())['stage'],'models')

    def test_rerun_recovers_preset_without_changing_licence_or_library(self):
        private_json(self.root/'setup-state.json',{'schema':1,'preset':'4','stage':'checks'})
        key=self.root/'profiles/native/data/license.dat';key.parent.mkdir(parents=True);key.write_text('synthetic untouched licence')
        asset=self.root/'profiles/native/library/asset.txt';asset.parent.mkdir(parents=True);asset.write_text('keep')
        w=self.wizard(['','','y','n','n']);w.command=Mock();self.run_wizard(w)
        w.command.assert_called_once_with('doctor','--mode','preview')
        self.assertEqual(key.read_text(),'synthetic untouched licence');self.assertEqual(asset.read_text(),'keep')

    def test_existing_session_is_not_stopped_by_setup(self):
        w=self.wizard(['','4']);w.command=Mock()
        with patch('shapecast_linux.wizard.active_sessions',return_value=True):
            with self.assertRaisesRegex(ValueError,'running'):w.run()
        w.command.assert_not_called();self.assertFalse((self.root/'setup-state.json').exists())

    def test_cancelled_plan_does_not_modify_installation(self):
        w=self.wizard(['','4','n']);w.command=Mock();self.run_wizard(w)
        w.command.assert_not_called();self.assertFalse((self.root/'setup-state.json').exists())

    def test_noninteractive_setup_is_actionable_and_does_not_run(self):
        with patch('sys.stdin.isatty',return_value=False),patch.object(Wizard,'run') as run:
            with self.assertRaisesRegex(ValueError,'interactive terminal'):setup(self.args)
            run.assert_not_called()

    def test_system_package_installation_needs_explicit_yes(self):
        w=self.wizard([''])
        with patch('shapecast_linux.wizard.missing_prerequisites',return_value=[('7-Zip','7zip')]),patch('shutil.which',return_value='/synthetic/apt-get'),patch('subprocess.run') as run:
            with self.assertRaisesRegex(ValueError,'paused'):w.prerequisites(False)
            run.assert_not_called()

    def test_launcher_preserves_paths_without_shell_interpolation(self):
        repo=Path(self.tmp.name)/'repo $() % space';repo.mkdir()
        (repo/'shapecast-linux').write_text('#!/bin/bash\nprintf \'%s\\0\' "$@"\n')
        root=Path(self.tmp.name)/'install $() % space';apps=Path(self.tmp.name)/'applications'
        with patch('shapecast_linux.wizard.REPO',repo):launcher=create_launchers(root,'native',apps)
        result=subprocess.run([str(launcher),'--no-browser'],capture_output=True,check=True)
        self.assertEqual(result.stdout.split(b'\0')[:-1],[b'--install-root',str(root).encode(),b'launch',b'--mode',b'native',b'--no-browser'])
        desktop=(apps/'shapecast-linux.desktop').read_text()
        self.assertIn('%%',desktop);self.assertIn('\\$',desktop)

    def test_unrelated_menu_entry_is_preserved(self):
        apps=Path(self.tmp.name)/'applications';apps.mkdir();p=apps/'shapecast-linux.desktop';p.write_text('owned by another app')
        with self.assertRaisesRegex(ValueError,'unrelated'):create_launchers(self.root,'native',apps)
        self.assertEqual(p.read_text(),'owned by another app')

    def test_quoted_path_answers_keep_literal_spaces_and_dollar_signs(self):
        self.assertEqual(path_answer('\"/tmp/data $test folder\"'),Path('/tmp/data $test folder'))

    def test_unrelated_launch_script_is_preserved(self):
        p=self.root/'bin/start-shapecast';p.parent.mkdir();p.write_text('keep this user script')
        with self.assertRaisesRegex(ValueError,'unrelated'):create_launchers(self.root,'native')
        self.assertEqual(p.read_text(),'keep this user script')

    def test_missing_gpu_can_finish_as_preview_without_downloading_models(self):
        w=self.wizard(['','1','1','y','n','n']);w.command=Mock()
        with patch('shapecast_linux.wizard.verify_vendor'),patch('shapecast_linux.wizard.active_sessions',return_value=False),patch('shapecast_linux.wizard.gpu_info',return_value=None),patch.object(w,'prerequisites'):
            w.run()
        w.command.assert_called_once_with('doctor','--mode','preview')

    def test_failed_original_licence_probe_never_looks_activated(self):
        from shapecast_linux.wizard import license_status
        with patch('subprocess.run',return_value=Namespace(returncode=1,stdout='',stderr='synthetic failure')):
            with self.assertRaisesRegex(ValueError,'licence check'):license_status(self.root)

    def test_fresh_preview_install_uses_only_the_reviewed_installer(self):
        (self.root/'install.json').unlink()
        installer=Path(self.tmp.name)/'purchased setup.exe';installer.write_text('synthetic installer')
        self.args.installer=installer
        w=self.wizard(['','4','y','n','n']);w.command=Mock()
        with patch('shapecast_linux.common.sha256',return_value=LOCK['shapecast']['installer_sha256']):self.run_wizard(w)
        self.assertEqual(w.command.call_args_list[0].args,('install','--installer',installer))
        self.assertEqual(w.command.call_args_list[1].args,('doctor','--mode','preview'))

if __name__=='__main__':unittest.main()
