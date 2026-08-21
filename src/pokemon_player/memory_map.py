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
OPTIONS = 0xD355
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
    0x04: "Lavender Town",
    0x05: "Vermilion City",
    0x06: "Celadon City",
    0x07: "Fuchsia City",
    0x08: "Cinnabar Island",
    0x09: "Indigo Plateau",
    0x0A: "Saffron City",
    0x0C: "Route 1",
    0x0D: "Route 2",
    0x0E: "Route 3",
    0x0F: "Route 4",
    0x10: "Route 5",
    0x11: "Route 6",
    0x12: "Route 7",
    0x13: "Route 8",
    0x14: "Route 9",
    0x15: "Route 10",
    0x16: "Route 11",
    0x17: "Route 12",
    0x18: "Route 13",
    0x19: "Route 14",
    0x1A: "Route 15",
    0x1B: "Route 16",
    0x1C: "Route 17",
    0x1D: "Route 18",
    0x1E: "Route 19",
    0x1F: "Route 20",
    0x20: "Route 21",
    0x21: "Route 22",
    0x22: "Route 23",
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
    0x3C: "Mt. Moon B1F",
    0x3D: "Mt. Moon B2F",
    0x40: "Cerulean PokeCenter",
    0x41: "Cerulean Gym",
    0x43: "Cerulean Mart",
    0x44: "Mt. Moon PokeCenter",
    0x52: "Rock Tunnel 1F",
    0x53: "Power Plant",
    0x6C: "Victory Road 1F",
    0x8E: "Pokemon Tower 1F",
    0x8F: "Pokemon Tower 2F",
    0x90: "Pokemon Tower 3F",
    0x91: "Pokemon Tower 4F",
    0x92: "Pokemon Tower 5F",
    0x93: "Pokemon Tower 6F",
    0x94: "Pokemon Tower 7F",
    0x9F: "Seafoam Islands B1F",
    0xA0: "Seafoam Islands B2F",
    0xA1: "Seafoam Islands B3F",
    0xA2: "Seafoam Islands B4F",
    0xA5: "Pokemon Mansion 1F",
    0xC0: "Seafoam Islands 1F",
    0xC2: "Victory Road 2F",
    0xC5: "Diglett's Cave",
    0xC6: "Victory Road 3F",
    0xD6: "Pokemon Mansion 2F",
    0xD7: "Pokemon Mansion 3F",
    0xD8: "Pokemon Mansion B1F",
    0xD9: "Safari Zone East",
    0xDA: "Safari Zone North",
    0xDB: "Safari Zone West",
    0xDC: "Safari Zone Center",
    0xE2: "Cerulean Cave 2F",
    0xE3: "Cerulean Cave B1F",
    0xE4: "Cerulean Cave 1F",
    0xE8: "Rock Tunnel B1F",
}

