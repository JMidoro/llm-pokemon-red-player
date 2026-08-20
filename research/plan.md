Absolutely. Here’s the researcher-shaped stance: **we are not trying to prove that RL can beat Pokémon Red. We are trying to prove that a language-directed, state-aware, tool-enriched agent architecture can complete meaningful Pokémon tasks from varied starting conditions under limited compute and limited human labor.**

That difference matters. The wrong project becomes “train a little electric ferret to press buttons until the Elite Four collapses.” The right project becomes an experimental platform where every failure teaches us whether the problem is planning, state interpretation, execution, recovery, policy learning, or scenario construction.

Below is the planning doc.

# Roadmap: Language-Directed Pokémon Red Agent

## 0. Plan Review and Research Posture

The current plan is directionally strong, but I would tighten the thesis.

The core hypothesis should be:

**A Pokémon Red agent can be made practically steerable by combining symbolic game-state extraction, natural-language goal/directive handling, a typed skill interface, replayable scenario capsules, and selective learned policies only where scripted or heuristic execution fails.**

The plan should not start with a monolithic RL policy. Public Pokémon Red RL work has shown that the game is learnable in pieces, but also that full-game success is not the same as producing a general Pokémon-playing policy. The Rubinstein/Whidden Pokémon RL project reports beating Pokémon Red with a sub-10M-parameter policy, but explicitly frames the result as a technique for producing solutions rather than a reusable Pokémon-solving policy. It also emphasizes that PRET and PyBoy make Pokémon Red unusually inspectable compared with many games. ([Drubinstein][1])

This project should therefore treat **RL as a later, evidence-driven optimization layer**, not the organizing principle. The organizing principle should be the **lab**: state inspection, state mutation, scenario generation, logging, replay, and evaluation.

The two pushbacks you gave should become explicit design decisions:

First, early “chat” should not be modeled as livestream chat. It should be modeled as a **single-user directive channel**. The human operator sends natural-language directives in a turn-based exchange, and the LLM director decides whether to accept, reject, defer, or reinterpret them. This validates steerability without pretending one human approximates a crowd.

Second, state and replay tooling are not side quests. They are core research infrastructure. A text-to-state tool, state-to-plaintext Q&A, run replay, state diffing, failure interrogation, and capsule generation are what keep us from wandering into the fog with a butterfly net and calling it science.

## 1. Guiding Constraints

The project should assume:

Limited compute. Prefer CPU-friendly emulation, deterministic tools, small models, short-horizon learned options, and cached/replayable evals. PyBoy supports programmatic control/probing and multiple emulator instances, and its documentation and package notes emphasize headless/accelerated execution, frame skipping, and direct memory access, which makes it a good fit for compute-constrained experimentation. ([Pyboy][2]) ([PyPI][3])

Limited human labor. Avoid large behavior-cloning datasets, large manual annotation efforts, and heavy human-in-the-loop debugging. Any human work should create reusable leverage: directive decks, scenario templates, golden states, invariant definitions, and failure labels.

No real livestream chat at build time. Early evaluation uses single-user directives, scripted directive decks, and optionally machine-generated distractor directives later. Real multi-user chat behavior is a later integration challenge, not a prerequisite for validating the agent.

ROM/state fragility. We should pin a specific ROM/version and treat save-state mutation as a dangerous operation unless mediated by typed validators. The PRET `pokered` disassembly builds specific Red/Blue ROMs and exposes source, constants, maps, RAM definitions, and tools that can anchor this work. ([GitHub][4])

Symbolic access is allowed. We are not trying to benchmark human-like pixel-only perception. We are trying to build a streamable, steerable agent. RAM inspection is instrumentation, not shame.

## 2. Core Architecture Hypothesis

The intended architecture is:

LLM Director
→ structured goal/directive compiler
→ state-aware planner/critic
→ typed skill router
→ scripted, heuristic, or learned executors
→ PyBoy emulator
→ RAM/screen/event/state extractor
→ replay and evaluation harness
→ director feedback loop

The LLM should not press buttons directly except in highly constrained diagnostic modes. It should reason over plaintext and structured summaries, issue goals, revise plans, and arbitrate directives.

The executor should be allowed to say “no,” “impossible,” “need prerequisite,” “unsafe,” or “I am stuck.” The critic should verify completion from game state, not from the LLM’s confidence fumes.

Prior LLM-agent work supports this general shape. PokéAI uses Planning, Execution, and Critique agents with memory banks for Pokémon Red, and Voyager’s Minecraft agent uses an automatic curriculum, reusable skill library, environment feedback, and self-verification rather than a monolithic low-level controller. ([arXiv][5]) ([arXiv][6])

## 3. Non-Goals for the First Research Cycle

Do not optimize for beating the full game.

Do not train a single unified policy first.

Do not require real livestream chat.

