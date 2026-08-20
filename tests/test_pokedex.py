from __future__ import annotations

from pokemon_player import memory_map as mm
from pokemon_player.pokedex import pokedex_flag, read_pokedex


class FakeMemory:
    def __init__(self, values: dict[int, int]) -> None:
        self.values = values

    def __getitem__(self, address: int) -> int:
        return self.values.get(address, 0)


def test_pokedex_flag_uses_lsb_first_dex_bit_order() -> None:
    flags = (0x01,) + (0x00,) * (mm.POKEDEX_FLAG_BYTES - 1)

    assert pokedex_flag(flags, 1)
    assert not pokedex_flag(flags, 8)


def test_read_pokedex_maps_pikachu_to_owned_dex_bit() -> None:
    memory = FakeMemory(
        {
            mm.POKEDEX_OWNED_START + 3: 0x01,
            mm.POKEDEX_SEEN_START + 3: 0x01,
        }
    )

    pokedex = read_pokedex(memory)

    assert pokedex["flag_bit_order"] == "least_significant_bit_first"
    assert pokedex["by_dex_number"]["25"]["species_name"] == "Pikachu"
    assert pokedex["by_dex_number"]["25"]["owned"]
    assert pokedex["by_dex_number"]["25"]["seen"]
    assert "Pikachu" in pokedex["owned_species"]
