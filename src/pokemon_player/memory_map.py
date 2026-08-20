from __future__ import annotations

from dataclasses import dataclass


PARTY_COUNT = 0xD163
PARTY_SPECIES_LIST = 0xD164
PARTY_STRUCT_START = 0xD16B
PARTY_STRUCT_SIZE = 44
PARTY_NICKNAME_START = 0xD2B5
PARTY_NICKNAME_SIZE = 11

ITEM_COUNT = 0xD31D
ITEM_LIST_START = 0xD31E
MAX_ITEM_SLOTS = 20

MONEY_START = 0xD347
BADGES = 0xD356

POKEDEX_OWNED_START = 0xD2F7
POKEDEX_SEEN_START = 0xD30A
POKEDEX_FLAG_BYTES = 19
POKEDEX_SPECIES_COUNT = 151

EVENT_FLAGS_START = 0xD747

BATTLE_TYPE = 0xD057
CURRENT_MAP = 0xD35E
PLAYER_Y = 0xD361
PLAYER_X = 0xD362
PLAYER_FACING = 0xD363
TEXT_BOX_ID = 0xFF8C
TEXT_OR_MENU_ACTIVE = 0xCC2D
CURRENT_MENU_ITEM = 0xCC26
ACTIVE_PARTY_INDEX = 0xCC2F

# Gen 1 naming screen cursor fields, promoted from local post-catch nickname
# captures. Values use odd column coordinates (1,3,...,17) and row values
# matching the keyboard rows.
NAMING_CURSOR_COLUMN = 0xCC25
NAMING_CURSOR_ROW = 0xCC2A
NAMING_SELECTED_TILE = 0xCC30

# In-battle opponent struct addresses, sourced from the local
# PokemonRedAndBlueRAMMap reference used by PokemonRedExperiments.
ENEMY_BATTLE_SPECIES = 0xCFE5
ENEMY_BATTLE_HP = 0xCFE6
ENEMY_BATTLE_LEVEL_ALIAS = 0xCFE8
ENEMY_BATTLE_LEVEL = 0xCFF3
ENEMY_BATTLE_STATUS = 0xCFE9
ENEMY_BATTLE_MAX_HP = 0xCFF4
ENEMY_BATTLE_CATCH_RATE = 0xD007


@dataclass(frozen=True)
class PartySlotLayout:
    species: int = 0
    hp: int = 1
    level_alias: int = 3
    status: int = 4
    type_1: int = 5
    type_2: int = 6
    move_1: int = 8
    move_2: int = 9
    move_3: int = 10
    move_4: int = 11
    pp_1: int = 29
    pp_2: int = 30
    pp_3: int = 31
    pp_4: int = 32
    level: int = 33
    max_hp: int = 34
    attack: int = 36
    defense: int = 38
    speed: int = 40
    special: int = 42


PARTY_SLOT = PartySlotLayout()


@dataclass(frozen=True)
class EventFlagSpec:
    key: str
    pret_name: str
    index: int
    address: int
    bit: int
    mask: int
    label: str
    source: str = "pret/pokered constants/event_constants.asm + wEventFlags"