Do not require pixel-only perception.

Do not rely on large human gameplay datasets.

Do not let the LLM write arbitrary bytes into RAM or save files.

Do not treat a successful scripted demo as proof of agentic robustness.

Do not treat a learned policy success as proof of steerability.

The first cycle is successful when the architecture can complete meaningful, varied, language-directed chapter capsules and produce inspectable failures.

---

# Phase 0: Research Charter and Experiment Contract

## Purpose

Define the project’s research questions, constraints, supported game version, evaluation philosophy, and artifact discipline before building. This is where we stop the project from growing extra heads in the basement.

## Methodology

Write a short experiment charter covering:

The supported Pokémon version and ROM assumptions.

The core architecture hypothesis.

The first two or three scenario capsules.

The definition of “steerability.”

The distinction between directive handling and livestream chat.

The compute budget per experiment.

The human labor budget per experiment.

The minimum logging/replay requirements.

The policy on glitches, exploits, destructive actions, and safety rails.

The preferred observation regime: RAM-first, screen as secondary, pixels for local control only where useful.

## KPIs

A frozen v0 research charter exists.

Every experiment has a named hypothesis.

Every experiment has an expected failure mode.

Every run has a seed, scenario version, state version, agent version, and config record.

No phase begins without an explicit compute cap and expected human review burden.

## Important Resources

The Pokémon RL writeup is useful here as a prior-art framing source because it makes clear that Pokémon Red is long-horizon, multi-task, nonlinear, and not cleanly solved by producing one run-winning policy. ([Drubinstein][1])

## Questions Before This Phase Can Begin

None.

## Questions Before This Phase Can Be Considered Complete

What exact game version are we supporting first?

What counts as “the approach worked” for the first research cycle?

What counts as “the approach failed”?

Which two or three capsules are in scope for v0?

What compute budget are we willing to spend per experiment class?

How much human review is acceptable per failed run?

Are glitches/exploits allowed by default, forbidden by default, or controlled by a scenario flag?

---

# Phase 1: Emulation Lab and Ground-Truth State Model

## Purpose

Build the minimum laboratory needed to load Pokémon Red, inspect state, advance frames, issue inputs, save/load emulator states, and produce reliable machine-readable and plaintext summaries.

This phase does not build the agent. It builds the microscope.

## Methodology

Use PyBoy as the emulator substrate. PyBoy is designed to be loaded as a Python object, controlled by scripts, and probed programmatically; it also supports save/load state operations and direct memory access. ([Pyboy][2]) ([Pyboy][2]) ([Pyboy][2])

Define a state inspector with two outputs:

A structured state representation for tools and evaluators.

A plaintext summary for the LLM director.

Start with a narrow but reliable state surface:

Current map.

Player x/y position and facing direction.

Battle state.

Text box/menu state.

Party species, levels, HP, status, moves.

Inventory essentials.

Money.

Badges.

Key event flags relevant to selected capsules.

Last detected event.

Goal-relevant facts.

Use golden states. A golden state is a known emulator/save state with expected extracted values. Every new parser field should be tested against at least one golden state.

## Testing Strategy

State extraction tests: compare extracted fields against manually verified golden states.

Determinism tests: load the same state, run the same button trace, confirm the same final high-level state.

Save/load tests: round-trip emulator states using PyBoy save/load.

Speed tests: measure headless execution throughput with rendering off or minimized.

State summary tests: verify that plaintext summaries preserve all goal-relevant facts while hiding irrelevant byte soup.

## KPIs

At least 20 golden states covering overworld, battle, menu, text box, Pokémon Center, wild encounter, trainer battle, and capsule starts.

Core state fields are correct on at least 98% of golden-state checks.

State summaries contain no known misleading claims across the golden set.

Save/load determinism succeeds on repeated traces for all golden states.

Headless run speed is measured and recorded before any RL training is considered.

## Important Resources

Data Crystal’s Pokémon Red/Blue RAM map is a key reference and explicitly points to the Pokémon Red disassembly for additional WRAM, VRAM, HRAM, and SRAM addresses. ([Data Crystal][7])

The PRET `pokered` disassembly should be treated as the deeper source of truth for symbols, maps, constants, scripts, and memory definitions. ([GitHub][4])

PyBoy’s memory interface supports reading/writing ROM/RAM spaces, with cautions around banked memory and special registers. That caution should shape the validator design later. ([Pyboy][2])

## Questions Before This Phase Can Begin

Which ROM/version is the initial target?

Which state fields are required for the first two capsules?

Will the first state model read from WRAM only, SRAM only, emulator APIs, or a mixture?

What is the minimum plaintext state summary the director needs?

What is the supported save-state format for v0?

## Questions Before This Phase Can Be Considered Complete

Can we reliably tell where the player is?

