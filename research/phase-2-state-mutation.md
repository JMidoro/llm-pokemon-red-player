# Phase 2 State Mutation and Text-to-State Tooling

Status: v0 scaffold
Last updated: 2026-06-16

## Supported v0 Runtime Edits

Officially supported:

- Swap a party Pokemon species by slot.
- Remove a party Pokemon by slot or species, while refusing to remove the last party member.
- Override party member level, current HP, max HP, attack, defense, speed, special, and status.
- Override party member moves and optionally PP.
- Set current map id plus x/y location using promoted map names.
- Set badges by names or mask.
- Set money.
- Set item counts, including removing an item by setting quantity to `0`.

Nice-to-have later:

- PC box manipulation.
- Pokedex seen/owned manipulation.
- Badge/story-flag edits.
- Player facing direction.
- Recovery-only clearing of battle/menu/dialogue state.

Badge/story/event edits should go through address promotion before becoming normal operations.

## Runtime vs Save Edits

v0 uses runtime/PyBoy emulator-state edits only. We are not editing `.sav` data or maintaining save-file checksums in Phase 2.

Important correction: cross-map runtime edits are not safe as normal verified operations. Changing only `current map`, `x`, and `y` can leave the loaded map engine/collision/script state from the original map, which creates strange control behavior. For v0, location variants should start from a template golden state already on the target map, then apply party/item/money edits. Same-map coordinate nudges are allowed.

Local generated `.state` files remain gitignored. Commit only patch recipes, metadata, and verification reports.

## Validation Policy

Every patch follows:

1. Structured proposal.
2. Typed validation.
3. Warning report.
4. Application to emulator memory.
5. Re-inspection through the Phase 1 state inspector.
6. Optional human approval for a goal-specific generated state.

A generated state is loadable when it can be opened and inspected. It is considered goal-valid only when the stated goal can be human-accomplished or otherwise verified for that capsule.

## LLM Autonomy Policy

LLMs may propose complete structured patches. Verified operations are normal patch operations.

Unverified address writes are allowed only as `raw_memory_write` operations. They produce a danger warning and require explicit `--allow-unverified` in the CLI before saving. The proposal must include a reason and should cite the canonical memory-map source or say plainly that the address is not promoted yet.

## Example Patch

```json
{
  "description": "Start a Viridian Forest catching variant with low-health Pikachu and no Poke Balls.",
  "goal": "Capture a Pikachu after buying more Poke Balls.",
  "operations": [
    {
      "type": "set_party_species",
      "slot": 1,
      "species": "Pikachu"
    },
    {
      "type": "set_party_stats",
      "slot": 1,
      "level": 8,
      "current_hp": 3,
      "max_hp": 26,
      "status": "ok"
    },
    {
      "type": "set_item_quantity",
      "item": "Poke Ball",
      "quantity": 0
    },
    {
      "type": "set_money",
      "amount": 3000
    },
    {
      "type": "set_map_location",
      "map": "Viridian Mart",
      "x": 2,
      "y": 3
    }
  ]
}
```

Apply with:

```powershell
.\.venv\Scripts\python scripts\apply_state_patch.py --state-in research\golden-states\local\viridian_mart_overworld.state --patch patch.json --state-out research\artifacts\patched\variant.state
```

Play a generated state with:

```powershell
.\.venv\Scripts\python scripts\play_state.py research\artifacts\patched\variant.state
```

If the generated state has a sidecar report, `play_state.py` prints its goal and approval status before the emulator loop starts.

After human testing, mark a generated state:

```powershell
.\.venv\Scripts\python scripts\approve_generated_state.py research\artifacts\patched\variant.state --status approved --notes "Goal completed manually."
```

## Additional Edits Worth Considering

- Timeboxed resource edits, such as "set enough money for three Poke Balls but no extra healing."
- Team-shape edits, such as "force exactly one healthy Pokemon and one fainted backup."
- Degraded condition edits, such as poison, paralysis, zero PP on a key move, or low HP.
- Route/capsule entry edits that preserve nearby story assumptions, such as "Pewter Mart with Boulder Badge owned" only after badge flags are promoted.
- Inventory safety edits, such as ensuring key items are retained when removing ordinary items.

## Open Phase 2 Questions

- Which generated states should become reusable scenario fixtures?
- What exact approval record should mark a generated state as goal-valid?
- Which unverified addresses are worth promoting first?
- Should patch recipes become first-class scenario-capsule inputs in Phase 4?

## Address Promotion

Address promotion is tracked in:

- `research/address-promotion.md`

The short version: unverified writes are allowed only as loud, explicitly approved raw writes; verified fields must have source evidence, tests, and typed validators.

## Closeout Artifacts

- `research/text-to-patch-contract.md`
- `research/phase-2-audit.md`
