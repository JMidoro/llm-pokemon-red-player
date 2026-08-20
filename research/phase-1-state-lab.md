# Phase 1 Emulation Lab and Ground-Truth State Model

Status: v0 scaffold
Source plan: `research/plan.md`
Phase 0 contract: `research/phase-0-charter.md`
Last updated: 2026-06-16

## Purpose

Phase 1 builds the microscope, not the agent. The deliverable is a small, testable lab that can load the pinned Pokemon Red ROM, advance frames, issue inputs, save/load emulator states, read a narrow WRAM-backed state surface, and produce plaintext summaries for director-facing reasoning.

## Resource Findings

PyBoy is the emulator substrate. The PyBoy API documents object-level emulator control, `window="null"`/headless-style operation, direct memory access through `pyboy.memory`, button input through `pyboy.button(...)`, frame advancement through `pyboy.tick(...)`, and file-like save/load state calls through `pyboy.save_state(...)` and `pyboy.load_state(...)`.

Data Crystal's Pokemon Red/Blue RAM map is the first WRAM address reference. The initial inspector uses:

- `D163`: party count
- `D164-D16A`: party species list
- `D16B` onward: party Pokemon structs, 44 bytes per slot
- `D31D-D346`: inventory count and item pairs
- `D347-D349`: money
- `D356`: badges
- `D35E`: current map id
- `D361-D362`: player y/x position
- `D057` and nearby battle bytes as provisional battle indicators

PRET `pokered` is the source of truth for constants and cross-checks. The v0 map-name table is intentionally small and focuses on the approved capsules: Viridian Forest catching and Cerulean/Misty prep. Unknown constants remain numeric until verified.

## Phase 1 Entry Answers

### Which ROM/version is the initial target?

The local target is `research/PokemonRed.gb`, gitignored and pinned by:

- SHA-256: `5CA7BA01642A3B27B0CC0B5349B52792795B62D3ED977E98A09390659AF96B7B`
- MD5: `3D45C1EE9ABD5738DF46D2BDDA8B57DC`
- Header title: `POKEMON RED`
- Size: 1,048,576 bytes

### Which state fields are required for the first two capsules?

Capsule A, Viridian Forest catching:

- Current map id/name, x/y position, and coarse location summary
- Battle status and enemy species when available
- Party count, species ids, nicknames, levels, HP, status, and moves
- Inventory item ids/counts, especially Poke Balls and healing items
- Money
- Badges for progress context
- Pokedex ownership bits for target species where relevant
- Dialogue/menu/battle uncertainty flags so the executor can avoid blind inputs

Capsule B, Cerulean/Misty prep:

- Everything from Capsule A
- Thunder Badge/Cascade Badge progress bits
- Cerulean City/Gym/PokeCenter map identification
- Team readiness facts: party health, levels, status, move ids, and healing item availability
- Soft-constraint facts such as highest party level and whether the party has a favorable known species id

### Will the first state model read from WRAM only, SRAM only, emulator APIs, or a mixture?

Phase 1 uses a mixture, but the semantic state model is WRAM-first:

- WRAM via `pyboy.memory` for game facts
- PyBoy emulator APIs for frame advancement, input, save/load state, and optional screen/tile evidence
- Screen/tile evidence only as a secondary source for menu/dialogue ambiguity
- No save-file/SRAM mutation in Phase 1

### What is the minimum plaintext state summary the director needs?

The director summary must include:

- Coarse mode: battle, overworld, menu/dialogue candidate, or unknown
- Map id/name and player coordinates
- Party overview with species ids/names where known, level, HP/max HP, status, and moves
- Inventory essentials, especially Poke Ball and healing item counts
- Money and badge flags
- Goal-relevant facts for the current capsule
- Explicit uncertainty notes when a field is provisional or unverified

### What is the supported save-state format for v0?

Use PyBoy binary emulator snapshots written through `pyboy.save_state(file_like)` and restored through `pyboy.load_state(file_like)`. These files use a local `.state` extension and are gitignored. Battery saves (`.sav`) are local artifacts and not the primary Phase 1 snapshot format.

## Exit Question Scaffolding

Phase 1 is complete only when these can be answered with tests and golden states:

