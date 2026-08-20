Yes. Here are the Phase 5 entrance defaults I’d recommend freezing.

**Capsule A Skills**
For `viridian_forest_catching`, required MVP skills:

- `advance_dialogue`
- `close_menu_or_cancel`
- `recover_to_overworld`
- `walk_local_direction`
- `navigate_within_viridian_forest_region`
- `enter_grass_search_loop`
- `detect_wild_battle`
- `wild_battle_policy` as a battle action skill bundle, not a strategic policy
- `use_move`
- `attempt_catch`
- `use_item`
- `switch_party_member`
- `handle_nickname_prompt`
- `detect_party_changed`
- `detect_blackout_or_party_wipe`
- `detect_capsule_success`
- `detect_stuckness`

This capsule should be our first real executor target.

`wild_battle_policy` is retained as the umbrella for modular battle action executors. The Director chooses the strategy and calls specific actions like `use_move:water_gun`, `attempt_catch`, `use_item:potion`, or `switch_party_member:<target>`. The executor skills only navigate menus, advance bounded dialogue, and report explainable results. See `research/battle-action-skill-bundle.md` for the frozen framing.

**Second Capsule Skills**
For `cerulean_misty`, MVP dry-run skills:

- all shared recovery/dialogue/menu skills
- `navigate_cerulean_region`
- `enter_gym`
- `basic_trainer_battle`
- `misty_battle_policy`
- `heal_at_pokecenter`
- `use_battle_item_or_potion`
- `switch_for_matchup`
- `detect_badge_change`
- `detect_constraint_violation`

I would not require Cerulean success before Phase 5 starts. It should be a dry-run pressure test until Capsule A works.

**Deterministic vs Heuristic**
Deterministic:
- menu closing/opening
- dialogue advancement
- item-count checks
- party/inventory/badge inspection
- Potion/item use once target is known
- nickname entry
- success/failure checks
- trace/log writing

Heuristic:
- navigation/local correction
- grass search pacing
- when to heal
- when to switch
- whether to throw another ball
- battle move choice
- stuck recovery

LLM-mediated:
- accepting/rejecting user directives
- converting safe directives into bounded goals/constraints
- impossible-goal preflight decisions

**Disallowed Destructive Actions**
Hard no by default:

- releasing Pokemon
- deleting/resetting save/run
- throwing away key items
- spending all money without a bounded purchase goal
- overwriting useful moves unless explicitly scenario-approved
- unverified raw memory writes during executor runs
- cross-map runtime teleporting
- intentionally blacking out
- leaving the capsule region without a recovery reason

**Impossible Goals**
I’d put this mostly before executor runtime.

Default behavior:
1. Director/preflight classifies impossible or missing-prerequisite goals as `defer` or `reject`.
2. Executor may return `blocked_missing_prerequisite` if discovered during play.
3. Executor does not flail in-game trying to prove impossibility.
4. The run records the blocker and stops cleanly.

So: no need for many impossible emulator states. Text/directive/preflight cases cover most of that.

**Recovery Defaults**
Menu loop:
- press `B`/cancel up to a small limit
- if still stuck, classify `menu_recovery_failed`

Text loop:
- press `A` through text up to a budget
- if text remains active with no state progress, classify `dialogue_loop`

Unexpected battle:
- if Capsule A and wild battle: handle via catch/fight/run policy
- if trainer battle or unsafe battle: use battle policy, then classify if unrecoverable

Low HP:
- if Potion available and HP below threshold, heal
- if no healing and overworld, route to safer behavior or stop as `low_hp_no_recovery`
- if battle and unsafe, switch if possible; otherwise fight/run according to capsule policy

Wrong mode/drift:
- always first recover to a known mode, preferably overworld or battle action menu
- never continue navigation while mode is uncertain

**Initial Phase 5 Success Bar**
For first implementation, I’d set the bar as:

- Capsule A runner can load a manifest start.
- It can execute a bounded run with structured logs.
- It can detect success/failure/timeout.
- It can handle at least wild battle catch attempts.
- It causes zero destructive actions.
- It produces a failure category for every failed run.

Then we iterate toward the real KPI: **70%+ Capsule A success on non-held-out tuning starts**.
