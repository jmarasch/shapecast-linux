"""Install from a user-supplied product installer; never redistribute the product."""
import inspect
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from .common import LOCK, REPO, private_json, relative_path, sha256, supported_platform, verify_vendor
from . import __version__


def run(args, **kwargs):
    live=kwargs.pop('live',False)
    result = subprocess.run([str(a) for a in args], text=True, capture_output=not live, **kwargs)
    if result.returncode:
        detail = (result.stderr or result.stdout or 'See the command output above.').strip()[-3000:]
        raise ValueError('Command failed: '+str(args[0])+'\n'+detail)
    return result.stdout or ''


def download(spec, cache):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    target = cache/(spec['sha256']+'-'+spec['url'].rsplit('/', 1)[1])
    if target.is_file() and sha256(target) == spec['sha256']:
        print('Using verified cached download.', flush=True)
        return target
    partial = target.with_name(target.name+'.partial')
    print('Downloading '+spec['url'].rsplit('/', 1)[1]+'…', flush=True)
    try:
        request = urllib.request.Request(spec['url'], headers={'User-Agent':'shapecast-linux/'+__version__})
        with urllib.request.urlopen(request, timeout=60) as response, partial.open('wb') as out:
            shutil.copyfileobj(response, out, length=1024*1024)
        if sha256(partial) != spec['sha256']:
            raise ValueError('Download checksum did not match. The component was not installed.')
        partial.replace(target)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return target


def extract_tar(archive, destination):
    """Verify paths and links before extracting a checksum-verified component."""
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as source:
        for member in source:
            name = relative_path(member.name)
            target = (destination/name).resolve()
            if not target.is_relative_to(destination):
                raise ValueError('Archive entry escapes the component directory.')
            if member.isdev() or member.isfifo():
                raise ValueError('Device entries are not allowed in downloaded components.')
            if member.issym() or member.islnk():
                link = relative_path(member.linkname) if member.islnk() else Path(member.linkname)
                link_target = ((destination if member.islnk() else target.parent)/link).resolve()
                if not link_target.is_relative_to(destination):
                    raise ValueError('Archive link escapes the component directory.')
            # Python's additional data filter protects metadata on versions that offer it.
            if 'filter' in inspect.signature(source.extract).parameters:
                source.extract(member, destination, filter='data')
            else:
                source.extract(member, destination)


def extract_installer(installer, destination):
    seven = next((shutil.which(name) for name in ('7zz','7z') if shutil.which(name)), None)
    if not seven:
        raise ValueError('7-Zip is required. Install your distribution\'s 7zip or p7zip-full package.')
    listing = run([seven,'l','-slt',installer], timeout=90)
    if '\n----------\n' not in listing:
        raise ValueError('7-Zip did not return a readable installer file list.')
    for line in listing.split('\n----------\n',1)[1].splitlines():
        if line.startswith('Path = '):
            relative_path(line[7:])
    run([seven,'x','-y','-o'+str(destination),installer], timeout=180)
    for path in Path(destination).rglob('*'):
        if path.is_symlink():
            raise ValueError('Installer extraction contains an unexpected symbolic link.')
    shell = list(Path(destination).rglob('shapecast-shell.exe'))
    if len(shell) != 1 or not (shell[0].parent/'core-runtime/integrity.json').is_file():
        raise ValueError('This installer layout is not supported.')
    return shell[0].parent


def component(name, root, cache):
    spec = LOCK[name]
    folder = Path(root)/'components'/name
    if folder.exists():
        raise ValueError('Component directory already exists: '+str(folder))
    with tempfile.TemporaryDirectory(prefix='component-',dir=Path(root)) as stage:
        extract_tar(download(spec,cache),stage)
        source = Path(stage)/spec['directory'] if 'directory' in spec else Path(stage)
        if not (source/spec['executable']).is_file():
            raise ValueError('Downloaded component lacks its expected executable.')
        folder.parent.mkdir(parents=True,exist_ok=True)
        shutil.move(str(source),str(folder))
    return folder/spec['executable']


def python_version(executable):
    value = run([executable,'-c','import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'],timeout=20).strip()
    if value != LOCK['shapecast']['python_minor']:
        raise ValueError('The commercial bytecode requires Python '+LOCK['shapecast']['python_minor']+'.')


def blender_version(executable):
    output = run([executable,'--version'],timeout=30)
    match = re.search(r'Blender (\d+)\.(\d+)',output)
    if not match or tuple(map(int,match.groups())) < (4,2):
        raise ValueError('Blender 4.2 or newer is required for exports.')


