# Text-to-Patch Contract

Status: v0

This document defines how an LLM or human should turn plaintext state-edit requests into structured patch JSON for Phase 2.

## Contract

The translator receives:

- Plaintext request
- Intended goal
- Base state name/path
- Current state summary
- Allowed operations
- Address-promotion policy

The translator outputs only structured JSON matching the patch schema. It must not write emulator memory directly.

## Required Behavior

- Use only promoted names from the catalog for species, moves, items, maps, and badges.
- Prefer a base state already on the target map.
- Do not use cross-map runtime edits unless explicitly requested and warned as unsafe.
- Refuse or ask for clarification when the request is contradictory.
- Include a goal when the generated state is intended for human approval.
- Use `raw_memory_write` only when no typed operation exists, and include a reason plus a warning that the address is unverified.

## Output Schema

```json
{
  "description": "Short description of the generated derivative state.",
  "goal": "Goal the generated state is meant to test.",
  "operations": [
    {
      "type": "set_item_quantity",
      "item": "Poke Ball",
      "quantity": 0
    }
  ],
  "metadata": {
    "source_request": "Remove our pokeballs and give us money to purchase more"
  }
}
```

## Supported Operation Types

- `set_party_species`
- `remove_party_member`
- `set_party_stats`
- `set_party_moves`
- `set_map_location`
- `set_money`
- `set_item_quantity`
- `set_badges`
- `raw_memory_write`

## Safety Reminder For Translators

Cross-map runtime edits are not a safe teleport. Use a target-map template state instead.

Unverified addresses must be loud:

```json
{
  "type": "raw_memory_write",
  "address": "0xD000",
  "value": "0x12",
  "reason": "Experimental address from local diffing; not promoted."
}
```

Any patch containing `raw_memory_write` requires explicit `--allow-unverified` before a generated state can be saved.

