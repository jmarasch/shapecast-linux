"""Standard-library bootstrap; commercial imports only run in the installed venv."""
import argparse
import os
import subprocess
import sys
from pathlib import Path

from .common import core_environment, default_root, read_install, supported_platform


def main():
    parser = argparse.ArgumentParser(description='Unofficial Shapecast Linux compatibility helper')
    parser.add_argument('--install-root', type=Path, default=default_root(), help='Private runtime and data directory')
    commands = parser.add_subparsers(dest='command', required=True)
    setup = commands.add_parser('install', help='Install from your purchased Windows installer')
    setup.add_argument('--installer', type=Path, required=True)
    setup.add_argument('--python', type=Path, help='Existing CPython 3.11 executable')
    setup.add_argument('--blender', type=Path, help='Existing Blender 4.2+ executable')
    setup.add_argument('--without-blender', action='store_true', help='Skip Blender; exports and some jobs will be unavailable')
    setup.add_argument('--cache-dir', type=Path)
    setup.add_argument('--wheelhouse', type=Path, help='Offline directory of pinned Linux dependency wheels')
    launch = commands.add_parser('launch', help='Open the local browser interface')
    launch.add_argument('--mode', choices=('preview', 'native'), default='native')
    launch.add_argument('--restart', action='store_true')
    launch.add_argument('--no-browser', action='store_true')
    doctor = commands.add_parser('doctor', help='Check private runtime, API, Blender and license status')
    doctor.add_argument('--mode', choices=('preview', 'native'), default='native')
    runtime = commands.add_parser('runtime', help='Install native inference environments')
    runtime.add_argument('--engine',choices=('quality','fast'),help='Select the default mesh engine after setup')
    runtime.add_argument('--components', default='all', help='quality,image,rig,tools,fast,topology or all')
    runtime.add_argument('--wheelhouse', type=Path)
    runtime.add_argument('--cuda-home', type=Path)
    runtime.add_argument('--cxx', type=Path)
    runtime.add_argument('--jobs', type=int, default=2)
    runtime.add_argument('--cache-dir', type=Path)
    models=commands.add_parser('models',help='Download or import licensed model/engine files')
    models.add_argument('--packs',default='models,engine',help='models,engine,rig,engine2 (comma-separated)')
    models.add_argument('--source',type=Path,help='Existing vendor packs folder or one pack with pack.json')
    update=commands.add_parser('update',help='Apply a reviewed Windows installer without replacing profiles')
    update.add_argument('--installer',type=Path,required=True)
    args = parser.parse_args()
    try:
        supported_platform()
        if args.command == 'install':
            from .installer import install
            install(args)
        elif args.command == 'runtime':
            from .native import install_runtimes
            install_runtimes(args)
        elif args.command == 'update':
            from .installer import update_vendor
            update_vendor(args)
        elif args.command == 'models':
            root,_=read_install(args.install_root)
            argv=[root/'venv/bin/python','-m','shapecast_linux.models','--install-root',root,'--packs',args.packs]
            if args.source:argv+=['--source',args.source.expanduser().resolve()]
            return subprocess.call([str(a) for a in argv],env=core_environment(root,'native'))
        else:
            root, _ = read_install(args.install_root)
            if args.command == 'launch':
                # Canonical argument order also identifies this exact profile on --restart.
                argv = [root/'venv/bin/python', '-m', 'shapecast_linux.server', '--install-root', root, '--mode', args.mode]
                if args.restart: argv.append('--restart')
                if args.no_browser: argv.append('--no-browser')
                os.execve(str(argv[0]), [str(v) for v in argv], core_environment(root, args.mode))
            result = subprocess.run([root/'venv/bin/python', '-m', 'shapecast_linux.doctor', '--install-root', root, '--mode', args.mode],
                                    env=core_environment(root, args.mode))
            return result.returncode
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        print('Shapecast Linux: '+str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
