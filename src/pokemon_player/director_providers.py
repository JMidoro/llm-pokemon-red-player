from __future__ import annotations

import json
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from pokemon_player.director_contracts import (
    DirectorError,
    JsonObject,
    ProviderCapabilities,
    ProviderResponse,
    ProviderUsage,
    ToolCall,
)
from pokemon_player.director_prompting import PreparedDirectorRequest


JsonTransport = Callable[[str, JsonObject, dict[str, str], int], JsonObject]


class DirectorProvider(Protocol):
    provider_id: str
    capabilities: ProviderCapabilities

    def complete(self, request: PreparedDirectorRequest) -> ProviderResponse:
        ...

    def public_config(self) -> JsonObject:
        ...


class ProviderFailure(RuntimeError):
    def __init__(self, error: DirectorError) -> None:
        super().__init__(error.message)
        self.error = error


def default_json_transport(
    endpoint: str,
    payload: JsonObject,
    headers: dict[str, str],
    timeout_seconds: int,
) -> JsonObject:
    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            parsed = json.loads(response.read().decode("utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError("Provider returned a non-object JSON response.")
            return parsed
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        message = provider_error_message(body) or f"Provider HTTP {exc.code}."
        raise ProviderFailure(error_for_http_status(exc.code, message)) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise ProviderFailure(
            DirectorError(category="timeout", message="Provider request timed out.", retryable=True)
        ) from exc
    except URLError as exc:
        reason = str(exc.reason)
        category = "timeout" if "timed out" in reason.lower() else "connection"
        raise ProviderFailure(
            DirectorError(
                category=category,
                message=f"Provider request failed: {reason}",
                retryable=True,
            )
        ) from exc
    except json.JSONDecodeError as exc:
        raise ProviderFailure(
            DirectorError(
                category="invalid_response",
                message="Provider returned invalid JSON.",
                retryable=False,
            )
        ) from exc


@dataclass
class OpenAICompatibleChatAdapter:
    base_url: str
    api_token: str
    timeout_seconds: int = 180
    transport: JsonTransport = default_json_transport
    provider_id: str = "openai-compatible-chat"
    capabilities: ProviderCapabilities = field(
        default_factory=lambda: ProviderCapabilities(
            images=True,
            structured_tools=True,
            reasoning_controls=False,
            streaming=False,
            usage_accounting=True,
        )
    )

    def complete(self, request: PreparedDirectorRequest) -> ProviderResponse:
        endpoint = self.base_url.rstrip("/") + "/chat/completions"
        payload = chat_completions_payload(request)
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        try:
            response = self.transport(endpoint, payload, headers, self.timeout_seconds)
        except ProviderFailure as exc:
            raise ProviderFailure(
                redact_error(with_provider(exc.error, self.provider_id), self.api_token)
            ) from exc
        except Exception as exc:
            raise ProviderFailure(
                DirectorError(
                    category="provider_error",
                    message=redact_text(f"Provider transport failed: {exc}", self.api_token),
                    retryable=False,
                    provider=self.provider_id,
                )
            ) from exc
        return normalize_chat_completions_response(response, provider=self.provider_id)

    def public_config(self) -> JsonObject:
        return {
            "provider": self.provider_id,
            "apiFamily": "chat_completions",
            "baseUrl": sanitize_public_url(self.base_url),
            "capabilities": self.capabilities.to_dict(),
        }


@dataclass
class OpenAIResponsesAdapter:
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: int = 180
    transport: JsonTransport = default_json_transport
    input_cost_per_million: float | None = None
    output_cost_per_million: float | None = None
    provider_id: str = "openai-responses"
    capabilities: ProviderCapabilities = field(
        default_factory=lambda: ProviderCapabilities(
            images=True,
            structured_tools=True,
            reasoning_controls=True,
            streaming=False,
            usage_accounting=True,
        )
    )

    def complete(self, request: PreparedDirectorRequest) -> ProviderResponse:
        endpoint = self.base_url.rstrip("/") + "/responses"
        payload = responses_payload(request)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = self.transport(endpoint, payload, headers, self.timeout_seconds)
        except ProviderFailure as exc:
            raise ProviderFailure(
                redact_error(with_provider(exc.error, self.provider_id), self.api_key)
            ) from exc
        except Exception as exc:
            raise ProviderFailure(
                DirectorError(
                    category="provider_error",
                    message=redact_text(f"Provider transport failed: {exc}", self.api_key),
                    retryable=False,
                    provider=self.provider_id,
                )
            ) from exc
        return normalize_responses_response(
            response,
            provider=self.provider_id,
            input_cost_per_million=self.input_cost_per_million,
            output_cost_per_million=self.output_cost_per_million,
        )

    def public_config(self) -> JsonObject:
        return {
            "provider": self.provider_id,
            "apiFamily": "responses",
            "baseUrl": sanitize_public_url(self.base_url),
            "capabilities": self.capabilities.to_dict(),
        }


@dataclass
class ReplayAdapter:
    responses: list[ProviderResponse | JsonObject]
    provider_id: str = "replay"
    capabilities: ProviderCapabilities = field(
        default_factory=lambda: ProviderCapabilities(
            images=False,
            structured_tools=True,
            reasoning_controls=False,
            streaming=False,
            usage_accounting=True,
        )
    )
    _index: int = field(default=0, init=False, repr=False)

    def complete(self, request: PreparedDirectorRequest) -> ProviderResponse:
        del request
        if self._index >= len(self.responses):
            raise ProviderFailure(
                DirectorError(
                    category="replay_exhausted",
                    message="Deterministic replay has no remaining decisions.",
                    retryable=False,
                    provider=self.provider_id,
                )
            )
        item = self.responses[self._index]
        self._index += 1
        if isinstance(item, ProviderResponse):
            return item
        if item.get("error"):
            raw_error = item["error"]
            if isinstance(raw_error, dict):
                raise ProviderFailure(
                    DirectorError(
                        category=str(raw_error.get("category") or "provider_error"),
                        message=redact_text(
                            str(raw_error.get("message") or "Replayed provider failure.")
                        ),
                        retryable=bool(raw_error.get("retryable")),
                        provider=self.provider_id,
                    )
                )
        raw_call = item.get("toolCall") if isinstance(item.get("toolCall"), dict) else None
        call = None
        if raw_call:
            call = ToolCall(
                name=str(raw_call.get("name") or ""),
                arguments=raw_call.get("arguments")
                if isinstance(raw_call.get("arguments"), dict)
                else {},
                call_id=str(raw_call.get("callId")) if raw_call.get("callId") else None,
            )
        return ProviderResponse(
            tool_calls=(call,) if call else (),
            assistant_message=str(item.get("assistantMessage") or ""),
            usage=usage_from_canonical(item.get("usage")),
            response_id=str(item.get("responseId")) if item.get("responseId") else None,
            finish_reason=str(item.get("finishReason")) if item.get("finishReason") else None,
        )

    def public_config(self) -> JsonObject:
        return {
            "provider": self.provider_id,
            "apiFamily": "replay",
            "capabilities": self.capabilities.to_dict(),
        }


def chat_completions_payload(request: PreparedDirectorRequest) -> JsonObject:
    messages: list[JsonObject] = [
        {"role": "system", "content": request.instructions},
        *[chat_message(message) for message in request.messages[:-1]],
    ]
    final_message = chat_message(request.messages[-1])
    if request.image_data_url:
        final_message["content"] = [
            {"type": "text", "text": str(final_message["content"])},
            {"type": "image_url", "image_url": {"url": request.image_data_url}},
        ]
    messages.append(final_message)
    payload: JsonObject = {
        "model": request.request.model,
        "messages": messages,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            }
            for tool in request.tools
        ],
        "tool_choice": "required",
        "max_tokens": request.request.max_output_tokens,
    }
    if request.request.temperature is not None:
        payload["temperature"] = request.request.temperature
    return payload


