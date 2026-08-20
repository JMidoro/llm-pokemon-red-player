# Address Promotion Process

Status: v0

Runtime patching may encounter useful memory addresses before they are safe enough to become normal operations. This document defines how an address moves from unverified to approved.

## Trust Levels

Unverified:

- May be used only through `raw_memory_write`.
- Must include a reason.
- Produces a danger warning.
- Requires explicit `--allow-unverified` before a patched state is saved.

Candidate:

- Has a likely source in PRET, Data Crystal, PyBoy, or direct golden-state diffing.
- Has at least one local experiment showing the expected effect.
- Still emits a warning when used.

Verified:

- Has a canonical source or a documented diff-based derivation.
- Has tests against at least one golden state.
- Has invariant checks where relevant.
- Is exposed through a typed operation rather than raw memory writes.

## Promotion Checklist

Before promoting an address to verified:

- Name the semantic field.
- Record the address and byte width.
- Identify the source: PRET, Data Crystal, emulator API, or golden-state diff.
- List the states used to test it.
- Add a negative test if invalid values can be dangerous.
- Add or update the state inspector if the field should be observable.
- Add or update the patch validator if the field should be mutable.

## WRAM Addressing Disambiguation Playbook

Use this process when a plausible address does not cleanly explain a gameplay state:

1. Start from the observed ambiguity and name the exact semantic question. Example: "Has Oak received the Parcel?" is different from "Is Oak's Parcel somewhere in the current story machinery?"
2. Use Data Crystal for broad WRAM anchors and directly named public addresses. Treat these as entry points, not proof of the full contract.
3. Use PRET `pokered` for symbolic event/script meaning. For story flags, find the relevant `EVENT_*` constants and the scripts that set or check them.
4. Convert event constants through `wEventFlags`: `address = EVENT_FLAGS_START + index // 8`, `bit = index % 8`, `mask = 1 << bit`. The local Gen 1 Red/Blue `wEventFlags` base promoted here is `0xD747`.
5. Read the candidate bytes from at least two local before/after states that bracket the story transition. Prefer states captured through normal play.
6. Promote the smallest named fact that answers the question. Keep neighboring or tempting bytes as candidates until they distinguish the local states.
7. Add inspector output and tests before relying on the address in planner logic. If fixtures do not yet include the promoted field, legacy heuristics may remain only as fallbacks.
8. Document negative evidence. For the parcel loop, `D60D` looked relevant from Data Crystal, but local states showed it did not distinguish "holding Oak's Parcel" from "Oak already received the Parcel"; the planner now relies on `EVENT_OAK_GOT_PARCEL` / `EVENT_GOT_POKEDEX` instead.

## Current Verified Runtime Mutation Fields

- Party count
- Party species list
- Party Pokemon struct species
- Party Pokemon current HP
- Party Pokemon level bytes
- Party Pokemon status
- Party Pokemon move slots
- Party Pokemon PP slots
- Party Pokemon max HP, attack, defense, speed, and special
- Party nicknames
- Inventory item list and quantities
- Money
- Current map id
- Player x/y
- Badge bits
- Read-only story event facts from `wEventFlags`: early starter/rival/Pokedex/parcel flags and Brock defeated flag

## Good Candidate Fields

- Player facing direction
- Pokedex seen/owned bitsets
- PC box count/species/structs
- Current battle enemy species and HP
- Additional event/story flags for capsule prerequisites
- Menu/dialogue recovery fields

## Known Unsafe Shortcut

Changing only `current map`, `player x`, and `player y` is not sufficient for a verified cross-map teleport. It can produce states that inspect as the target map but still behave like the source map internally. Use target-map template states until a full map-load promotion is researched.