Can we reliably tell whether the game is in overworld, battle, menu, or dialogue?

Can we reliably inspect party, HP, moves, items, money, and badge state?

Can we save, reload, and replay a short trace deterministically?

Can the plaintext state summary support basic Q&A like “Can I catch Pikachu right now?” or “Why can’t I fight Misty yet?”

---

# Phase 2: State Mutation and Text-to-State Tooling

## Purpose

Create safe tools for generating derivative test states from plaintext requests, without relying on manual save editing or reckless byte poking.

This is the phase that turns “Swap Bulbasaur for Charmander” from a hand-edited hack into a validated test fixture.

## Methodology

Build a typed patch system.

The LLM may translate plaintext into a proposed state edit, but it should not directly write bytes. A validator should convert approved operations into concrete changes and reject unsafe or inconsistent requests.

State mutation should happen in two layers:

Durable save edits for party, inventory, money, badges, boxes, and long-lived event flags.

Runtime/emulator-state edits for exact capsule start conditions, temporary flags, immediate battle/menu/text state, and fine-grained positioning.

This split matters because Generation I save data has checksums and banked structure. Bulbapedia documents that the Generation I main save checksum is only 8 bits, with specific checksum behavior and corruption consequences if invalid. ([Bulbapedia][8]) Data Crystal’s RAM map also identifies SRAM bank regions, party data, current box data, and the main data checksum location. ([Data Crystal][7])

## Testing Strategy

Round-trip tests: plaintext request → structured patch → applied state → inspected summary.

Invariant tests: party count matches party list, HP does not exceed max HP, moves are legal or intentionally overridden, item counts are valid, money bounds are sane, key flags are consistent.

Checksum tests: edited saves load cleanly and expose Continue where expected.

Metamorphic tests: changing starter species should not accidentally change badges, money, map position, or rival name unless requested.

Negative tests: reject impossible or dangerous edits, such as invalid species IDs, broken party sizes, corrupt checksums, illegal map positions, or inconsistent story flags.

Human-review sampling: review a small random subset of generated states, not every state.

## KPIs

At least 95% of generated simple derivative states load successfully.

Zero known checksum-corrupting accepted patches.

Zero accepted patches that violate core invariants.

Text-to-state requests for supported operations succeed at least 90% of the time after validation.

Median human review time per generated state is under two minutes for sampled states.

The tool can produce at least 25 valid randomized variants for each v0 capsule without manual editing.

## Important Resources

Bulbapedia’s Generation I save data structure and checksum notes are directly relevant to safe save editing. ([Bulbapedia][8])

Data Crystal and PRET should anchor the mapping from semantic state to actual memory/save layout. ([Data Crystal][7]) ([GitHub][4])

Existing Gen I save editors such as Rhydon/PKHeX-adjacent tooling are worth studying for conventions, but our project should still use its own typed validator because our needs are scenario-generation and experimental reproducibility, not general-purpose UI editing.

## Questions Before This Phase Can Begin

Which state edits are officially supported in v0?

Which edits must be save-file edits versus runtime/emulator-state edits?

Which invariants are mandatory?

Which invariants are warnings only?

How do we verify that generated states are playable, not merely loadable?

What degree of LLM autonomy is allowed in patch proposal?

## Questions Before This Phase Can Be Considered Complete

Can we generate a derivative state from a plaintext instruction and verify it through the inspector?

Can we safely randomize capsule starts without hand-editing each one?

Can we detect and reject invalid or contradictory state requests?

Can we repair or recompute checksums where needed?

Can the generated state be explained back in plaintext accurately?

---

# Phase 3: Directive Semantics and LLM Director Harness

## Purpose

Validate natural-language steerability without pretending to have livestream chat.

This phase builds the single-user directive interface: a human sends turn-based directives, and the LLM director decides whether to incorporate them into its plan.

## Methodology

Create a curated directive deck with labeled examples:

Strategic directives.

Cosmetic directives.

Constraint-setting directives.

Playful but non-optimal directives.

Ambiguous directives.

Impossible directives.

Destructive directives.

Derailing directives.

The director should classify each directive by intent, risk, compatibility with the current objective, and recommended response. The response space should include accept, reject, defer, reinterpret, ask for confirmation only when truly necessary, or convert into a bounded subgoal.

This is not yet about “chat heuristics.” It is about whether the agent has a sane theory of authority. The player/operator can influence goals, but should not automatically override the run’s safety constraints or current plan.

## Testing Strategy

Golden directive tests: fixed game states plus fixed directives with expected accept/reject/defer outcomes.

State-dependent directive tests: the same directive should be accepted in one state and rejected in another.

Example: “Use a Potion” may be accepted at low HP and rejected at full HP.

Adversarial directive tests: “Release Pikachu,” “Spend all our money,” “Teach over the best move,” “Run from the legendary,” and so on.

