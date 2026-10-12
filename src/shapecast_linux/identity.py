"""Choose a real Linux NIC before the bundled libuuid can cache a random node.

Commercial fingerprint hashing and signature verification remain unchanged.
The saved selector must match a currently present physical factory address.
"""
import fcntl
import hashlib
import json
import os
import re
import tempfile
import uuid
from pathlib import Path


def physical_node(interface, sys_root):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', interface) or interface in ('.', '..', 'lo'):
        raise ValueError('Invalid physical network interface selector.')
    directory = Path(sys_root)/interface
    try:
        if not (directory/'device').exists():
            raise ValueError('The selected adapter is not a physical network device.')
        if (directory/'addr_assign_type').read_text().strip() != '0':
            raise ValueError('The selected adapter address is not its permanent hardware address.')
        text = (directory/'address').read_text().strip().lower()
    except OSError as error:
        raise ValueError('The selected physical network adapter is unavailable.') from error
    if not re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', text):
        raise ValueError('The selected adapter has an invalid hardware address.')
    node = int(text.replace(':', ''), 16)
    if node in (0, (1<<48)-1) or node & (3<<40):
        raise ValueError('A permanent unicast, universally administered hardware address is required.')
    return node


def node_hash(node):
    return hashlib.sha256(b'shapecast:'+f'{node:012x}'.encode()).hexdigest()[:16]


def configure_machine_identity(root, sys_root=Path('/sys/class/net')):
    """Pin the real adapter, verify it every startup, and populate Python's node cache."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    state = root/'machine-interface.json'
    lock_fd = os.open(root/'machine-interface.lock', os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(lock_fd, 'r+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if state.exists():
            data = json.loads(state.read_text())
            if data.get('schema') != 1:
                raise ValueError('Unsupported machine-interface configuration.')
            node = physical_node(data['interface'], sys_root)
            if node_hash(node) != data['mac_hash']:
                raise ValueError('The selected adapter address changed. Stop and check licence reactivation before using a new request code.')
        else:
            # Prefer a factory Ethernet address; exclude bridges, VMs and randomized Wi-Fi.
            candidates = []
            for directory in Path(sys_root).iterdir():
                try:
                    node = physical_node(directory.name, sys_root)
                    candidates.append(((directory/'wireless').exists(), directory.name, node))
                except ValueError:
                    continue
            if not candidates:
                raise ValueError('No stable physical network address was found. No activation code will be generated from a random fallback.')
            _, interface, node = min(candidates)
            data = {'schema':1, 'interface':interface, 'mac_hash':node_hash(node)}
            fd, temporary = tempfile.mkstemp(prefix='.machine-interface-', dir=root)
            try:
                with os.fdopen(fd, 'w') as stream:
                    json.dump(data, stream, indent=2); stream.write('\n')
                os.replace(temporary, state)
            finally:
                if os.path.exists(temporary): os.unlink(temporary)
        # This is the actual verified adapter address, never a user-supplied licence hash.
        uuid._node = node
        return dict(data)
