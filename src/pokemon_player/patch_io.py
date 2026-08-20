from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pokemon_player.patch_model import (
    AddressTrust,
    PatchOperation,
    RawMemoryWrite,
    RemovePartyMember,
    SetItemQuantity,
    SetBadges,
    SetMapLocation,
    SetMoney,
    SetPartyMoves,
    SetPartySpecies,
    SetPartyStats,
    StatePatch,
)


def operation_from_dict(raw: dict[str, Any]) -> PatchOperation:
    op_type = raw.get("type")
    trust = AddressTrust(raw.get("trust", AddressTrust.VERIFIED.value))
    if op_type == "set_party_species":
        return SetPartySpecies(
            slot=int(raw["slot"]),
            species=raw["species"],
            rename_to_species=bool(raw.get("rename_to_species", True)),
            trust=trust,
        )
    if op_type == "remove_party_member":
        return RemovePartyMember(
            slot=raw.get("slot"),
            species=raw.get("species"),
            trust=trust,
        )
    if op_type == "set_party_stats":
        return SetPartyStats(
            slot=int(raw["slot"]),
            level=raw.get("level"),
            current_hp=raw.get("current_hp"),
            max_hp=raw.get("max_hp"),
            attack=raw.get("attack"),
            defense=raw.get("defense"),
            speed=raw.get("speed"),
            special=raw.get("special"),
            status=raw.get("status"),
            trust=trust,
        )
    if op_type == "set_party_moves":
        return SetPartyMoves(
            slot=int(raw["slot"]),
            moves=tuple(raw.get("moves", ())),
            pp=tuple(raw["pp"]) if "pp" in raw else None,
            trust=trust,
        )
    if op_type == "set_map_location":
        return SetMapLocation(
            map_id=raw["map"],
            x=int(raw["x"]),
            y=int(raw["y"]),
            allow_cross_map=bool(raw.get("allow_cross_map", False)),
            trust=trust,
        )
    if op_type == "set_badges":
        return SetBadges(
            badge_names=tuple(raw["badge_names"]) if "badge_names" in raw else None,
            badge_mask=raw.get("badge_mask"),
            trust=trust,
        )
    if op_type == "set_money":
        return SetMoney(amount=int(raw["amount"]), trust=trust)
    if op_type == "set_item_quantity":
        return SetItemQuantity(item=raw["item"], quantity=int(raw["quantity"]), trust=trust)
    if op_type == "raw_memory_write":
        return RawMemoryWrite(
            address=int(raw["address"], 0) if isinstance(raw["address"], str) else int(raw["address"]),
            value=int(raw["value"], 0) if isinstance(raw["value"], str) else int(raw["value"]),
            reason=str(raw.get("reason", "")),
            trust=AddressTrust.UNVERIFIED,
        )
    raise ValueError(f"Unsupported patch operation type {op_type!r}.")


def patch_from_dict(raw: dict[str, Any]) -> StatePatch:
    return StatePatch(
        description=str(raw["description"]),
        goal=raw.get("goal"),
        operations=tuple(operation_from_dict(operation) for operation in raw.get("operations", ())),
        metadata=dict(raw.get("metadata", {})),
    )


def load_patch(path: str | Path) -> StatePatch:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Patch file must contain a JSON object.")
    return patch_from_dict(raw)
