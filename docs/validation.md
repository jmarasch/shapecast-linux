# Validation and limits

This is an experimental community port. Evidence below distinguishes development runs from clean portable-helper checks. A placeholder box is never evidence of AI generation.

## Development runtime

The maintainer's Ubuntu/Kubuntu 26.04.1 x86-64 machine has an Intel i9-12900K, 32 GB RAM and an NVIDIA RTX 4060 Ti with 8 GB VRAM. Recent tests use NVIDIA driver 595.99.02, CPython 3.11.17 and Blender 4.5.14 LTS.

The native development environment has completed real reference-image generation, Quality shape and PBR texture generation, Fast image-to-3D, UniRig rigging, 4K sharpening, topology rebuilding, and Blender exports. The vendor core and browser interface remain unmodified. Native adaptations run around the core and in private copies of engine sources. Some high-detail jobs exhausted this 8 GB GPU; successful smaller jobs do not guarantee every preset fits.

The 0.3.17 update retained all 48 original core files and all 60 original embedded web assets. It passed a real GPU PBR texture/export run on an existing 20,000-face mesh with 2K textures, approximately 58 seconds and 2.3 GB peak allocated GPU memory. The new head-only reference projection and projection-disabled path were checked separately. This is a texture-stage regression check, not a new complete cast across every subject/preset.

## Portable helper 0.2.0

The helper was verified on 2026-10-14 in a newly created installation, independently of the development launcher. Its installer extracts the purchased, SHA256-pinned 0.3.17 Windows package, verifies all 48 core files and 60 UI assets, installs a new core environment, and installs private Python/Blender components from checksum-verified archives. Separate native runtime environments are built from the pinned dependency snapshots and the owner's engine pack sources.

Source-only tests exercise archive/download integrity, synthetic frontend extraction, stable physical-adapter selection, profile separation, API/browser authentication, licensed-download gating, update staging, hash-based change detection, interrupted-update recovery, and rollback. They contain no commercial software or models. GitHub CI runs these checks; it does not have a licence, GPU or commercial installation.

The opt-in preview integration test creates its own placeholder and verifies GLB download, Blender GLB/OBJ/STL exports, a watertight mesh, and rejection of unauthenticated requests, foreign Host/Origin headers and traversal requests. Preview data remains separate from native casts.

The clean installation passed these additional checks:

| Check | Observed result |
| --- | --- |
| Source checks | 48 Python tests passed on Python 3.11 and 3.14; synthetic extraction and setup-request JavaScript tests passed |
| Four fresh inference environments | Quality, image, rig and tools imports/CUDA checks passed; all four passed `pip check` |
| Quality PBR texture stage | 61.7 seconds including wrapper startup; 5.36 MB GLB with base-color and metallic/roughness textures; vendor stage reports 2.3 GB peak GPU allocation |
| Reference image | Four-step, 1024-pixel PNG; 14.5 seconds including startup; 2.57 GB peak GPU allocation |
| Rigging | 40.3 seconds; GLB with 27 joints, a skin and joint/weight vertex attributes |
| Fast and topology | Official pinned binaries installed; Fast backend detected the RTX GPU; native Instant Meshes started |
| Preview | Job, GLB download, Blender GLB/OBJ/STL exports and watertight geometry passed |
| Licence enforcement | Model setup and real native casting rejected without a valid licence; no private key or identity migration copied |
| Identity | Original-core request code identical across three fresh processes; value omitted |
| Updates | Startup check ran automatically; original server lifespan preserved; update API rejects unauthenticated calls |
| Reviewed software update | Real 0.3.17 installer extracted and applied to the disposable installation; previous vendor files/configuration/databases retained in a private checkpoint |
| Existing installation | All 165 recorded baseline files remained unchanged |

Weights were reused from the maintainer's purchased packs and mounted read-only during inference checks; they were not redistributed or fetched through an unlicensed account. External model symlinks used only for this validation are deliberately rejected as update destinations. Full fresh model-download and vendor activation by another owner remain outstanding. The newly built GPU stages above are real inference checks, not an end-to-end activated portable-server cast.

## Licence boundary

The maintainer's original licence was issued for an earlier unstable request code. Private troubleshooting of that migration is not included here. Runtime/GPU validation using the maintainer's purchased files does **not** prove that Shapecast will issue every other owner a Linux licence.

The public helper uses only its normal, stable physical-machine identity and Shapecast's original signature/machine checks. It contains no historical-code alias, signature bypass or preset licence. Obtain a vendor-issued licence for the request code displayed by this installation. Model download/import and model-update application are licence-gated. Unlicensed real casts must be rejected; explicit vendor placeholder mode remains available separately.

## Still requiring community/vendor validation

- Fresh licence issuance and a complete activation-to-download-to-generation walkthrough by another owner.
- Other Linux distributions, GPU architectures, driver versions and memory sizes.
- Every generation preset, animation workflow and export format.
- Future application/model code revisions beyond the reviewed installer and guarded adaptations.
- AMD, Intel GPUs and ARM Linux are not supported by this release.

Report the helper commit, core version, GPU/driver and exact stage, and identify whether evidence is a real output, an import/diagnostic check or an inference. Review logs before sharing them. Contributor roles are recorded in [CONTRIBUTORS.md](../CONTRIBUTORS.md).

## Guided setup 0.3.0 (2026-10-18)

The wizard was exercised in a real terminal against the disposable installation: it detected the GPU and existing reviewed core, opened a temporary original activation service, and stopped that service when “later” was selected. No model downloads or activation overrides were used. Resuming with the explicit placeholder preset passed core/UI integrity and diagnostics and created a private launch script. Application-menu changes and starting the app were declined for this validation.

Source checks cover reviewed-installer orchestration, prerequisite consent, fresh and resumed setup, licence-email pauses, rejection of failed licence checks, stopping before runtimes after model failures, preservation of existing licence/library files, active-session protection, cancellation, shell/desktop quoting, and preservation of unrelated launchers. A complete new-owner activation/download/generation walkthrough remains a community validation target.

## Job controls 0.4.1 (superseded by 0.4.2)

Helper 0.4.1 passed the 81-test source suite and separate purchased-core checks for snapshot queue clearing, active/approval job protection, filtering before pagination, file retention, authenticated routes, admission serialization and persistent hide/restore. Browser tests used disposable synthetic jobs. The deployed 0.3.17 setup serves the same helper code; no owner queue changes were made for validation. See [job controls](job-controls.md).

## Queue-page cleanup 0.4.2

The corrected implementation clears finished records directly on Queue, with Clear all and a left-side hover ×. Source checks pass 83 tests. Separate original-core checks verify that more than 25 finished records clear while pending, running and approval-paused jobs stay untouched; all statuses, work files, original parameters and non-Queue history are preserved. Undo and persistence across restart pass. The original Queue UI was tested with disposable records, including hover visibility and normal polling after clearing. Owner records are not changed by validation.

## Desktop and menu shortcuts 0.4.3

Guided setup now asks independently about menu and desktop entries. Source tests cover executable desktop files, localized/disabled XDG desktops, both shortcut choices, preservation of unrelated files, and rerunning setup with two installations without overwriting the first installation. Tests write into disposable folders; the owner is walking through a fresh install separately. This is shortcut validation, not a claim of a new complete AI-runtime installation.
