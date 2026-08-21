from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pokemon_player.config import load_dotenv
from pokemon_player.director_contracts import JsonObject
from pokemon_player.director_providers import (
    DirectorProvider,
    OpenAICompatibleChatAdapter,
    OpenAIResponsesAdapter,
    ReplayAdapter,
)


PROVIDER_ALIASES = {
    "lmstudio": "lmstudio-chat",
    "local": "lmstudio-chat",
    "chat-completions": "lmstudio-chat",
    "openai": "openai-responses",
    "responses": "openai-responses",
    "fake": "replay",
}


def canonical_provider_id(value: str | None) -> str:
    provider = (value or "openai-responses").strip().lower()
    return PROVIDER_ALIASES.get(provider, provider)


def make_provider(
    provider_id: str,
    *,
    env_path: Path | None = None,
    base_url: str | None = None,
    api_token: str | None = None,
    timeout_seconds: int = 180,
    replay_path: Path | None = None,
) -> DirectorProvider:
    if env_path:
        load_dotenv(env_path)
    provider_id = canonical_provider_id(provider_id)
    if provider_id == "lmstudio-chat":
        token = api_token or first_env("LM_API_TOKEN", "LMSTUDIO_API_KEY", "LM_STUDIO_API_KEY")
        if not token:
            raise RuntimeError(
                "LM Studio API token missing. Set LM_API_TOKEN in the environment or .env."
            )
        return OpenAICompatibleChatAdapter(
            base_url=base_url or os.environ.get("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1"),
            api_token=token,
            timeout_seconds=timeout_seconds,
            provider_id="lmstudio-chat",
        )
    if provider_id == "openai-responses":
        token = api_token or os.environ.get("OPENAI_API_KEY")
        if not token:
            raise RuntimeError("OPENAI_API_KEY is not set in the environment or .env.")
        return OpenAIResponsesAdapter(
            api_key=token,
            base_url=base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            timeout_seconds=timeout_seconds,
            input_cost_per_million=optional_float(
                os.environ.get("DIRECTOR_INPUT_COST_PER_MILLION")
            ),
            output_cost_per_million=optional_float(
                os.environ.get("DIRECTOR_OUTPUT_COST_PER_MILLION")
            ),
        )
    if provider_id == "replay":
        if not replay_path:
            raise RuntimeError("Replay provider requires --replay-path.")
        return ReplayAdapter(load_replay_responses(replay_path))
    raise ValueError(f"Unsupported Director provider: {provider_id}")


def load_replay_responses(path: Path) -> list[JsonObject]:
    parsed: Any = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(parsed, dict):
        parsed = parsed.get("decisions", parsed.get("responses"))
    if not isinstance(parsed, list) or not all(isinstance(item, dict) for item in parsed):
        raise ValueError("Replay file must contain a list of decision objects.")
    return parsed


def first_env(*keys: str) -> str | None:
    for key in keys:
        value = os.environ.get(key)
        if value:
            return value
    return None


def optional_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None
