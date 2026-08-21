from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.durable_io import atomic_write_json, utc_now  # noqa: E402
from pokemon_player.nuzlocke_ledger import NuzlockeLedger, replay_events, state_digest  # noqa: E402
from pokemon_player.nuzlocke_rules import load_ruleset  # noqa: E402


def timestamp_id() -> str:
    return utc_now().replace("-", "").replace(":", "").replace("+00:00", "Z").replace(".", "")


def observed_result(ledger: NuzlockeLedger) -> dict[str, Any]:
    pokemon = ledger.state["pokemon"]
    return {
        "consumedAreas": sorted(ledger.state["encounters"]),
        "livingCount": sum(1 for item in pokemon.values() if item.get("status") != "dead"),
        "deathCount": len(ledger.state["deaths"]),
        "gameOver": bool(ledger.state["gameOver"]),
        "exceptionCount": len(ledger.state["exceptions"]),
        "knownFamilies": list(ledger.state["knownFamilies"]),
        "boxedDexNumbers": sorted(
            int(item["speciesDex"])
            for item in pokemon.values()
            if item.get("location") == "box" and isinstance(item.get("speciesDex"), int)
        ),
    }


def evaluate_fixture(
    fixture_path: Path,
    *,
    ruleset_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(fixture, dict) or fixture.get("schema") != "nuzlocke_replay_fixture_v1":
        raise ValueError(f"Unsupported fixture schema: {fixture_path}")
    fixture_id = str(fixture.get("id") or fixture_path.stem)
    ruleset = load_ruleset(ruleset_path)
    ledger = NuzlockeLedger(
        output_root / fixture_id / "ledger.json",
        ruleset,
        lineage_id=fixture_id,
    )
    events = fixture.get("events") if isinstance(fixture.get("events"), list) else []
    for item in events:
        if not isinstance(item, dict):
            raise ValueError(f"Fixture event must be an object: {fixture_path}")
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        ledger.append(str(item.get("type") or ""), data, source="milestone_4_fixture")
    reopened = NuzlockeLedger(ledger.path, ruleset, lineage_id=fixture_id)
    replayed = replay_events(ruleset, reopened.events)
    actual = observed_result(reopened)
    expected = fixture.get("expect") if isinstance(fixture.get("expect"), dict) else {}
    expectation_checks = {
        key: actual.get(key) == value
        for key, value in expected.items()
    }
    replay_check = reopened.state == replayed and state_digest(reopened.state) == state_digest(replayed)
    return {
        "id": fixture_id,
        "fixture": fixture_path.name,
        "eventCount": len(reopened.events),
        "expected": expected,
        "actual": actual,
        "checks": {"deterministicReplay": replay_check, **expectation_checks},
        "passed": replay_check and all(expectation_checks.values()),
        "eventStreamDigest": reopened.public_summary()["eventStreamDigest"],
        "stateDigest": state_digest(reopened.state),
    }


def evaluate_directory(
    *,
    fixture_root: Path,
    ruleset_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    fixture_paths = sorted(fixture_root.glob("*.json"))
    if not fixture_paths:
        raise ValueError(f"No Nuzlocke fixtures found in {fixture_root}.")
    results = [
        evaluate_fixture(path, ruleset_path=ruleset_path, output_root=output_root)
        for path in fixture_paths
    ]
    summary = {
        "schema": "nuzlocke_contract_evaluation_v1",
        "createdUtc": utc_now(),
        "ruleset": load_ruleset(ruleset_path).public_summary(),
        "fixtureCount": len(results),
        "passedCount": sum(1 for result in results if result["passed"]),
        "allPassed": all(result["passed"] for result in results),
        "inference": {"used": False, "provider": None, "model": None},
        "results": results,
    }
    atomic_write_json(output_root / "evaluation-summary.json", summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay and verify the deterministic Milestone 4 Nuzlocke contract fixtures."
    )
    parser.add_argument(
        "--fixtures",
        default=str(ROOT / "research" / "evals" / "nuzlocke-contract"),
    )
    parser.add_argument(
        "--ruleset",
        default=str(ROOT / "research" / "rulesets" / "stream-nuzlocke-v1.json"),
    )
    parser.add_argument("--output-root", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = (
        Path(args.output_root).resolve()
        if args.output_root
        else ROOT / "research" / "artifacts" / "nuzlocke-contract-evaluations" / timestamp_id()
    )
    summary = evaluate_directory(
        fixture_root=Path(args.fixtures).resolve(),
        ruleset_path=Path(args.ruleset).resolve(),
        output_root=output_root,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["allPassed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
