# Development Checks

The repository has two verification lanes.

## Portable lane

Run this before publishing a branch or pull request:

```powershell
.\scripts\check.ps1 -Portable
```

This is the same ROM-free contract used by GitHub Actions. It validates tracked metadata and repository hygiene, runs lint and tests that need only tracked files, then builds and typechecks the lab UI.

## Full local lane

Run this on the gameplay host when local captures are available:

```powershell
.\scripts\check.ps1
```

The full lane includes tests marked `local_artifacts`. Depending on the test, these need one or more ignored host assets:

- `research/PokemonRed.gb` for emulator and golden-state reload checks.
- `.state` and `.png` captures under the ignored `local/` artifact directories.
- historical reports under `research/artifacts/` for regression cases.
- SDL/PyBoy for emulator-backed checks.

LM Studio, the local Gemma model, the GPU, Dropbox, and network credentials are not required by either standard check lane. They are needed only for live Director runs, model probes, and artifact syncing.

To inspect local artifact coverage without failing on missing optional captures, run:

```powershell
.\.venv\Scripts\python scripts\audit_local_artifacts.py
```

Add `--strict` when you expect every recorded optional artifact to be present on the host.

## Path contract

Tracked metadata stores repository-relative POSIX-style identifiers such as `research/golden-states/local/example.state`. Runtime code resolves these from the current checkout root. Older metadata containing an absolute checkout path remains readable: the resolver maps its `research/`, `scripts/`, `src/`, `tests/`, or `apps/` suffix into the current checkout and falls back to the original absolute path only when necessary.

Use this command to check whether durable metadata needs migration:

```powershell
.\.venv\Scripts\python scripts\migrate_metadata_paths.py --check
```
