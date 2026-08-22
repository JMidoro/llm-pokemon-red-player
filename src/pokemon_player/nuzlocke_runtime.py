from __future__ import annotations

from typing import Any

from pokemon_player import memory_map as mm
from pokemon_player.nuzlocke_rules import NuzlockeRuleset


# Despite the historical pret constant name BIT_BATTLE_SHIFT, the battle core
# skips the shift prompt when bit 6 is set. The stored option therefore reads
# as SET when the bit is 1 and SHIFT when it is 0.
BATTLE_SET_MASK = 1 << 6


def battle_style_from_options(options_raw: int) -> str:
    return "set" if int(options_raw) & BATTLE_SET_MASK else "shift"


def apply_configured_battle_style(
    memory: Any,
    ruleset: NuzlockeRuleset,
) -> dict[str, Any]:
    target = str(ruleset.raw.get("battle", {}).get("style") or "shift")
    before_raw = int(memory[mm.OPTIONS])
    if target == "set":
        after_raw = before_raw | BATTLE_SET_MASK
    elif target == "shift":
        after_raw = before_raw & ~BATTLE_SET_MASK
    else:
        raise ValueError(f"Unsupported battle style: {target}")
    if after_raw != before_raw:
        memory[mm.OPTIONS] = after_raw
    return {
        "target": target,
        "before": battle_style_from_options(before_raw),
        "after": battle_style_from_options(after_raw),
        "beforeRaw": before_raw,
        "afterRaw": after_raw,
        "changed": after_raw != before_raw,
    }
