# Phase 3 Directive Semantics and LLM Director Harness

Status: v0 scaffold
Last updated: 2026-06-16

## Purpose

Phase 3 validates single-user natural-language steerability without pretending to solve livestream chat.

The director receives:

- A game-state summary
- A current objective
- Safety constraints
- One user directive

It returns:

- Directive category
- Risk
- Decision: accept, reject, defer, reinterpret, or ask for clarification
- Bounded goal or constraint when accepted
- State-grounded explanation

## Model

Default director model:

- `gpt-5.4-mini`

Configuration:

- `.env`
- `.env.example`

Required variable:

- `OPENAI_API_KEY`

Optional variables:

- `OPENAI_DIRECTOR_MODEL`
- `OPENAI_REASONING_EFFORT`

## Harness Policy

The LLM director is not allowed to press buttons directly.

It may emit bounded goals or constraints such as:

- `use_potion_if_hp_below_threshold`
- `catch_species`
- `avoid_overleveling`
- `reject_destructive_action`

Executor completion must later be verified from game state.

## Safety Rules

Reject destructive directives by default:

- Release party Pokemon.
- Spend all money without scenario permission.
- Teach over valuable moves without confirmation.
- Throw away key items.
- Force unsafe/unverified memory writes.
- Derail the scenario objective.

Accept safe strategic or cosmetic directives when compatible with the objective.

Defer directives that are safe but not currently actionable.

Ask for clarification only when the directive cannot be safely grounded in current state.

## Current Artifacts

- `src/pokemon_player/directive_model.py`
- `src/pokemon_player/directive_prompt.py`
- `src/pokemon_player/director_client.py`
- `src/pokemon_player/directive_rules.py`
- `scripts/classify_directive.py`
- `research/directives/v0_directive_deck.json`