Ambiguity tests: directives like “go back” or “use the bird” should be interpreted only if state context makes them clear.

Regression tests: every directive failure becomes a new test case.

## KPIs

At least 100 curated directive cases in v0.

At least 90% accept/reject/defer accuracy against human-authored labels.

Zero accepted destructive directives in the golden test set.

At least 90% of accepted directives compile into bounded, inspectable goals or constraints.

Director explanations are concise and state-grounded in at least 90% of sampled cases.

No real chat simulation is required to complete the phase.

## Important Resources

PokéAI is relevant here because it frames Pokémon Red progression as planning, execution, and critique rather than raw low-level control. ([arXiv][5])

Voyager is relevant because its skill-library and feedback-loop approach supports compositional, language-directed behavior without parameter fine-tuning as the first move. ([arXiv][6])

## Questions Before This Phase Can Begin

What directive categories do we care about in v0?

What are the hard safety constraints?

What directives should be accepted for entertainment value even when not optimal?

What directives should be rejected even if they would be funny?

How much authority does the single human operator have compared with the director’s current plan?

What tone should the director use when rejecting a directive?

## Questions Before This Phase Can Be Considered Complete

Can the director distinguish strategic, cosmetic, playful, harmful, and impossible directives?

Can the director revise a plan based on a safe directive?

Can the director reject destructive directives without derailing execution?

Can directive decisions be evaluated offline from logged states?

Can a directive be carried through to execution and verified in game state?

---

# Phase 4: Scenario Capsule Design and Evaluation Protocol

## Purpose

Define the holistic tests: non-sequential Pokémon Red “chapter capsules” with lightly randomized beginning states.

This phase determines what “the system works” means.

## Methodology

Use scenario capsules, not full-game progression.

Each capsule should include:

A base state.

A natural-language objective.

Supported starting-state randomizations.

Optional directive schedule.

Success conditions.

Failure conditions.

Abort conditions.

Step/button/time budget.

Required logged events.

Relevant state fields.

Known impossible-state guards.

Suggested v0 capsules:

**Capsule A: Viridian Forest Catching**

Goal family: catch Pikachu specifically in Viridian Forest, then navigate through Viridian Forest to the north exit, optionally accept a safe nickname directive.

Why it matters: tests targeted encounter selection, catching, party update awareness, inventory preconditions, maze-like forest traversal, trainer-battle interruptions, and cosmetic directive handling.

**Capsule B: Rocket Hideout / Midgame Objective**

Goal family: retrieve or progress toward a key Rocket Hideout objective under lightly randomized party, item, and progress state.

Why it matters: tests non-sequential generality, dungeon navigation, trainer/item progression, key-item reasoning, and recovery.

**Capsule C: Cerulean / Misty Prep**

Goal family: prepare for and/or defeat Misty under soft constraints such as “don’t overlevel starter” or “try to add an Electric/Grass-friendly team member.”

Why it matters: tests strategy, battle planning, soft constraints, and readiness estimation.

For v0, I would treat A and B as the non-sequential core, with C as the strategic/battle-prep capsule if B is too brittle too early. Rocket Hideout is more architecture-revealing, but Cerulean is a friendlier bridge. Choose the pain level deliberately.

## Testing Strategy

Scenario validity tests: every randomized start must be loadable, playable, and goal-relevant.

Light randomization: vary party composition, HP, items, money, location within bounded regions, and partial progress flags.

Holdout starts: reserve some random seeds and state variants that are never used during executor tuning.

Impossible-goal tests: no Poké Balls for catching, low HP with no healing access, wrong story flags, invalid route access.

Ablation tests: run the same capsule with and without directives, with and without the LLM director, and with scripted versus learned options where applicable.

## KPIs

At least two non-sequential capsule families defined before learned-policy work begins.

At least 25 valid randomized starts per capsule.

At least 5 impossible or degraded-condition starts per capsule.

At least 20% of capsule starts held out for final validation.

Each capsule has clear success, failure, timeout, and abort conditions.

Each capsule produces useful failure data in dry runs.

## Important Resources

The PokeRL paper is useful as a warning label: it calls out sparse rewards, partial observability, menu spam, action loops, movement semantics, and memoryless exploration as practical failure modes in Pokémon Red RL environments. ([arXiv][9]) Those failure modes should directly inform capsule failure conditions and recovery metrics.

## Questions Before This Phase Can Begin

Which two capsules are mandatory for v0?

Is Rocket Hideout in v0, or is Cerulean/Misty the second capsule?

What degree of randomization is allowed before a state becomes implausible?

What are the exact success and failure criteria for each capsule?

What is the maximum button/step/frame budget for each capsule?

Which starts are training/tuning starts versus held-out eval starts?

## Questions Before This Phase Can Be Considered Complete

Can every capsule be instantiated from a base state and randomization recipe?

