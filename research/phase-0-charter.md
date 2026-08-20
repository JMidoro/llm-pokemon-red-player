# Phase 0 Research Charter and Experiment Contract

Status: v0 draft
Source plan: `research/plan.md`
Last updated: 2026-06-16

## Research Thesis

This project is not initially trying to train a monolithic policy that beats Pokemon Red. The v0 research thesis is:

> A Pokemon Red agent can be made practically steerable by combining symbolic game-state extraction, natural-language goal/directive handling, a typed skill interface, replayable scenario capsules, and selective learned policies only where scripted or heuristic execution fails.

The organizing artifact is the lab: deterministic emulation, state inspection, safe state construction, reproducible runs, logging, replay, and failure analysis.

## Supported Game Version

Initial target: Pokemon Red, provided locally as `research/PokemonRed.gb`.

The ROM file itself is not a repository artifact and must remain gitignored. The project pins the target by metadata:

- File size: 1,048,576 bytes
- Header title bytes: `POKEMON RED`
- SHA-256: `5CA7BA01642A3B27B0CC0B5349B52792795B62D3ED977E98A09390659AF96B7B`
- MD5: `3D45C1EE9ABD5738DF46D2BDDA8B57DC`

Save files, emulator states, replay bundles, screenshots, videos, and generated run artifacts are also local/generated artifacts unless a later phase explicitly promotes a small non-ROM fixture format.

## Architecture Hypothesis

The v0 architecture should follow this loop:

1. LLM director
2. Structured goal/directive compiler
3. State-aware planner and critic
4. Typed skill router
5. Scripted, heuristic, or learned executors
6. PyBoy emulator
7. RAM/screen/event/state extractor
8. Replay and evaluation harness
9. Director feedback loop

The LLM director should not press buttons directly except in tightly scoped diagnostic modes. It should reason over structured state and plaintext summaries, issue bounded goals, revise plans, and arbitrate operator directives. Completion must be verified from game state rather than from model confidence.

## Observation Policy

Default observation regime:

- RAM-first for game state, progress flags, party, inventory, battle/menu/dialogue state, and objective checks.
- Screen-derived features as secondary evidence and for UI/menu validation.
- Pixel-level control only for local control problems where it is genuinely useful.

Symbolic access is allowed because this is a steerable-agent research rig, not a human-like pixel-only benchmark.

## v0 Capsules

The first cycle will focus on two capsules plus one stretch candidate.

### Capsule A: Viridian Forest Catching

Goal family: catch Pikachu specifically in Viridian Forest, then navigate through Viridian Forest to the north exit, optionally accepting a safe nickname directive.

Why it matters: tests targeted encounter selection, wild encounters, catching, party updates, inventory preconditions, maze-like forest traversal, trainer-battle interruptions, and cosmetic directive handling.

### Capsule B: Cerulean / Misty Prep

Goal family: prepare for and/or defeat Misty under soft constraints such as avoiding excessive starter overleveling or trying to add a favorable team member.

Why it matters: tests strategy, battle planning, soft constraints, and readiness estimation while staying friendlier than midgame dungeon progression.

### Stretch Capsule: Rocket Hideout / Midgame Objective

Goal family: retrieve or progress toward a Rocket Hideout objective under lightly randomized party, item, and progress state.

Why it matters: tests non-sequential generality, dungeon navigation, key-item reasoning, trainer/item progression, and recovery. This is intentionally deferred unless the first two capsules are too easy or the lab matures quickly.

## Steerability Definition

For v0, steerability means the system can receive a single-user natural-language directive, classify its intent and risk, decide whether to accept, reject, defer, reinterpret, or ask for clarification, and then carry accepted directives into bounded goals that can be verified from state or logs.

This is not livestream chat. The operator is a turn-based directive source. Stream-shaped features such as aggregation, voting, cooldowns, and noisy multi-user input are explicitly later-phase concerns.

## Safety and Authority

The executor, planner, critic, and state tools may reject requests as impossible, unsafe, destructive, underspecified, or inconsistent with the current scenario.

Default safety policy:

