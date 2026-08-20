from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from pokemon_player.battle_ui import dark_ratio
from pokemon_player.skill_result import SkillResult


SKILL_ID = "purchase_pokemart_item"


@dataclass(frozen=True)
class MartStockItem:
    item_id: int
    name: str
    price: int


MART_STOCK: dict[int, tuple[MartStockItem, ...]] = {
    0x2A: (
        MartStockItem(0x04, "Poke Ball", 200),
        MartStockItem(0x0B, "Antidote", 100),
        MartStockItem(0x0E, "Parlyz Heal", 200),
        MartStockItem(0x0F, "Burn Heal", 250),
    ),
    0x38: (
        MartStockItem(0x04, "Poke Ball", 200),
        MartStockItem(0x14, "Potion", 300),
        MartStockItem(0x1D, "Escape Rope", 550),
        MartStockItem(0x0B, "Antidote", 100),
        MartStockItem(0x0F, "Burn Heal", 250),
        MartStockItem(0x0E, "Parlyz Heal", 200),
    ),
    0x43: (
        MartStockItem(0x04, "Poke Ball", 200),
        MartStockItem(0x14, "Potion", 300),
        MartStockItem(0x15, "Repel", 350),
        MartStockItem(0x0B, "Antidote", 100),
        MartStockItem(0x0F, "Burn Heal", 250),
        MartStockItem(0x0E, "Parlyz Heal", 200),
    ),
}


ITEM_ALIASES = {
    "poke ball": "Poke Ball",
    "pokeball": "Poke Ball",
    "pokeballs": "Poke Ball",
    "poke balls": "Poke Ball",
    "potion": "Potion",
    "potions": "Potion",
    "antidote": "Antidote",
    "antidotes": "Antidote",
    "parlyz heal": "Parlyz Heal",
    "paralyze heal": "Parlyz Heal",
    "paralysis heal": "Parlyz Heal",
    "burn heal": "Burn Heal",
    "escape rope": "Escape Rope",
    "repel": "Repel",
}


def purchase_pokemart_item(
    snapshot: Mapping[str, Any],
    *,
    item: str = "Poke Ball",
    quantity: int = 1,
    before_snapshot: Mapping[str, Any] | None = None,
    screenshot_path: str | Path | None = None,
) -> SkillResult:
    requested_quantity = max(int(quantity or 1), 1)
    position = snapshot.get("position") if isinstance(snapshot.get("position"), Mapping) else {}
    map_id = int(position.get("map_id", -1) if isinstance(position.get("map_id", -1), int) else -1)
    mode = str(snapshot.get("mode", "unknown"))
    battle_type_raw = snapshot.get("battle_type_raw")
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))
    stock = MART_STOCK.get(map_id, ())
    normalized_item = normalize_shop_item(item)
    stock_item = stock_item_by_name(stock, normalized_item)
    money = int(snapshot.get("money", 0) or 0)
    buy_menu_visible = screenshot_has_pokemart_buy_menu(screenshot_path)
    current_count = inventory_count(snapshot, normalized_item)
    evidence = (
        f"mode={mode}",
        f"battle_type_raw={battle_type_raw}",
        f"map_id=0x{map_id:02X}",
        f"item={normalized_item}",
        f"quantity={requested_quantity}",
        f"money={money}",
        f"buy_menu_visible={buy_menu_visible}",
        "stock=" + ",".join(item.name for item in stock),
        f"inventory_count={current_count}",
    )

    if battle_type_raw not in {None, 0} or mode == "battle":
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Poke Mart purchases are unavailable during battle.",
            evidence=evidence,
            warnings=warnings,
        )
    if not stock:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="The current map is not a supported Poke Mart.",
            evidence=evidence,
            warnings=warnings,
        )
    if stock_item is None:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=f"{normalized_item} is not sold by the current Poke Mart.",
            evidence=evidence,
            warnings=warnings,
        )
    if before_snapshot is not None:
        before_count = inventory_count(before_snapshot, normalized_item)
        before_money = int(before_snapshot.get("money", 0) or 0)
        bought = max(current_count - before_count, 0)
        evidence = evidence + (
            f"before_inventory_count={before_count}",
            f"before_money={before_money}",
            f"bought_quantity={bought}",
        )
        if bought >= min(requested_quantity, affordable_quantity(before_money, stock_item.price, requested_quantity)):
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary=f"Purchased {bought} {normalized_item}.",
                evidence=evidence,
                warnings=warnings,
            )
        if before_money < stock_item.price:
            return SkillResult(
                skill_id=SKILL_ID,
                status="blocked",
                summary=f"Not enough money to buy {normalized_item}.",
                evidence=evidence,
                warnings=warnings,
            )
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary=f"Purchase did not clearly add the requested {normalized_item}.",
            evidence=evidence,
            warnings=warnings,
        )

    if not buy_menu_visible:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Open the Poke Mart BUY item list before using this purchase skill.",
            evidence=evidence,
            warnings=warnings,
        )
    if money < stock_item.price:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=f"Not enough money to buy {normalized_item}.",
            evidence=evidence,
            warnings=warnings,
        )
    return SkillResult(
        skill_id=SKILL_ID,
        status="succeeded",
        summary=f"Poke Mart can sell {normalized_item}; requested quantity is {requested_quantity}.",
        evidence=evidence,
        warnings=warnings,
    )