Can every capsule be summarized in plaintext for the director?

Can the evaluator determine success/failure from game state rather than narrative claims?

Can impossible states be detected cleanly?

Do the capsules stress different parts of the architecture?

---

# Phase 5: Scripted and Heuristic Executor Baseline

## Purpose

Build a boring baseline executor before introducing RL.

This phase answers: “How far can structured state, scripts, heuristics, and a director get us?”

That answer is crucial. If a scripted baseline fails mysteriously, RL will not make the mystery more scientific. It will just add fog machines.

## Methodology

Implement a typed skill interface with a small set of dependable skills:

Advance dialogue.

Navigate to known location.

Move to nearby tile.

Interact with NPC/object.

Open/close menu.

Inspect party.

Use item.

Heal.

Buy item.

Handle wild battle.

Attempt catch.

Handle nickname.

Basic trainer battle.

Detect completion.

Detect stuckness.

Recover from menu/text/battle drift.

Execution should be state-driven and critic-verified. The LLM director proposes goals; the executor translates goals into skills; the critic verifies whether the objective actually completed.

Use heuristics where the game is symbolic and constrained. Battle decisions should initially use type/status/HP/item logic rather than learned policies. Menuing should be deterministic. Navigation can begin with map-aware planning plus local correction.

## Testing Strategy

Unit tests for each skill on golden states.

Integration tests for Capsule A.

Dry runs for Capsule B/C without expecting high success.

Skill idempotence tests: repeated calls should not cause destructive drift.

Recovery tests: start in menu, text box, wrong facing direction, low HP, or unexpected battle.

State-critic tests: verify that completion is detected only when game state supports it.

## KPIs

Capsule A success rate: initial target 70%+ on randomized non-held-out starts.

Capsule A destructive-action rate: 0%.

Capsule A nickname directive success: 80%+ when a safe nickname directive is triggered.

Capsule B or C dry-run success: any nonzero rate is useful; target should be set after baseline observation.

Median stuck detection time below a predefined threshold.

Every failed run has a logged final failure category.

Human intervention is not required during normal eval runs.

## Important Resources

PyBoy’s save/load state and memory access support this style of repeatable integration testing. ([Pyboy][2]) ([Pyboy][2])

The Data Crystal RAM map and PRET disassembly remain core references for event flags, player state, party state, inventory, and map IDs. ([Data Crystal][7]) ([GitHub][4])

## Questions Before This Phase Can Begin

Which skills are required for Capsule A?

Which skills are required for the second capsule?

What skills are deterministic versus heuristic?

What destructive actions are disallowed?

What does the executor do when the director requests an impossible goal?

What are the recovery behaviors for menu loops, text loops, unexpected battles, and low HP?

## Questions Before This Phase Can Be Considered Complete

Can the baseline complete Capsule A from randomized starts?

Can the executor reject or repair impossible prerequisites?

Can the critic verify objective completion from state?

Can failures be reproduced from saved traces?

Can we identify which failures are due to planning, state parsing, skill execution, or scenario generation?

---

# Phase 6: Replay, Run Interrogation, and Failure Taxonomy

## Purpose

Make every run inspectable.

This phase is where failed runs become data instead of little cursed movies.

## Methodology

Log every run as a timeline:

Initial state.

Scenario config.

Randomization seed.

Directive events.

Director messages.

Structured goals.

Skill calls.

Button traces.

State snapshots.

Detected events.

Warnings.

Stuck/recovery triggers.

Final outcome.

Build a run interrogator that can answer questions about a trace:

Why did this run fail?

When did progress stop?

What was the last useful event?

Did the agent have the required item?

Did it misread state?

Did it loop?

Did the director choose the wrong goal?

Did a skill fail?

Was the scenario invalid?

Did the critic miss completion?

This can be LLM-assisted, but it should rely on structured logs and state diffs rather than video vibes.

## Testing Strategy

Replay determinism tests: same initial state and input trace should reproduce the same outcome.

Event extraction tests: known events should appear in the timeline.

Failure classification tests: hand-label a small set of failures and compare automated classification.

Triage-time tests: measure how long it takes a human to understand a failed run with and without the tooling.

Coverage tests: every failure should map to at least one known failure category or become a new category.

## KPIs

At least 95% of runs are replayable or have sufficient logs to diagnose.

At least 90% of failed runs receive a useful failure classification.

Median human triage time per failed run under five minutes.

Every recurring failure class has an owner phase: state, scenario, director, executor, recovery, or learned option.

Failure taxonomy stabilizes enough that new categories become rare.

## Important Resources

PyBoy exposes a RecordReplay plugin flag and rewind support in its plugin kwargs, which may be useful for replay tooling, though the project should still maintain its own structured run logs. ([Pyboy][2])

