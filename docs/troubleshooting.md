# Troubleshooting

## Python or Blender already installed

The commercial core consists of CPython 3.11 bytecode. A system Python with a different minor version cannot load it. You may supply an existing CPython 3.11 and Blender 4.2+:

```bash
./shapecast-linux install --installer "$HOME/Downloads/Shapecast-Setup.exe" \
  --python /path/to/python3.11 --blender /path/to/blender
```

Setup validates both versions. It creates its own virtual environment rather than modifying your system Python. `--without-blender` skips Blender installation, but exports and stages that need it will be unavailable.

## Download failures

First check that you can reach GitHub release downloads, the Blender mirror and PyPI from your machine. The setup records fixed URLs and checksums in `components.lock.json`; corrupt or changed component downloads are rejected.

For an offline install, use `--cache-dir /path/to/cache` with previously verified component archives and `--wheelhouse /path/to/wheels` containing all dependencies in `requirements-core.txt` for Linux CPython 3.11. Component cache filenames use `<sha256>-<URL filename>` exactly as the installer reports. Supplying `--python` and `--blender` avoids downloading those components.

Failed setup removes its newly installed runtime folders and keeps cached downloads. If a process was interrupted before cleanup, choose a fresh install directory or inspect the partial installation before removing anything. Setup will not overwrite existing profiles.

## The interface is blank

Open the address printed in the launch terminal in a current Linux browser. Keep the whole address, including its `#core=...&token=...` fragment; it connects the interface to the local API. This address is private to the session. The server listens only on `127.0.0.1` and rejects arbitrary Host headers.

These scripts do not launch the Wine/WebView2 shell. That approach showed blank windows and crashes in the initial investigation. This native helper runs the web interface in your Linux browser instead.

## Only a box appears

That is the vendor placeholder pipeline. Prompt text changes the recipe, not the placeholder geometry. Test the library, viewer and exports here; meaningful AI geometry needs the licensed native pipeline, which remains unverified.

## A session is already open

Relaunching the same profile reopens it. `launch --mode preview --restart` stops only the matching preview server for this installation. Native and preview profiles can run separately. Do not delete a live profile's lock file; stop its terminal session or use the restart option.

## Diagnostics

```bash
./shapecast-linux doctor --mode preview
./shapecast-linux doctor --mode native
```

The report verifies original files, local API authentication and a small set of hardware/licence status fields. It excludes licence contents, activation codes and launch tokens. Review any additional logs before posting them; application logs can include personal paths or job details.
