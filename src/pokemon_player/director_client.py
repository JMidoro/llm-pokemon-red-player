from __future__ import annotations

import json
from typing import Protocol

from pokemon_player.config import OpenAIConfig, load_openai_config
from pokemon_player.directive_model import (
    DIRECTOR_DECISION_JSON_SCHEMA,
    DirectorContext,
    DirectorDecision,
)
from pokemon_player.directive_prompt import DIRECTOR_INSTRUCTIONS, build_director_input
from pokemon_player.directive_rules import classify_directive_offline


class DirectorClient(Protocol):
    def decide(self, context: DirectorContext, directive: str) -> DirectorDecision:
        ...


class OfflineDirectorClient:
    def decide(self, context: DirectorContext, directive: str) -> DirectorDecision:
        return classify_directive_offline(context, directive)


class OpenAIDirectorClient:
    def __init__(self, config: OpenAIConfig | None = None) -> None:
        self.config = config or load_openai_config()
        if not self.config.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set. Add it to .env or the environment.")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("The openai package is not installed. Run pip install -e .[dev].") from exc
        self.client = OpenAI(api_key=self.config.api_key)

    def decide(self, context: DirectorContext, directive: str) -> DirectorDecision:
        response = self.client.responses.create(
            model=self.config.director_model,
            reasoning={"effort": self.config.reasoning_effort},
            instructions=DIRECTOR_INSTRUCTIONS,
            input=build_director_input(context, directive),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "director_decision",
                    "schema": DIRECTOR_DECISION_JSON_SCHEMA,
                    "strict": True,
                }
            },
        )
        raw = json.loads(response.output_text)
        return DirectorDecision.from_dict(raw, directive=directive)


def make_director_client(mode: str = "auto") -> DirectorClient:
    if mode == "offline":
        return OfflineDirectorClient()
    if mode == "openai":
        return OpenAIDirectorClient()
    config = load_openai_config()
    if config.api_key:
        return OpenAIDirectorClient(config)
    return OfflineDirectorClient()

