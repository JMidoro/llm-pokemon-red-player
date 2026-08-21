# Milestone 4 Validation Record

Status: complete; the configurable rules, durable lineage, checkpoint reconciliation, pre-input guards, Director context, Operations view, and deterministic replay gates passed.

## Approved stream contract

The canonical `stream-nuzlocke-v1` profile records the approved defaults: evolutionary-family duplicates, failed-first-encounter consumption, gift and static independence, required nicknames, advisory level caps, Set battle style, allowed battle items, blackout game over, reset only after game over, and the required-progression HM softlock exception ladder. The `standard-run-v1` profile demonstrates that Nuzlocke enforcement and reset behavior can be changed through configuration.

Gift Pokemon are explicitly independent of the area's wild encounter opportunity. If a future profile changes `giftConsumesArea`, reconciliation attributes that consumption to the actual canonical area rather than a shared synthetic gift bucket.

The implementation preserves the Director's discretion over tactics, party order, training, item use, and whether to pursue an eligible encounter. Only objective illegality is blocked before emulator input.

## Deterministic contract gate

Run: `research/artifacts/nuzlocke-contract-evaluations/milestone-4-final-gate/evaluation-summary.json`

- 7 of 7 replay fixtures passed.
- Every fixture rebuilt an identical derived lineage state and state digest from its event stream.
- The fixtures cover a catch, failed first encounter, evolutionary-family duplicate, gift and static independence, death and blackout, full-party transfer to the box, and an HM exception.
- The evaluator records `inference.used=false`, with no provider or model.

The automated suite passed with 381 tests and 50 local-artifact tests deselected. Ruff passed for `src`, `scripts`, and `tests`. The Operations UI passed TypeScript checking and a production Next.js Webpack build. The default Turbopack builder cannot follow the worktree's intentionally shared `node_modules` junction, so the production build was verified through Next.js's supported `--webpack` path.

## Captured and real-emulator evidence

The test `test_captured_pikachu_artifacts_reconcile_without_new_gameplay_collection` replays the tracked before/after Pikachu capture evidence and verifies the Viridian Forest encounter and ownership change without requesting a new gameplay artifact.

Run: `research/artifacts/milestone-4-runtime-smoke-final/m4-runtime-smoke-final/report.json`

- A real PyBoy segment loaded the preserved post-Pikachu state and executed one deterministic replay decision through the canonical runner.
- The checkpoint was `healthy_continue`; the stop reason was the one-action inspection budget, not a failure.
- The configured Set battle style was present in RAM (`options_raw=3`) and in the final snapshot.
- The ledger persisted 21 events, the existing fainted Nidoran M death, and an active eligible Viridian Forest Weedle encounter.
- Usage was zero tokens and zero estimated cost. No local or hosted player inference was contacted.

## Guard and configuration coverage

Automated integration coverage verifies that the runtime:

- blocks an illegal extra catch, evolutionary-family duplicate catch, empty or declined nickname, forbidden reset, dead-Pokemon battle use, HM-carrier battle use, and raw-input bypass before emulator input;
- treats level-cap and HM party-position guidance as advisory rather than scripted strategy;
- distinguishes an overworld static encounter by configured object location, preventing an ordinary wild Power Plant Voltorb from being misclassified;
- does not report a fled duplicate-family encounter as a successful capture;
- detects full-party captures through Pokedex ownership flags and records them in the box;
- applies only the battle-style bit when enforcing Set mode;
- exposes sanitized rules, encounter use, deaths, exceptions, next eligible areas, advisories, and guard decisions to both the Director and Operations UI;
- rejects ledger tampering, non-contiguous event streams, lineage mismatch, and ruleset-digest mismatch on reopen.

## Source-backed game data

The complete 151-species internal-index mapping is derived from PRET's [Pokemon constants](https://github.com/pret/pokered/blob/master/constants/pokemon_constants.asm) and [Pokedex order](https://github.com/pret/pokered/blob/master/data/pokemon/dex_order.asm). Canonical map IDs come from [map constants](https://github.com/pret/pokered/blob/master/constants/map_constants.asm). Static encounter object coordinates are encoded from PRET's map object data, including [Power Plant](https://github.com/pret/pokered/blob/master/data/maps/objects/PowerPlant.asm), [Route 12](https://github.com/pret/pokered/blob/master/data/maps/objects/Route12.asm), [Route 16](https://github.com/pret/pokered/blob/master/data/maps/objects/Route16.asm), [Seafoam B4F](https://github.com/pret/pokered/blob/master/data/maps/objects/SeafoamIslandsB4F.asm), [Victory Road 2F](https://github.com/pret/pokered/blob/master/data/maps/objects/VictoryRoad2F.asm), and [Cerulean Cave B1F](https://github.com/pret/pokered/blob/master/data/maps/objects/CeruleanCaveB1F.asm).

Milestone 4 is complete. Blackout restart means a subsequent run begins a new durable lineage; the current lineage is never silently cleared or reused. Automatic clean-run orchestration belongs to the later full-playthrough qualification path, while this milestone supplies the enforceable stop and durable game-over evidence it needs.
