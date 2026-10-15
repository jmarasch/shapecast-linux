# Updates and recovery

The native interface adds a top banner and Updates button. It checks the vendor's public software metadata and installed model-pack manifests at startup and every six hours while running. Turn automatic checks off in that panel if desired. Offline failures retain cached notices and do not falsely report everything current.

Software and model updates are separate. Model changes are detected by file SHA256, including updates with unchanged pack versions or byte counts. Downloads resume and are verified before use. Apply is a separate action; it refuses to run while jobs or other writes are active. Previous files are backed up, and Restore previous models restores them. An interrupted apply/rollback is recovered from its journal. Model-code changes need compatibility review rather than automatic execution.

Software downloads remain staged Windows installers. Never run them through Wine over the native runtime. Update the helper source, close both profiles, and use `update --installer FILE` for the exact installer currently allowed by `components.lock.json`. The command verifies and extracts the core/UI, retains previous vendor files and backs up settings, licences and databases in a private `backups/before-VERSION-TIMESTAMP/` directory. It keeps the library and inference runtimes in place. Unreviewed versions remain blocked.

To restore a software checkpoint, close both profiles first, preserve the newer `vendor/` separately, restore the checkpoint's `vendor/` and `install.json`, and use the corresponding helper revision. Database/settings snapshots are available if a future release changes their schema; do not overwrite a newer library database casually because it contains work created since the checkpoint. The currently supported 0.3.17 update did not require a library-schema migration.

The helper itself updates through `git pull --ff-only`. A separate published helper-release feed is not configured. The banner says so rather than claiming an updater exists for the Linux launcher. This repository does not silently update itself.
