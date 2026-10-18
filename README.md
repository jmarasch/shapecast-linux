# shapecast-linux

Run your **purchased Shapecast 0.3.17** natively on Linux x86-64, using the original core and interface in a local browser. This unofficial helper installs native NVIDIA inference environments for Quality, Fast, reference images, rigging, sharpening and topology tools. Wine and Flatpak are not required.

**You need your own Shapecast installer, a vendor-issued licence for this Linux machine, and the licensed model packs.** This repository contains compatibility code only. It does not contain Shapecast, its interface, models, licences, activation overrides or private machine identifiers. Linux is not officially supported by Shapecast; vendor licence issuance is outside this project's control.

## Tested scope

The native components have completed real image generation, Quality shape/texturing, Fast image-to-3D, rigging, 4K sharpening, topology rebuilding and Blender exports on an RTX 4060 Ti (8 GB). The 0.3.17 update passed GPU texturing/export, head-only projection and core/API checks. These results come from one Ubuntu x86-64 machine; other GPUs/distributions need testing. Some large or maximum-detail jobs can still exceed an 8 GB card's memory.

The portable helper is validated separately from the original development environment. See [validation](docs/validation.md) for the exact checks and limits. Placeholder mode still creates a box; it is only a workflow test.

## Alternate-view approval

Native casts now pause after alternate images are generated. Compare them with the front reference, approve each view, or reject and regenerate an individual angle. Accepted views stay unchanged; geometry starts only after all alternate views are approved and you choose **Continue to geometry**. Reviews survive refreshes and restarts. See [view review](docs/view-review.md) for the workflow and failure recovery.

## Requirements

- Linux x86-64; tested on Ubuntu/Kubuntu 26.04.1.
- A real physical network adapter with its permanent factory address available for a stable licence identity; VM/bridge/random fallback identities are rejected.
- NVIDIA RTX-class GPU with at least 8 GB VRAM; 12–24 GB gives more room.
- A recent NVIDIA driver: the Quality/image/rig environments use CUDA 12.8 wheels; the optional pinned Fast runtime uses CUDA 13.1. The tested driver is 595.99.02. The driver must support the selected CUDA runtime.
- 16 GB RAM minimum, 32 GB recommended; allow **180 GB free** for full model packs, separate Python environments and build/download caches. Space varies by components and deduplication.
- Bash, Python 3.10+, Node.js 18+, 7-Zip, a C++ compiler compatible with CUDA 12.8 (GCC 13 recommended), and Blender 4.2+.

On recent Ubuntu/Debian systems:

```bash
sudo apt install git python3 nodejs 7zip g++-13 libgl1 libegl1 libxrender1 libxi6 libxrandr2 libxinerama1 libxcursor1
```

Older distributions may use `p7zip-full` and a different supported GCC package. The helper can download a private, checksum-verified Blender and Python runtime. For Quality it can also install a pinned private CUDA compiler; it does not replace your system CUDA toolkit or GPU driver.

## Guided setup (recommended)

Clone the repository and run the wizard in a terminal:

```bash
git clone https://github.com/jmarasch/shapecast-linux.git
cd shapecast-linux
./setup.sh
```

You can also run `./shapecast-linux` without a command, or `./shapecast-linux setup`. The wizard asks for your install folder and purchased installer, checks your NVIDIA GPU and prerequisites, and offers Full, Quality, Fast or placeholder-only setup. On apt-based systems it can install missing system packages after you explicitly choose yes and enter your normal sudo password. It never upgrades your driver or adds package repositories.

It then opens the original activation page, waits for a valid vendor-issued licence, downloads or imports the required model packs, builds the selected native runtimes, runs diagnostics and offers an application-menu launcher. Keys are entered in the local browser page, not logged or pasted into the terminal. If you are waiting for the licence email, choose **later**. Run the same wizard again to resume; verified downloads and finished runtimes are reused. Run it from a terminal; redirected/non-interactive input is rejected.

Advanced options:

```bash
./setup.sh --install-root "/path/to/private data" --installer "/path/to/Shapecast-Setup.exe"
./setup.sh --cxx /usr/bin/g++-13 --no-browser
```

Existing installations using this helper are reused. A reviewed software update keeps its normal backup checkpoint. Your other installations are not automatically imported or deleted. Keep the repository folder because the launcher uses its code.

The wizard's real licence-email pause and preview-resume paths have been checked against a local installation. Complete new-owner vendor activation and licensed model downloads still need independent validation; see [validation](docs/validation.md).

## Manual install and activate

```bash
git clone https://github.com/jmarasch/shapecast-linux.git
cd shapecast-linux
./shapecast-linux install --installer "$HOME/Downloads/Shapecast-Setup.exe"
./shapecast-linux launch --mode native
```

