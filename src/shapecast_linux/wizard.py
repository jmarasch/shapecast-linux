"""Interactive setup orchestration; uses the same verified installer and licence gates."""
from contextlib import contextmanager
import ctypes.util
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser

from .common import LOCK, REPO, core_environment, private_json, profile, read_install, verify_vendor

PRESETS = {
    '1': ('Full setup', 'quality,image,rig,tools,fast,topology', 'models,engine,rig,engine2', 'quality'),
    '2': ('Quality + images + rigging + topology', 'quality,image,rig,topology', 'models,engine,rig', 'quality'),
    '3': ('Fast + images + sharpening + topology', 'fast,image,tools,topology', 'models,engine,engine2', 'fast'),
    '4': ('Placeholder previews and exports only', '', '', 'preview'),
}


def path_answer(value):
    value=value.strip()
    if len(value)>1 and value[0]==value[-1] and value[0] in ('\"', "'"):
        value=value[1:-1]
    return Path(value).expanduser().resolve()


def compiler_available(supplied=None):
    for name in ((str(supplied),) if supplied else ('g++-13','g++-14','g++')):
        command=shutil.which(name)
        if not command:continue
        result=subprocess.run([command,'-dumpfullversion'],capture_output=True,text=True,timeout=10)
        try:
            if result.returncode==0 and int(result.stdout.strip().split('.')[0])<=14:return command
        except ValueError:pass
    return None


def missing_prerequisites(quality,cxx=None):
    missing=[]
    node=shutil.which('node')
    if node:
        result=subprocess.run([node,'--version'],capture_output=True,text=True,timeout=10)
        try:node=result.returncode==0 and int(result.stdout.strip().lstrip('v').split('.')[0])>=18
        except ValueError:node=False
    if not node:missing.append(('Node.js 18 or newer','nodejs'))
    if not any(shutil.which(n) for n in ('7zz','7z')):missing.append(('7-Zip','7zip'))
    if quality and not compiler_available(cxx):missing.append(('GCC 13/14 C++ compiler','g++-13'))
    for library,package in [('GL','libgl1'),('EGL','libegl1'),('Xrender','libxrender1'),('Xi','libxi6'),('Xrandr','libxrandr2'),('Xinerama','libxinerama1'),('Xcursor','libxcursor1')]:
        if not ctypes.util.find_library(library):missing.append((library+' shared library',package))
    return missing


def gpu_info():
    command=shutil.which('nvidia-smi')
    if not command:return None
    result=subprocess.run([command,'--query-gpu=name,memory.total,driver_version','--format=csv,noheader'],capture_output=True,text=True,timeout=20)
    return result.stdout.strip() if result.returncode==0 and result.stdout.strip() else None


def license_status(root):
    # Only the original signature/machine check decides whether setup can continue.
    code=('from pathlib import Path; import os,json; '
          'from shapecast_linux.identity import configure_machine_identity; '
          'configure_machine_identity(Path(os.environ["SHAPECAST_LINUX_ROOT"])); '
          'from shapecast_core.config import Settings; from shapecast_core import licensing; '
          's=licensing.load_status(Settings.load()); '
          'print(json.dumps({"ok":bool(s.ok),"message":str(s.message)}))')
    result=subprocess.run([str(root/'venv/bin/python'),'-c',code],env=core_environment(root,'native'),
                          text=True,capture_output=True,timeout=30)
    if result.returncode:raise ValueError('The original licence check could not run. Use the doctor command before continuing.')
    return json.loads(result.stdout.strip().splitlines()[-1])


def active_sessions(root):
    from .session_control import existing_url,matching_servers
    return any(matching_servers(root,mode) or existing_url(profile(root,mode)) for mode in ('native','preview'))