# Complete non-glitch Gen 1 internal-index mapping. Pokemon Red does not store party
# species in National Pokedex order, so lineage rules must translate through this table.
# Source: pret/pokered constants/pokemon_constants.asm and data/pokemon/dex_order.asm.
SPECIES_DATA = {
    0x01: ("Rhydon", 112), 0x02: ("Kangaskhan", 115), 0x03: ("Nidoran M", 32),
    0x04: ("Clefairy", 35), 0x05: ("Spearow", 21), 0x06: ("Voltorb", 100),
    0x07: ("Nidoking", 34), 0x08: ("Slowbro", 80), 0x09: ("Ivysaur", 2),
    0x0A: ("Exeggutor", 103), 0x0B: ("Lickitung", 108), 0x0C: ("Exeggcute", 102),
    0x0D: ("Grimer", 88), 0x0E: ("Gengar", 94), 0x0F: ("Nidoran F", 29),
    0x10: ("Nidoqueen", 31), 0x11: ("Cubone", 104), 0x12: ("Rhyhorn", 111),
    0x13: ("Lapras", 131), 0x14: ("Arcanine", 59), 0x15: ("Mew", 151),
    0x16: ("Gyarados", 130), 0x17: ("Shellder", 90), 0x18: ("Tentacool", 72),
    0x19: ("Gastly", 92), 0x1A: ("Scyther", 123), 0x1B: ("Staryu", 120),
    0x1C: ("Blastoise", 9), 0x1D: ("Pinsir", 127), 0x1E: ("Tangela", 114),
    0x21: ("Growlithe", 58), 0x22: ("Onix", 95), 0x23: ("Fearow", 22),
    0x24: ("Pidgey", 16), 0x25: ("Slowpoke", 79), 0x26: ("Kadabra", 64),
    0x27: ("Graveler", 75), 0x28: ("Chansey", 113), 0x29: ("Machoke", 67),
    0x2A: ("Mr. Mime", 122), 0x2B: ("Hitmonlee", 106), 0x2C: ("Hitmonchan", 107),
    0x2D: ("Arbok", 24), 0x2E: ("Parasect", 47), 0x2F: ("Psyduck", 54),
    0x30: ("Drowzee", 96), 0x31: ("Golem", 76), 0x33: ("Magmar", 126),
    0x35: ("Electabuzz", 125), 0x36: ("Magneton", 82), 0x37: ("Koffing", 109),
    0x39: ("Mankey", 56), 0x3A: ("Seel", 86), 0x3B: ("Diglett", 50),
    0x3C: ("Tauros", 128), 0x40: ("Farfetch'd", 83), 0x41: ("Venonat", 48),
    0x42: ("Dragonite", 149), 0x46: ("Doduo", 84), 0x47: ("Poliwag", 60),
    0x48: ("Jynx", 124), 0x49: ("Moltres", 146), 0x4A: ("Articuno", 144),
    0x4B: ("Zapdos", 145), 0x4C: ("Ditto", 132), 0x4D: ("Meowth", 52),
    0x4E: ("Krabby", 98), 0x52: ("Vulpix", 37), 0x53: ("Ninetales", 38),
    0x54: ("Pikachu", 25), 0x55: ("Raichu", 26), 0x58: ("Dratini", 147),
    0x59: ("Dragonair", 148), 0x5A: ("Kabuto", 140), 0x5B: ("Kabutops", 141),
    0x5C: ("Horsea", 116), 0x5D: ("Seadra", 117), 0x60: ("Sandshrew", 27),
    0x61: ("Sandslash", 28), 0x62: ("Omanyte", 138), 0x63: ("Omastar", 139),
    0x64: ("Jigglypuff", 39), 0x65: ("Wigglytuff", 40), 0x66: ("Eevee", 133),
    0x67: ("Flareon", 136), 0x68: ("Jolteon", 135), 0x69: ("Vaporeon", 134),
    0x6A: ("Machop", 66), 0x6B: ("Zubat", 41), 0x6C: ("Ekans", 23),
    0x6D: ("Paras", 46), 0x6E: ("Poliwhirl", 61), 0x6F: ("Poliwrath", 62),
    0x70: ("Weedle", 13), 0x71: ("Kakuna", 14), 0x72: ("Beedrill", 15),
    0x74: ("Dodrio", 85), 0x75: ("Primeape", 57), 0x76: ("Dugtrio", 51),
    0x77: ("Venomoth", 49), 0x78: ("Dewgong", 87), 0x7B: ("Caterpie", 10),
    0x7C: ("Metapod", 11), 0x7D: ("Butterfree", 12), 0x7E: ("Machamp", 68),
    0x80: ("Golduck", 55), 0x81: ("Hypno", 97), 0x82: ("Golbat", 42),
    0x83: ("Mewtwo", 150), 0x84: ("Snorlax", 143), 0x85: ("Magikarp", 129),
    0x88: ("Muk", 89), 0x8A: ("Kingler", 99), 0x8B: ("Cloyster", 91),
    0x8D: ("Electrode", 101), 0x8E: ("Clefable", 36), 0x8F: ("Weezing", 110),
    0x90: ("Persian", 53), 0x91: ("Marowak", 105), 0x93: ("Haunter", 93),
    0x94: ("Abra", 63), 0x95: ("Alakazam", 65), 0x96: ("Pidgeotto", 17),
    0x97: ("Pidgeot", 18), 0x98: ("Starmie", 121), 0x99: ("Bulbasaur", 1),
    0x9A: ("Venusaur", 3), 0x9B: ("Tentacruel", 73), 0x9D: ("Goldeen", 118),
    0x9E: ("Seaking", 119), 0xA3: ("Ponyta", 77), 0xA4: ("Rapidash", 78),
    0xA5: ("Rattata", 19), 0xA6: ("Raticate", 20), 0xA7: ("Nidorino", 33),
    0xA8: ("Nidorina", 30), 0xA9: ("Geodude", 74), 0xAA: ("Porygon", 137),
    0xAB: ("Aerodactyl", 142), 0xAD: ("Magnemite", 81), 0xB0: ("Charmander", 4),
    0xB1: ("Squirtle", 7), 0xB2: ("Charmeleon", 5), 0xB3: ("Wartortle", 8),
    0xB4: ("Charizard", 6), 0xB9: ("Oddish", 43), 0xBA: ("Gloom", 44),
    0xBB: ("Vileplume", 45), 0xBC: ("Bellsprout", 69), 0xBD: ("Weepinbell", 70),
    0xBE: ("Victreebel", 71),
}

SPECIES_NAMES = {species_id: value[0] for species_id, value in SPECIES_DATA.items()}
SPECIES_DEX_NUMBERS = {species_id: value[1] for species_id, value in SPECIES_DATA.items()}

# Numeric capsule-target arguments historically treated these promoted RAM ids as internal ids.
# Keep that API compatibility even though the general lineage mapping is now complete.
PROMOTED_SPECIES_IDS = frozenset(
    {0x03, 0x05, 0x0F, 0x22, 0x24, 0x54, 0x70, 0x71, 0x7B, 0x7D, 0x98, 0x99, 0xA5, 0xB0, 0xB1, 0xB3}
)

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
