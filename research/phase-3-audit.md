# Phase 3 Audit: Directive Harness

## Status

Phase 3 has a first-pass director harness in place. It can classify single-user directives against a compact state summary and current objective, either through an offline deterministic baseline or through the OpenAI Responses API once `OPENAI_API_KEY` is added to `.env`.

The default director model is `gpt-5.4-mini`.

## Built

- `.env.example` and ignored local `.env` with OpenAI director settings.
- `TODO.md` for durable cross-phase follow-ups.
- Director data model and JSON schema in `src/pokemon_player/directive_model.py`.
- Prompt construction and default safety rules in `src/pokemon_player/directive_prompt.py`.
- Offline deterministic classifier in `src/pokemon_player/directive_rules.py`.
- OpenAI-backed client wrapper in `src/pokemon_player/director_client.py`.
- Directive classification CLI in `scripts/classify_directive.py`.
- Auditable directive deck evaluator in `scripts/evaluate_directive_deck.py`.
- Saved directive eval inspector in `scripts/inspect_directive_eval.py`.
- 100-case directive deck in `research/directives/v0_directive_deck.json`.
- Unit coverage in `tests/test_directive_harness.py`.

## Current Contract

The director receives:

- A state summary.
- A current objective.
- A user directive.
- Safety rules and allowed flavor constraints from the prompt layer.

The director returns:

- Category: strategic, cosmetic, constraint, playful, ambiguous, impossible, destructive, or derailing.
- Risk: low, medium, or high.
- Decision: accept, reject, defer, reinterpret, or ask_clarification.
- Explanation, bounded goal, constraints, and warnings.

## Verification

Last verified:

- `python -m pytest`: 41 passed.
- `python -m ruff check .`: passed.
- `python scripts/evaluate_directive_deck.py --mode offline`: 100 passed, 0 failed, report saved.
- `python scripts/classify_directive.py ... --mode auto`: keyless auto mode fell back to the offline director and returned a valid JSON decision.

## Auditable Eval Reports

Directive deck evals now write timestamped local reports by default:

```powershell
.\.venv\Scripts\python scripts\evaluate_directive_deck.py --mode offline
```

Reports are saved under `research/artifacts/directive-evals/`, with `latest.json` updated for quick inspection. These are local artifacts and are gitignored.

Inspect the latest summary:

```powershell
.\.venv\Scripts\python scripts\inspect_directive_eval.py
```

Inspect one saved verdict:

```powershell
.\.venv\Scripts\python scripts\inspect_directive_eval.py --case-id vf_accept_catch_pikachu
```

The report tracks per-case expected labels, actual director verdicts, errors, match flags, duration, and KPI gates. Current measurable KPI gates are:

- 100 curated cases.
- 90% category+decision label accuracy.
- 0 accepted destructive directives.
- 90% accepted-directive compilation into a bounded goal or constraint.
- 90% non-empty explanations.

## Remaining Phase 3 Work

- Add an API-key-backed smoke run with `--mode openai`.
- Add API-key-backed eval runs with `--mode openai`.
- Store every surprising director miss as a new regression case.
- Decide how accepted directives should be handed to the later executor/patch layers.
