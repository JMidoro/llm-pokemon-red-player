# Golden States

This directory is for Phase 1 manually verified state fixtures.

Local emulator state files (`*.state`, `*.state.*`) are gitignored. Put them under:

`research/golden-states/local/`

Commit only small metadata or expected-value files after confirming they do not contain ROM/save data.

The preferred metadata filename is:

`research/golden-states/<name>.expected.json`

Use this command to capture a local state plus expected metadata:

```powershell
.\.venv\Scripts\python scripts\capture_golden_state.py viridian_forest_entrance --state-in research\golden-states\local\some_existing_state.state --note "Manual state dropped by Joey; needs verification."
```

For normal human play with capture prompts, use:

```powershell
.\.venv\Scripts\python scripts\play_and_capture.py
```

Controls in the PyBoy window:

- D-pad: arrow keys
- A: `A`
- B: `S`
- Start: `Enter`
- Select: `Backspace`
- Speed toggle: `Space`
- Capture named state: press `Z`, then return to the terminal and enter the name
- Quit: `Escape` in the PyBoy window or `Ctrl+C` in the terminal

When `Z` is pressed, PyBoy writes a temporary quicksave. The script detects it, pauses before resuming play, asks for a canonical name, reloads that exact captured point, and writes:

- `research/golden-states/local/<name>.state`
- `research/golden-states/<name>.expected.json`

To resume from a captured state:

```powershell
.\.venv\Scripts\python scripts\play_and_capture.py --state-in research\golden-states\local\pallet_overworld_started.state
```

Use this command to verify a captured state against expected metadata:

```powershell
.\.venv\Scripts\python scripts\verify_golden_state.py research\golden-states\viridian_forest_entrance.expected.json
```

If you already have a PyBoy `.state` file, drop it into `research/golden-states/local/` and either run the capture command above or tell Codex the filename.

If you have a different save-state format from another emulator, drop it into `research/golden-states/local/incoming/` and keep the original extension. It may need conversion or recreation in PyBoy before it can become an official Phase 1 golden state.

Each golden state should eventually have:

- Local state file path
- Scenario/capsule label
- ROM hash
- Human-verified expected fields
- Button trace used to reach it, if any
- Notes about uncertainty or visual verification

`human_verified: false` means the state was captured but should not yet be used as a ground-truth assertion. Flip it only after a human-readable summary and/or visual check confirms the expected fields.

Do not promote title-screen or early boot snapshots to golden states. Until gameplay has initialized, WRAM fields can look plausible while not describing an actual playable state.
