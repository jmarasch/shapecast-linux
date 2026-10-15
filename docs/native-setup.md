# Native inference setup

The core and all inference hosts use CPython 3.11. The helper keeps separate environments because the Quality, image and rigging stacks use different Diffusers/Transformers versions. `requirements/*.txt` records the complete tested environment snapshots; the installer uses `--no-deps` deliberately to reproduce these exact snapshots rather than resolve a different combination.

Torch 2.11.0 and torchvision 0.26.0 use the official CUDA 12.8 index. Rigging's torch-scatter/torch-cluster wheels use the matching official PyG wheel page. Native extensions are built from the engine source provided in your licensed pack. The CUDA compiler packages, Fast binary, Python, Blender and Instant Meshes are individually checksum-pinned in `components.lock.json`.

The helper copies engine sources to a private worktree before adapting them. It never patches Shapecast's core bytecode or embedded UI. The Quality changes establish CPU offload before GPU allocations, use the execution device instead of dormant `meta` tensors, and offload shape blocks and paint sequentially on smaller cards. Startup flags such as `-s -E -B -X utf8` are preserved by the GPU host launcher.

Rigging uses an inference-only SDPA adapter for the point encoder to avoid materializing its large attention matrix. Training, relative-position encodings, upcasts and upstream Flash Attention retain the original implementation. Topology substitutes official native Instant Meshes for the Windows binary supplied by the original action.

Touch-up calls also receive the missing context parameters needed by the original GPU timeout calculation; the vendor timeout checks and subprocess supervision remain active.

Generated Hugging Face modules live in the writable cache, separate from model weights. Exporter scratch files live in the private engine workspace. These locations avoid the read-only failures found during the update investigation.

## Source packs

Download/import `engine,models` before Quality, `rig` before rigging, and `engine2` before Fast inference. The pack `linux-selection.json` explicitly records that only native-use files were selected; it does not claim that a complete Windows environment was installed. Native paths are restored at launch so a pack import cannot silently switch a host to `python.exe`.

The vendor's own Windows pack installer remains part of its unchanged interface. Prefer this helper's `models` command for initial Linux setup. Before any pack or runtime operation, close the native session. During normal use, use the helper's model-update panel.

## Offline/cache options

`install --cache-dir /path/to/cache` and `runtime --cache-dir /path/to/cache` reuse checksum-verified archives. `install --wheelhouse /path/to/wheels` installs pinned core dependencies without a package index. `runtime --wheelhouse /path/to/wheels` does the same for inference dependencies. The wheelhouse must include all pinned packages, including CUDA/PyG wheels and build requirements. Some dependencies such as BasicSR are distributed as source packages, so include their build requirements as well.

The models command supports existing vendor pack files through `--source`. Inference uses the vendor host's offline settings and previously downloaded weights. No account token or licence is sent to PyTorch, PyG, NVIDIA's compiler archive host or this repository by runtime setup.

CUDA compilation needs a compatible C++ compiler; `g++-13` is the recommended Ubuntu choice. The helper detects the current NVIDIA compute capability for the rasterizer build rather than hardcoding the maintainer's 8.9 architecture. The private CUDA compiler also receives a narrowly scoped, host-detected declaration fix on newer glibc; original headers are retained. External toolkits supplied with `--cuda-home` are never edited. GPU/driver architectures not present on the test machine remain community validation targets.

Sources: [PyTorch CUDA 12.8 installation](https://pytorch.org/get-started/previous-versions/), [trellis.cpp releases](https://github.com/pwilkin/trellis.cpp/releases), [Diffusers cache configuration](https://github.com/huggingface/diffusers/blob/main/src/diffusers/utils/constants.py).
