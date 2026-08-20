from __future__ import annotations

from collections.abc import Sequence

from pokemon_player import memory_map as mm
from pokemon_player.state_model import (
    BattleEnemy,
    GameMode,
    GameSnapshot,
    InventoryItem,
    MapPosition,
    MoveSlot,
    PartyMember,
    StoryEvent,
)


class MemoryReader:
    """Small adapter around PyBoy's memory view for testable WRAM reads."""

    def __init__(self, memory: object) -> None:
        self._memory = memory

    def u8(self, address: int) -> int:
        return int(self._memory[address])

    def bytes(self, address: int, length: int) -> tuple[int, ...]:
        values = self._memory[address : address + length]
        return tuple(int(value) for value in values)

    def u16be(self, address: int) -> int:
        high, low = self.bytes(address, 2)
        return (high << 8) | low


def decode_bcd(bytes_: Sequence[int]) -> int:
    digits: list[str] = []
    for byte in bytes_:
        digits.append(str((byte >> 4) & 0x0F))
        digits.append(str(byte & 0x0F))
    return int("".join(digits))


GEN1_TEXT = {
    0x7F: " ",
    **{0x80 + i: chr(ord("A") + i) for i in range(26)},
    **{0xA0 + i: chr(ord("a") + i) for i in range(26)},
    **{0xF6 + i: str(i) for i in range(10)},
}


def decode_gen1_text(raw: Sequence[int]) -> str:
    chars: list[str] = []
    for byte in raw:
        if byte == 0x50:
            break
        chars.append(GEN1_TEXT.get(byte, ""))
    return "".join(chars).strip() or ""


