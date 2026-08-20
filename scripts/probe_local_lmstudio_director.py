from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.director_player import promoted_signals, skill_availability  # noqa: E402
from pokemon_player.pyboy_lab import load_state, open_emulator, save_screenshot, snapshot  # noqa: E402
from pokemon_player.rom import fingerprint_rom  # noqa: E402
from pokemon_player.snapshot_io import snapshot_to_dict  # noqa: E402


DEFAULT_STATE = ROOT / "research" / "golden-states" / "local" / "viridian_forest_wild_battle_weedle.state"
DEFAULT_ROM = ROOT / "research" / "PokemonRed.gb"
DEFAULT_BASE_URL = "http://127.0.0.1:1234/v1"
DEFAULT_MODEL = "google/gemma-4-e4b"


def timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def enabled_skills(availability: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [skill for skill in availability if skill.get("enabled") is True]


def compact_party(snapshot_dict: dict[str, Any]) -> list[dict[str, Any]]:
    compacted = []
    for member in snapshot_dict.get("party", []):
        if not isinstance(member, dict):
            continue
        compacted.append(
            {
                "slot": member.get("slot"),
                "species": member.get("species_name"),
                "nickname": member.get("nickname"),
                "level": member.get("level"),
                "hp": member.get("hp"),
                "maxHp": member.get("max_hp"),
                "status": member.get("status"),
                "moves": [
                    {
                        "id": move.get("move_id"),
                        "name": move.get("move_name"),
                        "pp": move.get("pp"),
                    }
                    for move in member.get("moves", [])
                    if isinstance(move, dict) and move.get("move_id")
                ],
            }
        )
    return compacted


def compact_inventory(snapshot_dict: dict[str, Any]) -> list[dict[str, Any]]:
    compacted = []
    for item in snapshot_dict.get("inventory", []):
        if not isinstance(item, dict):
            continue
        compacted.append(
            {
                "id": item.get("item_id"),
                "name": item.get("item_name"),
                "quantity": item.get("quantity"),
            }
        )
    return compacted


def compact_snapshot(snapshot_dict: dict[str, Any]) -> dict[str, Any]:
    enemy = snapshot_dict.get("enemy") if isinstance(snapshot_dict.get("enemy"), dict) else None
    position = snapshot_dict.get("position") if isinstance(snapshot_dict.get("position"), dict) else None
    return {
        "mode": snapshot_dict.get("mode"),
        "battleTypeRaw": snapshot_dict.get("battle_type_raw"),
        "position": position,
        "activePartySlot": snapshot_dict.get("active_party_slot"),
        "enemy": enemy,
        "party": compact_party(snapshot_dict),
        "inventory": compact_inventory(snapshot_dict),
        "money": snapshot_dict.get("money"),
        "badges": snapshot_dict.get("badge_names"),
        "summary": snapshot_dict.get("plaintext_summary"),
    }


def compact_skill(skill: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": skill.get("id"),
        "label": skill.get("label"),
        "reason": skill.get("reason"),
        "params": skill.get("params") or {},
    }


def read_png_data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def resolve_api_token(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    dotenv = load_dotenv(ROOT / ".env")
    for key in ("LM_API_TOKEN", "LMSTUDIO_API_KEY", "LM_STUDIO_API_KEY"):
        value = os.environ.get(key) or dotenv.get(key)
        if value:
            return value
    return None


def build_messages(
    *,
    goal: str,
    state_path: Path,
    snapshot_dict: dict[str, Any],
    signals: list[dict[str, Any]],
    available: list[dict[str, Any]],
    screenshot_path: Path,
    include_image: bool,
) -> list[dict[str, Any]]:
    system = (
        "You are the Pokemon Red LLM Director. Choose exactly one currently enabled skill "
        "that best advances the stated capsule goal. The executor will handle button-level "
        "details, so you should choose strategy and provide valid skill arguments only. "
        "Prefer precise high-level skills over literal_button_press when a specific skill applies."
    )
    text = {
        "goal": goal,
        "state": str(state_path),
        "screenshot": str(screenshot_path),
        "snapshot": compact_snapshot(snapshot_dict),
        "promotedSignals": signals,
        "enabledSkills": [compact_skill(skill) for skill in available],
        "responseRules": {
            "tool": "Call execute_skill once. If tool calling is unavailable, return JSON with skillId, args, and plaintextReasoning.",
            "args": "Use the params on the selected skill to choose valid arguments.",
        },
    }
    content: list[dict[str, Any]] = [{"type": "text", "text": json.dumps(text, indent=2)}]
    if include_image:
        content.append({"type": "image_url", "image_url": {"url": read_png_data_url(screenshot_path)}})
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": content},
    ]


def build_tools(available: list[dict[str, Any]]) -> list[dict[str, Any]]:
    skill_ids = [str(skill.get("id")) for skill in available if skill.get("id")]
    return [
        {
            "type": "function",
            "function": {
                "name": "execute_skill",
                "description": "Execute one enabled Pokemon player skill.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skillId": {
                            "type": "string",
                            "enum": skill_ids,
                            "description": "The enabled skill id to execute.",
                        },
                        "args": {
                            "type": "object",
                            "description": "Arguments for the selected skill. Follow that skill's params.",
                        },
                        "plaintextReasoning": {
                            "type": "string",
                            "description": "Brief natural-language reason for choosing this skill.",
                        },
                    },
                    "required": ["skillId", "plaintextReasoning"],
                    "additionalProperties": False,
                },
            },
        }
    ]


