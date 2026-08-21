# Durable Segment Supervisor

Milestone 3 adds a provider-neutral process supervisor around the bounded chapter runner. It owns continuation, process exclusivity, recovery, artifact registration, and deferred review; the LLM Director still owns Pokemon strategy through semantic skills.

## Start a lineage

The first launch needs an existing safe emulator state. Later launches recover the lineage from its manifest and ignore `--initial-state` unless a new lineage is being created.

```powershell
.\.venv\Scripts\python.exe scripts\run_segment_supervisor.py `
  --lineage-id early-game-development `
  --initial-state research\golden-states\local\pallet_overworld_started.state `
  --provider lmstudio-chat `
  --model google/gemma-4-e4b `
  --no-video
```

The same command can use `openai-responses` or `replay`. Provider choice changes only adapter configuration; chapter logic, semantic tools, reports, checkpoint policy, and supervisor behavior remain unchanged. Credentials are loaded from the local environment or `.env` and are never written to supervisor artifacts.

For ordinary host operation, the PowerShell launcher also starts Remote Operations when needed and keeps the supervisor hidden in the background:

```powershell
.\scripts\supervisor.ps1 -Action Start `
  -LineageId early-game-development `
  -InitialState research\golden-states\local\pallet_overworld_started.state `
  -Provider lmstudio-chat `
  -Model google/gemma-4-e4b
```

`-Action Status`, `-Action Stop`, and `-Action EmergencyStop` provide local lifecycle control. Stop actions write the same durable boundary control used by the phone UI; they do not terminate an emulator input sequence mid-action.

Use the same command after a host or supervisor restart. An OS-backed lease prevents a second supervisor from operating on the same lineage. If the previous child segment is still alive, the replacement waits for and adopts it before considering another launch.

## State and continuation policy

The durable state machine is:

- `idle`, `starting`, `running`, and `checkpointing` for normal work;
- `paused` for durable operator pauses and safe operator stops;
- `waiting_review` for safe checkpoints that policy does not permit automatically;
- `blocked` for unsafe, repeated model, stalled, skill-gap, or interpretation-gap outcomes;
- `completed` for a chapter success or an explicit bounded supervisor limit;
- `failed` for supervisor, artifact, disk-space, or missing-safe-state failures.

`healthy_continue` advances from the hashed `finalState`. `provisional_continue` queues review and advances when provisional continuation is enabled. A model error receives one retry from the unchanged safe input only after a provider health check. Repeated model errors are quarantined. `unsafe_state` never replaces the last safe state. Stalled loops, skill gaps, and state-interpretation gaps preserve their bundles and enter the review/failure queues.

Every terminal supervisor stop writes `final-checkpoint.json` with a stable last-safe-state reference and a machine-readable reason.

## Durable files

Each lineage lives below `research/artifacts/segment-supervisor/lineages/<lineage-id>/`:

- `state.json`, `heartbeat.json`, `lease.json`, and the OS-held `lease.lock`;
- `manifest.json` with sequence and last-safe-state history;
- `segments/<segment-id>/manifest.json` plus report, checkpoint, final state, screenshot, process logs, and video when enabled;
- `review-queue/*.json`, `failures/*.json`, and atomic event records;
- `operator-stop.json` for a host-local stop signal independent of the Operations service;
- `final-checkpoint.json` for the latest supervisor stop.

JSON records are written to a fully flushed temporary file and atomically replaced. Required artifact records include byte size and SHA-256. A completed segment manifest is registered in the lineage only after its report, checkpoint, state, and screenshot are stable.

## Remote Operations

The existing private `/operations` page now reads the newest supervisor lineage in addition to the active bounded runner. It shows supervisor health, lineage and segment counts, current state, latest verdict, queued reviews, failures, and stable segment history. Existing pause, resume, stop-after-action, and emergency-stop commands remain durable when the phone disconnects.

Pause waits at a semantic action boundary and keeps the supervisor alive until resume. Stop-after-action and emergency-stop produce a final segment checkpoint and stop unattended continuation. The page never exposes credentials, ROM/save paths, raw provider payloads, arbitrary filesystem access, or raw emulator buttons.

## Verification harnesses

The fault evaluator is ROM-free and uses no model tokens:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_supervisor_faults.py
```

It samples stalled loops, state-interpretation gaps, unsafe states, repeated model failures, and missing reports, then checks stale-lease recovery, disk-pressure shutdown, partial-state recovery, and concurrent lease rejection. The summary records the percentage diagnosable without video; the Milestone 3 target is at least 95%.

The real-wall-clock soak gate is also ROM-free:

```powershell
.\.venv\Scripts\python.exe scripts\run_supervisor_soak.py `
  --duration-seconds 28800 `
  --restart-after-seconds 900
```

The harness force-terminates the supervisor while a child segment is active, confirms the child survives, launches a replacement supervisor, and audits process intervals for overlap. It passes only when at least eight wall-clock hours elapsed, the restart was adopted, segment IDs are unique, no lineage executions overlap, all segment bundles are complete, every segment has a machine reason, and the final checkpoint is stable.