- Can we reliably tell where the player is?
  - Evidence: golden states spanning Viridian Forest, Cerulean City, Cerulean Gym, PokeCenters, and transition gates pass map/x/y checks.
- Can we reliably tell whether the game is in overworld, battle, menu, or dialogue?
  - Evidence: battle states are detected from battle WRAM; menu/dialogue states require either WRAM fields discovered during golden-state work or screen/tile corroboration. Until then, summaries must say `unknown` or `overworld_or_ui_uncertain`.
- Can we reliably inspect party, HP, moves, items, money, and badges?
  - Evidence: golden states compare each field against manual observations. Current scaffold supports WRAM reads for these fields, with partial constant names.
- Can we save, reload, and replay a short trace deterministically?
  - Evidence: a PyBoy `.state` plus a button trace produces the same final high-level snapshot hash across repeated runs.
- Can the plaintext state summary support basic Q&A such as "Can I catch Pikachu right now?" or "Why can't I fight Misty yet?"
  - Evidence: summary facts include location, ball availability, party readiness, badge/progress context, and explicit missing prerequisites.

## Initial Artifact Layout

- `src/pokemon_player/rom.py`: local ROM fingerprinting
- `src/pokemon_player/memory_map.py`: WRAM addresses and small verified constants
- `src/pokemon_player/state_model.py`: typed snapshot model and plaintext summary
- `src/pokemon_player/state_inspector.py`: WRAM-backed inspector
- `src/pokemon_player/pyboy_lab.py`: PyBoy loading, snapshots, traces
- `scripts/inspect_state.py`: local CLI for inspecting the current ROM state
- `research/golden-states/`: notes and local-only state files
- `tests/`: unit tests for pure-Python scaffold behavior

## First Golden-State Targets

The first 20 golden states should cover:

1. Title/new-game baseline after boot
2. Overworld outside player's house
3. Route 1
4. Viridian City
5. Viridian PokeCenter
6. Viridian Mart
7. Route 2
8. Viridian Forest south gate
9. Viridian Forest entrance
10. Viridian Forest grass
11. Wild battle in Viridian Forest
12. Successful catch state
13. Party full or near-full state
14. No Poke Balls degraded state
15. Low HP degraded state
16. Cerulean City
17. Cerulean PokeCenter
18. Cerulean Gym
19. Misty battle
20. Post-Misty badge state

Each golden state needs a local `.state` file, a small expected JSON record, and a human note explaining how the expected values were verified.

## Known Open Work

- Build and verify the first 20 golden states. These are required to complete Phase 1, but not required to keep building the lab scaffolding.
- Discover or verify UI/dialogue/menu WRAM fields against golden states.
- Expand constants from PRET rather than hand-maintaining large lookup tables.
- Decide whether generated expected-state JSON fixtures can be committed without leaking save data.
- Add richer deterministic trace tests once the first playable golden state exists.

## Current Tooling Status

Implemented:

- ROM fingerprinting and header-title detection.
- PyBoy emulator boot, button trace, save-state, load-state, and snapshot wrappers.
- In-memory battery RAM by default so smoke tests do not create persistent save data unless requested.
- WRAM-backed snapshot inspector for map, position, battle flag, party, inventory, money, and badges.
- Plaintext director summary.
- Commit-safe snapshot JSON serialization and stable snapshot hashes.
- `scripts/inspect_state.py` for ad hoc inspection.
- `scripts/capture_golden_state.py` for writing local `.state` files and matching `.expected.json` metadata.
- `scripts/play_and_capture.py` for visible human play with named state capture prompts.
- `scripts/verify_golden_state.py` for checking a local `.state` against expected metadata.
- `scripts/run_trace.py` for applying a JSON button trace from a saved PyBoy state.
- `scripts/refresh_golden_metadata.py` for refreshing expected metadata after inspector improvements.
- `scripts/benchmark_pyboy.py` for measuring headless PyBoy frame throughput.
- `tests/test_golden_states.py` for reloading the available golden states and enforcing stable hashes, mode coverage, and progression coverage.

Golden-state drop location:

- PyBoy state files: `research/golden-states/local/`
- Incoming non-PyBoy state files: `research/golden-states/local/incoming/`
- Commit-safe expected metadata: `research/golden-states/<name>.expected.json`

Current audit:

- `research/phase-1-golden-state-audit.md`