def call_lmstudio(base_url: str, payload: dict[str, Any], *, api_token: str | None) -> dict[str, Any]:
    endpoint = base_url.rstrip("/") + "/chat/completions"
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    request = Request(endpoint, data=data, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LM Studio HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"LM Studio request failed: {exc.reason}") from exc


def extract_text(choice: dict[str, Any]) -> str:
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return "\n".join(parts)
    return ""


def parse_json_choice(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def selected_tool_from_response(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices") if isinstance(response.get("choices"), list) else []
    if not choices:
        return {"source": "none", "status": "no_choices"}
    choice = choices[0] if isinstance(choices[0], dict) else {}
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        call = tool_calls[0] if isinstance(tool_calls[0], dict) else {}
        function = call.get("function") if isinstance(call.get("function"), dict) else {}
        arguments = function.get("arguments")
        parsed_args = None
        if isinstance(arguments, str):
            try:
                parsed_args = json.loads(arguments)
            except json.JSONDecodeError:
                parsed_args = {"raw": arguments}
        return {
            "source": "tool_call",
            "name": function.get("name"),
            "arguments": parsed_args,
            "raw": call,
        }
    text = extract_text(choice)
    parsed = parse_json_choice(text)
    if parsed:
        return {"source": "json_content", "arguments": parsed, "rawText": text}
    return {"source": "text_content", "rawText": text}


def load_state_context(rom_path: Path, state_path: Path, screenshot_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    rom = fingerprint_rom(rom_path)
    pyboy = open_emulator(rom.path, window="null")
    try:
        load_state(pyboy, state_path)
        pyboy.tick(60, False)
        save_screenshot(pyboy, screenshot_path)
        snap = snapshot(pyboy)
    finally:
        pyboy.stop(False)
    snapshot_dict = snapshot_to_dict(snap)
    signals = promoted_signals(snapshot_dict, screenshot_path)
    availability = skill_availability(snapshot_dict, screenshot_path)
    return snapshot_dict, signals, availability


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe a local LM Studio model as a Pokemon Director.")
    parser.add_argument("--state", default=str(DEFAULT_STATE), help="Golden or derivative .state to inspect.")
    parser.add_argument("--rom", default=str(DEFAULT_ROM), help="Pokemon Red ROM path.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="LM Studio model id.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="OpenAI-compatible LM Studio base URL.")
    parser.add_argument("--goal", default="Complete Capsule A: catch a Pikachu or another allowed early wild Pokemon in or near Viridian Forest without blacking out.")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--api-token", default=None, help="LM Studio API token. Defaults to LM_API_TOKEN/LMSTUDIO_API_KEY from env or .env.")
    parser.add_argument("--no-image", action="store_true", help="Do not send screenshot image input to LM Studio.")
    args = parser.parse_args()

    run_dir = ROOT / "research" / "artifacts" / "local-model-probes" / timestamp()
    run_dir.mkdir(parents=True, exist_ok=True)
    state_path = Path(args.state).resolve()
    rom_path = Path(args.rom).resolve()
    screenshot_path = run_dir / "screenshot.png"
    report_path = run_dir / "report.json"
    api_token = resolve_api_token(args.api_token)

    snapshot_dict, signals, availability = load_state_context(rom_path, state_path, screenshot_path)
    available = enabled_skills(availability)
    messages_with_image = build_messages(
        goal=args.goal,
        state_path=state_path,
        snapshot_dict=snapshot_dict,
        signals=signals,
        available=available,
        screenshot_path=screenshot_path,
        include_image=not args.no_image,
    )
    payload = {
        "model": args.model,
        "messages": messages_with_image,
        "tools": build_tools(available),
        "tool_choice": "auto",
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
    }

    attempts: list[dict[str, Any]] = []
    response: dict[str, Any] | None = None
    failure: str | None = None
    try:
        response = call_lmstudio(args.base_url, payload, api_token=api_token)
        attempts.append({"mode": "image" if not args.no_image else "text", "status": "ok"})
    except RuntimeError as exc:
        attempts.append({"mode": "image" if not args.no_image else "text", "status": "error", "error": str(exc)})
        if args.no_image:
            failure = str(exc)
        else:
            text_payload = dict(payload)
            text_payload["messages"] = build_messages(
                goal=args.goal,
                state_path=state_path,
                snapshot_dict=snapshot_dict,
                signals=signals,
                available=available,
                screenshot_path=screenshot_path,
                include_image=False,
            )
            try:
                response = call_lmstudio(args.base_url, text_payload, api_token=api_token)
                payload = text_payload
                attempts.append({"mode": "text_retry", "status": "ok"})
            except RuntimeError as retry_exc:
                attempts.append({"mode": "text_retry", "status": "error", "error": str(retry_exc)})
                failure = str(retry_exc)

    selected = selected_tool_from_response(response or {})
    report = {
        "createdUtc": datetime.now(UTC).isoformat(),
        "statePath": str(state_path),
        "romPath": str(rom_path),
        "screenshotPath": str(screenshot_path),
        "model": args.model,
        "baseUrl": args.base_url,
        "auth": {"tokenProvided": bool(api_token)},
        "attempts": attempts,
        "snapshot": compact_snapshot(snapshot_dict),
        "signals": signals,
        "enabledSkills": [compact_skill(skill) for skill in available],
        "request": payload,
        "response": response,
        "selectedTool": selected,
    }
    if failure:
        report["failure"] = failure
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "report": str(report_path),
                "screenshot": str(screenshot_path),
                "selectedTool": selected,
                "enabledSkills": [skill.get("id") for skill in available],
                "attempts": attempts,
                "failure": failure,
            },
            indent=2,
        )
    )
    return 1 if failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
