"""Own this test's lock and reopen or restart only its native setup server."""
import fcntl
import json
import os
import signal
import time
import urllib.error
import urllib.request
import webbrowser
from .common import private_json
from pathlib import Path


def matching_servers(root, mode):
    found = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdecimal() or int(entry.name) == os.getpid():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            args = (entry/'cmdline').read_bytes().split(b'\0')
            expected = ['-m', 'shapecast_linux.server', '--install-root', str(root), '--mode', mode]
            if [v.decode() for v in args[1:7]] != expected:
                continue
            if not Path(args[0].decode()).name.startswith('python'):
                continue
            stat = (entry/'stat').read_text().rsplit(')', 1)[1].split()
            found.append((int(entry.name), stat[19]))
        except (OSError, UnicodeError, IndexError):
            continue
    return found


def still_same(pid, started):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return fields[0] != 'Z' and fields[19] == started
    except (OSError, IndexError):
        return False


def stop_servers(root, mode):
    servers = matching_servers(root, mode)
    for pid, started in servers:
        if still_same(pid, started):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and any(still_same(*p) for p in servers):
        time.sleep(.1)
    for pid, started in servers:
        if still_same(pid, started):
            # An explicit --restart may stop an unresponsive setup server too.
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    return len(servers)


def existing_url(root):
    try:
        state = json.loads((root/'session.json').read_text())
        port, core_port = int(state['ui_port']), int(state['core_port'])
        if not (0 < port < 65536 and 0 < core_port < 65536):
            return None
        token = state['token']
        if not isinstance(token, str) or not token or not all(c.isalnum() or c in '-_' for c in token):
            return None
        # Authenticate against the running UI, rather than trust a stale PID file.
        request = urllib.request.Request(f'http://127.0.0.1:{port}/native-status', headers={'Authorization': 'Bearer '+token})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=3) as response:
            if response.status != 200:
                return None
        start_path = state.get('start_path', '/')
        if start_path not in ('/', '/preview'):
            return None
        return f'http://127.0.0.1:{port}{start_path}#core={core_port}&token={token}'
    except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError):
        return None


def acquire(root, install_root, mode, restart=False, no_browser=False):
    if restart:
        print('Closing the previous native setup session…', flush=True)
        stop_servers(install_root, mode)
    lock = (root/'serve.lock').open('a')
    # Python descriptors are non-inheritable: spawned tools/browser cannot retain this lock.
    os.set_inheritable(lock.fileno(), False)
    deadline = time.monotonic() + (3 if restart else 0)
    while True:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return lock
        except BlockingIOError:
            if time.monotonic() < deadline:
                time.sleep(.1)
                continue
            url = existing_url(root)
            lock.close()
            if url:
                print('Reopening the running native setup page:\n'+url, flush=True)
                if not no_browser:
                    webbrowser.open(url)
                return None
            raise RuntimeError('An older native test still holds the setup lock. Run this launcher with --restart from your normal terminal.')


def save_session(root, ui_port, core_port, token, start_path='/'):
    private_json(root/'session.json', {'ui_port': ui_port, 'core_port': core_port, 'token': token, 'start_path': start_path})


def clear_session(root, token):
    try:
        path = root/'session.json'
        if json.loads(path.read_text()).get('token') == token:
            path.unlink()
    except (OSError, ValueError):
        pass
