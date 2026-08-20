# Phase 2 Audit

Status: complete enough for v0
Last updated: 2026-06-16

## Summary

Phase 2 now has a runtime state-mutation pipeline:

1. Plaintext request is translated into structured patch JSON.
2. Patch JSON is loaded into typed operations.
3. Operations are validated.
4. Verified operations are applied to PyBoy runtime memory.
5. The resulting state is inspected and summarized.
6. A generated-state report is written beside the ignored `.state` artifact.
7. Human play can approve or reject the generated state for its stated goal.

The project is still not editing `.sav` files. Generated emulator states remain local artifacts.

## Supported v0 Edits

Implemented:

- Change party Pokemon species by slot.
- Remove party Pokemon by slot or species.
- Override party level, HP, max HP, attack, defense, speed, special, and status.
- Override party moves and PP.
- Set same-map x/y location.
- Reject cross-map WRAM-only teleports by default.
- Set money.
- Set item quantities, including removing items.
- Set badges by name or mask.
- Apply raw unverified memory writes only with danger warnings.

## Generated Approved States

Three derivative states were generated and manually approved by Joey:

- `viridian_forest_low_health_catching.state`
  - Goal: From Viridian Forest, safely continue exploring and catch a wild Pokemon without blacking out.
- `cerulean_misty_underleveled_team.state`
  - Goal: From inside Cerulean Gym, defeat Misty with the available underleveled team and limited healing.
- `pewter_brock_remove_backup.state`
  - Goal: From inside Pewter Gym, defeat Brock with only Squirtle in the party.

The `.state` and `.state.report.json` artifacts live under `research/artifacts/` and are gitignored. The reusable patch recipes are tracked in `research/patches/`.

## Exit Questions

Can we generate a derivative state from a plaintext instruction and verify it through the inspector?

Yes. The current contract is plaintext-to-structured-patch, documented in `research/text-to-patch-contract.md`. The generated states are inspected after patching and stored with snapshot hashes and summaries.

Can we safely randomize capsule starts without hand-editing each one?

Partially. The patch engine can generate reusable variants from target-map template states. Full randomized batch generation is ready to build on top of this, but not yet implemented as a batch tool.

Can we detect and reject invalid or contradictory state requests?

Yes for implemented invariants and validators:

- Empty patches rejected.
- Invalid party slots rejected.
- HP above max HP rejected.
- Invalid quantities/money/ranges rejected.
- Unknown names rejected until promoted to the catalog.
- Removing the last party member rejected.
- Cross-map runtime edits rejected unless explicitly marked unsafe.

Can we repair or recompute checksums where needed?

Not applicable to v0 because Phase 2 uses runtime PyBoy state edits, not save-file edits.

Can the generated state be explained back in plaintext accurately?

Yes. `apply_state_patch.py` prints operations and the post-patch state summary. `play_state.py` prints the derivative-state goal and approval status when a sidecar report exists.

## Known Limits

- Cross-map starts must use target-map template states.
- PC box manipulation is not implemented.
- Pokedex seen/owned manipulation is not implemented.
- Story/event flag patching is not implemented.
- Battle enemy-state mutation is not implemented.
- Batch randomized variant generation is not implemented yet.

## Verification

Current verification commands:

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\ruff check .
```

The suite covers patch validation, invariants, generated-state report lookup, golden-state reloads, and emulator save/load smoke checks.

