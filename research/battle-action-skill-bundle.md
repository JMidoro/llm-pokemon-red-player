# Battle Action Skill Bundle

`wild_battle_policy` is an umbrella bundle for battle action execution skills. It is not a strategic policy that chooses how to win a battle.

The Director owns strategy. Given battle facts, screenshots, memory, and recent action logs, the Director decides what action should be attempted next: use Tackle, use Water Gun, throw a Poke Ball, switch to a named party member, use a Potion, flee, or stop and replan.

The executor owns bounded menu routing. Once the Director selects an action, the matching skill may recover from a known battle submenu, move the cursor to the requested action, press the needed buttons, advance result dialogue within a budget, and return a structured result.

## Director-Facing Skills

- `use_move`: execute a requested active move by name or slot.
- `attempt_catch`: select a supported ball and classify catch success, failed throw, blocker, or uncertainty.
- `use_item`: select a supported battle item and verify the expected item effect.
- `switch_party_member`: switch to a requested viable party member.
- `flee_battle`: choose Run only when the Director explicitly requests it and the capsule allows it.
- `advance_battle_dialogue`: advance battle text without making a strategic selection.

## Shared Promotions

- `battle-menu-and-cursor-detection`: identifies action, item, move, party, and dialogue surfaces plus cursor position.
- `battle-enemy-facts`: identifies enemy species, level, HP, status, and related battle facts.
- `party-switch-and-active-battler`: identifies active battler, party menu selection, and switch viability.
- `item-use-and-bag-selection`: identifies battle bag contents, cursor/index, and item effect preconditions.
- `battle-move-selection-and-result`: maps active moves to move-menu slots and verifies selected move outcomes.
- `director-stuckness-progress-signals`: detects repeated no-progress loops and returns replanning evidence.

## Result Contract

Each battle action executor should report:

- requested Director action and normalized target, such as `use_move:water_gun`;
- starting battle UI surface and any recovery steps taken;
- selected menu action, item, party slot, or move slot;
- before/after facts relevant to the action, such as PP, item count, HP, status, party, or Pokedex ownership;
- dialogue/result state when the action cannot yet be fully classified;
- final status: `succeeded`, `blocked`, `failed`, or `uncertain`.

This keeps the architecture explainable: the LLM Director can reason about Pokemon strategy, while small executor skills handle the fiddly Game Boy menu mechanics.
