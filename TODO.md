# TODO

Durable project TODOs live here. Keep phase-closeout audits in `research/`, and use this file for cross-phase work that should not be lost.

## Phase 2 Follow-Ups

- Build batch randomized variant generation on top of approved patch recipes.
- Implement PC box manipulation after address promotion.
- Implement Pokedex seen/owned manipulation after address promotion.
- Promote story/event flags needed for capsule prerequisites.
- Research battle enemy-state mutation for encounter and battle-policy tests.
- Research full cross-map teleport/map-load mutation. Until then, use target-map template states.

## Phase 3 Follow-Ups

- Add API-backed directive eval once an OpenAI API key is present.
- Add regression capture: every directive failure becomes a new deck case.
- Wire accepted directives into patch recipes or executor goals in later phases.
- Expand the lab UI directive review surface as the directive deck grows.

## Lab UI Follow-Ups

- Add Pokedex seen/owned reads after the relevant WRAM/SRAM addresses are promoted.
- Add LLM-backed state interrogation once the state surface includes the facts needed by the questions.
- Add run and failure interrogation views for `skill_run_report_v1`, `skill_chain_report_v1`, and `throw_execution_v1` reports during Phase 6.

## Phase 4 Follow-Ups

- Approve enough generated derivative starts to populate MVP tuning/holdout manifests.
- Add an automated capsule manifest view to the lab UI.
- Add evaluator controls for post-success states such as post-Misty badge/dialogue.
- Promote event detection needed for automated catch success and blackout/failure classification.

## Phase 5 Follow-Ups

- Continue the skill loop documented in `research/phase-5-skill-development.md`.
- Add preset non-LLM skill-chain directives once Capsule A skills have result flagging.
- Add lab UI browsing for saved `skill_eval_report_v1` reports.
- Add lab UI browsing for saved `skill_run_report_v1` reports.
- Research why programmatic PyBoy input reaches overworld states but is ignored by Gen 1 battle menus after loading battle save states.
- Expand battle-menu RL start states: cursor offsets, bag submenu, failed-throw dialogue, different ball inventory ordering, and no-ball blocked cases.
- Validate promoted enemy battle HP reads (`0xCFE6-0xCFE7`, max `0xCFF4-0xCFF5`) against human-observed damage in multiple wild battles.
- Audit local `PLAYER_FACING = 0xD363`; Data Crystal labels `D363/D364` as current block coordinates, so facing direction needs PRET/source confirmation before promotion.
- Investigate/promote a current music or SFX WRAM signal as a possible trainer-engagement hook; PyBoy currently opens with `sound_emulated=False`, so this needs source-backed memory evidence before use.
- Train and compare the throw-ball battle-menu micro-policy against the scripted `attempt_catch` executor.
- If PPO still needs long runs for clear throw-ball behavior, replace pure reward shaping with action masks and/or behavior cloning from expert traces.
- Battle-menu policy execution currently requires `--window SDL2 --render true`; `window=null` and `render=false` can load states but do not reliably deliver menu inputs after savestate load.
- Treat move-menu and party-menu starts as a separate recovery curriculum until the cancel/non-damaging-move routes are verified.
- Build out `resolve_battle_outcome_dialogue_bundle` from post-catch and end-of-battle captures: caught text, Pokedex entry, nickname prompt, XP, level-up, move learning, and evolution/cancel branches.
- Split battle-outcome switch handling in Director gating: optional trainer-KO switch prompt should expose a yes/no decision, while forced party selection after player KO should expose only replacement selection and must not be treated as a normal optional `switch_party_member` menu.
- Make Capsule A navigation planning asynchronous or otherwise separated from visible frame progression so the director player can report "planning" versus "walking" instead of appearing frozen or reset/replayed.
- Treat Viridian Forest north-gate routing failures as trainer-battle progression blockers, not missing waypoint data: `mid_north` (`map=0x33,x=17,y=9`) is the intended intermediary waypoint, and paths north of it may require resolving the blocking trainer battle before traversal can complete.
- Generalize the waypoint/warp model so future capsules do not require dense landmark collection for every map tile.
- Add a lab UI browser for `manual_input` diagnostic reports captured from Director play sessions.

## Phase 6 Follow-Ups

- Build a report browser/interrogator over `research/artifacts/skill-runs/`.
- Add replay determinism checks for `skill_run_report_v1` button traces.
- Add hand-labeled failure-classification fixtures once a small failed-run set exists.
