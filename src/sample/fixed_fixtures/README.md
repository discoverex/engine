## Fixed Fixtures

This directory holds shared local fixture assets for parameter sweeps and replay-style experiments.

Current layout:

- `backgrounds/`
  - Fixed background images reused across many runs
- `objects/`
  - Fixed object assets for future object-only experiments

Conventions:

- Worker-visible paths should be referenced through `/app/src/sample/fixed_fixtures/...`
- The current fixed-background sweep expects:
  - `/app/src/sample/fixed_fixtures/backgrounds/base_bg.png`

Notes:

- Keep fixture files stable so experiment comparisons remain reproducible.
- Prefer a small number of named assets over many ad hoc files.
