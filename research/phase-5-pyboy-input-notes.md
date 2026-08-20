# Phase 5 PyBoy Input Notes

Reference inspected: `D:\projects\PokemonRedExperiments`.

Relevant pattern from the reference RL environments:

- Use `pyboy.send_input(WindowEvent.PRESS_...)` and matching release events.
- Hold each action for about 8 frames.
- Advance a full action envelope around 24 frames or more.
- Render only the final frame when a screen observation is needed.
- Do not inject a synthetic blank `ram_file` when constructing PyBoy for normal loaded-state execution.

Changes adopted here:

- `open_emulator()` no longer supplies a zeroed RAM file by default.
- Skill execution now uses explicit `WindowEvent` press/release events.
- Skill execution settles for 60 frames after loading a state before sending inputs.
- `run_skill.py` has an explicit `--execution-mode headful|headless`; headful uses an SDL2 window and rendered ticks.
- `attempt_catch` reports `uncertain` when execution produces no ball-count or party delta.
- `attempt_catch` advances visible throw dialogue and waits for a stable post-throw result.

Known behavior:

- Programmatic input works in overworld states.
- Programmatic input is delivered to Gen 1 joypad HRAM buffers in loaded battle-menu states.
- Loaded battle-menu states respond in headful SDL2/rendered execution.
- The same loaded battle-menu states may ignore programmatic inputs under null-window headless execution.

Likely next probes:

- Capture a short pre-battle overworld seed and let the executor enter a battle naturally, then test whether null-window battle menu input works in a continuous emulator session.
- Compare responsive SDL2/rendered battle input against null-window headless input at HRAM addresses `FFB1`-`FFB7`, `FFF8`, and `FFF9`.
- Promote battle menu cursor/state addresses from PRET/Data Crystal so we can tell whether the menu loop is accepting input but not redrawing, or not consuming input at all.

RL micro-policy note:

- The `PokemonRedExperiments` input pattern is now mirrored in `battle_menu_env`: explicit `WindowEvent` press/release, 24-frame action envelope, release around frame 8.
- `null` window mode is useful for smoke tests but still should not be trusted as representative battle-menu behavior.
- First useful training/evaluation should run headful SDL2/rendered unless the execution-mode matrix proves a headless mode accepts battle-menu input reliably.
