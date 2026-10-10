"""Paths and validation shared by the installer and launchers (standard library only)."""
import hashlib
import json
import os
import platform
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath

REPO = Path(__file__).resolve().parents[2]
WEB = REPO/'web'
LOCK = json.loads((REPO/'components.lock.json').read_text())


def default_root():
    return Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))/'shapecast-linux'


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def relative_path(value):
    """Normalize archive names and reject absolute, drive and traversal paths."""
    value = str(value).replace('\\', '/')
    path = PurePosixPath(value)
    if not value or path.is_absolute() or PureWindowsPath(value).drive or '..' in path.parts:
        raise ValueError('Unsafe relative path: '+value)
    return Path(*path.parts)


def private_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix='.'+path.name+'-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, indent=2)
            stream.write('\n')
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_install(root):
    root = Path(root).expanduser().resolve()
    try:
        config = json.loads((root/'install.json').read_text())
    except FileNotFoundError:
        raise ValueError('Shapecast is not installed here. Run the install command first.') from None
    if config.get('schema') != 1:
        raise ValueError('This installation uses an unsupported configuration format.')
    return root, config


def profile(root, mode):
    if mode not in ('native', 'preview'):
        raise ValueError('Unknown profile.')
    return Path(root)/'profiles'/mode


def core_environment(root, mode):
    root = Path(root).resolve()
    home = profile(root, mode)
    env = os.environ.copy()
    env.update(PYTHONPATH=os.pathsep.join([str(root/'vendor/packages'), str(REPO/'src')]),
               SHAPECAST_DATA_DIR=str(home/'data'), SHAPECAST_LIBRARY_DIR=str(home/'library'),
               SHAPECAST_RESOURCES=str(root/'vendor/resources'), SHAPECAST_CHECK_UPDATES='false')
    for key in ('SHAPECAST_PARENT_PID', 'SHAPECAST_LAUNCH_TOKEN', 'SHAPECAST_API_KEY',
                'SHAPECAST_FAKE_STAGES', 'SHAPECAST_ALLOW_PREVIEW_GENERATION', 'PYTHONHOME'):
        env.pop(key, None)
    return env


def verify_vendor(root):
    root = Path(root)
    manifest = json.loads((root/'vendor/integrity.json').read_text())
    for name, size, digest in manifest['files']:
        prefix = 'python/Lib/site-packages/'
        if not name.startswith(prefix):
            raise ValueError('Unexpected commercial-core manifest path.')
        path = root/'vendor/packages'/relative_path(name[len(prefix):])
        if path.stat().st_size != size or sha256(path) != digest:
            raise ValueError('Commercial-core integrity check failed: '+name)
    ui = json.loads((root/'vendor/ui/extraction-manifest.json').read_text())
    for entry in ui['assets']:
        path = root/'vendor/ui'/relative_path(entry['path'].lstrip('/'))
        if path.stat().st_size != entry['size'] or sha256(path) != entry['sha256']:
            raise ValueError('Original interface integrity check failed: '+entry['path'])
    return len(manifest['files']), len(ui['assets'])


def supported_platform():
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'amd64'):
        raise ValueError('This experimental release supports Linux x86-64 only.')