def event_flag_spec(key: str, pret_name: str, index: int, label: str) -> EventFlagSpec:
    bit = index % 8
    return EventFlagSpec(
        key=key,
        pret_name=pret_name,
        index=index,
        address=EVENT_FLAGS_START + (index // 8),
        bit=bit,
        mask=1 << bit,
        label=label,
    )


STORY_EVENT_FLAGS = {
    "got_starter": event_flag_spec(
        "got_starter",
        "EVENT_GOT_STARTER",
        0x022,
        "Starter received",
    ),
    "battled_rival_in_oaks_lab": event_flag_spec(
        "battled_rival_in_oaks_lab",
        "EVENT_BATTLED_RIVAL_IN_OAKS_LAB",
        0x023,
        "First Oak's Lab rival battle resolved",
    ),
    "got_pokeballs_from_oak": event_flag_spec(
        "got_pokeballs_from_oak",
        "EVENT_GOT_POKEBALLS_FROM_OAK",
        0x024,
        "Oak gave Poke Balls",
    ),
    "got_pokedex": event_flag_spec(
        "got_pokedex",
        "EVENT_GOT_POKEDEX",
        0x025,
        "Pokedex received",
    ),
    "pallet_after_getting_pokeballs_2": event_flag_spec(
        "pallet_after_getting_pokeballs_2",
        "EVENT_PALLET_AFTER_GETTING_POKEBALLS_2",
        0x026,
        "Post-Pokedex Pallet flag",
    ),
    "oak_got_parcel": event_flag_spec(
        "oak_got_parcel",
        "EVENT_OAK_GOT_PARCEL",
        0x038,
        "Oak received parcel",
    ),
    "got_oaks_parcel": event_flag_spec(
        "got_oaks_parcel",
        "EVENT_GOT_OAKS_PARCEL",
        0x039,
        "Viridian Mart gave Oak's Parcel",
    ),
    "beat_brock": event_flag_spec(
        "beat_brock",
        "EVENT_BEAT_BROCK",
        0x077,
        "Brock defeated",
    ),
}


MAP_NAMES = {
    0x00: "Pallet Town",
    0x01: "Viridian City",
    0x02: "Pewter City",
    0x03: "Cerulean City",
    0x0C: "Route 1",
    0x0D: "Route 2",
    0x0E: "Route 3",
    0x0F: "Route 4",
    0x21: "Route 22",
    0x23: "Route 24",
    0x24: "Route 25",
    0x25: "Red's House 1F",
    0x26: "Red's House 2F",
    0x27: "Blue's House",
    0x28: "Oak's Lab",
    0x29: "Viridian PokeCenter",
    0x2A: "Viridian Mart",
    0x2F: "Viridian Forest North Gate",
    0x32: "Viridian Forest South Gate",
    0x33: "Viridian Forest",
    0x36: "Pewter Gym",
    0x38: "Pewter Mart",
    0x3A: "Pewter PokeCenter",
    0x3B: "Mt. Moon 1F",
    0x40: "Cerulean PokeCenter",
    0x41: "Cerulean Gym",
    0x43: "Cerulean Mart",
    0x44: "Mt. Moon PokeCenter",
}

SPECIES_NAMES = {
    0x03: "Nidoran M",
    0x05: "Spearow",
    0x22: "Onix",
    0x24: "Pidgey",
    0x54: "Pikachu",
    0x70: "Weedle",
    0x71: "Kakuna",
    0x7B: "Caterpie",
    0x7D: "Butterfree",
    0x0F: "Nidoran F",
    0x98: "Starmie",
    0x99: "Bulbasaur",
    0xA5: "Rattata",
    0xB0: "Charmander",
    0xB1: "Squirtle",
    0xB3: "Wartortle",
}

SPECIES_DEX_NUMBERS = {
    0x99: 1,  # Bulbasaur
    0xB0: 4,  # Charmander
    0xB1: 7,  # Squirtle
    0xB3: 8,  # Wartortle
    0x7B: 10,  # Caterpie
    0x7D: 12,  # Butterfree
    0x70: 13,  # Weedle
    0x71: 14,  # Kakuna
    0x24: 16,  # Pidgey
    0xA5: 19,  # Rattata
    0x05: 21,  # Spearow
    0x54: 25,  # Pikachu
    0x0F: 29,  # Nidoran F
    0x03: 32,  # Nidoran M
    0x22: 95,  # Onix
    0x98: 121,  # Starmie
}

DEX_NUMBER_TO_SPECIES_ID = {dex_number: species_id for species_id, dex_number in SPECIES_DEX_NUMBERS.items()}

ITEM_NAMES = {
    0x01: "Master Ball",
    0x02: "Ultra Ball",
    0x03: "Great Ball",
    0x04: "Poke Ball",
    0x05: "Town Map",
    0x0A: "Moon Stone",
    0x0B: "Antidote",
    0x14: "Potion",
    0x1D: "Escape Rope",
    0x21: "Super Potion",
    0x23: "HP Up",
    0x28: "Rare Candy",
    0x2A: "Helix Fossil",
    0x46: "Oak's Parcel",
    0xC9: "TM01",
    0xD3: "TM03",
    0xD4: "TM04",
    0xEA: "HM01",
}

MOVE_NAMES = {
    0x00: "No Move",
    0x0A: "Scratch",
    0x1E: "Horn Attack",
    0x21: "Tackle",
    0x27: "Tail Whip",
    0x28: "Poison Sting",
    0x2B: "Leer",
    0x2D: "Growl",
    0x37: "Water Gun",
    0x3F: "Hyper Beam",
    0x40: "Peck",
    0x51: "String Shot",
    0x54: "ThunderShock",
    0x56: "Thunder Wave",
    0x62: "Quick Attack",
    0x91: "Bubble",
}

BADGE_NAMES = [
    "Boulder Badge",
    "Cascade Badge",
    "Thunder Badge",
    "Rainbow Badge",
    "Soul Badge",
    "Marsh Badge",
    "Volcano Badge",
    "Earth Badge",
]


def map_name(map_id: int) -> str:
    return MAP_NAMES.get(map_id, f"Unknown map 0x{map_id:02X}")


def species_name(species_id: int) -> str:
    return SPECIES_NAMES.get(species_id, f"Species 0x{species_id:02X}")


def dex_number_for_species_id(species_id: int) -> int | None:
    return SPECIES_DEX_NUMBERS.get(species_id)


def item_name(item_id: int) -> str:
    return ITEM_NAMES.get(item_id, f"Item 0x{item_id:02X}")


def move_name(move_id: int) -> str:
    return MOVE_NAMES.get(move_id, f"Move 0x{move_id:02X}")
