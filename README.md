# shapecast-linux

An unofficial community helper for running a purchased copy of **Shapecast 0.3.15** natively on Linux x86-64, using its original core and web interface in your browser.

**Current status: previews and basic exports work; real AI generation is experimental and has not been verified.** Preview jobs produce a sample box regardless of the prompt. They test the library, viewer and export workflow; they do not generate AI geometry.

This project is independent of [Shapecast](https://shapecast.io/). It contains our compatibility scripts and browser adapter. Each user supplies their own Windows installer. Shapecast's application files, interface assets, licenses and models are not distributed here.

## What has been tested

| Feature | Status |
| --- | --- |
| Original Python core on native Linux | Working; 48 original files checked against the installer manifest |
| Original interface in a Linux browser | Working; privately extracted assets remain unchanged |
| Vendor placeholder pipeline without activation | Working in a separate preview profile |
| Library and 3D viewer | Working with the placeholder model |
| GLB, OBJ and STL exports through native Blender | Working with the placeholder model |
| Licence checks for real generation | Preserved; unlicensed real jobs are rejected |
| Native CUDA runtime | Optional runtime can be configured; inference is unverified |
| Licensed AI generation, rigging, other export formats | Not verified |

Local validation used Ubuntu 26.04.1 x86-64, Python 3.11.17, Blender 4.5.14 LTS and an RTX 4060 Ti with 8 GB VRAM. This is one tested machine, not a promise of compatibility with every distribution. See [validation notes](docs/validation.md).

## Quick start

You need a Linux x86-64 machine, Bash, Python 3.10 or newer for the setup helper, Node.js 18 or newer for asset extraction, and `7z` or `7zz`. On recent Ubuntu/Debian releases, install the prerequisites using your package manager:

```bash
sudo apt install git python3 nodejs 7zip
```

Some older distributions call the 7-Zip package `p7zip-full`. The installer checks prerequisites before proceeding. Wine and Flatpak are unnecessary.

Clone or download this repository, open a terminal inside its folder, and use your purchased installer:

```bash
git clone https://github.com/jmarasch/shapecast-linux.git
cd shapecast-linux
./shapecast-linux install --installer "$HOME/Downloads/Shapecast-Setup.exe"
./shapecast-linux launch --mode preview
```

The setup downloads a checksum-verified standalone Python 3.11 runtime, installs the pinned Linux dependencies, and uses a suitable system Blender or downloads a checksum-verified portable Blender. It does not run the Windows installer. Allow a few GB of space for the runtime, Blender and cached downloads; AI models require substantially more space separately.

The tested installer is identified by this SHA-256:

```text
4478901fbff2a07dee1cbaf5cd14a2e33adf45917e7ae8f7ec8b8b80ad09659e
```

A different installer is rejected before extraction. New product versions need a compatibility update rather than removing this check.

## Try previews and exports

The browser opens the **Placeholder tests** page. Create a test, choose its sample concept, then open the asset in the original library. Try an export preset there, or download the sample GLB directly from the test page. A box is the expected result, even if you describe something else.

Keep the terminal open while using Shapecast. Press Ctrl+C to stop. Running the same launch command again reopens the existing session. To restart just that profile:

```bash
./shapecast-linux launch --mode preview --restart
```

Preview data and the normal library live in separate folders. The preview session uses the core's own `fake_stages` and `allow_preview_generation` settings. The native session does not grant the preview permission to real jobs.

## Open the normal interface

```bash
./shapecast-linux launch --mode native
./shapecast-linux doctor
```

Use **Linux setup** in the browser to inspect the licence, Blender and model status. Apply your legitimate licence through Shapecast's normal activation workflow. Activation is never performed automatically by installation or diagnostics. See [activation and experimental AI setup](docs/ai-generation.md).

## Where files go

The default private installation is `$XDG_DATA_HOME/shapecast-linux`, or `~/.local/share/shapecast-linux` when that variable is unset:

```text
vendor/                Your privately extracted core, resources and interface
venv/                  Linux Python dependencies
components/            Downloaded Python, Blender and optional CUDA runtime
profiles/preview/      Placeholder test settings, database and library
profiles/native/       Normal settings, licence, database and library
cache/                 Verified component downloads and pip cache
install.json           Local component configuration
```

Keep the repository folder as well; the launcher loads the compatibility code from it. Use `--install-root` **before** the command to choose a different private installation:

```bash
./shapecast-linux --install-root "$HOME/Apps/shapecast-data" install --installer "$HOME/Downloads/Shapecast-Setup.exe"
./shapecast-linux --install-root "$HOME/Apps/shapecast-data" launch --mode preview
```

Installation refuses to overwrite an existing runtime or profiles. Back up your libraries and licence before changing or removing an installation. Removing this repository alone does not remove your private data.

## More help

- [Troubleshooting and existing Python/Blender options](docs/troubleshooting.md)
- [Activation and experimental AI generation](docs/ai-generation.md)
- [Validation notes and remaining work](docs/validation.md)
- [Contributing](CONTRIBUTING.md)

The MIT licence applies to this helper's source only. Shapecast and downloaded components retain their own licences; see [NOTICE](NOTICE).
