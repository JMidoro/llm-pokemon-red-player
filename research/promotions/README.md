# Promotion Evidence Workflow

Promotion evidence should be collected through the unified capture script unless an artifact already exists.

1. Open the Lab Console at `http://localhost:3001`.
2. Go to `Promotions`.
3. Choose a promotion and read `Evidence Collection Steps`.
4. For the relevant step, choose a `Start From` state.
5. Copy the generated `Unified Capture Command`.
6. Run it from the repo root.
7. Play in the PyBoy window and press `Z` when the screen represents the evidence.
8. Return to the terminal, accept or edit the label/expected observation, and let the script save the capture.
9. Refresh the Lab Console.

The script saves files here:

- State and screenshot: `research/promotions/evidence/local/<promotion-id>/`
- Metadata: `research/promotions/evidence/<promotion-id>/`

By default, the script also attaches the captured evidence to:

- `research/promotions/mvp-skill-promotions.json`

The manual `Attach Evidence` form in the Lab Console is for retroactive artifacts that already exist.

## WRAM Assertions

Screenshots prove what a human can see. They do not prove that our memory reader found the same facts.

Promotion evidence metadata can also include `assertions`. These compare expected human-observed facts against the
captured snapshot. For example, `battle_enemy_facts` evidence can assert:

- `snapshot.mode == "battle"`
- `snapshot.enemy.species_name == "Weedle"`
- `snapshot.enemy.level == 3`
- `snapshot.enemy.hp == snapshot.enemy.max_hp`

Validate promotion evidence assertions with:

```powershell
.\.venv\Scripts\python scripts\validate_promotion_evidence.py --promotion battle_enemy_facts
```

Refresh existing promotion evidence after snapshot-reader changes with:

```powershell
.\.venv\Scripts\python scripts\refresh_promotion_evidence_metadata.py --promotion battle_enemy_facts --infer-assertions --force-assertions
```