PokeRL’s documented failure modes should seed the initial taxonomy: loops, sparse rewards, button spam, incorrect movement semantics, and memoryless exploration. ([arXiv][9])

## Questions Before This Phase Can Begin

What minimal trace is required to reproduce a run?

How frequently do we snapshot state?

Which events must be detected explicitly?

What is the first version of the failure taxonomy?

What artifacts are too large to keep for every run?

Which logs are for machine analysis versus human debugging?

## Questions Before This Phase Can Be Considered Complete

Can a failed run be replayed or reconstructed?

Can the interrogator explain the failure using logged evidence?

Can repeated failures be clustered?

Can failure clusters drive decisions about whether to script, fix state parsing, improve planning, or train a learned option?

Can we compare two agent versions on the same scenario seeds?

---

# Phase 7: Selective Learned Options

## Purpose

Introduce RL or learned policies only where the replay/failure data says they are needed.

This phase should be ruthlessly empirical. No “RL because it’s fancy.” RL must earn its chair at the table.

## Methodology

Candidate learned options:

Local navigation around obstacles and NPCs.

Unstuck behavior.

Grass search and encounter management.

Short-horizon dungeon movement.

Trainer pathing.

Possibly battle execution later, but only after symbolic/heuristic battle logic has clear bottlenecks.

Use small, goal-conditioned option policies. The policy should receive a compact observation surface: screen features where useful, RAM-derived state where allowed, local map context, previous action history, and a structured local goal.

Training should be capsule-adjacent, not full-game. Use short episodes, randomized starts, explicit success conditions, and tight step budgets. Prefer headless PyBoy execution, frame skipping, and parallel CPU instances before considering expensive GPU-heavy setups. PyBoy’s package notes report major speedups from no-rendering and frame skipping, with examples of hundreds of times real-time in favorable settings. ([PyPI][3])

Reward design should be conservative. PokeRL’s findings are directly relevant: dense shaping can help, but agents can exploit rewards, spam buttons, loop, or wander unproductively if the environment does not model these failure modes. ([arXiv][9])

## Testing Strategy

Before/after tests against the scripted/heuristic baseline on identical seeds.

Holdout start tests.

Ablations: learned option versus heuristic, with and without anti-loop penalties, with and without RAM-derived features.

Compute-ledger tests: measure improvement per simulated hour and per wall-clock hour.

Safety regression tests: learned option must not increase destructive actions or invalid states.

Generalization tests: policy trained on one map region should be tested on related but unseen starts where reasonable.

## KPIs

A learned option must beat the baseline on its target failure class by a meaningful margin.

Suggested initial gate: at least 20% relative reduction in that failure class or at least 10 percentage-point absolute improvement on a capsule metric, within the compute cap.

No increase in destructive-action rate.

No increase in invalid menu/item behavior.

Learned option performance holds on reserved seeds.

Training curves and failure examples are logged.

If an option does not beat the heuristic within the compute cap, retire or redesign it.

## Important Resources

PokeRL is the primary methodological warning source for loop-aware wrappers, anti-spam mechanisms, hierarchical rewards, movement semantics, and curriculum design. ([arXiv][9])

The earlier Rubinstein/Whidden Pokémon RL project is useful for understanding what larger RL attempts needed in terms of observations, shaping, and engineering, but our project should stay smaller and more diagnostic. ([Drubinstein][1])

## Questions Before This Phase Can Begin

Which failure class is being targeted?

What is the scripted/heuristic baseline for that failure class?

What is the compute cap?

What is the episode definition?

What observations are allowed?

What actions are allowed?

What reward terms are necessary, and what reward exploits do we expect?

What would make us abandon this learned option?

## Questions Before This Phase Can Be Considered Complete

Did the learned option improve the target metric on held-out starts?

Did it stay within compute budget?

Did it avoid new safety failures?

Did replay analysis show qualitatively better behavior, not just metric gaming?

Is the learned option reusable across capsules or narrowly overfit?

Should this option replace, augment, or remain behind the heuristic executor?

---

# Phase 8: Holistic Multi-Capsule Validation

## Purpose

Validate the architecture as a whole across non-sequential chapter capsules.

This is the “does the beast have a nervous system?” phase.

## Methodology

Freeze an evaluation suite.

Run the same director, state inspector, directive harness, skill interface, executor, critic, and logging stack across all capsules.

Use held-out randomized starts.

Use a fixed directive deck subset.

Run ablations:

No directives.

Director disabled or replaced with static planner.

State summaries only versus structured state plus summaries.

Scripted executor only versus learned-option-enhanced executor.

Capsule-specific hacks disabled.

Score the system across three dimensions:

Task competence.

Steerability.

Diagnosability.

Task competence means it completes the capsule objective.

Steerability means it appropriately incorporates, rejects, or defers directives.

Diagnosability means failures are logged, replayable, and attributable.

