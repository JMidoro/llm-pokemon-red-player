# Milestone 5 Phase Contract: Early-Game Reliability Through Brock

Status: active; the evaluation suite was frozen before any Director run against its selected start-state hashes.

## Purpose

Milestone 5 turns the existing early-game capability into a repeatable, unattended path from a clean boot through receipt of the Boulder Badge. It closes recurrent visual, dialogue, battle-outcome, catching, nickname, blackout, and stuckness gaps while preserving the LLM Director's tactical and routing agency.

## Hypothesis

A provider-neutral Director with semantic gameplay skills, durable Nuzlocke enforcement, bounded segment recovery, and explicit progress interrogation can clear the early game reliably without literal-button scripting or human gameplay intervention. Local Gemma is the hardening model for this milestone; passing evidence is about runtime reliability and schema legibility, not selection of the eventual stream provider.

## Evaluation lanes

### Capsule A compatibility

The historical Capsule A objective specifically requires catching Pikachu and reaching the Viridian Forest north exit. That objective can conflict with a canonical first-encounter Nuzlocke lineage, so this lane uses `standard-run-v1.json`. It measures the original catching/navigation target without pretending that a forced Pikachu catch is Nuzlocke-legal.

Five generated derivatives are frozen in `research/evals/early-game-reliability/frozen-suite.json`. They cover forest overworld search, a live Weedle battle, a weakened Pikachu battle, and the south gate with different legal party/resource conditions. All selected starts lack Pikachu initially, contain at least one conscious Pokemon and one Poke Ball, and pass snapshot invariants. Their state-file and snapshot hashes were recorded before model evaluation.

The previously observed historical holdout `golden:viridian_forest_south_gate` is tuning evidence only. Its result exposed a repeated successful navigation no-op and therefore cannot be counted as untouched final evidence.

### Clean boot through Boulder Badge

Ten fresh-start trials use `stream-nuzlocke-v1.json`, inference seeds 5301 through 5310, and a fixed implementation commit. Each trial begins from clean RAM through the canonical `--fresh-start` path. Segment boundaries may continue automatically from safe checkpoints; no state from one trial may seed another.

The run is successful only when the Boulder Badge is observed in the final lineage/snapshot, the lineage is not game over, the final state is inspectable, and no human gameplay input occurred. A blackout is a failed trial and ends that lineage.

### Deterministic branch coverage

Captured or formally generated fixtures exercise the branches that are too sparse to trust to aggregate end-to-end frequency alone:

- post-catch and Pokedex dialogue;
- nickname acceptance and text entry;
- optional Shift-style trainer switching, both keep and switch;
- level-up move learning, both skip and replace;
- evolution;
- blackout detection before inference;
- XP and ordinary battle-outcome dialogue;
- forced switching and stable return to tactical or overworld control.

These fixtures prove semantic mechanics but do not substitute for either model-driven success-rate gate.

## Fixed local inference profile

- Provider: `lmstudio-chat`.
- Model: `google/gemma-4-e4b`.
- Temperature: `0.1`.
- Seed policy: each trial records a first inference seed and increments it once per Director action.
- Images and semantic structured tools remain enabled.
- A local provider timeout receives only the canonical bounded retry. A suspected LM Studio KV-cache failure stops that trial for diagnosis/reload; it is not silently converted to a gameplay failure.
- Hosted inference is outside this milestone. No OpenAI API endpoint may be contacted without separate explicit authorization.

## Agency and safety boundary

Semantic skills may hide controller mechanics and validate postconditions, but they may not encode battle strategy, party ordering, training choices, or route tactics that belong to the Director. Hard guards block only objectively illegal actions before emulator input. A model proposal rejected with `actionStarted=false` is a prevented mistake, not an executed rules violation.

For evaluation:

- an executed illegal action is a `hard_rule_violation` whose recorded result has `actionStarted` other than `false`, or any forbidden raw/reset/dead-Pokemon/extra-catch input found in the audit stream;
- a destructive action is any reset, lineage overwrite, uncontrolled raw-input bypass, or action against a confirmed unsafe checkpoint not explicitly permitted by the active ruleset;
- prevented illegal proposals are reported separately as model mistakes and must retain their policy evidence;
- ordinary action-budget exhaustion is an inspection checkpoint, not a failure.

## Failure usefulness

A failed trial is usefully classified only when it has all of:

1. a non-empty machine-readable failure category or a non-healthy checkpoint verdict;
2. a preserved final or last-safe state;
3. a screenshot from the same checkpoint;
4. a checkpoint summary and evidence identifying the category, stalled loop, unsafe state, provider failure, or missing semantic capability.

Aborted trials caused by missing fixtures, invalid hashes, unavailable ROM, or local-provider infrastructure are reported separately and do not enter a gameplay success denominator. They must be rerun from the identical frozen case after repair.

## Acceptance gate

Milestone 5 passes only when one fixed commit proves all of the following:

1. at least 4 of the 5 frozen Capsule A cases succeed (80%);
2. at least 7 of the 10 frozen clean-boot trials receive the Boulder Badge (70%);
3. executed destructive or Nuzlocke-illegal actions total zero;
4. at least 95% of gameplay failures have a useful category and checkpoint bundle;
5. deterministic branch coverage passes for all named early-game surfaces;
6. ordinary repeated literal-button reliance has been removed from the evaluated paths;
7. no human gameplay intervention occurs during evaluation;
8. the relevant automated tests, static checks, repository hygiene checks, and evaluator self-tests pass.

## Long-run operation

The clean-boot matrix may be a long wall-clock evaluation. It must not be polled through automatic goal continuation. Before starting it, pause the active goal and install a scheduled monitor that checks durable trial summaries at a sensible interval, diagnoses preserved failures, and never stops a healthy run.

## Human burden

No new gameplay capture is currently required. Generated states remain provisional artifacts rather than promoted golden states; this is acceptable for a frozen evaluation derivative when its source, patch, invariants, and hashes are explicit. Human review is limited to a small sample of success/failure bundles after automated scoring.
