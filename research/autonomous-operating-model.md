# Autonomous Operating Model

Status: v0 working agreement
Last updated: 2026-06-30

This document preserves the revised operating approach for the Pokemon Player research project. It should be treated as required context after thread compaction, long pauses, or agent handoff.

## Core Project Goal

The project is not primarily "make an LLM beat Pokemon Red." That may be a fun side effect.

The core goal is to build a language-directed, state-aware Pokemon-playing agent that can:

- reason about the current game state and future chapter goals;
- announce and explain its decision-making;
- ask for help when appropriate;
- interpret live human/chat support later, including potentially adversarial input;
- choose typed skills expressed in planning language, not raw button language;
- use skills that disambiguate game controls from strategic planning;
- produce inspectable logs so failures teach us whether the problem was planning, state extraction, skill execution, recovery, prompting, or scenario design.

The LLM Director is intentionally important. Guardrails should make the game legible and safe for the Director, not replace Director strategy with deterministic scripts.

## Architecture Stance

The intended split is:

- Chapter layer: objective, constraints, current facts, future-relevant context, known risks, success checks.
- LLM Director: strategy, prioritization, tradeoffs, help-seeking, narration, chat interpretation, and choosing which skill should serve the current goal.
- Skill layer: typed, bounded translation from Director intent into reliable emulator control.
- Critic and verifier layer: state-grounded result checks, safety checks, progress checks, and failure attribution.
- Human layer: scarce high-leverage review, taste-setting, strategy direction, and approval of promoted evidence. Human availability should not block ordinary progress.

Chapter guidance should be a strategy brief, not a script. It may enforce safety or hard prerequisites, but it should not over-prescribe tactics merely because a weaker local model struggles.

## Action Budgets Are Checkpoints

An `action_budget_exhausted` outcome is not a failure by itself.

Action budgets are intentionally low so that runs stop at inspectable checkpoints before loops or drift get away from us. The important question is the health of the checkpoint:

- Did the run make coherent progress?
- Is the final state recoverable and inspectable?
- Did the Director's choices serve the current objective?
- Did any skill loop, mode drift, unsafe state, or model/tool error occur?
- Can the next segment safely continue from this state?

Reports should distinguish budget checkpoints from real failures. Suggested checkpoint verdicts:

- `healthy_continue`: coherent progress, safe state, continue automatically.
- `healthy_needs_review`: likely good, but worth human review later.
- `provisional_continue`: safe enough to continue under a stated assumption.
- `stalled_loop`: repeated action or skill pattern without meaningful progress.
- `unsafe_state`: low confidence, destructive risk, blackout risk, corrupt state, or unrecoverable mode.
- `skill_gap`: the Director needed an action that current skills do not represent well.
- `state_interpretation_gap`: available state/signals were misleading, incomplete, or ambiguous.
- `model_error`: local model timeout, malformed tool call, text response without tool, or similar runtime issue.

Only the unsafe and machine-unavailable categories should halt the current line of work. Other categories should trigger a patch, a rerun, a provisional continuation, or a pivot.

## Human Review Must Not Block Progress

Human review can improve confidence, but lack of human availability should not stop the project.

When human input would be helpful but is unavailable, choose the safest useful fallback:

1. Proceed with a conservative assumption.
   Mark the result as provisional, record the assumption, and continue if risk is low.

2. Create a deferred review item.
   Save a screenshot, state, report, and short explanation for later human review. Continue with adjacent work.

3. Build the missing capture or tooling autonomously.
   If existing skills can plausibly reach the needed state, try to collect it.

4. Use generated or derivative states.
   Clearly label them as provisional or generated. Do not promote them to golden without later validation.

5. Pivot to adjacent useful work.
   If a chapter is blocked, work on run interrogation, schema clarity, prompt construction, skill tests, promotion scaffolding, deterministic skill chains, or failure classification.

6. Run both safe alternatives.
   When ambiguity is safe and bounded, test both plausible approaches and compare outcomes.