## Testing Strategy

Batch evals across all capsule starts.

Seeded comparisons between agent versions.

Directive stress tests.

Impossible-state tests.

Heldout-state final evals.

Failure-cluster review.

Compute/cost review.

Human-review audit of a small sample of successes and failures.

## KPIs

Capsule A target: 80%+ success on held-out randomized starts.

Second capsule target: 50%+ initial success if Rocket Hideout, 70%+ if Cerulean/Misty. Adjust after first dry run, but freeze the threshold before tuning.

Destructive-action rate: 0%.

Impossible-goal handling: 90%+ clean abort/replan rate.

Directive handling: 90%+ correct accept/reject/defer on labeled directive cases.

Run diagnosability: 95%+ of failures have a useful trace and category.

Human intervention during eval: 0 during runs, limited review after runs.

Compute budget: all evals runnable on the intended development hardware without heroic cloud spending.

## Important Resources

PokéAI and Voyager are relevant architectural comparators for planner/executor/critic loops and reusable skill libraries. ([arXiv][5]) ([arXiv][6])

PokeRL and the Pokémon RL project remain useful comparators for what RL-heavy approaches accomplish and where they struggle. ([Drubinstein][1]) ([arXiv][9])

## Questions Before This Phase Can Begin

Are the eval capsules frozen?

Are held-out starts truly held out?

Are the success/failure thresholds frozen?

Which agent variants are being compared?

Which learned options, if any, are included?

What is the maximum evaluation budget?

What would falsify the architecture hypothesis?

## Questions Before This Phase Can Be Considered Complete

Can the same architecture handle multiple non-sequential capsules?

Does the director improve steerability without harming task success too much?

Do directives affect behavior in observable, appropriate ways?

Are failures attributable rather than mysterious?

Are learned options worth their compute cost?

Do we have enough evidence to decide whether to expand, refactor, or distill?

---

# Phase 9: Stream-Shaped Interaction Layer

## Purpose

Prepare the system for eventual livestream use without pretending that real chat has already been solved.

This phase comes after the architecture works in controlled single-user directive mode.

## Methodology

Extend the directive harness into a stream-shaped interface.

At first, still use synthetic or single-user inputs, but add stream-like concepts:

Directive priority.

Directive aggregation.

Cooldowns.

Nickname voting.

Safe command classes.

Rejected command classes.

Director narration.

Plan updates.

Viewer-facing explanations.

The agent should remain sovereign over destructive or derailing inputs. Chat can suggest, name, flavor, tease, and occasionally redirect. It should not be allowed to turn the run into a bag-fire unless the scenario explicitly enables chaos mode.

## Testing Strategy

Replay-based stream simulations: feed directive scripts into known run traces.

Synthetic multi-directive bursts.

Nickname-selection tests.

Safety rejection tests.

Latency tests.

Narration coherence tests.

Human review of sampled interactions.

## KPIs

The director can process directive bursts without derailing execution.

Safe cosmetic inputs are incorporated at high rates.

Destructive inputs are rejected at near-100% rates.

Narration remains consistent with actual game state.

The stream interface does not materially increase task failure rate in controlled evals.

Human-authored directive scripts can be reused across runs.

## Important Resources

The same planner/executor/critic literature remains relevant, but this phase is more product/interface research than core game-playing research.

## Questions Before This Phase Can Begin

Has single-user directive handling passed Phase 8?

What kinds of chat input are allowed to affect gameplay?

What kinds of chat input are cosmetic only?

What kinds of chat input are always rejected?

How should conflicting directives be resolved?

How should nickname suggestions be filtered and selected?

What is the persona boundary between entertainment and control?

## Questions Before This Phase Can Be Considered Complete

Can stream-shaped input be incorporated without reducing capsule success below threshold?

Can the director explain why it accepted or rejected directives?

Can the system handle multiple simultaneous suggestions?

Can cosmetic directives produce visible game effects?

Can the system preserve run integrity under noisy inputs?

---

# Phase 10: Distillation and Unified Policy Track

## Purpose

Only after the modular architecture works, consider whether a more unified learned policy is useful.

This is not the first mountain. This is the later mountain with a suspiciously nice hat.

## Methodology

Collect successful and failed traces from the modular system.

Use traces as data for:

Goal-conditioned policy learning.

Skill-router distillation.

Option-selection models.

Recovery classifiers.

Battle-policy improvement.

State-to-action imitation for narrow skills.

The “unified policy” should be defined carefully. It might mean:

A shared encoder across skills.

A learned skill router.

A goal-conditioned local controller.

A model that chooses among options.

A full button-level policy.

Those are not the same. The roadmap should resist collapsing them into one magic phrase.

## Testing Strategy

Compare distilled components against the modular baseline.

Evaluate on held-out capsules and held-out random starts.

