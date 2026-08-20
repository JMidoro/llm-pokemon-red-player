from __future__ import annotations

from typing import Any

from pokemon_player import memory_map as mm


POKEDEX_FLAG_BIT_ORDER = "least_significant_bit_first"


def read_pokedex(memory: object) -> dict[str, Any]:
    owned = read_flag_bytes(memory, mm.POKEDEX_OWNED_START)
    seen = read_flag_bytes(memory, mm.POKEDEX_SEEN_START)
    known_entries: dict[str, dict[str, Any]] = {}

    for dex_number, species_id in sorted(mm.DEX_NUMBER_TO_SPECIES_ID.items()):
        name = mm.species_name(species_id)
        known_entries[str(dex_number)] = {
            "dex_number": dex_number,
            "species_id": species_id,
            "species_name": name,
            "owned": pokedex_flag(owned, dex_number),
            "seen": pokedex_flag(seen, dex_number),
        }

    return {
        "owned_bytes_hex": bytes_to_hex(owned),
        "seen_bytes_hex": bytes_to_hex(seen),
        "flag_bit_order": POKEDEX_FLAG_BIT_ORDER,
        "owned_dex_numbers": [
            dex_number for dex_number in range(1, mm.POKEDEX_SPECIES_COUNT + 1) if pokedex_flag(owned, dex_number)
        ],
        "seen_dex_numbers": [
            dex_number for dex_number in range(1, mm.POKEDEX_SPECIES_COUNT + 1) if pokedex_flag(seen, dex_number)
        ],
        "owned_species": [
            entry["species_name"] for entry in known_entries.values() if entry["owned"]
        ],
        "seen_species": [
            entry["species_name"] for entry in known_entries.values() if entry["seen"]
        ],
        "by_dex_number": known_entries,
    }


def read_flag_bytes(memory: object, start_address: int) -> tuple[int, ...]:
    return tuple(int(memory[address]) for address in range(start_address, start_address + mm.POKEDEX_FLAG_BYTES))


def pokedex_flag(flag_bytes: tuple[int, ...], dex_number: int) -> bool:
    if dex_number < 1 or dex_number > mm.POKEDEX_SPECIES_COUNT:
        raise ValueError(f"Pokedex number must be 1-{mm.POKEDEX_SPECIES_COUNT}; got {dex_number}.")
    bit_index = dex_number - 1
    byte_index = bit_index // 8
    bit_in_byte = bit_index % 8
    return bool(flag_bytes[byte_index] & (1 << bit_in_byte))


def bytes_to_hex(values: tuple[int, ...]) -> str:
    return " ".join(f"{value:02X}" for value in values)