True blockers should be rare: missing ROM, unavailable local machine/model with no useful fallback task, risk of corrupting important artifacts, or a decision whose wrong answer would make the project less trustworthy.

## Director Evaluation Is Separate From Task Completion

The Director should be evaluated on planning quality, not just final game completion.

For each action or segment, preserve enough evidence to ask:

- What facts did the Director see?
- What reasoning or plaintext explanation did it provide?
- Which skill and arguments did it choose?
- Did the selected skill serve the current chapter objective?
- Did the Director adapt after skill results?
- Did it ask for help when uncertainty was strategically appropriate?
- Did it avoid destructive or irrelevant choices?

A weak local model is useful because it exposes unclear schemas, missing state, ambiguous skill names, and brittle prompts. Weak-model mistakes should not automatically lead us to remove LLM agency. They should usually lead us to make the state and skills more legible.

## Skill Design Principle

Skills should be semantic and typed. They should match how a smart player describes an intention:

- `use_move` with valid move names.
- `switch_party_member` with valid party targets.
- `attempt_catch` with clear item/catch-attempt semantics.
- `navigate_within_*_region` with valid destination options.
- `enter_grass_search_loop` with approved patch options.
- `heal_at_pokecenter`.
- `purchase_pokemart_item` with item and quantity.
- `handle_nickname_prompt` and `enter_nickname_text`.

Skills should not hide broad strategy unless the skill's purpose is explicitly a bounded local loop. For example, a future `train_until_ready_for_brock` skill may be valid if it is treated as a typed bounded goal with progress reports, safety stops, and clear readiness criteria. It should not erase the Director's responsibility for choosing why training is needed.

`literal_button_press` is maintenance and recovery tooling. If it appears frequently during normal play, treat that as evidence of a missing semantic skill, a gating bug, or a state interpretation gap.

## New Default Run Loop

The preferred autonomous loop is:

1. Run a bounded segment from a known state.
2. Generate or update a run report with a checkpoint verdict.
3. If `healthy_continue`, continue automatically from the final state.
4. If `provisional_continue`, continue under the recorded assumption and queue review.
5. If `stalled_loop`, `skill_gap`, or `state_interpretation_gap`, patch the likely cause and rerun from the start of that segment.
6. If `model_error`, retry once after a local model health check; then pivot if needed.
7. If `unsafe_state`, roll back to the previous healthy checkpoint or pivot.
8. Periodically concatenate healthy segment videos for human review.

Long end-to-end runs remain useful smoke tests, but they should not be the only measure of progress. Short scenario slices are better for diagnosing the architecture:

- acquire Poke Balls and set a Viridian PokeCenter checkpoint;
- catch Route 22 Spearow;
- enter Viridian Forest and catch Pikachu;
- exit Viridian Forest;
- heal in Pewter;
- train for Brock readiness;
- challenge Brock and resolve the badge state.

## Implementation Needs

To enact this operating model, build or update:

- a run interrogator that reads canonical `director_segment_run_v1` reports while accepting legacy `local_gemma_chapter_run_v1` artifacts;
- checkpoint health classification separate from `finish.failureCategory`;
- report fields such as `checkpoint`, `verdict`, `confidence`, `continueRecommended`, `reviewItems`, and `fallbackTaken`;
- a "continue from last healthy or provisional checkpoint" workflow;
- automatic detection of repeated skill loops and literal-button overuse;
- a deferred human review queue for screenshots, states, and concise notes;
- Director decision audit summaries for planning quality;
- tests showing that budget exhaustion is treated as an inspection checkpoint, not a failure.

## Compaction Recovery Instructions

After context compaction or thread resume:

1. Read this document first.
2. Read `research/phase-0-charter.md` for the core research thesis.
3. Read `research/progression-chapters.md` for current chapter framing.
4. Treat human availability as helpful but non-blocking.
5. Treat action-budget stops as checkpoints until a checkpoint verdict says otherwise.
6. Preserve LLM Director agency unless safety, impossibility, or missing skills require bounded guardrails.