Run safety regressions.

Check directive compliance.

Check recovery behavior.

Check whether distilled behavior is still interpretable enough for stream use.

## KPIs

Distilled component improves latency, success, generalization, or simplicity without damaging steerability.

No increase in destructive-action rate.

No meaningful loss of inspectability unless justified by major performance gain.

Distilled model works across at least two capsule families.

Distillation uses logged traces rather than requiring large new human datasets.

## Important Resources

Voyager’s emphasis on interpretable, reusable, compositional skills is a useful counterweight here: distillation should not destroy the properties that made the system steerable in the first place. ([arXiv][6])

## Questions Before This Phase Can Begin

What exactly do we mean by “unified policy”?

Which modular component is the bottleneck?

Do we have enough traces to train anything useful?

What metric must improve?

What interpretability are we willing to lose?

What safety rails remain outside the learned model?

## Questions Before This Phase Can Be Considered Complete

Did distillation improve the chosen metric?

Did it preserve directive handling?

Did it preserve failure diagnosability?

Did it generalize beyond the traces it learned from?

Is the distilled component better than the modular version, or merely cooler?

---

# Cross-Phase Evaluation Principles

## Every Phase Should Produce Reusable Artifacts

Good artifacts:

Golden states.

State summaries.

Patch recipes.

Scenario templates.

Directive decks.

Run traces.

Failure labels.

Replay bundles.

Evaluation reports.

Bad artifacts:

One-off demos.

Unlogged “it worked once” runs.

Hand-edited mystery states.

Undocumented reward tweaks.

Policies trained against forgotten configs.

## Prefer Falsifiable Questions

Examples:

Can text-to-state generate 25 valid Viridian Forest variants?

Can the director reject 100% of destructive directives in the golden deck?

Can the baseline complete Capsule A with no RL?

Does a learned local navigation option reduce stuck failures on held-out seeds?

Does the same director work across early-game and midgame capsules?

## Maintain Three Scoreboards

Task scoreboard:

Completion rate.

Step/button budget.

Resource usage.

Faint/blackout rate.

Invalid action rate.

Steerability scoreboard:

Directive accept/reject/defer accuracy.

Cosmetic directive completion.

Goal revision correctness.

Unsafe directive rejection.

Plan consistency.

Research scoreboard:

Run reproducibility.

Failure diagnosability.

Human triage time.

Compute per experiment.

Scenario-generation throughput.

Regression count.

## Suggested First v0 Success Bar

The first meaningful green light would be:

Capsule A and one non-sequential second capsule are both running from randomized starts.

The system can generate derivative states from plaintext and verify them.

The director can handle a curated single-user directive deck.

The scripted/heuristic baseline completes Capsule A reliably.

Failures are replayable and categorized.

At least one decision about RL is made from failure data rather than intuition.

That would be enough evidence to say: yes, this architecture has legs. Maybe not Dragonite legs yet, but legs.

## My Strongest Recommendation

Build this in the following order:

State lab.

Text-to-state.

Directive harness.

Capsule authoring.

Scripted executor.

Replay interrogation.

Only then learned options.

The temptation will be to train early because training feels like progress. But for this project, the real unlock is **cheap, precise experimental control**. Once we can spawn “Charmander Lv8, no Pikachu, five balls, Viridian Forest entrance, nickname directive pending” from plaintext and then replay exactly why the agent failed, the rest of the project becomes tractable.

That’s the difference between doing Pokémon RL and building a Pokémon agent research rig. The rig is the treasure chest. The policy is just one of the weird little jewels inside it.

[1]: https://drubinstein.github.io/pokerl/ "Learning Pokémon With Reinforcement Learning | Pokémon RL"
[2]: https://docs.pyboy.dk/ "pyboy API documentation"
[3]: https://pypi.org/project/pyboy/ "pyboy · PyPI"
[4]: https://github.com/pret/pokered "GitHub - pret/pokered: Disassembly of Pokémon Red/Blue · GitHub"
[5]: https://arxiv.org/abs/2506.23689 "[2506.23689] PokéAI: A Goal-Generating, Battle-Optimizing Multi-agent System for Pokemon Red"
[6]: https://arxiv.org/abs/2305.16291 "[2305.16291] Voyager: An Open-Ended Embodied Agent with Large Language Models"
[7]: https://datacrystal.tcrf.net/wiki/Pok%C3%A9mon_Red_and_Blue/RAM_map "Pokémon Red and Blue/RAM map - Data Crystal"
[8]: https://bulbapedia.bulbagarden.net/wiki/Save_data_structure_%28Generation_I%29 "Save data structure (Generation I) - Bulbapedia, the community-driven Pokémon encyclopedia"
[9]: https://arxiv.org/html/2604.10812v1 "PokeRL: Reinforcement Learning for Pokémon Red"
