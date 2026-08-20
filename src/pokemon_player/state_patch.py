from __future__ import annotations

from collections.abc import MutableSequence

from pokemon_player import memory_map as mm
from pokemon_player.catalog import resolve_item, resolve_map, resolve_move, resolve_species
from pokemon_player.patch_model import (
    AddressTrust,
    PatchOperation,
    PatchReport,
    PatchWarning,
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
from pokemon_player.state_inspector import MemoryReader, decode_gen1_text


STATUS_BY_NAME = {
    "ok": 0x00,
    "none": 0x00,
    "sleep": 0x04,
    "poison": 0x08,
    "burn": 0x10,
    "freeze": 0x20,
    "paralysis": 0x40,
    "paralyze": 0x40,
}


class PatchValidationError(ValueError):
    pass


class MemoryWriter:
    def __init__(self, memory: MutableSequence[int]) -> None:
        self.memory = memory

    def u8(self, address: int, value: int) -> None:
        if not 0 <= value <= 0xFF:
            raise PatchValidationError(f"Value {value} does not fit in one byte.")
        self.memory[address] = value

    def u16be(self, address: int, value: int) -> None:
        if not 0 <= value <= 0xFFFF:
            raise PatchValidationError(f"Value {value} does not fit in two bytes.")
        self.u8(address, (value >> 8) & 0xFF)
        self.u8(address + 1, value & 0xFF)

    def bytes(self, address: int, values: list[int]) -> None:
        for offset, value in enumerate(values):
            self.u8(address + offset, value)


class StatePatchApplier:
    def __init__(self, memory: MutableSequence[int]) -> None:
        self.reader = MemoryReader(memory)
        self.writer = MemoryWriter(memory)

    def apply(self, patch: StatePatch) -> PatchReport:
        warnings = self.validate(patch)
        operations: list[str] = []
        for operation in patch.operations:
            operations.append(self._apply_operation(operation))
        return PatchReport(applied=True, operations=tuple(operations), warnings=tuple(warnings))

    def validate(self, patch: StatePatch) -> list[PatchWarning]:
        if not patch.operations:
            raise PatchValidationError("Patch must contain at least one operation.")

        warnings: list[PatchWarning] = []
        for operation in patch.operations:
            if operation.trust == AddressTrust.UNVERIFIED:
                warnings.append(
                    PatchWarning(
                        "This patch includes unverified memory writes. Explain the source "
                        "of every address and verify the resulting state manually.",
                        "danger",
                    )
                )
            self._validate_operation(operation)
            if isinstance(operation, SetMapLocation):
                target_map = resolve_map(operation.map_id)
                current_map = self.reader.u8(mm.CURRENT_MAP)
                if target_map != current_map and operation.allow_cross_map:
                    warnings.append(
                        PatchWarning(
                            "Cross-map runtime edits only update visible WRAM fields, not the full "
                            "loaded map engine state. Prefer a template state already on the target map.",
                            "danger",
                        )
                    )
        return warnings

    def _validate_operation(self, operation: PatchOperation) -> None:
        if isinstance(operation, SetPartySpecies):
            require_slot(operation.slot)
            require_species(resolve_species(operation.species))
        elif isinstance(operation, RemovePartyMember):
            if operation.slot is None and operation.species is None:
                raise PatchValidationError("RemovePartyMember requires slot or species.")
            if operation.slot is not None:
                require_slot(operation.slot)
            if operation.species is not None:
                require_species(resolve_species(operation.species))
        elif isinstance(operation, SetPartyStats):
            require_slot(operation.slot)
            if operation.level is not None:
                require_range("level", operation.level, 1, 100)
            for field in ("current_hp", "max_hp", "attack", "defense", "speed", "special"):
                value = getattr(operation, field)
                if value is not None:
                    require_range(field, value, 0, 999)
            if operation.status is not None:
                resolve_status(operation.status)
            if operation.current_hp is not None:
                max_hp = operation.max_hp or self._party_u16(operation.slot, mm.PARTY_SLOT.max_hp)
                if operation.current_hp > max_hp:
                    raise PatchValidationError("current_hp cannot exceed max_hp.")
        elif isinstance(operation, SetPartyMoves):
            require_slot(operation.slot)
            if not 0 <= len(operation.moves) <= 4:
                raise PatchValidationError("A party member can have at most four moves.")
            for move in operation.moves:
                require_range("move_id", resolve_move(move), 0, 0xA5)
            if operation.pp is not None:
                if len(operation.pp) != len(operation.moves):
                    raise PatchValidationError("PP list must match move list length.")
                for pp in operation.pp:
                    require_range("pp", pp, 0, 99)
        elif isinstance(operation, SetMapLocation):
            target_map = resolve_map(operation.map_id)
            current_map = self.reader.u8(mm.CURRENT_MAP)
            if target_map != current_map and not operation.allow_cross_map:
                raise PatchValidationError(
                    "Cross-map runtime edits are not safe as a verified operation. "
                    f"Base the patch on a state already in {mm.map_name(target_map)}, "
                    "or set allow_cross_map=true and treat the result as unverified."
                )
            require_range("x", operation.x, 0, 255)
            require_range("y", operation.y, 0, 255)
        elif isinstance(operation, SetBadges):
            self._badge_mask(operation)
        elif isinstance(operation, SetMoney):
            require_range("money", operation.amount, 0, 999999)
        elif isinstance(operation, SetItemQuantity):
            require_item(resolve_item(operation.item))
            require_range("quantity", operation.quantity, 0, 99)
        elif isinstance(operation, RawMemoryWrite):
            require_range("address", operation.address, 0x0000, 0xFFFF)
            require_range("value", operation.value, 0, 0xFF)
            if not operation.reason:
                raise PatchValidationError("RawMemoryWrite requires a reason.")
        else:
            raise PatchValidationError(f"Unsupported operation {operation!r}.")

    def _apply_operation(self, operation: PatchOperation) -> str:
        if isinstance(operation, SetPartySpecies):
            species_id = resolve_species(operation.species)
            self._write_party_species(operation.slot, species_id)
            if operation.rename_to_species:
                self._write_party_nickname(operation.slot, mm.species_name(species_id))
            return f"set slot {operation.slot} species to {mm.species_name(species_id)}"
        if isinstance(operation, RemovePartyMember):
            slot = operation.slot or self._find_party_slot(resolve_species(operation.species))
            self._remove_party_slot(slot)
            return f"removed party slot {slot}"
        if isinstance(operation, SetPartyStats):
            self._write_party_stats(operation)
            return f"updated stats for party slot {operation.slot}"
        if isinstance(operation, SetPartyMoves):
            self._write_party_moves(operation)
            return f"updated moves for party slot {operation.slot}"
        if isinstance(operation, SetMapLocation):
            map_id = resolve_map(operation.map_id)
            self.writer.u8(mm.CURRENT_MAP, map_id)
            self.writer.u8(mm.PLAYER_X, operation.x)
            self.writer.u8(mm.PLAYER_Y, operation.y)
            return f"set location to {mm.map_name(map_id)} x={operation.x} y={operation.y}"
        if isinstance(operation, SetBadges):
            badge_mask = self._badge_mask(operation)
            self.writer.u8(mm.BADGES, badge_mask)
            names = ", ".join(badge_names_from_mask(badge_mask)) or "none"
            return f"set badges to {names}"
        if isinstance(operation, SetMoney):
            self._write_money(operation.amount)
            return f"set money to {operation.amount}"
        if isinstance(operation, SetItemQuantity):
            item_id = resolve_item(operation.item)
            self._write_item_quantity(item_id, operation.quantity)
            return f"set {mm.item_name(item_id)} quantity to {operation.quantity}"
        if isinstance(operation, RawMemoryWrite):
            self.writer.u8(operation.address, operation.value)
            return f"wrote 0x{operation.value:02X} to unverified address 0x{operation.address:04X}"
        raise PatchValidationError(f"Unsupported operation {operation!r}.")

    def _party_base(self, slot: int) -> int:
        return mm.PARTY_STRUCT_START + (slot - 1) * mm.PARTY_STRUCT_SIZE

    def _party_u16(self, slot: int, offset: int) -> int:
        return self.reader.u16be(self._party_base(slot) + offset)

    def _write_party_species(self, slot: int, species_id: int) -> None:
        count = self.reader.u8(mm.PARTY_COUNT)
        if slot > count:
            raise PatchValidationError(f"Party slot {slot} is outside current party count {count}.")
        self.writer.u8(mm.PARTY_SPECIES_LIST + slot - 1, species_id)
        self.writer.u8(self._party_base(slot) + mm.PARTY_SLOT.species, species_id)

    def _write_party_nickname(self, slot: int, nickname: str) -> None:
        base = mm.PARTY_NICKNAME_START + (slot - 1) * mm.PARTY_NICKNAME_SIZE
        self.writer.bytes(base, encode_gen1_text(nickname, mm.PARTY_NICKNAME_SIZE))

    def _find_party_slot(self, species_id: int) -> int:
        count = self.reader.u8(mm.PARTY_COUNT)
        for slot in range(1, count + 1):
            if self.reader.u8(self._party_base(slot) + mm.PARTY_SLOT.species) == species_id:
                return slot
        raise PatchValidationError(f"Species {mm.species_name(species_id)} is not in party.")

    def _remove_party_slot(self, slot: int) -> None:
        count = self.reader.u8(mm.PARTY_COUNT)
        if slot > count:
            raise PatchValidationError(f"Party slot {slot} is outside current party count {count}.")
        if count <= 1:
            raise PatchValidationError("Cannot remove the last party member.")

        for current in range(slot, count):
            next_slot = current + 1
            self.writer.u8(
                mm.PARTY_SPECIES_LIST + current - 1,
                self.reader.u8(mm.PARTY_SPECIES_LIST + next_slot - 1),
            )
            self.writer.bytes(
                self._party_base(current),
                list(self.reader.bytes(self._party_base(next_slot), mm.PARTY_STRUCT_SIZE)),
            )
            self.writer.bytes(
                mm.PARTY_NICKNAME_START + (current - 1) * mm.PARTY_NICKNAME_SIZE,
                list(
                    self.reader.bytes(
                        mm.PARTY_NICKNAME_START + (next_slot - 1) * mm.PARTY_NICKNAME_SIZE,
                        mm.PARTY_NICKNAME_SIZE,
                    )
                ),
            )

        self.writer.u8(mm.PARTY_COUNT, count - 1)
        self.writer.u8(mm.PARTY_SPECIES_LIST + count - 1, 0xFF)
        self.writer.bytes(self._party_base(count), [0] * mm.PARTY_STRUCT_SIZE)
        self.writer.bytes(
            mm.PARTY_NICKNAME_START + (count - 1) * mm.PARTY_NICKNAME_SIZE,
            [0x50] + [0] * (mm.PARTY_NICKNAME_SIZE - 1),
        )

    def _write_party_stats(self, operation: SetPartyStats) -> None:
        base = self._party_base(operation.slot)
        if operation.level is not None:
            self.writer.u8(base + mm.PARTY_SLOT.level, operation.level)
            self.writer.u8(base + mm.PARTY_SLOT.level_alias, operation.level)
        if operation.max_hp is not None:
            self.writer.u16be(base + mm.PARTY_SLOT.max_hp, operation.max_hp)
        if operation.current_hp is not None:
            self.writer.u16be(base + mm.PARTY_SLOT.hp, operation.current_hp)
        if operation.attack is not None:
            self.writer.u16be(base + mm.PARTY_SLOT.attack, operation.attack)
        if operation.defense is not None:
            self.writer.u16be(base + mm.PARTY_SLOT.defense, operation.defense)
        if operation.speed is not None:
            self.writer.u16be(base + mm.PARTY_SLOT.speed, operation.speed)
        if operation.special is not None:
            self.writer.u16be(base + mm.PARTY_SLOT.special, operation.special)
        if operation.status is not None:
            self.writer.u8(base + mm.PARTY_SLOT.status, resolve_status(operation.status))

    def _write_party_moves(self, operation: SetPartyMoves) -> None:
        base = self._party_base(operation.slot)
        moves = [resolve_move(move) for move in operation.moves]
        pp = list(operation.pp or ())
        for index in range(4):
            move_id = moves[index] if index < len(moves) else 0
            self.writer.u8(base + getattr(mm.PARTY_SLOT, f"move_{index + 1}"), move_id)
            if operation.pp is not None:
                value = pp[index] if index < len(pp) else 0
                self.writer.u8(base + getattr(mm.PARTY_SLOT, f"pp_{index + 1}"), value)

    def _write_money(self, amount: int) -> None:
        digits = f"{amount:06d}"
        self.writer.bytes(
            mm.MONEY_START,
            [int(digits[index : index + 2], 16) for index in range(0, 6, 2)],
        )

    def _write_item_quantity(self, item_id: int, quantity: int) -> None:
        count = self.reader.u8(mm.ITEM_COUNT)
        slots: list[tuple[int, int]] = []
        for index in range(min(count, mm.MAX_ITEM_SLOTS)):
            address = mm.ITEM_LIST_START + index * 2
            current_item = self.reader.u8(address)
            current_quantity = self.reader.u8(address + 1)
            if current_item not in {0x00, 0xFF}:
                slots.append((current_item, current_quantity))

        slots = [(item, qty) for item, qty in slots if item != item_id]
        if quantity > 0:
            slots.append((item_id, quantity))
        if len(slots) > mm.MAX_ITEM_SLOTS:
            raise PatchValidationError("Inventory would exceed max item slots.")

        self.writer.u8(mm.ITEM_COUNT, len(slots))
        for index in range(mm.MAX_ITEM_SLOTS):
            address = mm.ITEM_LIST_START + index * 2
            if index < len(slots):
                self.writer.u8(address, slots[index][0])
                self.writer.u8(address + 1, slots[index][1])
            else:
                self.writer.u8(address, 0xFF if index == len(slots) else 0)
                self.writer.u8(address + 1, 0)

    def _badge_mask(self, operation: SetBadges) -> int:
        if operation.badge_mask is not None and operation.badge_names is not None:
            raise PatchValidationError("SetBadges accepts badge_mask or badge_names, not both.")
        if operation.badge_mask is not None:
            require_range("badge_mask", operation.badge_mask, 0, 0xFF)
            return operation.badge_mask
        if operation.badge_names is None:
            raise PatchValidationError("SetBadges requires badge_mask or badge_names.")

        mask = 0
        for name in operation.badge_names:
            normalized = name.strip().lower()
            matches = [
                index
                for index, badge_name in enumerate(mm.BADGE_NAMES)
                if badge_name.lower() == normalized
            ]
            if not matches:
                raise PatchValidationError(f"Unknown badge name {name!r}.")
            mask |= 1 << matches[0]
        return mask


def require_slot(slot: int) -> None:
    require_range("slot", slot, 1, 6)


def require_species(species_id: int) -> None:
    require_range("species_id", species_id, 1, 0xBE)


def require_item(item_id: int) -> None:
    require_range("item_id", item_id, 1, 0xFA)


def require_range(name: str, value: int, lower: int, upper: int) -> None:
    if not lower <= value <= upper:
        raise PatchValidationError(f"{name} must be between {lower} and {upper}; got {value}.")


def resolve_status(value: int | str) -> int:
    if isinstance(value, int):
        require_range("status", value, 0, 0xFF)
        return value
    key = value.strip().lower()
    if key not in STATUS_BY_NAME:
        raise PatchValidationError(f"Unknown status {value!r}.")
    return STATUS_BY_NAME[key]


GEN1_TEXT_BY_CHAR = {
    " ": 0x7F,
    **{chr(ord("A") + index): 0x80 + index for index in range(26)},
    **{chr(ord("0") + index): 0xF6 + index for index in range(10)},
}


def encode_gen1_text(value: str, length: int) -> list[int]:
    encoded = [GEN1_TEXT_BY_CHAR.get(char, 0x7F) for char in value.upper()]
    encoded = encoded[: length - 1]
    encoded.append(0x50)
    encoded.extend([0] * (length - len(encoded)))
    return encoded


def decode_party_nickname(memory: MutableSequence[int], slot: int) -> str:
    reader = MemoryReader(memory)
    base = mm.PARTY_NICKNAME_START + (slot - 1) * mm.PARTY_NICKNAME_SIZE
    return decode_gen1_text(reader.bytes(base, mm.PARTY_NICKNAME_SIZE))


def badge_names_from_mask(mask: int) -> tuple[str, ...]:
    return tuple(name for index, name in enumerate(mm.BADGE_NAMES) if mask & (1 << index))
