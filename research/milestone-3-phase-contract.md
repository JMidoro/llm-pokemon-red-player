# Milestone 3 Phase Contract: Durable Segment Supervisor

Status: active implementation phase

## Hypothesis

A provider-neutral, artifact-first supervisor can chain bounded Director segments from the last verified safe state for unattended operation while preserving LLM strategy, preventing concurrent execution on one save lineage, and making every stop recoverable and remotely legible.

## Expected failure modes

- A crash or forced restart occurs between launching a segment and registering its artifacts.
- A stale process lease permits duplicate execution against the same save lineage.
- A report, manifest, heartbeat, or control file is only partially written.
- A provider outage or repeated model error causes an unbounded retry loop.
- An unsafe checkpoint is treated as a continuation state instead of rolling back.
- A stalled loop, skill gap, or state-interpretation gap loses the evidence needed for diagnosis.
- Disk exhaustion prevents a final checkpoint or corrupts the artifact bundle.
- Remote pause or stop state is lost when the browser disconnects or the supervisor restarts.

## Compute cap

- Development and fault-injection runs use ROM-free deterministic fixtures or replay providers by default.
- The completion gate includes one real wall-clock eight-hour ROM-free soak; a shortened or virtual-clock run does not substitute for it.
- The soak may run bounded segments continuously but must not use a paid hosted provider.
- Any live gameplay validation remains bounded by the existing segment action and timeout limits. Additional hosted-model spend requires separate operator authorization.

## Human burden

- No checkpoint requires synchronous approval to continue when policy permits continuation.
- Human review is limited to a sample of checkpoint and failure bundles, targeting under five minutes per selected segment.
- Ambiguous evidence is queued for later review while safe provisional or adjacent work continues.

## Required artifacts

- Versioned supervisor state, control state, process lease, and heartbeat records.
- Atomic lineage and per-segment manifests with hashes, sizes, timestamps, input/final state references, and machine-readable stop reasons.
- Stable bundles for the report, checkpoint, final state, screenshot, video when enabled, event log, and failure evidence.
- Durable asynchronous review queue entries for provisional checkpoints and diagnosable gaps.
- Fault-injection evidence for model errors, unsafe states, partial writes, stale leases, disk pressure, and forced restart recovery.
- Eight-hour soak summary with elapsed wall time, restart evidence, segment counts, concurrency audit, stop-reason audit, and diagnostic sampling result.

## Completion criteria

- The state machine implements `idle`, `starting`, `running`, `checkpointing`, `waiting_review`, `paused`, `blocked`, `completed`, and `failed`.
- `healthy_continue` and configured `provisional_continue` checkpoints continue from `finalState`; unsafe states roll back; reviewable gaps are preserved and queued.
- Model errors receive at most one retry after a provider health check, then quarantine without losing the last safe checkpoint.
- An eight-hour soak survives normal action-budget checkpoints and at least one forced supervisor restart.
- No segment runs twice concurrently against the same save lineage.
- Every stop has a stable final checkpoint and machine-readable reason.
- At least 95% of sampled failed or stalled segments are diagnosable from their artifact bundles without watching the full video.
- Remote Operations exposes supervisor health, continuation state, queued reviews, failures, and safe controls without exposing credentials, ROM/save paths, raw provider payloads, or raw emulator buttons.
