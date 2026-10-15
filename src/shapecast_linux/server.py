"""Loopback-only browser host for a privately installed commercial core."""
import argparse
import ctypes
import secrets
import socket
import threading
import time
import webbrowser
from pathlib import Path

from .common import profile, read_install, verify_vendor
from .identity import configure_machine_identity
from .session_control import acquire, clear_session, save_session
from .ui_server import make_ui


def profile_settings(settings, root, mode):
    """Keep preview jobs and their explicit vendor permission in the preview profile."""
    home = profile(root, mode)
    for key, folder in (('data_dir', 'data'), ('library_dir', 'library')):
        if Path(getattr(settings, key)).resolve() != (home/folder).resolve():
            raise ValueError('This launcher requires its own separate profile folders.')
    changes = {'allow_preview_generation': mode == 'preview','fake_stages':mode == 'preview'}
    if mode == 'preview':
        changes.update(fake_stages=True, multiview=False)
    return settings.model_copy(update=changes)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--install-root', type=Path, required=True)
    parser.add_argument('--mode', choices=('preview', 'native'), required=True)
    parser.add_argument('--restart', action='store_true')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    root, config = read_install(args.install_root)
    verify_vendor(root)
    configure_machine_identity(root)
    home = profile(root, args.mode)
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = acquire(home, root, args.mode, args.restart, args.no_browser)
    if lock is None:
        return
    import uvicorn
    from shapecast_core.api.app import create_app
    from shapecast_core.config import Settings
    from shapecast_core.stages.engine2 import missing_weights

    native={}
    if args.mode=='native':
        from .native import configure
        native=configure(root)
    settings = profile_settings(Settings.load(), root, args.mode)
    token = secrets.token_urlsafe(32)
    from .compat import install as install_compat
    install_compat(root)
    app = create_app(settings=settings, token=token)
    if args.mode=='native':
        from .updates import install_update_routes
        from shapecast_core import __version__
        install_update_routes(app,root,settings,__version__)
    cuda = {'devices': None, 'message': 'Optional CUDA runtime is not installed'}
    if config.get('cuda'):
        try:
            folder = Path(config['cuda']).parent
            library = next(folder.rglob('libggml-cuda.so*'))
            backend = ctypes.CDLL(str(library))
            count = backend.ggml_backend_cuda_get_device_count
            count.restype = ctypes.c_int
            cuda = {'devices': count(), 'message': 'Native CUDA runtime loaded'}
        except (OSError, AttributeError, StopIteration):
            cuda = {'devices': None, 'message': 'CUDA runtime could not be loaded; check the NVIDIA driver'}
    core_socket = socket.socket()
    core_socket.bind(('127.0.0.1', 0))
    core_socket.listen(128)
    core_port = core_socket.getsockname()[1]
    ui = make_ui(root/'vendor/ui', token,
                 lambda: {'cuda': cuda, 'native':native,'missing_models': missing_weights(Settings.load().engine2_models_dir, 512) if Settings.load().mesh_engine=='engine2' else []},
                 preview_mode=args.mode == 'preview')
    ui_port = ui.server_address[1]
    start_path = '/preview' if args.mode == 'preview' else '/'
    url = f'http://127.0.0.1:{ui_port}{start_path}#core={core_port}&token={token}'
    threading.Thread(target=ui.serve_forever, daemon=True).start()
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=core_port,
                                        log_level='warning', access_log=False))

    def open_page():
        while not server.started and not server.should_exit:
            time.sleep(.1)
        if server.started:
            save_session(home, ui_port, core_port, token, start_path)
            label = 'Placeholder preview tests' if args.mode == 'preview' else 'Shapecast native interface'
            print(label+' ready. Keep this terminal open; Ctrl+C stops the session.\n'+url, flush=True)
            if not args.no_browser:
                webbrowser.open(url)

    threading.Thread(target=open_page, daemon=True).start()
    try:
        server.run(sockets=[core_socket])
    finally:
        clear_session(home, token)
        ui.shutdown()
        ui.server_close()
        core_socket.close()
        lock.close()


if __name__ == '__main__':
    main()