class StateInspector:
    def __init__(self, memory: object) -> None:
        self.reader = MemoryReader(memory)

    def inspect(self, game_area: Sequence[Sequence[int]] | None = None) -> GameSnapshot:
        warnings: list[str] = []
        battle_type = self.reader.u8(mm.BATTLE_TYPE)
        text_box_id = self.reader.u8(mm.TEXT_BOX_ID)
        text_or_menu_active = self.reader.u8(mm.TEXT_OR_MENU_ACTIVE)
        screen_mode = classify_screen_mode(game_area)
        mode = self._read_mode(
            battle_type,
            text_box_id,
            text_or_menu_active,
            screen_mode,
            warnings,
        )

        party = self._read_party(warnings)

        return GameSnapshot(
            mode=mode,
            position=self._read_position(),
            party=party,
            inventory=self._read_inventory(warnings),
            money=self._read_money(warnings),
            badges=self.reader.u8(mm.BADGES),
            battle_type_raw=battle_type,
            active_party_slot=self._read_active_party_slot(battle_type, len(party), warnings),
            enemy=self._read_enemy() if battle_type else None,
            story_events=self._read_story_events(),
            warnings=tuple(warnings),
        )

    def _read_mode(
        self,
        battle_type: int,
        text_box_id: int,
        text_or_menu_active: int,
        screen_mode: GameMode | None,
        warnings: list[str],
    ) -> GameMode:
        if battle_type:
            return GameMode.BATTLE
        if text_box_id == 0x03:
            return GameMode.MENU
        if text_box_id == 0x02:
            return GameMode.DIALOGUE
        if screen_mode in {GameMode.MENU, GameMode.DIALOGUE}:
            return screen_mode
        if screen_mode == GameMode.OVERWORLD:
            if text_box_id or text_or_menu_active:
                warnings.append("Screen tiles indicate overworld despite stale text/menu WRAM flags.")
            return GameMode.OVERWORLD
        if text_box_id and game_area_was_provided(screen_mode):
            warnings.append(
                f"Text box id 0x{text_box_id:02X} is present but not classified yet."
            )
            return GameMode.MENU_OR_DIALOGUE_UNCERTAIN
        if text_or_menu_active:
            warnings.append(
                "Text/menu activity flag is nonzero, but no active text box id is present."
            )
        return GameMode.OVERWORLD

    def _read_position(self) -> MapPosition:
        return MapPosition(
            map_id=self.reader.u8(mm.CURRENT_MAP),
            y=self.reader.u8(mm.PLAYER_Y),
            x=self.reader.u8(mm.PLAYER_X),
        )

    def _read_party(self, warnings: list[str]) -> tuple[PartyMember, ...]:
        count = self.reader.u8(mm.PARTY_COUNT)
        if count > 6:
            warnings.append(f"Party count {count} is invalid; clamping to six slots.")
            count = 6

        party: list[PartyMember] = []
        for index in range(count):
            base = mm.PARTY_STRUCT_START + index * mm.PARTY_STRUCT_SIZE
            nickname_base = mm.PARTY_NICKNAME_START + index * mm.PARTY_NICKNAME_SIZE
            moves = tuple(
                MoveSlot(
                    move_id=self.reader.u8(base + getattr(mm.PARTY_SLOT, f"move_{move_index}")),
                    pp=self.reader.u8(base + getattr(mm.PARTY_SLOT, f"pp_{move_index}")),
                )
                for move_index in range(1, 5)
            )
            party.append(
                PartyMember(
                    slot=index + 1,
                    species_id=self.reader.u8(base + mm.PARTY_SLOT.species),
                    level=self.reader.u8(base + mm.PARTY_SLOT.level),
                    hp=self.reader.u16be(base + mm.PARTY_SLOT.hp),
                    max_hp=self.reader.u16be(base + mm.PARTY_SLOT.max_hp),
                    status=self.reader.u8(base + mm.PARTY_SLOT.status),
                    moves=moves,
                    nickname=decode_gen1_text(
                        self.reader.bytes(nickname_base, mm.PARTY_NICKNAME_SIZE)
                    ),
                )
            )
        return tuple(party)

    def _read_inventory(self, warnings: list[str]) -> tuple[InventoryItem, ...]:
        count = self.reader.u8(mm.ITEM_COUNT)
        if count > mm.MAX_ITEM_SLOTS:
            warnings.append(f"Inventory count {count} exceeds {mm.MAX_ITEM_SLOTS}; clamping.")
            count = mm.MAX_ITEM_SLOTS

        items: list[InventoryItem] = []
        for index in range(count):
            address = mm.ITEM_LIST_START + index * 2
            item_id = self.reader.u8(address)
            quantity = self.reader.u8(address + 1)
            if item_id in {0x00, 0xFF}:
                continue
            items.append(InventoryItem(item_id=item_id, quantity=quantity))
        return tuple(items)

    def _read_money(self, warnings: list[str]) -> int | None:
        raw = self.reader.bytes(mm.MONEY_START, 3)
        if any(((byte >> 4) > 9 or (byte & 0x0F) > 9) for byte in raw):
            warnings.append(f"Money bytes are not valid BCD: {raw!r}.")
            return None
        return decode_bcd(raw)

    def _read_enemy(self) -> BattleEnemy:
        return BattleEnemy(
            species_id=self.reader.u8(mm.ENEMY_BATTLE_SPECIES),
            hp=self.reader.u16be(mm.ENEMY_BATTLE_HP),
            level=self.reader.u8(mm.ENEMY_BATTLE_LEVEL),
            status=self.reader.u8(mm.ENEMY_BATTLE_STATUS),
            max_hp=self.reader.u16be(mm.ENEMY_BATTLE_MAX_HP),
            catch_rate=self.reader.u8(mm.ENEMY_BATTLE_CATCH_RATE),
        )

    def _read_active_party_slot(
        self,
        battle_type: int,
        party_count: int,
        warnings: list[str],
    ) -> int | None:
        if not battle_type:
            return None
        raw_index = self.reader.u8(mm.ACTIVE_PARTY_INDEX)
        if raw_index >= party_count:
            warnings.append(
                f"Active battle party index {raw_index} is outside party count {party_count}."
            )
            return None
        return raw_index + 1

    def _read_story_events(self) -> tuple[StoryEvent, ...]:
        events: list[StoryEvent] = []
        for spec in mm.STORY_EVENT_FLAGS.values():
            events.append(
                StoryEvent(
                    key=spec.key,
                    pret_name=spec.pret_name,
                    label=spec.label,
                    address=spec.address,
                    bit=spec.bit,
                    mask=spec.mask,
                    value=bool(self.reader.u8(spec.address) & spec.mask),
                    source=spec.source,
                )
            )
        return tuple(events)


def game_area_was_provided(screen_mode: GameMode | None) -> bool:
    return screen_mode is not None


def classify_screen_mode(game_area: Sequence[Sequence[int]] | None) -> GameMode | None:
    if game_area is None:
        return None

    rows = [list(row) for row in game_area]
    if not rows:
        return None

    if has_bottom_text_box(rows):
        return GameMode.DIALOGUE
    if has_upper_menu_box(rows):
        return GameMode.MENU
    return GameMode.OVERWORLD


def has_bottom_text_box(rows: list[list[int]]) -> bool:
    border_tiles = {377, 378, 379, 380, 381, 382}
    bottom_rows = rows[-4:]
    if not bottom_rows:
        return False

    border_count = sum(1 for row in bottom_rows for tile in row if tile in border_tiles)
    has_bottom_border = any(row.count(378) >= 8 for row in bottom_rows)
    has_vertical_sides = any(row and row[0] == 380 and row[-1] == 380 for row in bottom_rows)
    has_bottom_corners = any(row and row[0] == 381 and row[-1] == 382 for row in bottom_rows)
    return border_count >= 12 and has_bottom_border and (has_vertical_sides or has_bottom_corners)


def has_upper_menu_box(rows: list[list[int]]) -> bool:
    border_tiles = {377, 378, 379, 380, 381, 382}
    upper_rows = rows[: max(1, len(rows) // 2)]
    for row in upper_rows:
        if 377 in row and 379 in row and sum(1 for tile in row if tile in border_tiles) >= 4:
            return True
    return False
