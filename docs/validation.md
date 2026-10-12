# Validation and limitations

Initial compatibility investigation: 2026-10-10.

The initial native installation ran the unmodified Shapecast 0.3.15 core with native Linux Python 3.11.17. All 48 core files matched the installer integrity manifest. The original shell's 60 embedded Brotli web assets were recovered privately and checked for modification. Our adapter supplies the local API connection at page load and normalizes JSON responses for the browser interface.

On Ubuntu 26.04.1 x86-64 with Blender 4.5.14 LTS:

- Unlicensed placeholder jobs completed through concept selection and asset creation.
- The original library and 3D viewer displayed the sample model.
- Blender generated actual GLB, OBJ and STL exports from the sample; the STL was checked as a 12-triangle closed cube.
- Real generation with preview permission enabled but fake stages disabled was rejected with `license_required`.
- Requests without a launch token were rejected; foreign origins were rejected by the original API.

The host had an RTX 4060 Ti (8 GB), NVIDIA driver 595.91.07, Intel i9-12900K and 32 GB RAM. The optional native CUDA runtime recognized the GPU in the desktop session. Some sandboxed diagnostics could not see the host NVIDIA driver, so diagnostic visibility alone was not used as proof of a broken host driver.

The public helper has separate source-only tests for archive traversal, download checksums, original-file integrity, private session state, profile separation and synthetic PE/Brotli extraction. CI does not include or run Shapecast's commercial application. The opt-in integration check requires your own local installation and creates a placeholder asset in its preview library.

Before initial publication, the portable helper passed 11 Python tests and its synthetic frontend tests on Python 3.14; the Python tests also passed on 3.11. Two fresh private installations passed: one using existing Python/Blender executables, and one using the pinned component archives from a verified local cache. Both installed the pinned dependencies into new environments. The fresh preview installation completed a browser job and passed API, GLB/OBJ/STL export, authentication, Host, Origin and traversal checks. Real generation without a licence was again rejected, even with the preview permission set. The archive checksums and extraction were tested locally; live re-downloading those large archives was not repeated.

The 2026-10-12 machine-identity fix passed 16 helper tests on Python 3.14 and 3.11. Six fresh processes using the legacy native runtime and three full portable native server starts returned the same code derived from a verified physical Ethernet adapter. Tests also check rejection of synthetic, virtual and randomized sources, pinning across adapter additions, and refusal to silently change the identifier when hardware changes. This validates fingerprint stability, not successful licence activation or AI generation.

## Still to verify

- Legitimate licence activation and licensed generation on Linux.
- Complete model downloads, compatible weights and full text/image pipelines.
- Rigging, animation and the remaining export formats.
- Other distributions, GPU models and driver versions.
- Product updates beyond the exact tested Windows installer.

Successful placeholders do not establish that any item above works. Contributions should identify whether evidence comes from a real run, a diagnostic check or an inference.