The Windows installer is extracted, never executed. Only the reviewed 0.3.17 installer is accepted:

```text
3d97579f809419743f6c6cad0554b17f618b95ebe0e8ce545620aea65f061070
```

Open **Linux setup**, copy the stable request code and obtain a licence from Shapecast. Apply the emailed licence there, or use the original online activation controls if the vendor service is available. A Windows/macOS request code is different. The Linux code may be shorter because Windows/macOS-only identifiers are absent; explain that you are using Linux when contacting the vendor. The helper never invents those missing identifiers or impersonates a previously licensed machine.

**Stop the native session with Ctrl+C before installing models or runtimes.**

## Install models and native runtimes

For the full setup after activation:

```bash
./shapecast-linux models --packs models,engine,rig,engine2
./shapecast-linux runtime --components all --engine quality
./shapecast-linux launch --mode native
./shapecast-linux doctor
```

Model operations require a valid local vendor licence. They fetch the vendor's manifests, resume downloads, verify sizes/SHA256, and deduplicate identical cache blobs. They select model files and engine sources without installing Windows Python or DLLs. Model weights are not sourced from this GitHub repository.

If you already downloaded the vendor packs, import from the parent folder containing `models/pack.json`, `engine/pack.json`, and so on:

```bash
./shapecast-linux models --packs models,engine,rig,engine2 --source "/path/to/vendor/packs"
```

For a smaller Quality-only setup:

```bash
./shapecast-linux models --packs models,engine
./shapecast-linux runtime --components quality,image --engine quality
```

For Fast generation, add `engine2` models and the `fast` runtime. Rigging needs the `rig` pack and `rig` runtime. The `tools` runtime supplies standalone sharpening when using Fast; Quality includes sharpening. `topology` installs official Linux Instant Meshes. All components are optional, and setup reports missing requirements instead of pretending that directory existence proves inference works.

Quality builds two native extensions. Setup chooses GCC 13/14 when present; override with `--cxx /usr/bin/g++-13`. You can supply an existing CUDA 12.8 toolkit with `--cuda-home /path/to/cuda`, limit compilation with `--jobs 2`, or use a prepared Linux `--wheelhouse`. See [native setup details](docs/native-setup.md).

## Everyday use and updates

Keep the launcher terminal open. Ctrl+C stops that profile. Running the same command again reopens the existing session; `launch --mode native --restart` restarts that profile only. Preview and native data are separate.

The **Updates** button/banner checks software and model manifests at startup and every six hours. Downloads and model installation are opt-in; model application waits for an idle queue, verifies hashes, and keeps a rollback backup. Checks do not send your licence, machine ID or library.

Software installers are staged, not run. For a version supported by the current helper, close both profiles and apply your installer with:

```bash
git pull --ff-only
./shapecast-linux update --installer "/path/to/Shapecast-Setup.exe"
```

This backs up the previous vendor files, configuration and databases, then replaces the reviewed core/interface without replacing your libraries or native runtimes. Unknown installer hashes remain blocked until reviewed. Updating model code may also need a Linux compatibility update. See [updates and recovery](docs/updates.md).

## Files and privacy

Default installation: `$XDG_DATA_HOME/shapecast-linux`, or `~/.local/share/shapecast-linux`.

```text
vendor/                 Privately extracted original core/resources/interface
venv/                   Native core dependencies
runtimes/               Separate Quality, image, rigging and tools environments
engines/                Private engine workspaces and Linux adapters
components/             Python, Blender, Fast binary and Instant Meshes
profiles/native/        Your settings, licence, database, library and pack files
profiles/preview/       Separate placeholder tests
models/fast/            Vendor GGUF weights for Fast
cache/                  Downloads, pip, CUDA and generated Python module caches
backups/                Reviewed software-update rollback checkpoints
machine-interface.json  Local stable physical-adapter selector
```

Use `--install-root /path/to/data` **before** each command for another location. Keep the repository folder: the launcher loads its helper code. Installation refuses to overwrite an existing installation; use the update command for reviewed software updates.

Licence checks, product signatures and the original core remain intact. Do not post licence keys, request codes, order information or launch-token URLs in issues. See [activation](docs/ai-generation.md), [troubleshooting](docs/troubleshooting.md), [validation](docs/validation.md), and [contributing](CONTRIBUTING.md).

## Contributors and licensing

**Jakob ([jmarasch](https://github.com/jmarasch))** — project direction, hardware testing, troubleshooting and maintenance. **OpenAI Codex** — AI coding assistance with implementation, tests and documentation. See [CONTRIBUTORS.md](CONTRIBUTORS.md).

This is independent of [Shapecast](https://shapecast.io/). The MIT licence covers this helper's original code only; downloaded applications, model packs and third-party components retain their own licences. See [NOTICE](NOTICE).
