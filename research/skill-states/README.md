# Skill State Captures

Skill-state captures are Phase 5 fixtures for validating skill result flagging.

Local `.state` files and `.png` screenshots live under:

```text
research/skill-states/local/
```

Commit-safe metadata lives under:

```text
research/skill-states/<skill_id>/
```

Use the interactive capture script:

```powershell
.\.venv\Scripts\python scripts\play_and_capture_skill_state.py attempt_catch --state-in path\to\start.state
```

Press `Z` in the PyBoy window to quicksave. If the skill has no seed yet, the first capture becomes the seed and later captures reset to it. After a seed exists, enter one of the valid result codes from `catalog.json`; blank input resets to the seed without saving a new capture.

Evaluate implemented skill flagging against captured states:

```powershell
.\.venv\Scripts\python scripts\evaluate_skill_states.py detect_wild_battle
```

Eval reports are written under `research/artifacts/skill-evals/`.

Execute a skill from a captured state:

```powershell
.\.venv\Scripts\python scripts\run_skill.py attempt_catch --state-in "research\skill-states\local\attempt_catch\success_before.state"
```

`run_skill.py` defaults to `--execution-mode headful`, which opens an SDL2 window and uses rendered ticks. Use `--execution-mode headless` when you specifically want the null-window path.