def responses_payload(request: PreparedDirectorRequest) -> JsonObject:
    input_items: list[JsonObject] = []
    for index, message in enumerate(request.messages):
        role = str(message.get("role") or "user")
        if role == "assistant":
            content_type = "output_text"
        else:
            role = "user" if role == "tool" else role
            content_type = "input_text"
        content: list[JsonObject] = [
            {"type": content_type, "text": str(message.get("content") or "")}
        ]
        if index == len(request.messages) - 1 and request.image_data_url:
            content.append({"type": "input_image", "image_url": request.image_data_url})
        input_items.append({"role": role, "content": content})
    payload: JsonObject = {
        "model": request.request.model,
        "instructions": request.instructions,
        "input": input_items,
        "tools": [
            {
                "type": "function",
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
                "strict": False,
            }
            for tool in request.tools
        ],
        "parallel_tool_calls": False,
        "max_tool_calls": 1,
        "max_output_tokens": request.request.max_output_tokens,
    }
    if request.request.reasoning_effort:
        payload["reasoning"] = {"effort": request.request.reasoning_effort}
    return payload


def normalize_chat_completions_response(
    response: JsonObject,
    *,
    provider: str,
) -> ProviderResponse:
    choices = response.get("choices") if isinstance(response.get("choices"), list) else []
    if not choices or not isinstance(choices[0], dict):
        raise ProviderFailure(
            DirectorError(
                category="invalid_response",
                message="Chat Completions response contained no choices.",
                provider=provider,
            )
        )
    choice = choices[0]
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    calls: list[ToolCall] = []
    raw_calls = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []
    for raw_call in raw_calls:
        if not isinstance(raw_call, dict):
            continue
        function = raw_call.get("function") if isinstance(raw_call.get("function"), dict) else {}
        calls.append(
            ToolCall(
                name=str(function.get("name") or ""),
                arguments=parse_tool_arguments(function.get("arguments"), provider=provider),
                call_id=str(raw_call.get("id")) if raw_call.get("id") else None,
            )
        )
    assistant_message = content_text(message.get("content"))
    if not calls:
        recovered = recover_text_tool_call(assistant_message)
        if recovered:
            calls.append(recovered)
    return ProviderResponse(
        tool_calls=tuple(calls),
        assistant_message=assistant_message,
        usage=usage_from_chat(response.get("usage")),
        response_id=str(response.get("id")) if response.get("id") else None,
        finish_reason=str(choice.get("finish_reason")) if choice.get("finish_reason") else None,
    )


