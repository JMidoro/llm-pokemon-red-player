from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from pokemon_player.memory_map import BADGE_NAMES, item_name, map_name, move_name, species_name


class GameMode(StrEnum):
    UNKNOWN = "unknown"
    OVERWORLD = "overworld"
    BATTLE = "battle"
    MENU = "menu"
    DIALOGUE = "dialogue"
    MENU_OR_DIALOGUE_UNCERTAIN = "menu_or_dialogue_uncertain"


@dataclass(frozen=True)
class MapPosition:
    map_id: int
    x: int
    y: int

    @property
    def map_name(self) -> str:
        return map_name(self.map_id)


@dataclass(frozen=True)
class MoveSlot:
    move_id: int
    pp: int | None = None

    def summary(self) -> str:
        suffix = "" if self.pp is None else f" ({self.pp} PP)"
        return f"{move_name(self.move_id)}{suffix}"


@dataclass(frozen=True)
class PartyMember:
    slot: int
    species_id: int
    level: int
    hp: int
    max_hp: int
    status: int
    moves: tuple[MoveSlot, ...]
    nickname: str | None = None

    @property
    def species_name(self) -> str:
        return species_name(self.species_id)

    def summary(self) -> str:
        name = self.nickname or self.species_name
        status = "OK" if self.status == 0 else f"status 0x{self.status:02X}"
        moves = ", ".join(move.summary() for move in self.moves if move.move_id)
        moves_text = f"; moves: {moves}" if moves else ""
        return f"{self.slot}. {name} Lv{self.level} HP {self.hp}/{self.max_hp} {status}{moves_text}"


@dataclass(frozen=True)
class InventoryItem:
    item_id: int
    quantity: int

    @property
    def item_name(self) -> str:
        return item_name(self.item_id)

    def summary(self) -> str:
        return f"{self.item_name} x{self.quantity}"


@dataclass(frozen=True)
class BattleEnemy:
    species_id: int
    level: int
    hp: int
    max_hp: int
    status: int
    catch_rate: int | None = None

    @property
    def species_name(self) -> str:
        return species_name(self.species_id)

    def summary(self) -> str:
        status = "OK" if self.status == 0 else f"status 0x{self.status:02X}"
        catch_rate = "" if self.catch_rate is None else f"; catch rate {self.catch_rate}"
        return f"{self.species_name} Lv{self.level} HP {self.hp}/{self.max_hp} {status}{catch_rate}"


@dataclass(frozen=True)
class StoryEvent:
    key: str
    pret_name: str
    label: str
    address: int
    bit: int
    mask: int
    value: bool
    source: str

    def summary(self) -> str:
        state = "set" if self.value else "clear"
        return f"{self.label}: {state} ({self.pret_name} @ 0x{self.address:04X} bit {self.bit})"


@dataclass(frozen=True)
class GameSnapshot:
    mode: GameMode
    position: MapPosition | None
    party: tuple[PartyMember, ...]
    inventory: tuple[InventoryItem, ...]
    money: int | None
    badges: int | None
    battle_type_raw: int | None = None
    active_party_slot: int | None = None
    enemy: BattleEnemy | None = None
    story_events: tuple[StoryEvent, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def has_item(self, item_id: int) -> bool:
        return any(item.item_id == item_id and item.quantity > 0 for item in self.inventory)

    def badge_names(self) -> tuple[str, ...]:
        if self.badges is None:
            return ()
        return tuple(name for bit, name in enumerate(BADGE_NAMES) if self.badges & (1 << bit))

    def story_event_value(self, key: str) -> bool | None:
        for event in self.story_events:
            if event.key == key:
                return event.value
        return None

    def facts(self) -> tuple[str, ...]:
        facts: list[str] = []
        story_events = {event.key: event.value for event in self.story_events}
        if self.position and self.position.map_id == 0x33:
            facts.append("Player is in Viridian Forest.")
        if self.has_item(0x04):
            facts.append("Inventory contains Poke Balls.")
        else:
            facts.append("No Poke Balls detected in inventory.")
        if story_events.get("oak_got_parcel"):
            facts.append("Oak has received the Parcel.")
        elif story_events.get("got_oaks_parcel"):
            facts.append("Viridian Mart has given Oak's Parcel.")
        if story_events.get("got_pokedex"):
            facts.append("Pokedex has been received.")
        if self.badges is not None and self.badges & (1 << 1):
            facts.append("Cascade Badge is owned.")
        elif self.position and self.position.map_id in {0x03, 0x40, 0x41}:
            facts.append("Player is in the Cerulean area and Cascade Badge is not detected.")
        return tuple(facts)

    def plaintext_summary(self) -> str:
        lines: list[str] = [f"Mode: {self.mode.value}"]

        if self.position:
            lines.append(
                f"Location: {self.position.map_name} "
                f"(map 0x{self.position.map_id:02X}, x={self.position.x}, y={self.position.y})"
            )
        else:
            lines.append("Location: unknown")

        if self.party:
            lines.append("Party:")
            lines.extend(f"- {member.summary()}" for member in self.party)
        else:
            lines.append("Party: none detected")

        if self.inventory:
            essentials = ", ".join(item.summary() for item in self.inventory)
            lines.append(f"Inventory: {essentials}")
        else:
            lines.append("Inventory: none detected")

        if self.enemy:
            lines.append(f"Enemy: {self.enemy.summary()}")

        if self.active_party_slot is not None:
            active_member = next(
                (member for member in self.party if member.slot == self.active_party_slot),
                None,
            )
            active_name = active_member.species_name if active_member else f"slot {self.active_party_slot}"
            lines.append(f"Active battler: {active_name} (party slot {self.active_party_slot})")

        if self.money is not None:
            lines.append(f"Money: {self.money}")

        if self.badges is not None:
            badges = ", ".join(self.badge_names()) or "none"
            lines.append(f"Badges: {badges}")

        if self.story_events:
            set_events = [event.summary() for event in self.story_events if event.value]
            if set_events:
                lines.append("Story events:")
                lines.extend(f"- {event}" for event in set_events)

        facts = self.facts()
        if facts:
            lines.append("Goal-relevant facts:")
            lines.extend(f"- {fact}" for fact in facts)

        if self.warnings:
            lines.append("Uncertainty/warnings:")
            lines.extend(f"- {warning}" for warning in self.warnings)

        return "\n".join(lines)
