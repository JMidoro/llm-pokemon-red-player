import unittest

import _path  # noqa: F401

from pokemon_player.state_inspector import (
    StateInspector,
    classify_screen_mode,
    decode_bcd,
    decode_gen1_text,
)
from pokemon_player.state_model import GameMode, GameSnapshot, InventoryItem, MapPosition


class FakeMemory:
    def __init__(self, values: dict[int, int]) -> None:
        self.values = values

    def __getitem__(self, key):
        if isinstance(key, slice):
            return [self.values.get(address, 0) for address in range(key.start, key.stop)]
        return self.values.get(key, 0)


class StateSummaryTests(unittest.TestCase):
    def test_decode_bcd_money(self) -> None:
        self.assertEqual(decode_bcd([0x12, 0x34, 0x56]), 123456)

    def test_decode_gen1_text(self) -> None:
        self.assertEqual(
            decode_gen1_text([0x8F, 0x88, 0x8A, 0x80, 0x82, 0x87, 0x94, 0x50]),
            "PIKACHU",
        )

    def test_summary_mentions_capsule_relevant_facts(self) -> None:
        snapshot = GameSnapshot(
            mode=GameMode.OVERWORLD,
            position=MapPosition(map_id=0x33, x=4, y=7),
            party=(),
            inventory=(InventoryItem(item_id=0x04, quantity=5),),
            money=3000,
            badges=0,
        )

        summary = snapshot.plaintext_summary()

        self.assertIn("Viridian Forest", summary)
        self.assertIn("Poke Ball x5", summary)
        self.assertIn("Player is in Viridian Forest.", summary)

    def test_inspector_reads_core_wram_fields(self) -> None:
        memory = FakeMemory(
            {
                0xD057: 0,
                0xD163: 1,
                0xD16B: 0x54,
                0xD16C: 0x00,
                0xD16D: 0x12,
                0xD16F: 0,
                0xD173: 0x21,
                0xD188: 35,
                0xD18C: 5,
                0xD18D: 0x00,
                0xD18E: 0x14,
                0xD2B5: 0x8F,
                0xD2B6: 0x88,
                0xD2B7: 0x8A,
                0xD2B8: 0x80,
                0xD2B9: 0x82,
                0xD2BA: 0x87,
                0xD2BB: 0x94,
                0xD2BC: 0x50,
                0xD31D: 1,
                0xD31E: 0x04,
                0xD31F: 5,
                0xD347: 0x00,
                0xD348: 0x30,
                0xD349: 0x00,
                0xD356: 0,
                0xD35E: 0x33,
                0xD361: 7,
                0xD362: 4,
            }
        )

        snapshot = StateInspector(memory).inspect()

        self.assertIsNotNone(snapshot.position)
        self.assertEqual(snapshot.position.map_name, "Viridian Forest")
        self.assertEqual(snapshot.party[0].species_name, "Pikachu")
        self.assertEqual(snapshot.party[0].hp, 18)
        self.assertEqual(snapshot.party[0].max_hp, 20)
        self.assertEqual(snapshot.inventory[0].item_name, "Poke Ball")
        self.assertEqual(snapshot.money, 3000)

    def test_inspector_reads_promoted_story_event_flags(self) -> None:
        memory = FakeMemory(
            {
                0xD057: 0,
                0xD163: 0,
                0xD31D: 0,
                0xD347: 0x00,
                0xD348: 0x30,
                0xD349: 0x00,
                0xD356: 0,
                0xD35E: 0x00,
                0xD361: 7,
                0xD362: 4,
                0xD74B: 0xAF,
                0xD74E: 0x03,
            }
        )

        snapshot = StateInspector(memory).inspect()
        events = {event.key: event for event in snapshot.story_events}

        self.assertTrue(events["got_starter"].value)
        self.assertTrue(events["battled_rival_in_oaks_lab"].value)
        self.assertTrue(events["got_pokedex"].value)
        self.assertTrue(events["oak_got_parcel"].value)
        self.assertTrue(events["got_oaks_parcel"].value)
        self.assertEqual(events["oak_got_parcel"].address, 0xD74E)
        self.assertEqual(events["oak_got_parcel"].bit, 0)
        self.assertIn("Oak has received the Parcel.", snapshot.facts())

    def test_inspector_reads_enemy_battle_fields(self) -> None:
        memory = FakeMemory(
            {
                0xD057: 1,
                0xCC2F: 0,
                0xCFE5: 0x70,
                0xCFE6: 0x00,
                0xCFE7: 0x0D,
                0xCFE8: 0,
                0xCFE9: 0,
                0xCFF3: 3,
                0xCFF4: 0x00,
                0xCFF5: 0x0D,
                0xD007: 255,
                0xD163: 0,
                0xD31D: 0,
                0xD347: 0x00,
                0xD348: 0x30,
                0xD349: 0x00,
                0xD356: 0,
                0xD35E: 0x33,
                0xD361: 7,
                0xD362: 4,
            }
        )

        snapshot = StateInspector(memory).inspect()

        self.assertIsNotNone(snapshot.enemy)
        self.assertEqual(snapshot.enemy.species_name, "Weedle")
        self.assertEqual(snapshot.enemy.level, 3)
        self.assertEqual(snapshot.enemy.hp, 13)
        self.assertEqual(snapshot.enemy.max_hp, 13)
        self.assertEqual(snapshot.enemy.catch_rate, 255)
        self.assertIn("Enemy: Weedle Lv3 HP 13/13", snapshot.plaintext_summary())

    def test_inspector_reads_active_battle_party_slot(self) -> None:
        memory = FakeMemory(
            {
                0xD057: 1,
                0xCC2F: 1,
                0xD163: 2,
                0xD16B: 0x05,
                0xD16C: 0x00,
                0xD16D: 0x0F,
                0xD18C: 3,
                0xD197: 0xB1,
                0xD198: 0x00,
                0xD199: 0x1D,
                0xD1B8: 8,
                0xCFE5: 0x70,
                0xCFE6: 0x00,
                0xCFE7: 0x0D,
                0xCFE9: 0,
                0xCFF3: 3,
                0xCFF4: 0x00,
                0xCFF5: 0x0D,
                0xD007: 255,
                0xD31D: 0,
                0xD347: 0x00,
                0xD348: 0x30,
                0xD349: 0x00,
                0xD356: 0,
                0xD35E: 0x33,
                0xD361: 7,
                0xD362: 4,
            }
        )

        snapshot = StateInspector(memory).inspect()

        self.assertEqual(snapshot.active_party_slot, 2)
        self.assertEqual(snapshot.party[1].species_name, "Squirtle")
        self.assertIn("Active battler: Squirtle (party slot 2)", snapshot.plaintext_summary())

    def test_inspector_distinguishes_menu_from_overworld(self) -> None:
        memory = FakeMemory(
            {
                0xCC2D: 2,
                0xD057: 0,
                0xD163: 0,
                0xD31D: 0,
                0xD347: 0x00,
                0xD348: 0x00,
                0xD349: 0x00,
                0xD356: 0,
                0xD35E: 0x0D,
                0xD361: 7,
                0xD362: 1,
                0xFF8C: 0x03,
            }
        )

        self.assertEqual(StateInspector(memory).inspect().mode, GameMode.MENU)

    def test_inspector_distinguishes_dialogue_from_overworld(self) -> None:
        memory = FakeMemory(
            {
                0xCC2D: 2,
                0xD057: 0,
                0xD163: 0,
                0xD31D: 0,
                0xD347: 0x00,
                0xD348: 0x00,
                0xD349: 0x00,
                0xD356: 0,
                0xD35E: 0x02,
                0xD361: 7,
                0xD362: 1,
                0xFF8C: 0x02,
            }
        )

        self.assertEqual(StateInspector(memory).inspect().mode, GameMode.DIALOGUE)

    def test_inspector_keeps_stale_text_activity_as_overworld_warning(self) -> None:
        memory = FakeMemory(
            {
                0xCC2D: 2,
                0xD057: 0,
                0xD163: 0,
                0xD31D: 0,
                0xD347: 0x00,
                0xD348: 0x00,
                0xD349: 0x00,
                0xD356: 0,
                0xD35E: 0x02,
                0xD361: 7,
                0xD362: 1,
                0xFF8C: 0x00,
            }
        )

        snapshot = StateInspector(memory).inspect()

        self.assertEqual(snapshot.mode, GameMode.OVERWORLD)
        self.assertTrue(snapshot.warnings)

    def test_classify_screen_mode_dialogue_box(self) -> None:
        rows = [[256] * 20 for _ in range(18)]
        rows[-4] = [380] + [150] * 18 + [380]
        rows[-3] = [380] + [383] * 18 + [380]
        rows[-2] = [380] + [182] * 18 + [380]
        rows[-1] = [381] + [378] * 18 + [382]

        self.assertEqual(classify_screen_mode(rows), GameMode.DIALOGUE)

    def test_classify_screen_mode_upper_menu_box(self) -> None:
        rows = [[256] * 20 for _ in range(18)]
        rows[0] = [256] * 10 + [377] + [378] * 8 + [379]
        rows[1] = [256] * 10 + [380] + [383] * 8 + [380]

        self.assertEqual(classify_screen_mode(rows), GameMode.MENU)