def install(args):
    supported_platform()
    root = args.install_root.expanduser().resolve()
    installer = args.installer.expanduser().resolve()
    if not installer.is_file():
        raise ValueError('The purchased Windows installer was not found.')
    if sha256(installer) != LOCK['shapecast']['installer_sha256']:
        raise ValueError('This is not the tested Shapecast '+LOCK['shapecast']['core_version']+' Windows installer. A new version needs a compatibility update; no files were extracted.')
    if any((root/name).exists() for name in ('install.json','vendor','venv','profiles')):
        raise ValueError('An installation already exists here. Choose another --install-root; existing data will not be overwritten.')
    node = shutil.which('node')
    if not node:
        raise ValueError('Node.js is required to extract the web assets. Install nodejs from your distribution.')
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    cache = args.cache_dir.expanduser().resolve() if args.cache_dir else root/'cache'
    completed = []
    try:
        with tempfile.TemporaryDirectory(prefix='.extract-',dir=root) as stage:
            vendor=prepare_vendor(installer,Path(stage),node)
            shutil.move(str(vendor),str(root/'vendor'));completed.append(root/'vendor')
        core_count,asset_count=verify_vendor(root)
        print(f'Verified {core_count} commercial core files and {asset_count} private UI assets.',flush=True)
        py = args.python.expanduser().resolve() if args.python else component('python',root,cache)
        if not args.python:completed.append(root/'components/python')
        python_version(py)
        venv=root/'venv';completed.append(venv);run([py,'-m','venv',venv],timeout=60)
        command=[venv/'bin/python','-m','pip','install','--disable-pip-version-check','--cache-dir',cache/'pip','-r',REPO/'requirements-core.txt']
        if args.wheelhouse:
            command.extend(['--no-index','--find-links',args.wheelhouse.expanduser().resolve()])
        print('Installing the pinned Linux dependencies…',flush=True)
        run(command,timeout=600)
        blender=None
        if args.blender:
            blender=args.blender.expanduser().resolve();blender_version(blender)
        elif not args.without_blender:
            installed=shutil.which('blender')
            if installed:
                try:blender_version(installed);blender=Path(installed).resolve()
                except ValueError:pass
            if blender is None:
                blender=component('blender',root,cache);completed.append(root/'components/blender')
                blender_version(blender)
        completed.append(root/'profiles')
        for mode in ('preview','native'):
            home=root/'profiles'/mode
            (home/'library').mkdir(parents=True,exist_ok=True,mode=0o700)
            settings={'check_updates':False,'fake_stages':mode=='preview','allow_preview_generation':mode=='preview'}
            if blender:settings['blender_exe']=str(blender)
            if mode=='preview':settings['multiview']=False
            private_json(home/'data/settings.json',settings)
        private_json(root/'install.json',{'schema':1,'core_version':LOCK['shapecast']['core_version'],'installer_sha256':sha256(installer),'blender':str(blender) if blender else None,'cuda':None})
        print('Installation ready. Run: ./shapecast-linux launch --mode native; activate your own licence, then close the app and set up models/runtimes.',flush=True)
        print('Install directory: '+str(root),flush=True)
    except Exception:
        for path in reversed(completed):
            if path.is_dir():shutil.rmtree(path)
        raise


def prepare_vendor(installer,stage,node):
    source=extract_installer(installer,Path(stage)/'installer')
    vendor=Path(stage)/'vendor'
    packages=vendor/'packages';packages.mkdir(parents=True)
    original=source/'core-runtime/python/Lib/site-packages'
    dist=original/('shapecast_core-'+LOCK['shapecast']['core_version']+'.dist-info')
    if not dist.is_dir():raise ValueError('Installer core version does not match the reviewed release.')
    for name in ('shapecast_core',dist.name,'pipeline'):shutil.copytree(original/name,packages/name)
    shutil.copy2(source/'core-runtime/integrity.json',vendor/'integrity.json')
    shutil.copytree(source/'core-runtime/resources',vendor/'resources')
    run([node,REPO/'scripts/extract_frontend.cjs',source/'shapecast-shell.exe',vendor/'ui'],timeout=90)
    verify_vendor(Path(stage))
    return vendor


def update_vendor(args):
    import sqlite3
    import time
    from .common import read_install,profile
    from .session_control import existing_url,matching_servers
    root,config=read_install(args.install_root)
    if any(matching_servers(root,mode) or existing_url(profile(root,mode)) for mode in ('native','preview')):
        raise ValueError('Close native and preview sessions before applying a software update.')
    installer=args.installer.expanduser().resolve()
    if not installer.is_file() or sha256(installer)!=LOCK['shapecast']['installer_sha256']:
        raise ValueError('Only the installer reviewed in components.lock.json can be applied. Update the helper first.')
    node=shutil.which('node')
    if not node:raise ValueError('Node.js is required for interface extraction.')
    backup=root/'backups'/('before-'+LOCK['shapecast']['core_version']+'-'+str(time.time_ns()))
    backup.mkdir(parents=True,mode=0o700)
    private_json(backup/'install.json',config)
    for mode in ('native','preview'):
        home=profile(root,mode);dest=backup/mode;dest.mkdir(mode=0o700)
        for name in ('settings.json','license.dat'):
            if (home/'data'/name).is_file():shutil.copy2(home/'data'/name,dest/name)
        db=home/'data/library.db'
        if db.is_file():
            with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as source:
                with sqlite3.connect(dest/'library.db') as target:source.backup(target)
    with tempfile.TemporaryDirectory(prefix='.update-',dir=root) as stage:
        vendor=prepare_vendor(installer,Path(stage),node)
        (root/'vendor').rename(backup/'vendor')
        try:
            shutil.move(str(vendor),str(root/'vendor'))
            config.update(core_version=LOCK['shapecast']['core_version'],installer_sha256=sha256(installer))
            private_json(root/'install.json',config)
        except BaseException:
            if (root/'vendor').exists():shutil.rmtree(root/'vendor')
            (backup/'vendor').rename(root/'vendor');private_json(root/'install.json',json.loads((backup/'install.json').read_text()));raise
    print('Software updated. Profiles and native runtimes preserved. Rollback checkpoint: '+str(backup),flush=True)