def normalize_shop_item(item: str | Any) -> str:
    text = str(item or "Poke Ball").strip()
    if not text:
        return "Poke Ball"
    return ITEM_ALIASES.get(text.lower(), text)


def stock_for_snapshot(snapshot: Mapping[str, Any]) -> tuple[MartStockItem, ...]:
    position = snapshot.get("position") if isinstance(snapshot.get("position"), Mapping) else {}
    map_id = position.get("map_id", -1)
    return MART_STOCK.get(int(map_id) if isinstance(map_id, int) else -1, ())


def stock_item_by_name(stock: tuple[MartStockItem, ...], name: str) -> MartStockItem | None:
    target = name.strip().lower()
    for item in stock:
        if item.name.lower() == target:
            return item
    return None


def stock_index(stock: tuple[MartStockItem, ...], name: str) -> int | None:
    target = name.strip().lower()
    for index, item in enumerate(stock):
        if item.name.lower() == target:
            return index
    return None


def inventory_count(snapshot: Mapping[str, Any], item_name: str) -> int:
    inventory = snapshot.get("inventory")
    if not isinstance(inventory, list):
        return 0
    target = item_name.strip().lower()
    for item in inventory:
        if isinstance(item, Mapping) and str(item.get("item_name", "")).strip().lower() == target:
            return int(item.get("quantity", 0) or 0)
    return 0


def affordable_quantity(money: int, price: int, requested: int) -> int:
    if price <= 0:
        return requested
    return min(max(money // price, 0), requested)


def screenshot_has_pokemart_buy_menu(path: str | Path | None) -> bool:
    if path is None:
        return False
    image_path = Path(path)
    if not image_path.exists():
        return False
    image = Image.open(image_path).convert("L")
    if image.size[0] < 160 or image.size[1] < 144:
        return False
    # BUY lists have the money box at the top, the stock list on the upper
    # right, and a bottom text box. This distinguishes them from stable Mart
    # overworld while keeping the detector lightweight and explainable.
    money_top = dark_ratio(image.crop((105, 0, 160, 10))) > 0.18
    stock_left_edge = dark_ratio(image.crop((63, 18, 72, 88))) > 0.15
    stock_right_edge = dark_ratio(image.crop((151, 18, 160, 88))) > 0.18
    stock_top_edge = dark_ratio(image.crop((63, 18, 160, 27))) > 0.18
    text_top = dark_ratio(image.crop((0, 94, 160, 103))) > 0.30
    text_bottom = dark_ratio(image.crop((0, 136, 160, 144))) > 0.30
    return money_top and stock_left_edge and stock_right_edge and stock_top_edge and text_top and text_bottom
