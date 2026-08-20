from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal


class AddressTrust(StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class PatchWarning:
    message: str
    severity: Literal["info", "warning", "danger"] = "warning"


@dataclass(frozen=True)
class PatchReport:
    applied: bool
    operations: tuple[str, ...]
    warnings: tuple[PatchWarning, ...] = ()

    def loud_warnings(self) -> tuple[str, ...]:
        return tuple(f"{warning.severity.upper()}: {warning.message}" for warning in self.warnings)


@dataclass(frozen=True)
class PatchOperation:
    trust: AddressTrust = AddressTrust.VERIFIED


@dataclass(frozen=True)
class SetPartySpecies(PatchOperation):
    slot: int = 1
    species: int | str = 0
    rename_to_species: bool = True


@dataclass(frozen=True)
class RemovePartyMember(PatchOperation):
    slot: int | None = None
    species: int | str | None = None


@dataclass(frozen=True)
class SetPartyStats(PatchOperation):
    slot: int = 1
    level: int | None = None
    current_hp: int | None = None
    max_hp: int | None = None
    attack: int | None = None
    defense: int | None = None
    speed: int | None = None
    special: int | None = None
    status: int | str | None = None


@dataclass(frozen=True)
class SetPartyMoves(PatchOperation):
    slot: int = 1
    moves: tuple[int | str, ...] = ()
    pp: tuple[int, ...] | None = None


@dataclass(frozen=True)
class SetMapLocation(PatchOperation):
    map_id: int | str = 0
    x: int = 0
    y: int = 0
    allow_cross_map: bool = False


@dataclass(frozen=True)
class SetBadges(PatchOperation):
    badge_names: tuple[str, ...] | None = None
    badge_mask: int | None = None


@dataclass(frozen=True)
class SetMoney(PatchOperation):
    amount: int = 0


@dataclass(frozen=True)
class SetItemQuantity(PatchOperation):
    item: int | str = 0
    quantity: int = 0


@dataclass(frozen=True)
class RawMemoryWrite(PatchOperation):
    address: int = 0
    value: int = 0
    reason: str = ""
    trust: AddressTrust = AddressTrust.UNVERIFIED


@dataclass(frozen=True)
class StatePatch:
    description: str
    goal: str | None = None
    operations: tuple[PatchOperation, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
