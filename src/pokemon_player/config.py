from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: str | None
    director_model: str = "gpt-5.4-mini"
    reasoning_effort: str = "low"


def load_dotenv(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def load_openai_config(env_path: str | Path = ".env") -> OpenAIConfig:
    load_dotenv(env_path)
    return OpenAIConfig(
        api_key=os.environ.get("OPENAI_API_KEY") or None,
        director_model=os.environ.get("OPENAI_DIRECTOR_MODEL", "gpt-5.4-mini"),
        reasoning_effort=os.environ.get("OPENAI_REASONING_EFFORT", "low"),
    )

