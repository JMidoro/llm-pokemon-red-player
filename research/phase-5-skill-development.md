# Phase 5 Skill Development Loop

This note preserves the working loop for skill implementation and validation.

1. Pick a small set of skills from the current capsule.
2. For each skill, capture skill-specific states under `research/skill-states/`.
3. The first capture for a skill is the seed state; later captures reset to that seed.
4. Each later capture uses a catalog result code such as `success_before`, `success_after`, `failed_after_breakout`, or `uncertain_throw_dialogue`.
5. Use the before/after captures to validate result flagging before building more automation.
6. Refine execution code against those state fixtures.
7. Repeat until every skill in the capsule lineup has dependable result flagging.
8. Test skill chaining with preset, non-LLM directives.
9. Wire the LLM director into the skill harness after deterministic chaining is explainable.

Captured local `.state` and `.png` files remain ignored. Metadata stays in-repo so the harness, lab UI, and future compaction runs can recover the intent of each fixture.

## Director Play Gap Logging

During Director UI playtests, manual input should be treated as evidence that the current skill surface is incomplete or too brittle. The Director page exposes manual button controls that send one bounded input through the sidecar player and capture before/after states, screenshots, trace metadata, and a report under `research/artifacts/director-player-runs/manual_input/`.

Use these reports to decide whether the missing coverage is:

- A new narrow executor skill.
- A classifier/gating promotion gap.
- A recovery skill bug.
- A director-planning prompt or state-summary gap.

Manual gap reports should become either skill-state fixtures, promotion evidence, or TODOs before the next skill-chaining pass.

Each Director sidecar run also writes a durable session directory under `research/artifacts/director-player-runs/sessions/`. The `events.jsonl` file records session start, state loads, skill results, manual inputs, promoted observation events, and performance warnings. Observation events capture linked state/screenshot artifacts under that same session directory so we can discuss a run after the fact and promote the exact state that exposed a gap.

## Post-Battle Dialogue Bundle

`advance_battle_dialogue` is intentionally scoped to safe battle text advancement back to a neutral action menu or clean battle exit. Post-catch and end-of-battle aftermath can require decisions, so the catalog tracks `resolve_battle_outcome_dialogue_bundle` separately.

Important branches to capture:

- Successful catch aftermath, including "caught" text and any Pokedex page.
- Nickname prompt before/after declining.
- Victory, XP, level-up, and stat-growth dialogue.
- Move-learning and move-overwrite prompts.
- Evolution start/progress/cancel states, if cancellation becomes rule-relevant.

The Director session `session-20260624T165939662396Z0000` supplied initial trainer-battle outcome fixtures for this bundle:

- Enemy KO damage text.
- XP gain text.
- Level-up text.
- Forced party choice after trainer KO.
- Trainer defeated text.

## Battle Menu Micro-Policy

`attempt_catch` execution exposed enough battle-menu brittleness that a tiny RL policy is now a supported Phase 5 experiment. The policy's job is intentionally narrow: from a loaded wild-battle state, navigate battle UI until a ball is thrown.

Current reward intent:

- Positive terminal reward when any ball count decreases.
- Extra positive reward when the party count increases after the ball is thrown.
- Negative step reward to discourage wandering.
- Negative reward if enemy HP decreases, because weakening/fighting is not this policy's job.
- Negative reward if player HP decreases.
- Negative terminal reward if battle ends without ball consumption, including flee-like outcomes.

Current code surfaces:

- `src/pokemon_player/battle_menu_env.py` defines the Gymnasium-compatible environment.
- `scripts/collect_battle_menu_traces.py` collects random or scripted traces into `research/artifacts/battle-menu-traces/`.
- `scripts/train_battle_menu_policy.py` trains a small SB3 PPO baseline into `research/artifacts/battle-menu-policies/`.

Useful future captures: battle action menu with cursor on each option, item menu already open, throw-result dialogue, different ball inventory ordering, and no-ball blocked states.
