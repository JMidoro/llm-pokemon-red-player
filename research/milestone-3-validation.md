# Milestone 3 Validation Record

Status: implementation gates passed; real eight-hour soak pending.

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

## Remaining completion gate

Run `scripts/run_supervisor_soak.py --duration-seconds 28800 --restart-after-seconds 900`. Milestone 3 remains incomplete until its summary reports at least eight elapsed wall-clock hours and every soak check passes.
