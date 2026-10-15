# Contributing

Existing contributions, including OpenAI Codex's AI coding assistance, are listed in [CONTRIBUTORS.md](CONTRIBUTORS.md).

Report the Linux distribution, helper revision, Shapecast core version, GPU/driver and the exact step that failed. Say whether you used the preview or native profile. Please distinguish real AI output from placeholder samples.

Keep contributions limited to compatibility code, tests and documentation. Do not commit Shapecast's core, recovered interface, installers, licence files, proprietary model files or personal session data. Synthetic fixtures keep the source-only tests runnable without a purchase.

Run the source-only checks from the repository folder:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
node tests/test_frontend.cjs
node tests/test_setup.cjs
```

For an installed copy, the opt-in integration check creates and exports a placeholder in its separate preview profile:

```bash
./shapecast-linux launch --mode preview --no-browser
# In a second terminal:
python3 scripts/check_preview.py
```

For native-runtime changes, build fresh environments from the pinned snapshots and run the affected real GPU stage using your own purchased files. Preserve a known working installation and mount shared weights read-only during regression tests. Include hardware/driver and peak memory when available. Never publish model outputs belonging to another owner.

New installer support needs the new SHA-256, verified core/runtime versions, extraction checks and an actual preview/export test. Preserve original commercial files and licence enforcement. Do not simply disable the known-version check.
