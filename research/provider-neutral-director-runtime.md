# Provider-Neutral Director Runtime

Status: Milestone 2 complete

## Boundary

The canonical Director path lives in Python. It owns:

- provider-neutral request, decision, tool-call, usage, capability, and error contracts;
- stable prompt construction and semantic tool schemas;
- history truncation, provider-response normalization, tool validation, and skill-argument normalization;
- one retry for retryable provider failures before any emulator action;
- provider/model/capability, latency, token, and optional cost telemetry;
- the decision-before-action barrier used by both browser ticks and unattended chapter segments.

Provider adapters only translate the prepared canonical request to an API family and translate the response back. Chapter code and semantic skills do not import a provider SDK or provider-specific response shape.

`src/pokemon_player/director_client.py` is a separate, legacy directive-classification helper for the lab UI. It does not choose or execute gameplay skills and is not part of the canonical gameplay Director path described here.

The hosted adapter follows the current OpenAI Responses function-tool shape: function definitions are sent in `tools`, and returned `function_call` items supply a `call_id`, name, and JSON arguments. See the [official Responses API reference](https://developers.openai.com/api/reference/typescript/resources/beta/subresources/responses/methods/create).

## Providers

| Provider id | API family | Intended use |
| --- | --- | --- |
| `lmstudio-chat` | OpenAI-compatible Chat Completions | Local Gemma hardening and other LM Studio models |
| `openai-responses` | OpenAI Responses | First hosted comparison adapter; not a production-model commitment |
| `replay` | Deterministic recorded decisions | Unit tests, regression reproduction, and emulator smoke tests |

The capability record explicitly reports image input, structured tools, reasoning controls, streaming, and usage accounting. These are effective adapter capabilities, not marketing claims about the underlying provider. For example, the current Responses adapter reports `streaming=false` because this milestone uses complete single-decision responses even though the upstream API also offers a streaming mode.

## Executables

Run a provider-neutral bounded chapter segment:

```powershell
.\.venv\Scripts\python scripts\run_chapter_segment.py --provider lmstudio-chat --model google/gemma-4-e4b --max-actions 100
```

The old command remains compatible and pins the local adapter:

```powershell
.\.venv\Scripts\python scripts\run_local_gemma_chapter.py --max-actions 100
```

The browser `/api/llm-player` endpoint is a thin local-process client of `scripts/run_director_tick.py`. It validates that a goal exists, forwards JSON on standard input, and returns the canonical result. Prompting, credentials, provider calls, sidecar state checks, skill execution, and report writing stay in Python.

Use `DIRECTOR_RUNTIME_PYTHON` only when the project interpreter is not at the platform-standard `.venv` path. The browser worker timeout defaults to fifteen minutes so it exceeds two worst-case provider attempts plus one bounded sidecar skill call; it must not kill the worker during an otherwise healthy long navigation skill.

## Reports and credentials

Every adapter writes `director_segment_run_v1`. Its common fields include:

- provider id, API family, model, and capability flags;
- canonical request summaries and normalized decisions;
- latency and canonical input/output/total/reasoning/cached-token usage;
- estimated cost only when both current per-million rates are configured;
- normalized errors such as `authentication`, `rate_limit`, `timeout`, `connection`, `provider_unavailable`, `invalid_response`, `missing_tool_call`, and `unavailable_skill`;
- the pre-provider checkpoint and whether execution started.

Reports never include authorization headers, API keys, LM Studio tokens, or full raw provider payloads. Public provider URLs have user information, query parameters, and fragments removed before serialization.

## Failure safety

The runner saves the emulator state and screenshot before asking a provider. The browser path records the sidecar snapshot hash, screenshot, and session before asking a provider. The runtime then follows this order:

1. Prepare and validate the canonical request.
2. Call the provider, retrying only retryable failures.
3. Normalize exactly one tool call.
4. Reject unknown tools, malformed calls, or disabled skills.
5. Only then invoke the emulator or sidecar executor.

A provider exception, timeout, malformed response, or invalid tool call therefore cannot start an emulator action. Skill execution has its own input-state checkpoint in the player layer.

Once an executor has been invoked, an exception is conservatively reported as `actionStarted=null`, `actionStateKnown=false`, and `requiresCheckpointReconciliation=true`; the chapter runner stops and saves final evidence instead of issuing another decision. This distinction keeps the strong pre-action provider guarantee honest without mislabeling an interrupted gameplay action as unstarted.

## Frozen provider gate

`research/evals/provider-neutral-director/frozen_scenario.json` is the single scenario and semantic registry for every provider comparison. The evaluator hashes both the full canonical scenario and its semantic registry into each report:

```powershell
.\.venv\Scripts\python scripts\evaluate_director_provider_gate.py --provider lmstudio-chat --model google/gemma-4-e4b --output research\artifacts\provider-gate-local.json

.\.venv\Scripts\python scripts\evaluate_director_provider_gate.py --provider openai-responses --model gpt-5.4-nano --output research\artifacts\provider-gate-hosted.json

.\.venv\Scripts\python scripts\verify_director_provider_gate.py --local research\artifacts\provider-gate-local.json --hosted research\artifacts\provider-gate-hosted.json
```

The deterministic replay fixture exercises the same path without network access. The gate is decision-only: it proves prompt, registry, normalization, telemetry, schema, and error parity without changing emulator state. A separate replay-backed chapter smoke test proves that the canonical chapter executable can execute the selected semantic skill and emit a healthy action-budget checkpoint.

The verifier also requires the local and hosted adapters to produce the same normalized semantic decision. Provider variants such as a singleton navigation `targets` list are normalized to the canonical singular `target` argument before validation or execution.
