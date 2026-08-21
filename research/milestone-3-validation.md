# Milestone 3 Validation Record

Status: complete; all implementation, fault, diagnostics, restart, and real-wall-clock soak gates passed.

## Automated fault and diagnostics gate

Run: `research/artifacts/supervisor-fault-evals/fault-eval-20260821T041529156031Z/fault-evaluation-summary.json`

- 24 of 24 sampled failed or stalled segment bundles were diagnosable without video: 100%, above the 95% target.
- Samples covered stalled loops, repeated state-interpretation gaps, unsafe final states, first and repeated model errors, and child exits without a report.
- Repeated model errors were retried once only after the injected provider health check, then quarantined with the previous safe state intact.
- Stale lease recovery, disk-pressure shutdown, partial-state recovery, and concurrent lease rejection passed.
- Every sampled supervisor stop retained a stable final checkpoint and machine-readable reason.

## Forced-restart development gates

Short real-process harnesses passed after the final process-identity hardening:

- `research/artifacts/supervisor-soaks/dev-short-soak/soak-summary.json`
- `research/artifacts/supervisor-soaks/dev-short-soak-identity/soak-summary.json`
- `research/artifacts/supervisor-soaks/dev-recovery-regression/soak-summary.json`

In each run the supervisor was force-terminated while a child segment was active. The child remained alive, the replacement supervisor adopted it, no segment IDs duplicated, process intervals did not overlap, required artifact manifests were complete, and the final operator stop produced a stable checkpoint. The final run also verifies that recovery cannot reuse the interrupted segment's sequence number.

The complete Python suite passes with 414 tests, repository validation passes, Ruff passes, and the Operations UI passes both type checking and a production Webpack build.

These short runs validate the harness and restart mechanism. They do not substitute for the required real-wall-clock eight-hour soak.

## Real eight-hour soak gate

Run: `research/artifacts/supervisor-soaks/milestone-3-eight-hour-9ce23d9/soak-summary.json`

The final run exercised commit `9ce23d9` and passed every soak check:

- 28,800.797 elapsed wall-clock seconds against a required 28,800 seconds.
- 937 completed segments, with 937 complete artifact manifests and 937 machine-readable segment reasons.
- The harness terminated the first supervisor during `segment-000030-a1`; its child process remained alive and replacement supervisor PID 18648 adopted the lineage.
- All 937 segment IDs were unique and the recorded process intervals contained zero overlaps.
- The harness observed no unexpected worker exit and the replacement supervisor exited successfully after the deadline.
- The final stable checkpoint referenced `segment-000937-a1` and recorded `operator_stop_after_action` as its machine-readable reason.

Together with the 24-of-24 diagnosability sample above, this supplies the required elapsed-time, restart, segment-count, concurrency, stop-reason, stable-artifact, and diagnostic evidence. Milestone 3 is complete.
