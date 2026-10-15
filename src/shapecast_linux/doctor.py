"""Local diagnostic with an allowlist of report fields; never emit license contents."""
import argparse
import json
import platform
import secrets
from pathlib import Path

from .common import read_install, verify_vendor
from .identity import configure_machine_identity
from .server import profile_settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--install-root', type=Path, required=True)
    parser.add_argument('--mode', choices=('preview', 'native'), required=True)
    args = parser.parse_args()
    root, config = read_install(args.install_root)
    core_count, asset_count = verify_vendor(root)
    configure_machine_identity(root)
    from fastapi.testclient import TestClient
    from shapecast_core.api.app import create_app
    from shapecast_core.config import Settings
    token = secrets.token_urlsafe(32)
    settings = profile_settings(Settings.load(), root, args.mode)
    report = {'platform': platform.system(), 'python': platform.python_version(),
              'core_version': config['core_version'], 'core_files_verified': core_count,
              'ui_assets_verified': asset_count, 'profile': args.mode, 'runs_generation': False}
    report['machine_id_source'] = 'Verified permanent physical network adapter'
    with TestClient(create_app(settings=settings, token=token)) as client:
        headers = {'Authorization': 'Bearer '+token}
        for name, route, fields in (
            ('health', '/healthz', ('status', 'version')),
            ('system', '/v1/system', ('engine_ready',)),
            ('license', '/v1/system/license', ('ok', 'code')),
            ('hardware', '/v1/system/hardware', ('gpu_name', 'vram_mib', 'cuda_capable')),
        ):
            response = client.get(route, headers=headers)
            response.raise_for_status()
            value = response.json()
            report[name] = {key: value.get(key) for key in fields}
        if client.get('/v1/system').status_code != 401:
            raise RuntimeError('API authentication check failed.')
    from .installer import blender_version
    try:
        if not config.get('blender'): raise ValueError('Blender not configured')
        blender_version(config['blender'])
        report['blender_available'] = True
    except (OSError, ValueError):
        report['blender_available'] = False
    report['native_runtimes']={name:(root/'runtimes'/name/'linux-runtime-ready.json').is_file() for name in ('quality','image','rig','tools')}
    report['cuda_runtime_installed'] = bool(config.get('cuda'))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