def normalize_responses_response(
    response: JsonObject,
    *,
    provider: str,
    input_cost_per_million: float | None = None,
    output_cost_per_million: float | None = None,
) -> ProviderResponse:
    output = response.get("output") if isinstance(response.get("output"), list) else []
    calls: list[ToolCall] = []
    text_chunks: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "function_call":
            calls.append(
                ToolCall(
                    name=str(item.get("name") or ""),
                    arguments=parse_tool_arguments(item.get("arguments"), provider=provider),
                    call_id=str(item.get("call_id")) if item.get("call_id") else None,
                )
            )
        for content in item.get("content") if isinstance(item.get("content"), list) else []:
            if isinstance(content, dict) and content.get("type") == "output_text":
                text_chunks.append(str(content.get("text") or ""))
    if response.get("output_text"):
        text_chunks.insert(0, str(response["output_text"]))
    return ProviderResponse(
        tool_calls=tuple(calls),
        assistant_message="\n".join(chunk for chunk in text_chunks if chunk).strip(),
        usage=usage_from_responses(
            response.get("usage"),
            input_cost_per_million=input_cost_per_million,
            output_cost_per_million=output_cost_per_million,
        ),
        response_id=str(response.get("id")) if response.get("id") else None,
        finish_reason=str(response.get("status")) if response.get("status") else None,
    )


def parse_tool_arguments(value: Any, *, provider: str) -> JsonObject:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ProviderFailure(
            DirectorError(
                category="invalid_tool_arguments",
                message="Provider returned malformed tool arguments.",
                provider=provider,
            )
        ) from exc
    if not isinstance(parsed, dict):
        raise ProviderFailure(
            DirectorError(
                category="invalid_tool_arguments",
                message="Provider tool arguments were not a JSON object.",
                provider=provider,
            )
        )
    return parsed


def recover_text_tool_call(content: str) -> ToolCall | None:
    stripped = content.strip().strip("`")
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or not parsed.get("skillId"):
        return None
    return ToolCall(name="execute_skill", arguments=parsed)


