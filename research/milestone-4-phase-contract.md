# Milestone 4 Phase Contract: Configurable Nuzlocke Rules and Durable Lineage

## Purpose

Milestone 4 makes the intended playthrough rules explicit, configurable, durable, and legible without replacing the LLM Director's strategic agency. The runner must prevent objectively illegal emulator inputs, record the evidence behind every rules decision, and expose the current rules and lineage state to both the Director and the remote Operations view.

## Hypothesis

A versioned ruleset, an event-sourced lineage ledger, checkpoint reconciliation, and a narrow pre-input legality guard are sufficient to make a Nuzlocke run reconstructable and enforceable across process restarts and segment boundaries. Strategic choices can remain with the Director when hard legality, advisory risk, and ordinary model mistakes are represented as separate concepts.

## Approved default contract

- The first eligible wild encounter in each canonical area is the area's encounter opportunity.
- A failed eligible encounter consumes that opportunity.
- The duplicate clause applies to the full evolutionary family. A duplicate does not consume the area's opportunity, and a family remains a duplicate after death.
- Static encounters and gift Pokemon do not consume the area's wild encounter opportunity.
- A configurable shiny exception may override the first-encounter rule. It is inert for original Pokemon Red, which has no shiny mechanic.
- Captured Pokemon must be nicknamed.
- Level caps are advisory. Party order and the use of overleveled or locally strong Pokemon remain Director decisions.
- Battle items are allowed.
- Canonical Nuzlocke runs use Set battle style. Standard and development profiles may use Shift.
- A blackout is game over in the canonical profile and begins a new lineage. The behavior is configurable for non-Nuzlocke runs.
- Manual resets are disallowed in the canonical profile except after game over. Reset policy is configurable for other profiles.
- Required-progression HM softlocks use a living legal Pokemon first. If none can progress, a dead Pokemon may serve as a field-only carrier; if that is impossible, an out-of-encounter utility capture may be made. Such a Pokemon must not intentionally battle, should remain at the back of the party, must be removed at the next PC, and must be recorded as an exception. Optional convenience moves such as Fly and Flash do not qualify.

## Agency boundary

Hard guards may block only actions whose illegality can be established from the ruleset and durable evidence before emulator input. Examples include attempting an extra area capture, selecting a confirmed-dead Pokemon for battle, declining a required nickname, or issuing a forbidden reset.

The following remain advice or observations rather than scripted strategy:

- level-cap management;
- party ordering and matchup preparation;
- voluntary switching and training choices;
- item use;
- route planning;
- whether to exploit an allowed static, gift, duplicate, or shiny opportunity.

Each policy result is classified as one of `hard_rule_violation`, `strategic_risk`, or `model_mistake` so that reports do not confuse illegality with weak play.

## Intended artifacts

- A tracked, versioned canonical Nuzlocke ruleset and a configurable standard-run profile.
- Canonical area and evolutionary-family data used through configuration rather than runner conditionals.
- A durable, event-sourced lineage ledger with deterministic replay and an integrity digest.
- Checkpoint reconciliation using promoted RAM state, including Pokedex owned/seen flags.
- Pre-input legality guards at the semantic skill boundary.
- Director context describing rules, eligibility, deaths, advisory risks, and recorded exceptions.
- Operations summaries and UI cards for the active ruleset and lineage.
- Synthetic and captured-state-compatible fixtures covering catches, failed encounters, duplicates, gifts, static encounters, deaths, full-party transfers, blackouts, and HM exceptions.
- A deterministic evaluator and automated tests. No model inference is required for the milestone gate.

## Compute and inference budget

The implementation and acceptance gate are deterministic. They use unit/integration tests and replay fixtures; they do not call OpenAI or another hosted inference provider. Local inference is also unnecessary unless a later gameplay validation reveals a problem that cannot be reproduced from preserved artifacts. Any hard need for hosted player inference stops the milestone and is raised to the project owner before use.

## Human burden

The rules decisions required for this phase have been supplied. No synchronous gameplay collection or review is required. Human review remains asynchronous and confidence-building; it does not block fixture construction, deterministic evaluation, or adjacent implementation.

## Principal failure modes

- A process restart loses encounter, death, or exception history.
- An area alias or evolutionary family mismatch permits an illegal catch or consumes the wrong opportunity.
- A full party causes a successful capture to disappear from reconciliation because the Pokemon went directly to the PC.
- Nickname or evolution changes cause a living Pokemon to be mistaken for a new or dead one.
- The guard blocks a strategic choice rather than a hard rule violation.
- A blocked action reaches the emulator before the decision is recorded.
- Ledger corruption or duplicate checkpoint processing changes replay results.
- Operations output exposes raw filesystem data or fails to explain a rules decision.
- Reset, blackout, gift, static, or HM-exception behavior is embedded in code instead of configuration.

## Acceptance gate

Milestone 4 passes only when:

1. replaying the durable event stream reconstructs the same lineage state and digest;
2. encounter consumption, duplicate-family handling, gift/static independence, capture failure, deaths, full-party box transfer, blackout, and required HM exceptions pass deterministic fixtures;
3. illegal extra-capture, dead-Pokemon battle, required-nickname refusal, and forbidden-reset actions are blocked before emulator input;
4. hard violations, strategic risks, and model mistakes remain distinct in reports;
5. rules, encounter eligibility, deaths, and exceptions are visible in sanitized Director and Operations context;
6. the exact stream rules can be changed by selecting or editing a validated ruleset rather than modifying runtime code;
7. the relevant automated test suite and the standalone Milestone 4 evaluator pass without provider inference.
