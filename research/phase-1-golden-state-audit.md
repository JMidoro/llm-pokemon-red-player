# Phase 1 Golden-State Audit

Status: current as of 2026-06-16

## Summary

The Phase 1 state collection is complete enough to proceed with hardening the state lab.

There are 42 available local PyBoy states with matching expected metadata. Each available state:

- Is marked `human_verified: true`
- Uses the pinned Pokemon Red ROM hash
- Reloads successfully through PyBoy
- Produces the expected stable snapshot hash

The current test gate is `tests/test_golden_states.py`.

## Coverage

Mode coverage:

- Overworld: 32
- Battle: 8
- Menu: 1
- Dialogue: 1
- Uncertain: 0

Progression and location coverage includes:

- Pallet Town and early journey setup
- Oak's Lab and town-map/Pokedex/Poke Ball setup
- Route 1 and Route 2
- Viridian City, Mart, PokeCenter, Forest gate, Forest grass, and Forest battles
- Pewter City, Gym, Mart, PokeCenter, Brock battle, and post-Brock badge state
- Route 3, Mt. Moon, Route 4, and Mt. Moon PokeCenter
- Cerulean City, PokeCenter, Gym, Misty battle, and post-Misty badge state

State-surface coverage includes:

- Map id/name and x/y position
- Overworld, battle, menu, and dialogue modes
- Party species, nicknames, levels, HP/max HP, status, moves, and PP
- Inventory item names/counts
- Money
- Badge flags
- Fainted/low-HP/degraded party states
- Wild battle and trainer battle states

No available golden state currently has unknown map, species, item, or move names in the serialized summary.

## Known Exceptions

Two expected metadata files point to missing local `.state` files and are not part of the active golden-state gate:

- `battle_route_1_pidgey_weakened.expected.json`
- `battle_route_1_ratata.expected.json`

The available local file `route_1_wild_battle_ratata.state` has been promoted under matching metadata:

- `route_1_wild_battle_ratata.expected.json`

The old missing metadata files are preserved for traceability but ignored by the active test helper because their local state files do not exist.

## Phase 1 Exit Evidence

Can we reliably tell where the player is?

Yes for the available golden set. All loaded states resolve to named maps and coordinates, and no available state has an unknown map name.

Can we reliably tell whether the game is in overworld, battle, menu, or dialogue?

Yes for the currently captured golden set. Battle detection uses WRAM, explicit menu/dialogue states use WRAM text-box IDs, and optional screen/tile evidence is available for future UI ambiguity checks.

Can we reliably inspect party, HP, moves, items, money, and badges?

Yes for the available golden set. All observed species, moves, items, and badge states are named and serialized into stable expected JSON.

Can we save, reload, and replay a short trace deterministically?

Save/reload determinism is covered by `tests/test_pyboy_smoke.py` and full golden-state reload/hash checks. Trace replay tooling exists in `scripts/run_trace.py`; richer trace determinism should be attached to the first actual executor trace.

Can the plaintext state summary support basic Q&A?

Yes for first-pass Phase 1 purposes. Summaries include location, mode, party, inventory, money, badges, and goal-relevant facts such as Poke Ball availability, Viridian Forest location, and Cascade Badge ownership.

## Speed Measurement

Headless benchmark command:

```powershell
.\.venv\Scripts\python scripts\benchmark_pyboy.py --state-in research\golden-states\local\viridian_forest_grass.state --frames 10000
```

Latest local result:

- State: `viridian_forest_grass.state`
- Frames: 10,000
- Elapsed: 0.788 seconds
- Throughput: 12,682.8 FPS
- Approximate real-time multiplier: 211.4x