- Glitches and exploits are forbidden by default.
- A scenario may opt into a specific glitch/exploit only with an explicit flag and success/failure criteria.
- Destructive actions are forbidden unless the scenario explicitly exists to test them in a sandboxed way.
- LLMs may propose structured state patches, but may not directly write arbitrary bytes into ROM, RAM, SRAM, save files, or emulator state.
- State mutation must pass typed validation and invariant checks.

Examples of destructive or high-risk actions include releasing important Pokemon, overwriting key moves without confirmation, spending all money, corrupting story flags, invalidating checksums, or creating impossible party/inventory states.

## Compute Contract

Available compute:

- Local development machine only.
- One NVIDIA RTX 3070 is available.
- No cloud budget.

Default v0 caps:

- Unit/golden-state checks: target under 10 minutes per full local run.
- Single capsule dry run: target under 30 minutes wall-clock.
- Batch capsule evaluation: target under 4 hours wall-clock on local hardware.
- Learned-option exploration, once allowed by later phases: max 8 RTX 3070 GPU-hours per candidate before review.
- No phase may begin without stating its expected compute cap.

RL or learned-policy work is not allowed to become the first expensive activity. It must be justified by replay/failure evidence from scripted or heuristic baselines.

## Human Labor Contract

Human work should create reusable leverage: directives, golden states, scenario templates, invariant decisions, failure labels, and review notes.

Default v0 caps:

- Failed-run review target during early lab work: under 10 minutes per selected failed run.
- Failed-run review target by replay/interrogation phase: under 5 minutes.
- Generated-state review target: under 2 minutes per sampled state.
- State-generation and directive-evaluation flows should use sampling rather than requiring review of every artifact.

No phase may begin without stating its expected human review burden.

## Minimum Run Record

Every run must record, at minimum:

- Run id
- Seed
- Scenario name and scenario version
- State version or state artifact id
- Agent version
- Config record
- Initial state summary
- Directive events, if any
- Structured goals
- Skill calls
- Button trace or replay reference
- State snapshots or event summaries
- Warnings and recovery triggers
- Final outcome

The exact schema may evolve, but these fields are the v0 contract.

## Success Definition for the First Research Cycle

The v0 approach worked if:

- Capsule A and Capsule B can both run from randomized starts.
- Generated states can be explained, inspected, and rejected when invalid.
- The directive harness handles a curated single-user directive deck with state-grounded accept/reject/defer decisions.
- The scripted/heuristic baseline completes Capsule A reliably enough to produce meaningful failure data.
- Failures are replayable or reconstructable and classified into useful categories.
- At least one decision about whether to introduce a learned option is made from logged failure evidence rather than intuition.

## Failure Definition for the First Research Cycle

The v0 approach failed, or needs major redesign, if:

- Core state extraction remains too brittle to support objective checks.
- Save/runtime state generation cannot be made safe enough for reusable capsule starts.
- Directive handling cannot reliably reject destructive or impossible requests.
- Runs cannot be replayed, reconstructed, or diagnosed well enough to improve the system.
- The scripted/heuristic baseline fails in ways the lab cannot attribute to state parsing, scenario design, planning, execution, recovery, or evaluation.
- Compute or human-review costs exceed the local-only contract before producing reusable artifacts.

## Phase Gates

Before any phase begins, it must state:

- Named hypothesis
- Expected failure mode
- Compute cap
- Human review burden
- Required artifacts
- Completion criteria

Before Phase 1 begins, the immediate decisions are:

- Confirm the local ROM hash above as the v0 target.
- Choose the first required state fields for Capsule A and Capsule B.
- Choose the local layout for ROMs, saves, generated states, traces, and reports.
- Decide whether the initial implementation is a Python package, a scripts-first lab, or a hybrid.

## Artifact Discipline

Good artifacts:

- Golden states
- State summaries
- Patch recipes
- Scenario templates
- Directive decks
- Run traces
- Failure labels
- Replay bundles
- Evaluation reports

Bad artifacts:

- One-off demos
- Unlogged successful runs
- Hand-edited mystery states
- Undocumented reward tweaks
- Policies trained against forgotten configs
