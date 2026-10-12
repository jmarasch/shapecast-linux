# Contributing

Existing contributions, including OpenAI Codex's AI coding assistance, are listed in [CONTRIBUTORS.md](CONTRIBUTORS.md).

Report the Linux distribution, helper revision, Shapecast core version, GPU/driver and the exact step that failed. Say whether you used the preview or native profile. Please distinguish real AI output from placeholder samples.

Keep contributions limited to compatibility code, tests and documentation. Do not commit Shapecast's core, recovered interface, installers, licence files, proprietary model files or personal session data. Synthetic fixtures keep the source-only tests runnable without a purchase.

Run the source-only checks from the repository folder:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
node tests/test_frontend.cjs
```

For an installed copy, the opt-in integration check creates and exports a placeholder in its separate preview profile:

```bash
./shapecast-linux launch --mode preview --no-browser
# In a second terminal:
python3 scripts/check_preview.py
```

New installer support needs the new SHA-256, verified core/runtime versions, extraction checks and an actual preview/export test. Preserve original commercial files and licence enforcement. Do not simply disable the known-version check.