def usage_from_chat(value: Any) -> ProviderUsage:
    usage = value if isinstance(value, dict) else {}
    details = usage.get("prompt_tokens_details")
    details = details if isinstance(details, dict) else {}
    return ProviderUsage(
        input_tokens=optional_int(usage.get("prompt_tokens")),
        output_tokens=optional_int(usage.get("completion_tokens")),
        total_tokens=optional_int(usage.get("total_tokens")),
        cached_input_tokens=optional_int(details.get("cached_tokens")),
    )


def usage_from_responses(
    value: Any,
    *,
    input_cost_per_million: float | None = None,
    output_cost_per_million: float | None = None,
) -> ProviderUsage:
    usage = value if isinstance(value, dict) else {}
    output_details = usage.get("output_tokens_details")
    output_details = output_details if isinstance(output_details, dict) else {}
    input_details = usage.get("input_tokens_details")
    input_details = input_details if isinstance(input_details, dict) else {}
    input_tokens = optional_int(usage.get("input_tokens"))
    output_tokens = optional_int(usage.get("output_tokens"))
    estimated_cost = None
    if input_cost_per_million is not None and output_cost_per_million is not None:
        estimated_cost = round(
            (
                ((input_tokens or 0) * input_cost_per_million)
                + ((output_tokens or 0) * output_cost_per_million)
            )
            / 1_000_000,
            8,
        )
    return ProviderUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=optional_int(usage.get("total_tokens")),
        reasoning_tokens=optional_int(output_details.get("reasoning_tokens")),
        cached_input_tokens=optional_int(input_details.get("cached_tokens")),
        estimated_cost_usd=estimated_cost,
    )


def usage_from_canonical(value: Any) -> ProviderUsage:
    usage = value if isinstance(value, dict) else {}
    return ProviderUsage(
        input_tokens=optional_int(usage.get("inputTokens")),
        output_tokens=optional_int(usage.get("outputTokens")),
        total_tokens=optional_int(usage.get("totalTokens")),
        reasoning_tokens=optional_int(usage.get("reasoningTokens")),
        cached_input_tokens=optional_int(usage.get("cachedInputTokens")),
        estimated_cost_usd=optional_float(usage.get("estimatedCostUsd")),
    )


def error_for_http_status(status: int, message: str) -> DirectorError:
    if status in {401, 403}:
        return DirectorError("authentication", message, retryable=False, status_code=status)
    if status == 429:
        return DirectorError("rate_limit", message, retryable=True, status_code=status)
    if status in {408, 504}:
        return DirectorError("timeout", message, retryable=True, status_code=status)
    if status >= 500:
        return DirectorError("provider_unavailable", message, retryable=True, status_code=status)
    return DirectorError("provider_error", message, retryable=False, status_code=status)


def with_provider(error: DirectorError, provider: str) -> DirectorError:
    return DirectorError(
        category=error.category,
        message=error.message,
        retryable=error.retryable,
        provider=provider,
        status_code=error.status_code,
    )


def provider_error_message(body: str) -> str | None:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return body.strip()[:500] or None
    if not isinstance(parsed, dict):
        return None
    error = parsed.get("error")
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])
    return str(error) if error else None


def chat_message(message: JsonObject) -> JsonObject:
    role = str(message.get("role") or "user")
    if role == "tool":
        role = "user"
    return {"role": role, "content": str(message.get("content") or "")}


def content_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return ""
    chunks: list[str] = []
    for item in value:
        if isinstance(item, dict) and item.get("text"):
            chunks.append(str(item["text"]))
    return "\n".join(chunks).strip()


def optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def sanitize_public_url(value: str) -> str:
    parsed = urlsplit(value)
    hostname = parsed.hostname or ""
    if parsed.port:
        hostname = f"{hostname}:{parsed.port}"
    return urlunsplit((parsed.scheme, hostname, parsed.path, "", ""))


def redact_error(error: DirectorError, *secrets: str) -> DirectorError:
    return DirectorError(
        category=error.category,
        message=redact_text(error.message, *secrets),
        retryable=error.retryable,
        provider=error.provider,
        status_code=error.status_code,
    )


def redact_text(value: str, *secrets: str) -> str:
    redacted = value
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    redacted = re.sub(r"(?i)Bearer\s+[^\s,;]+", "Bearer [REDACTED]", redacted)
    redacted = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", redacted)
    return redacted
