# Phase 4 Scenario Capsules

Status: v0 scaffold
Last updated: 2026-06-16

## Entry Defaults

Phase 4 begins with two v0 capsule families:

- `viridian_forest_catching`
- `cerulean_misty`

Rocket Hideout is deferred until later. It remains useful, but v0 should first prove the capsule/evaluation loop on early-game starts where the current state inspector and mutation tooling are already strongest.

Training/tuning and held-out evaluation starts use an 80/20 deterministic split over human-verified golden states and approved generated derivatives. The split is random-shaped but reproducible through a hash seed.

## Capsule Specs

Tracked capsule specs live in:

- `research/capsules/viridian_forest_catching.json`
- `research/capsules/cerulean_misty.json`

Each spec defines:

- Objective.
- Candidate base state IDs.
- Randomization bounds.
- Valid start requirements.
- Impossible/degraded starts.
- Success, failure, and abort conditions.
- Button/frame budgets.
- Required logged events.
- Relevant state fields.

## Manifest Builder

Build the local start manifest with:

```powershell
.\.venv\Scripts\python scripts\build_capsule_manifest.py --strict
```

The manifest is written to:

```text
research/artifacts/capsules/v0_manifest.json
```

This artifact is local and gitignored. It includes resolved state metadata, tuning/holdout assignment, mode, location, party overview, and unresolved/unusable references.

Current local manifest:

- `cerulean_misty`: 5 usable starts, 4 tuning, 1 holdout.
- `viridian_forest_catching`: 6 usable starts, 5 tuning, 1 holdout.

Generated derivative approval candidates:

- `cerulean_misty`: 25 valid candidates, 5 degraded candidates.
- `viridian_forest_catching`: 25 valid candidates, 5 degraded candidates.

Generate or refresh these local candidates with:

```powershell
.\.venv\Scripts\python scripts\generate_capsule_derivatives.py --overwrite
```

Coverage metadata is written to:

```text
research/artifacts/capsule-derivatives/coverage_manifest.json
```

These generated candidates are `loadable_unapproved` by default. They are intended for approval through `scripts/approve_generated_state.py` or the lab UI before becoming held-out/tuning starts.

## Phase 4 KPI Status

Met enough to begin:

- Two non-sequential capsule families are defined.
- Each capsule has explicit success, failure, timeout, and abort conditions.
- Each capsule can be summarized for the director through existing snapshot plaintext.
- Impossible/degraded start classes are defined.
- Starts are split into tuning and holdout sets.

Still open:

- Approve enough generated derivative starts to promote them into the tuning/holdout manifest.
- Promote enough event/run logging for automated success and failure classification.
- Build dry-run evaluator output once the Phase 5 executor baseline exists.

## Recommended Next Step

Phase 5 should consume the capsule specs and manifest. The first executor baseline should target `viridian_forest_catching`, because it stresses navigation, encounter/catch handling, inventory checks, and directive compliance while staying within our strongest current state surface.
