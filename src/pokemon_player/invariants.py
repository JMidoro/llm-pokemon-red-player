from __future__ import annotations

from dataclasses import dataclass

from pokemon_player.state_model import GameSnapshot


@dataclass(frozen=True)
class InvariantResult:
    ok: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...] = ()


def check_snapshot_invariants(snapshot: GameSnapshot) -> InvariantResult:
    errors: list[str] = []
    warnings: list[str] = []

    if not snapshot.party:
        errors.append("Party must not be empty.")
    if len(snapshot.party) > 6:
        errors.append("Party must not have more than six members.")

    seen_slots = set()
    for member in snapshot.party:
        if member.slot in seen_slots:
            errors.append(f"Duplicate party slot {member.slot}.")
        seen_slots.add(member.slot)
        if member.hp > member.max_hp:
            errors.append(f"{member.summary()} has HP above max HP.")
        if not 1 <= member.level <= 100:
            errors.append(f"{member.summary()} has invalid level.")
        if member.max_hp <= 0:
            errors.append(f"{member.summary()} has non-positive max HP.")
        if member.hp == 0 and member.status == 0:
            warnings.append(f"{member.summary()} has 0 HP with no explicit status.")

    if len(snapshot.inventory) > 20:
        errors.append("Inventory has more than 20 item slots.")
    for item in snapshot.inventory:
        if not 1 <= item.quantity <= 99:
            errors.append(f"{item.summary()} has invalid quantity.")

    if snapshot.money is not None and not 0 <= snapshot.money <= 999999:
        errors.append(f"Money value {snapshot.money} is outside valid bounds.")
    if snapshot.position is None:
        errors.append("Position must be known.")
    if snapshot.badges is not None and not 0 <= snapshot.badges <= 0xFF:
        errors.append(f"Badge mask {snapshot.badges} is invalid.")

    return InvariantResult(ok=not errors, errors=tuple(errors), warnings=tuple(warnings))

