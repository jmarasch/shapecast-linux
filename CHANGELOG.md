# Changelog

## 0.4.2 — Queue-page cleanup

- Moved cleanup directly onto Queue: Clear all removes finished records only; a left-side × appears when hovering over a finished row.
- Pending, running and approval-paused jobs are untouched. Queue cleanup preserves library assets, files and other job history. Undo clear restores the last cleared group.
- Removed the separate Manage jobs panel and its waiting-job cancellation controls. The original ambiguous Clear-waiting button is hidden on Queue.
- Original vendor files stay unchanged; reviewed UI row identifiers are added only while serving the page.

## 0.4.1 — 2026-10-18

- Added Manage jobs: clear a snapshot of waiting jobs, cancel an individual waiting job, and reversibly hide finished jobs from history and queue recents.
- Preserve running casts, casts awaiting approval, and all generated files/library assets. Hidden jobs persist across restarts and can be restored.
- Added authenticated same-origin relay, paginated job lists and queue admission locking for safe clearing.

## 0.4.0 — alternate-view approval

- Review alternate views before geometry, approve each angle, or regenerate a rejected view while retaining approved siblings.
- Persist reviews across restarts, reject stale actions, retain the previous image on regeneration failure and preserve original generation permissions.

## 0.3.0 — guided setup

- One terminal wizard for prerequisites, installer validation, activation, models, native runtimes, diagnostics and launchers.
- Saved setup stages support pausing for an activation email and resuming. Existing data stays in place; unlicensed model setup remains blocked.

- Check shared read-only model folders without treating them as failed update feeds. Staging remains available; applying still requires a private writable model copy.

## 0.2.0 — native inference and Shapecast 0.3.17

- Reviewed 0.3.17 installer, original core/UI integrity checks and safe software-update backups.
- Native Quality, image, rigging, sharpening, Fast and topology setup; pinned environment snapshots and portable CUDA build components.
- Licence-gated native-use model download/import with resumes, hash verification and duplicate-cache deduplication.
- Low-memory Quality shape/paint adapters, inference-only rig attention, native Instant Meshes and preserved Python startup flags.
- Touch-up host context compatibility preserves parameters for the original timeout checks.
- Writable module caches and private engine workspaces.
- Model/software update banner, opt-in verified model updates, backups and recovery.
- Refreshed activation, hardware, setup and validation documentation. No machine-identity overrides, vendor binaries, model weights or licence data are included.

## 0.1.0 — initial preview helper

Original core/interface extraction, placeholder exports and verified physical-adapter identity selection.
