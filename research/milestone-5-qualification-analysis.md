# Milestone 5 frozen qualification analysis

## Scope

This analysis covers the completed local-Gemma qualification at candidate commit
`8e1909f5650320941110a2ea74cc9874973621be`. The frozen suite and completed case
outcomes were not changed or rerun while diagnosing them. No hosted inference was
used.

## Corrected baseline

The original evaluator output reported no completed cases because it searched
`supervisor/<case-id>` instead of the canonical
`supervisor/lineages/<case-id>` directory. Re-evaluating the preserved lineages
after correcting discovery produced:

- Capsule A: 2/5 successes.
- Clean boot through Boulder Badge: 0/10 successes.
- Executed illegal actions: 0.
- Executed destructive actions: 0.
- Literal-button actions: 75, all in Capsule A.
- Useful gameplay failures: 13/13 (1.0).
- Human gameplay interventions: 0.
- Deterministic branches: 10/10 passed.
- Single tested commit and complete-case checks: passed.

The corrected generated summary is
`research/artifacts/m5-evals/qualification/evaluation-summary.json`.

## Failure clusters and exact evidence

### Viridian Mart clerk interaction (8/10 clean-boot cases)

Eight clean-boot cases reached the Viridian Mart counter, then alternated between
navigation and a failing `talk_to_npc(viridian_mart_clerk)` call. The skill faced
up from map `0x2A`, `(2,5)`, moving the player away from the counter. An exact-state
probe from the preserved input state showed that facing left and pressing A opens
the clerk dialogue without moving.

- Frozen failure report:
  `research/artifacts/m5-evals/qualification/clean-boot-boulder-01/supervisor/lineages/clean-boot-boulder-01/segments/segment-000003-a1/skill-runs/talk_to_npc/20260821T231259Z/report.json`
- Fixed exact-state reproduction:
  `research/artifacts/m5-evals/diagnostics/mart-clerk-fix/talk_to_npc/20260822T030320Z/report.json`

### Oak's Lab starter precondition (clean-boot case 03)

`choose_starter` treated any non-battle dialogue or overworld state anywhere in
Oak's Lab as a valid starter surface. The first call in case 03 ran at the lab
entrance during Oak's escort dialogue, map `0x28`, `(5,11)`. Repeated execution of
the fixed macro from invalid positions eventually left the case stalled at
`(5,5)`. All nine other clean-boot cases that selected a starter successfully
entered the skill from the stable starter-table handoff at `(5,3)`.

- First invalid invocation:
  `research/artifacts/m5-evals/qualification/clean-boot-boulder-03/supervisor/lineages/clean-boot-boulder-03/segments/segment-000001-a1/skill-runs/choose_starter/20260821T232624Z/report.json`
- First successful comparison:
  `research/artifacts/m5-evals/qualification/clean-boot-boulder-01/supervisor/lineages/clean-boot-boulder-01/segments/segment-000001-a1/skill-runs/choose_starter/20260821T230149Z/report.json`

The exact-state repair also exposed a post-nickname handoff defect. Squirtle had
entered the party while Pokemon Red's `got_starter` event remained false, leaving
the apparent overworld unable to accept movement. `choose_starter` now resolves
the remaining acquisition dialogue and requires the event flag before reporting
success. A local-Gemma replay subsequently reached the first rival battle with
zero literal-button actions.

- Completed exact-state handoff:
  `research/artifacts/m5-evals/diagnostics/oaks-lab-complete-handoff-fix/choose_starter/20260822T034218Z/report.json`
- Local-Gemma continuation:
  `research/artifacts/m5-evals/diagnostics/local-probes/m5-oaks-lab-complete-handoff-v2/report.json`

### Catch-resolution semantics (3/5 Capsule A cases)

The three failed Capsule A cases remained in wild-battle/catch-resolution loops.
Their Directors repeatedly combined `attempt_catch`, `run_from_wild_battle`, and
literal A/B presses. The two successful Capsule A cases also used literal-button
fallbacks, so the ordinary-play literal-action gate fails independently of the
success-rate gate. The next repair must make the semantic catch skill own the
low-level throw-resolution and post-catch prompt flow, while leaving the decision
to weaken, catch, or flee with the Director.

The repaired catch executor now owns throw-result dialogue through a stable
action menu, battle end, or nickname surface. It also respects Pokemon Red's
remembered Bag cursor instead of assuming the cursor resets to the first item.
The identical preserved weakened-Pikachu state now catches Pikachu and stops at
the nickname prompt. A local-Gemma replay caught Pikachu, declined the nickname
semantically, and resumed forest navigation without a literal action.

- Exact catch reproduction:
  `research/artifacts/m5-evals/diagnostics/capsule-a03-remembered-cursor-v2/attempt_catch/20260822T032857Z/report.json`
- Local-Gemma catch replay:
  `research/artifacts/m5-evals/diagnostics/local-probes/m5-capsule-a03-catch-fix-v2/report.json`

### Route 22 navigation-to-search handoff

An exploratory continuation from the repaired Mart state reached the approved
Route 22 grass, then repeatedly requested navigation to the landmark it already
occupied. The chapter policy did not explicitly hand control from navigation to
`enter_grass_search_loop`, and its Viridian PokeCenter checkpoint existed only in
the current segment's action history.

The policy now exposes only encounter search while a healthy player is already
inside the chapter's approved grass, treats arrival at Route 22 or Viridian
Forest as durable checkpoint evidence across supervisor segments, and suppresses
fleeing from the named target encounter above 50% HP. It still leaves the Director
free to weaken or catch the target and permits retreat when survival is at risk.
An exact local-Gemma continuation searched five encounters without navigation
repetition. From the preserved Spearow encounter, Gemma weakened and caught the
target, accepted the required nickname prompt, and named it with semantic tools.

- Search-handoff replay:
  `research/artifacts/m5-evals/diagnostics/local-probes/m5-route22-grass-handoff-fix/report.json`
- Target-commitment replay:
  `research/artifacts/m5-evals/diagnostics/local-probes/m5-route22-target-commitment-fix/report.json`

## Repair order

1. Preserve the canonical lineage discovery fix and its regression coverage.
2. Correct Viridian Mart clerk geometry and retain the exact-state reproduction.
3. Restrict `choose_starter` to the stable starter-table handoff before inputs run.
4. Minimize the Capsule A catch-resolution traces and repair semantic postconditions.
5. Repair the Route 22 navigation-to-search and cross-segment checkpoint handoffs.
6. Run targeted local validations. Only after they pass should a new frozen
   qualification be scheduled; completed frozen gameplay failures are not rerun
   in place or used to alter the suite.

## Pre-qualification validation

The repaired candidate is ready for a new frozen qualification:

- ROM-free portable tests: 449 passed, 51 local-artifact tests deselected.
- Focused Mart, starter, catch, Route 22, and chapter-policy tests: passed.
- Deterministic branch evaluator: 10/10 passed with no issues.
- Ruff: passed.
- Repository portability and hygiene validation: passed.
- Operations UI TypeScript check: passed.
- Operations UI production build: passed with Next.js's Webpack builder. The
  default Turbopack builder cannot follow this worktree's intentional
  `node_modules` junction outside the worktree root; this is a local worktree
  layout restriction, not an application build error.

The host-only full test invocation additionally passed 499 tests but found the
known golden-metadata schema drift in local human-captured states: 54 records
predate the battle-style and Pokedex fields now included in snapshot hashes. The
portable CI gate marks those artifact tests separately, so refreshing all 54
human records is intentionally left out of this repair candidate.
