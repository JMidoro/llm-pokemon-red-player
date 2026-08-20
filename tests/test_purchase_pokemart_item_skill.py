from __future__ import annotations

from pathlib import Path

from pokemon_player.skills.purchase_pokemart_item import purchase_pokemart_item, screenshot_has_pokemart_buy_menu


ROOT = Path(__file__).resolve().parents[1]
BUY_MENU_SCREENSHOT = ROOT / "research" / "artifacts" / "manual-probes" / "shop_buy_probe" / "step_00.png"


def mart_snapshot(*, money: int = 3175, inventory: list[dict] | None = None) -> dict:
    return {
        "mode": "dialogue",
        "battle_type_raw": 0,
        "position": {"map_id": 0x2A, "map_name": "Viridian Mart", "x": 2, "y": 5},
        "money": money,
        "inventory": inventory or [],
        "warnings": [],
    }


def test_purchase_pokemart_item_enables_for_visible_buy_menu() -> None:
    assert screenshot_has_pokemart_buy_menu(BUY_MENU_SCREENSHOT)
    result = purchase_pokemart_item(
        mart_snapshot(),
        item="Poke Ball",
        quantity=5,
        screenshot_path=BUY_MENU_SCREENSHOT,
    )
    assert result.status == "succeeded"
    assert "requested quantity is 5" in result.summary


def test_purchase_pokemart_item_blocks_item_not_in_current_stock() -> None:
    result = purchase_pokemart_item(
        mart_snapshot(),
        item="Potion",
        quantity=1,
        screenshot_path=BUY_MENU_SCREENSHOT,
    )
    assert result.status == "blocked"
    assert "not sold" in result.summary


def test_purchase_pokemart_item_blocks_when_money_too_low() -> None:
    result = purchase_pokemart_item(
        mart_snapshot(money=100),
        item="Poke Ball",
        quantity=1,
        screenshot_path=BUY_MENU_SCREENSHOT,
    )
    assert result.status == "blocked"
    assert "Not enough money" in result.summary


def test_purchase_pokemart_item_classifies_after_quantity_delta() -> None:
    before = mart_snapshot(money=3175, inventory=[])
    after = mart_snapshot(money=2175, inventory=[{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 5}])
    result = purchase_pokemart_item(
        after,
        item="Poke Ball",
        quantity=5,
        before_snapshot=before,
        screenshot_path=BUY_MENU_SCREENSHOT,
    )
    assert result.status == "succeeded"
    assert "Purchased 5 Poke Ball" in result.summary