@contextmanager
def activation_session(root):
    """Own just this temporary server; close it on pause, interruption or success."""
    from .session_control import existing_url
    if active_sessions(root):raise ValueError('Close this installation\'s running sessions before setup.')
    folder=root/'setup-logs';folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(folder/'activation.log',os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    process=None
    with os.fdopen(fd,'a') as log:
        try:
            process=subprocess.Popen([str(root/'venv/bin/python'),'-m','shapecast_linux.server',
                                      '--install-root',str(root),'--mode','native','--no-browser'],
                                     env=core_environment(root,'native'),stdout=log,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+60
            while time.monotonic()<deadline:
                if process.poll() is not None:raise ValueError('Activation page did not start. See '+str(folder/'activation.log'))
                url=existing_url(profile(root,'native'))
                if url:
                    yield url.replace('/#','/setup#',1)
                    return
                time.sleep(.2)
            raise ValueError('Activation page startup timed out. See '+str(folder/'activation.log'))
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:process.wait(timeout=15)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)


def desktop_quote(value):
    value=str(value).replace('%','%%')
    for old,new in [('\\','\\\\'),('"','\\"'),('`','\\`'),('$','\\$')]:value=value.replace(old,new)
    return '"'+value+'"'


def desktop_directory():
    """Respect localized/custom XDG desktops; home means desktop icons are disabled."""
    command=shutil.which('xdg-user-dir')
    if command:
        try:
            result=subprocess.run([command,'DESKTOP'],capture_output=True,text=True,timeout=10)
            value=result.stdout.strip()
            if result.returncode==0 and value and Path(value).is_absolute():
                folder=Path(value).resolve()
                return folder if folder!=Path.home().resolve() else None
        except (OSError,subprocess.TimeoutExpired):pass
    folder=Path.home()/'Desktop'
    return folder if folder.is_dir() else None


def create_launchers(root,mode,applications=None,desktop_dir=None):
    root=Path(root).resolve()
    folder=root/'bin'
    launcher=folder/'start-shapecast'
    script_marker='# Generated by shapecast-linux guided setup'
    if launcher.exists() and script_marker not in launcher.read_text():
        raise ValueError('An unrelated start-shapecast file already exists; it was kept: '+str(launcher))
    install_id=hashlib.sha256(str(root).encode()).hexdigest()[:16]
    marker='X-Shapecast-Linux-Helper=true'
    identity='X-Shapecast-Linux-Install='+install_id
    targets=[(Path(directory),'desktop' if is_desktop else 'menu',is_desktop)
             for directory,is_desktop in ((applications,False),(desktop_dir,True)) if directory is not None]
    alternate=False
    for directory,label,_ in targets:
        entry=directory/'shapecast-linux.desktop'
        if not entry.exists():continue
        content=entry.read_text()
        if marker not in content:
            raise ValueError('An unrelated Shapecast '+label+' entry already exists; it was kept: '+str(entry))
        if identity not in content.splitlines() and 'Exec='+desktop_quote(launcher) not in content.splitlines():
            alternate=True
    filename='shapecast-linux'+('-'+install_id if alternate else '')+'.desktop'
    name='Shapecast (Linux'+(' — '+' '.join(root.name.split()) if alternate else '')+')'
    destinations=[]
    for directory,label,is_desktop in targets:
        own=[]
        if directory.is_dir():
            for candidate in sorted(directory.glob('shapecast-linux*.desktop')):
                if not candidate.is_file():continue
                content=candidate.read_text()
                if marker in content and (identity in content.splitlines() or 'Exec='+desktop_quote(launcher) in content.splitlines()):
                    own.append(candidate)
        entry=own[0] if own else directory/filename
        if entry.exists():
            content=entry.read_text()
            if marker not in content or (identity not in content.splitlines() and 'Exec='+desktop_quote(launcher) not in content.splitlines()):
                raise ValueError('An unrelated Shapecast '+label+' entry already exists; it was kept: '+str(entry))
        destinations.append((entry,is_desktop))
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    launcher.write_text('#!/usr/bin/env bash\n'+script_marker+'\nset -euo pipefail\nexec bash '+shlex.quote(str(REPO/'shapecast-linux'))+
                        ' --install-root '+shlex.quote(str(root))+' launch --mode '+shlex.quote(mode)+' "$@"\n')
    launcher.chmod(0o700)
    content=('[Desktop Entry]\nVersion=1.0\nType=Application\nName='+name+'\nComment=Start Shapecast\nExec='+desktop_quote(launcher)+
             '\nIcon=applications-graphics\nTerminal=true\nCategories=Graphics;3DGraphics;\nStartupNotify=false\n'+marker+'\n'+identity+'\n')
    for entry,is_desktop in destinations:
        entry.parent.mkdir(parents=True,exist_ok=True)
        entry.write_text(content);entry.chmod(0o755 if is_desktop else 0o644)
    return launcher


class Wizard:
    def __init__(self,args,input_fn=None,output=None):
        self.args=args;self.ask=input_fn or input;self.say=output or print
        self.root=args.install_root.expanduser().resolve()
        self.state={}

    def prompt(self,label,default=None):
        suffix=' ['+str(default)+']' if default is not None else ''
        value=self.ask(label+suffix+': ').strip()
        return value or (str(default) if default is not None else '')

    def yes(self,label,default=True):
        while True:
            value=self.ask(label+(' [Y/n]: ' if default else ' [y/N]: ')).strip().lower()
            if not value:return default
            if value in ('y','yes'):return True
            if value in ('n','no'):return False
            self.say('Please enter y or n.')

    def choose(self,label,choices,default):
        self.say(label)
        for key,value in choices.items():self.say('  '+key+' · '+value)
        while True:
            value=self.prompt('Choose',default)
            if value in choices:return value
            self.say('Choose one of: '+', '.join(choices))

    def save(self,stage):
        self.state.update(schema=1,stage=stage)
        private_json(self.root/'setup-state.json',self.state)

    def command(self,*args):
        labels={'install':'Installing the reviewed core, private Python and Blender…',
                'update':'Backing up and updating the reviewed application…',
                'models':'Checking and setting up your licensed model packs…',
                'runtime':'Preparing the selected native inference environments…',
                'doctor':'Running the final installation checks…','launch':'Starting Shapecast…'}
        self.say('\n'+labels.get(args[0],'Continuing setup…'))
        result=subprocess.run(['bash',str(REPO/'shapecast-linux'),'--install-root',str(self.root),*[str(v) for v in args]])
        if result.returncode:raise ValueError('This setup step did not finish. Fix the error above and rerun ./setup.sh to resume.')

    def prerequisites(self,quality):
        if quality and self.args.cxx and not compiler_available(self.args.cxx):
            raise ValueError('The supplied C++ compiler is missing or newer than GCC 14.')
        missing=missing_prerequisites(quality,self.args.cxx)
        if not missing:return
        self.say('System packages still needed: '+', '.join(label for label,_ in missing))
        packages=[package for _,package in missing]
        if not shutil.which('apt-get'):
            raise ValueError('Install those packages with your distribution\'s package manager, then run setup again.')
        if not self.yes('Install just these packages using apt and sudo?',False):
            raise ValueError('Setup paused. Install the listed packages, then run ./setup.sh again.')
        if '7zip' in packages and shutil.which('apt-cache'):
            if subprocess.run(['apt-cache','show','7zip'],capture_output=True).returncode:
                packages[packages.index('7zip')]='p7zip-full'
        sudo=[] if os.geteuid()==0 else ['sudo']
        for command in ([*sudo,'apt-get','update'],[*sudo,'apt-get','install','-y',*packages]):
            if subprocess.run(command).returncode:raise ValueError('System package installation failed. Setup can be resumed.')
        remaining=missing_prerequisites(quality,self.args.cxx)
        if remaining:raise ValueError('A supported package version is still missing: '+', '.join(label for label,_ in remaining))

    def installer_path(self):
        from .common import sha256
        candidate=self.args.installer
        while True:
            if candidate is None:candidate=path_answer(self.prompt('Path to your purchased Shapecast '+LOCK['shapecast']['core_version']+' Windows installer'))
            candidate=Path(candidate).expanduser().resolve()
            if candidate.is_file() and sha256(candidate)==LOCK['shapecast']['installer_sha256']:return candidate
            self.say('That file is missing or is not the reviewed '+LOCK['shapecast']['core_version']+' installer. Existing files were not changed.')
            candidate=None

    def activate(self):
        if license_status(self.root)['ok']:return True
        self.say('Activation uses Shapecast\'s original licence check. Your licence must match this Linux machine.')
        with activation_session(self.root) as url:
            self.say('Open this local activation page:\n'+url)
            if not self.args.no_browser:
                try:webbrowser.open(url)
                except OSError:pass
            self.say('Use the page to request/apply your emailed licence. Do not paste the licence into this terminal.')
            while True:
                answer=self.prompt('Press Enter after activation, or type later to save and finish','check').lower()
                if answer in ('later','q','quit'):return False
                status=license_status(self.root)
                if status['ok']:return True
                self.say(status.get('message') or 'Still awaiting a valid licence. You can leave and resume later.')

    def run(self):
        self.say('\nShapecast Linux setup — guided installation\n')
        if sys.version_info<(3,10):raise ValueError('Run this helper with Python 3.10 or newer.')
        self.say('Your purchased installer and vendor-issued licence are required for AI generation. You can pause and resume this wizard.')
        self.root=path_answer(self.prompt('Install/data folder',self.root))
        state_path=self.root/'setup-state.json'
        if state_path.is_file():
            saved=json.loads(state_path.read_text())
            if saved.get('schema')==1:self.state=saved
        selected=self.choose('What would you like to set up?',{k:v[0] for k,v in PRESETS.items()},self.state.get('preset','1'))
        label,components,packs,engine=PRESETS[selected]
        if engine!='preview':
            gpu=gpu_info()
            if gpu:self.say('NVIDIA graphics: '+gpu)
            else:
                self.say('The NVIDIA driver/GPU is unavailable. Fix the driver before downloading AI packs, or use placeholder previews now.')
                choice=self.choose('Continue with:',{'1':'Placeholder previews only','2':'Stop setup'},'2')
                if choice=='2':return 0
                selected='4';label,components,packs,engine=PRESETS[selected]
        if active_sessions(self.root):raise ValueError('Shapecast is running here. Close its terminal, then rerun setup; no running cast was stopped.')
        self.prerequisites('quality' in components.split(','))
        existing=(self.root/'install.json').is_file()
        config=None
        if existing:
            _,config=read_install(self.root);verify_vendor(self.root)
            self.say('Found existing Shapecast '+config['core_version']+'. Your licence, libraries and runtimes will be kept.')
        installer=None
        if not existing or config['core_version']!=LOCK['shapecast']['core_version']:installer=self.installer_path()
        self.say('\nSetup plan: '+label+'\nPrivate installation: '+str(self.root))
        if packs:self.say('Model packs: '+packs+'\nNative runtimes: '+components+'\nAllow up to 180 GB for a full fresh setup; each model step checks actual free space.')
        if installer:self.say('Installer: '+str(installer)+' (verified reviewed release)')
        if not self.yes('Continue with this setup?',True):self.say('Setup cancelled.');return 0
        self.state.update(preset=selected,components=components,packs=packs,engine=engine)
        self.save('install')
        if not existing:self.command('install','--installer',installer)
        elif installer:self.command('update','--installer',installer)
        if engine!='preview':
            self.save('activation')
            if not self.activate():
                self.save('activation');self.say('Setup saved. Run ./setup.sh again when your licence email arrives.');return 0
            # The temporary activation session is closed before any model/runtime writes.
            self.save('models')
            action=self.choose('How should the model packs be installed?',{'1':'Download official packs','2':'Import packs you already downloaded','3':'Save and do this later'},'1')
            if action=='3':self.say('Setup saved. Run ./setup.sh again to continue.');return 0
            args=['models','--packs',packs]
            if action=='2':args+=['--source',path_answer(self.prompt('Parent folder containing your vendor packs'))]
            self.command(*args)
            self.save('runtimes');runtime_args=['runtime','--components',components,'--engine',engine]
            if self.args.cxx:runtime_args+=['--cxx',self.args.cxx.expanduser().resolve()]
            self.command(*runtime_args)
        mode='preview' if engine=='preview' else 'native'
        self.save('checks');self.command('doctor','--mode',mode)
        applications=None
        if self.yes('Create a Shapecast entry in your application menu?',True):
            applications=Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'applications'
        desktop_dir=desktop_directory()
        if desktop_dir is not None:
            if not self.yes('Create a Shapecast shortcut on your desktop?',True):desktop_dir=None
        else:self.say('No desktop folder is configured; skipping the desktop shortcut.')
        launcher=create_launchers(self.root,mode,applications,desktop_dir)
        if applications is not None:self.say('Application-menu shortcut saved in '+str(applications))
        if desktop_dir is not None:self.say('Desktop shortcut saved in '+str(desktop_dir))
        self.save('complete')
        self.say('\nSetup complete. Start Shapecast with:\n'+str(launcher)+'\nKeep the repository folder; it contains the launcher code. Ctrl+C in its terminal stops the app.')
        if self.yes('Start Shapecast now?',False):self.command('launch','--mode',mode,*(['--no-browser'] if self.args.no_browser else []))
        return 0


def setup(args):
    if not sys.stdin.isatty():raise ValueError('Guided setup needs an interactive terminal. Open a terminal and run ./setup.sh, or use the documented install/models/runtime commands.')
    try:return Wizard(args).run()
    except (KeyboardInterrupt,EOFError):
        print('\nSetup paused. Run ./setup.sh again to resume.');return 130
