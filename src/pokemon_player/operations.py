from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pokemon_player.chapter_direction import current_chapter_goal


CONTROL_ACTIONS = {"pause", "resume", "stop_after_action", "emergency_stop"}
SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
WINDOWS_PATH = re.compile(r"(?i)(?:[A-Z]:\\[^\"\r\n,;]+)")
UNC_PATH = re.compile(r"(?:\\\\[^\\\s\"']+\\[^\"\r\n,;]+)")
UNIX_PATH = re.compile(r"(?<![A-Za-z0-9])/(?:[^/\s\"']+/)+[^\s\"',;\])}]+")
URL_WITH_AUTHORITY = re.compile(r"(?i)https?://[^\s\"']+")
SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "auth",
    "baseurl",
    "eventlogpath",
    "framedir",
    "path",
    "reportpath",
    "request",
    "requests",
    "response",
    "rom",
    "rundir",
    "secret",
    "state",
    "statein",
    "statepath",
    "token",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    return value if isinstance(value, dict) else None


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def safe_text(value: Any, *, limit: int = 800) -> str:
    text = str(value or "").strip()
    text = WINDOWS_PATH.sub("[local path hidden]", text)
    text = UNC_PATH.sub("[local path hidden]", text)
    text = UNIX_PATH.sub("[local path hidden]", text)
    text = URL_WITH_AUTHORITY.sub("[service address hidden]", text)
    if text.startswith(("/", "\\")):
        text = "[local path hidden]"
    return text[:limit]


def _key_is_sensitive(key: str) -> bool:
    normalized = key.replace("_", "").replace("-", "").lower()
    return normalized in {item.replace("_", "") for item in SENSITIVE_KEYS} or any(
        fragment in normalized
        for fragment in ("credential", "password", "privatekey", "screenshotpath")
    )


def sanitized_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 5:
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return safe_text(value)
    if isinstance(value, list):
        return [sanitized_value(item, depth=depth + 1) for item in value[:30]]
    if isinstance(value, dict):
        return {
            str(key): sanitized_value(item, depth=depth + 1)
            for key, item in list(value.items())[:50]
            if not _key_is_sensitive(str(key))
        }
    return safe_text(value)


def _safe_text_list(value: Any, *, limit: int, item_limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [safe_text(item, limit=item_limit) for item in value[:limit]]


def _compact_party(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    party = snapshot.get("party") if isinstance(snapshot.get("party"), list) else []
    compact: list[dict[str, Any]] = []
    for member in party[:6]:
        if not isinstance(member, dict):
            continue
        compact.append(
            {
                "slot": member.get("slot"),
                "species": safe_text(member.get("species_name") or "Unknown", limit=40),
                "nickname": safe_text(member.get("nickname") or "", limit=40),
                "level": member.get("level"),
                "hp": member.get("hp"),
                "maxHp": member.get("max_hp"),
                "status": member.get("status"),
            }
        )
    return compact


def _compact_inventory(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    inventory = snapshot.get("inventory") if isinstance(snapshot.get("inventory"), list) else []
    compact: list[dict[str, Any]] = []
    for item in inventory[:30]:
        if not isinstance(item, dict):
            continue
        compact.append(
            {
                "item": safe_text(item.get("item_name") or "Unknown", limit=60),
                "quantity": item.get("quantity"),
            }
        )
    return compact


def _compact_position(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    position = snapshot.get("position")
    if not isinstance(position, dict):
        return None
    return {
        "map": safe_text(position.get("map_name") or "Unknown", limit=80),
        "x": position.get("x"),
        "y": position.get("y"),
    }


def _compact_result(history_item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(history_item, dict):
        return None
    result = history_item.get("result") if isinstance(history_item.get("result"), dict) else {}
    evidence = result.get("evidence") if isinstance(result.get("evidence"), list) else []
    warnings = result.get("warnings") if isinstance(result.get("warnings"), list) else []
    return {
        "action": history_item.get("action"),
        "skillId": safe_text(history_item.get("skillId") or result.get("skill_id"), limit=80),
        "status": safe_text(result.get("status") or "unknown", limit=30),
        "summary": safe_text(result.get("summary") or "No result summary.", limit=500),
        "evidence": [safe_text(item, limit=240) for item in evidence[:8] if "path=" not in str(item).lower()],
        "warnings": [safe_text(item, limit=160) for item in warnings[:8]],
    }


def _compact_decision(history_item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(history_item, dict):
        return None
    return {
        "action": history_item.get("action"),
        "skillId": safe_text(history_item.get("skillId") or "unknown", limit=80),
        "reasoning": safe_text(history_item.get("plaintextReasoning") or "No reasoning recorded.", limit=1000),
        "args": sanitized_value(history_item.get("args") if isinstance(history_item.get("args"), dict) else {}),
    }


def _chapter(report: dict[str, Any]) -> dict[str, Any]:
    timeline = report.get("chapterTimeline") if isinstance(report.get("chapterTimeline"), list) else []
    item = timeline[-1] if timeline and isinstance(timeline[-1], dict) else {}
    return {
        "id": safe_text(item.get("chapterId") or "unknown", limit=100),
        "title": safe_text(item.get("title") or "Unknown chapter", limit=160),
        "objective": safe_text(item.get("objective") or report.get("goal") or "No goal recorded.", limit=800),
        "success": bool(item.get("success")),
    }


def _chapter_from_snapshot(snapshot: dict[str, Any], fallback_goal: str) -> dict[str, Any]:
    try:
        chapter = current_chapter_goal(snapshot)
        return {
            "id": safe_text(chapter.chapter_id, limit=100),
            "title": safe_text(chapter.title, limit=160),
            "objective": safe_text(chapter.objective, limit=800),
            "success": bool(chapter.success),
        }
    except (KeyError, TypeError, ValueError):
        return {
            "id": "unknown",
            "title": "Live Director session",
            "objective": safe_text(fallback_goal, limit=800),
            "success": False,
        }


def _timeline(report: dict[str, Any]) -> list[dict[str, Any]]:
    source = report.get("chapterTimeline") if isinstance(report.get("chapterTimeline"), list) else []
    compact: list[dict[str, Any]] = []
    previous_id: str | None = None
    for item in source:
        if not isinstance(item, dict):
            continue
        chapter_id = safe_text(item.get("chapterId") or "unknown", limit=100)
        if chapter_id == previous_id and not item.get("success"):
            if compact:
                compact[-1]["lastAction"] = item.get("action")
            continue
        compact.append(
            {
                "chapterId": chapter_id,
                "title": safe_text(item.get("title") or "Unknown chapter", limit=160),
                "firstAction": item.get("action"),
                "lastAction": item.get("action"),
                "success": bool(item.get("success")),
            }
        )
        previous_id = chapter_id
    return compact[-20:]


def _review_items(checkpoint: dict[str, Any], run_id: str) -> list[dict[str, Any]]:
    source = checkpoint.get("reviewItems") if isinstance(checkpoint.get("reviewItems"), list) else []
    items: list[dict[str, Any]] = []
    for index, item in enumerate(source[:20], start=1):
        if isinstance(item, dict):
            title = item.get("title") or item.get("summary") or item.get("kind") or f"Review item {index}"
            detail = item.get("detail") or item.get("description") or item.get("reason") or "Deferred review requested."
            severity = item.get("severity") or item.get("priority") or "review"
        else:
            title = f"Review item {index}"
            detail = item
            severity = "review"
        items.append(
            {
                "id": f"{run_id}-{index}",
                "runId": run_id,
                "title": safe_text(title, limit=160),
                "detail": safe_text(detail, limit=500),
                "severity": safe_text(severity, limit=30),
            }
        )
    return items


def report_summary(report: dict[str, Any], run_id: str, *, video_available: bool) -> dict[str, Any]:
    history = report.get("history") if isinstance(report.get("history"), list) else []
    last_history = history[-1] if history and isinstance(history[-1], dict) else None
    checkpoint = report.get("checkpoint") if isinstance(report.get("checkpoint"), dict) else {}
    finish = report.get("finish") if isinstance(report.get("finish"), dict) else {}
    snapshot = report.get("finalSnapshot") if isinstance(report.get("finalSnapshot"), dict) else {}
    review_items = _review_items(checkpoint, run_id)
    verdict = safe_text(checkpoint.get("verdict") or "unclassified", limit=60)
    failure_category = safe_text(finish.get("failureCategory") or "", limit=100)
    failure = None
    failure_verdicts = {"stalled_loop", "unsafe_state", "skill_gap", "state_interpretation_gap", "model_error"}
    if (failure_category and failure_category != "action_budget_exhausted") or verdict in failure_verdicts:
        failure = {
            "category": failure_category or verdict,
            "summary": safe_text(checkpoint.get("summary") or finish.get("summary") or "Run needs attention.", limit=500),
        }
    created = safe_text(report.get("createdUtc") or "", limit=50)
    provider = report.get("provider") if isinstance(report.get("provider"), dict) else {}
    return {
        "id": run_id,
        "createdUtc": created,
        "model": safe_text(report.get("model") or provider.get("model") or "Unknown model", limit=120),
        "status": safe_text(finish.get("status") or "unknown", limit=40),
        "finishSummary": safe_text(finish.get("summary") or "No finish summary.", limit=500),
        "actionCount": len(history),
        "goal": safe_text(report.get("goal") or "No goal recorded.", limit=800),
        "chapter": _chapter(report),
        "position": _compact_position(snapshot),
        "mode": safe_text(snapshot.get("mode") or "unknown", limit=40),
        "party": _compact_party(snapshot),
        "inventory": _compact_inventory(snapshot),
        "lastDecision": _compact_decision(last_history),
        "lastSkillResult": _compact_result(last_history),
        "checkpoint": {
            "verdict": verdict,
            "confidence": safe_text(checkpoint.get("confidence") or "unknown", limit=30),
            "continueRecommended": bool(checkpoint.get("continueRecommended")),
            "summary": safe_text(checkpoint.get("summary") or "No checkpoint summary.", limit=500),
        },
        "timeline": _timeline(report),
        "failure": failure,
        "reviewItems": review_items,
        "artifacts": {
            "screenshot": f"/api/operations/artifacts/{run_id}/screenshot",
            "summary": f"/api/operations/artifacts/{run_id}/summary",
            "video": f"/api/operations/artifacts/{run_id}/video" if video_available else None,
        },
        "dropbox": {
            "status": "ready_in_dropbox_folder" if video_available else "not_available",
            "playable": video_available,
        },
        "nuzlocke": sanitized_value(
            report.get("nuzlocke") if isinstance(report.get("nuzlocke"), dict) else None
        ),
    }


def director_report_summary(report: dict[str, Any], run_id: str, *, created_utc: str) -> dict[str, Any]:
    player_status = report.get("playerStatus") if isinstance(report.get("playerStatus"), dict) else {}
    snapshot = player_status.get("snapshot") if isinstance(player_status.get("snapshot"), dict) else {}
    if not snapshot:
        environment = report.get("envSnapshot") if isinstance(report.get("envSnapshot"), dict) else {}
        snapshot = environment.get("snapshot") if isinstance(environment.get("snapshot"), dict) else {}
    steps = report.get("steps") if isinstance(report.get("steps"), list) else []
    last_step = next((item for item in reversed(steps) if isinstance(item, dict)), None)
    step_result = last_step.get("result") if isinstance(last_step, dict) and isinstance(last_step.get("result"), dict) else {}
    last_result = step_result.get("lastResult") if isinstance(step_result.get("lastResult"), dict) else step_result
    status = safe_text(report.get("status") or "unknown", limit=40)
    goal = safe_text(report.get("goal") or "No browser Director goal recorded.", limit=800)
    if status == "error":
        verdict, confidence, continue_recommended = "model_error", "high", False
    elif status == "completed":
        verdict, confidence, continue_recommended = "healthy_needs_review", "medium", False
    else:
        verdict, confidence, continue_recommended = "provisional_continue", "medium", True
    failure = None
    if status == "error":
        failure = {
            "category": "browser_director_error",
            "summary": safe_text(report.get("error") or "Browser Director run failed.", limit=500),
        }
    decision = None
    result = None
    if isinstance(last_step, dict):
        step_args = last_step.get("args") if isinstance(last_step.get("args"), dict) else {}
        selected_args = step_result.get("args") if isinstance(step_result.get("args"), dict) else step_args.get("args")
        decision = {
            "skillId": safe_text(step_result.get("skillId") or step_args.get("skillId") or last_step.get("name") or "unknown", limit=80),
            "reasoning": safe_text(last_step.get("plaintextReasoning") or step_args.get("plaintextReasoning") or "No reasoning recorded.", limit=1000),
            "args": sanitized_value(selected_args if isinstance(selected_args, dict) else {}),
        }
        result = {
            "skillId": decision["skillId"],
            "status": safe_text(last_result.get("status") or last_step.get("status") or "unknown", limit=30),
            "summary": safe_text(last_result.get("summary") or last_step.get("summary") or "No result summary.", limit=500),
            "evidence": _safe_text_list(last_result.get("evidence"), limit=8, item_limit=240),
            "warnings": _safe_text_list(last_result.get("warnings"), limit=8, item_limit=160),
        }
    chapter = _chapter_from_snapshot(snapshot, goal)
    summary_text = safe_text(report.get("assistantMessage") or f"Browser Director run ended with status {status}.", limit=500)
    return {
        "id": run_id,
        "source": "browser_director",
        "createdUtc": created_utc,
        "model": safe_text(report.get("model") or "Unknown provider model", limit=120),
        "status": status,
        "finishSummary": summary_text,
        "actionCount": len(steps),
        "goal": goal,
        "chapter": chapter,
        "position": _compact_position(snapshot),
        "mode": safe_text(snapshot.get("mode") or "unknown", limit=40),
        "party": _compact_party(snapshot),
        "inventory": _compact_inventory(snapshot),
        "lastDecision": decision,
        "lastSkillResult": result,
        "checkpoint": {
            "verdict": verdict,
            "confidence": confidence,
            "continueRecommended": continue_recommended,
            "summary": summary_text,
        },
        "timeline": [
            {
                "chapterId": chapter["id"],
                "title": chapter["title"],
                "firstAction": 1 if steps else 0,
                "lastAction": len(steps),
                "success": chapter["success"],
            }
        ],
        "failure": failure,
        "reviewItems": [],
        "artifacts": {
            "screenshot": None,
            "summary": f"/api/operations/artifacts/{run_id}/summary",
            "video": None,
        },
        "dropbox": {"status": "not_available", "playable": False},
    }


@dataclass
class OperationsPaths:
    state_dir: Path
    report_root: Path
    dropbox_root: Path | None = None
    director_report_root: Path | None = None
    director_status_dir: Path | None = None
    supervisor_root: Path | None = None

    @property
    def control(self) -> Path:
        return self.state_dir / "control.json"

    @property
    def audit(self) -> Path:
        return self.state_dir / "audit.jsonl"

    @property
    def active_run(self) -> Path:
        return self.state_dir / "active-run.json"


class OperationsStore:
    def __init__(
        self,
        paths: OperationsPaths,
        *,
        director_url: str = "http://127.0.0.1:8765",
        active_stale_seconds: float = 45.0,
    ) -> None:
        self.paths = paths
        self.director_url = director_url.rstrip("/")
        self.active_stale_seconds = active_stale_seconds
        self._lock = threading.RLock()
        self._report_cache: dict[str, tuple[tuple[int, int, int | None], dict[str, Any]]] = {}
        self._director_report_cache: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}
        self._supervisor_report_cache: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}
        self._supervisor_report_dirs: dict[str, Path] = {}
        self._snapshot_cache: dict[str, Any] | None = None
        self._snapshot_cache_at = 0.0
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        if not self.paths.control.exists():
            atomic_write_json(self.paths.control, self._default_control())

    @staticmethod
    def _default_control() -> dict[str, Any]:
        return {
            "schema": "operations_control_v1",
            "revision": 0,
            "state": "running",
            "stopAfterAction": False,
            "updatedUtc": utc_now(),
            "lastCommandId": None,
        }

    def read_control(self) -> dict[str, Any]:
        with self._lock:
            control = read_json(self.paths.control)
            return control if control and control.get("schema") == "operations_control_v1" else self._default_control()

    def command(self, action: str, *, source: str = "operations_ui") -> dict[str, Any]:
        if action not in CONTROL_ACTIONS:
            raise ValueError(f"Unsupported operations control: {action}")
        with self._lock:
            current = self.read_control()
            command_id = uuid.uuid4().hex
            next_state = str(current.get("state") or "running")
            stop_after_action = bool(current.get("stopAfterAction"))
            if action == "pause":
                next_state = "paused"
            elif action == "resume":
                next_state = "running"
                stop_after_action = False
            elif action == "stop_after_action":
                stop_after_action = True
            elif action == "emergency_stop":
                next_state = "emergency_stopped"
                stop_after_action = False
            updated = {
                "schema": "operations_control_v1",
                "revision": int(current.get("revision") or 0) + 1,
                "state": next_state,
                "stopAfterAction": stop_after_action,
                "updatedUtc": utc_now(),
                "lastCommandId": command_id,
            }
            atomic_write_json(self.paths.control, updated)
            self._snapshot_cache = None
            event = {
                "schema": "operations_audit_event_v1",
                "commandId": command_id,
                "createdUtc": updated["updatedUtc"],
                "action": action,
                "source": safe_text(source, limit=80),
                "resultingState": next_state,
                "stopAfterAction": stop_after_action,
                "revision": updated["revision"],
            }
            with self.paths.audit.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, sort_keys=True) + "\n")
            return {"accepted": True, "command": event, "control": self.public_control(updated)}

    @staticmethod
    def public_control(control: dict[str, Any]) -> dict[str, Any]:
        return {
            "state": safe_text(control.get("state") or "running", limit=40),
            "stopAfterAction": bool(control.get("stopAfterAction")),
            "updatedUtc": safe_text(control.get("updatedUtc") or "", limit=50),
            "revision": int(control.get("revision") or 0),
        }

    def audit_events(self, limit: int = 30) -> list[dict[str, Any]]:
        try:
            lines = self.paths.audit.read_text(encoding="utf-8").splitlines()
        except (FileNotFoundError, OSError):
            return []
        events: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(
                    {
                        "createdUtc": safe_text(event.get("createdUtc") or "", limit=50),
                        "action": safe_text(event.get("action") or "unknown", limit=60),
                        "source": safe_text(event.get("source") or "unknown", limit=80),
                        "resultingState": safe_text(event.get("resultingState") or "unknown", limit=40),
                    }
                )
        return list(reversed(events))

    def _video_path(self, run_id: str) -> Path | None:
        if not self.paths.dropbox_root:
            return None
        candidate = self.paths.dropbox_root.resolve() / f"{run_id}.mp4"
        return candidate if candidate.is_file() else None

    def report_summaries(self, limit: int = 25) -> list[dict[str, Any]]:
        try:
            directories = sorted(
                (item for item in self.paths.report_root.iterdir() if item.is_dir() and SAFE_RUN_ID.fullmatch(item.name)),
                key=lambda item: item.name,
                reverse=True,
            )
        except (FileNotFoundError, OSError):
            return []
        summaries: list[dict[str, Any]] = []
        for directory in directories:
            report_path = directory / "report.json"
            try:
                report_stat = report_path.stat()
            except OSError:
                continue
            video = self._video_path(directory.name)
            try:
                video_mtime = video.stat().st_mtime_ns if video else None
            except OSError:
                video_mtime = None
            signature = (report_stat.st_mtime_ns, report_stat.st_size, video_mtime)
            cached = self._report_cache.get(directory.name)
            if cached and cached[0] == signature:
                summaries.append(cached[1])
                if len(summaries) >= limit:
                    break
                continue
            report = read_json(report_path)
            if not report:
                continue
            summary = report_summary(report, directory.name, video_available=video is not None)
            self._report_cache[directory.name] = (signature, summary)
            summaries.append(summary)
            if len(summaries) >= limit:
                break
        return summaries

    def director_report_summaries(self, limit: int = 15) -> list[dict[str, Any]]:
        root = self.paths.director_report_root
        if not root:
            return []
        try:
            directories = sorted(
                (item for item in root.iterdir() if item.is_dir() and SAFE_RUN_ID.fullmatch(item.name)),
                key=lambda item: item.name,
                reverse=True,
            )
        except (FileNotFoundError, OSError):
            return []
        summaries: list[dict[str, Any]] = []
        for directory in directories:
            report_path = directory / "report.json"
            try:
                report_stat = report_path.stat()
            except OSError:
                continue
            signature = (report_stat.st_mtime_ns, report_stat.st_size)
            cache_key = f"director-{directory.name}"
            cached = self._director_report_cache.get(cache_key)
            if cached and cached[0] == signature:
                summaries.append(cached[1])
                if len(summaries) >= limit:
                    break
                continue
            report = read_json(report_path)
            if not report or report.get("schema") != "llm_director_run_v1":
                continue
            created = datetime.fromtimestamp(report_stat.st_mtime, UTC).isoformat()
            summary = director_report_summary(report, cache_key, created_utc=created)
            self._director_report_cache[cache_key] = (signature, summary)
            summaries.append(summary)
            if len(summaries) >= limit:
                break
        return summaries

    def supervisor_report_summaries(self, limit: int = 25) -> list[dict[str, Any]]:
        root = self.paths.supervisor_root
        lineages_root = root / "lineages" if root else None
        if not lineages_root or not lineages_root.is_dir():
            return []
        candidates: list[tuple[int, str, str, Path]] = []
        self._supervisor_report_dirs = {}
        for lineage_dir in lineages_root.iterdir():
            if not lineage_dir.is_dir() or not SAFE_RUN_ID.fullmatch(lineage_dir.name):
                continue
            segments_dir = lineage_dir / "segments"
            if not segments_dir.is_dir():
                continue
            for segment_dir in segments_dir.iterdir():
                if not segment_dir.is_dir() or not SAFE_RUN_ID.fullmatch(segment_dir.name):
                    continue
                public_id = self._supervisor_public_run_id(lineage_dir.name, segment_dir.name)
                self._supervisor_report_dirs[public_id] = segment_dir
                report_path = segment_dir / "report.json"
                try:
                    modified = report_path.stat().st_mtime_ns
                except OSError:
                    continue
                candidates.append((modified, public_id, lineage_dir.name, segment_dir))
        summaries: list[dict[str, Any]] = []
        for _, public_id, lineage_id, segment_dir in sorted(candidates, reverse=True):
            report_path = segment_dir / "report.json"
            try:
                report_stat = report_path.stat()
            except OSError:
                continue
            signature = (report_stat.st_mtime_ns, report_stat.st_size)
            cached = self._supervisor_report_cache.get(public_id)
            if cached and cached[0] == signature:
                summaries.append(cached[1])
            else:
                report = read_json(report_path)
                if not report:
                    continue
                summary = report_summary(
                    report,
                    public_id,
                    video_available=(segment_dir / "segment.mp4").is_file(),
                )
                summary.update(
                    {
                        "source": "segment_supervisor",
                        "sourceSegmentId": segment_dir.name,
                        "lineageId": safe_text(lineage_id, limit=80),
                    }
                )
                self._supervisor_report_cache[public_id] = (signature, summary)
                summaries.append(summary)
            if len(summaries) >= limit:
                break
        return summaries

    @staticmethod
    def _supervisor_public_run_id(lineage_id: str, segment_id: str) -> str:
        lineage_hash = hashlib.sha256(lineage_id.encode("utf-8")).hexdigest()[:10]
        return f"sv-{lineage_hash}-{segment_id}"

    def _supervisor_run_dir(self, run_id: str) -> Path | None:
        directory = self._supervisor_report_dirs.get(run_id)
        if directory and directory.is_dir():
            return directory
        self.supervisor_report_summaries()
        directory = self._supervisor_report_dirs.get(run_id)
        return directory if directory and directory.is_dir() else None

    def _director_health(self) -> tuple[dict[str, Any], dict[str, Any] | None]:
        request = Request(f"{self.director_url}/status", headers={"accept": "application/json"})
        try:
            with urlopen(request, timeout=0.25) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Director status is not an object")
            return ({"id": "director", "label": "Director player", "status": "online", "detail": "Ready"}, payload)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
            return ({"id": "director", "label": "Director player", "status": "offline", "detail": "Not running"}, None)

    def _active(self) -> dict[str, Any] | None:
        active = read_json(self.paths.active_run)
        if not active or not SAFE_RUN_ID.fullmatch(str(active.get("runId") or "")):
            return None
        updated_epoch = active.get("updatedEpoch")
        try:
            age = max(time.time() - float(updated_epoch), 0.0)
        except (TypeError, ValueError):
            age = self.active_stale_seconds + 1
        active["heartbeatAgeSeconds"] = round(age, 1)
        active["stale"] = age > self.active_stale_seconds
        return active

    def _active_public(self, active: dict[str, Any], reports: list[dict[str, Any]]) -> dict[str, Any]:
        run_id = str(active["runId"])
        matching = next(
            (
                report
                for report in reports
                if report["id"] == run_id or report.get("sourceSegmentId") == run_id
            ),
            None,
        )
        mapped_id = next(
            (
                public_id
                for public_id, directory in self._supervisor_report_dirs.items()
                if directory.name == run_id
            ),
            None,
        )
        public_run_id = str(matching.get("id")) if matching else (mapped_id or run_id)
        snapshot = active.get("snapshot") if isinstance(active.get("snapshot"), dict) else {}
        chapter = active.get("chapter") if isinstance(active.get("chapter"), dict) else {}
        last_decision = active.get("lastDecision") if isinstance(active.get("lastDecision"), dict) else None
        last_result = active.get("lastSkillResult") if isinstance(active.get("lastSkillResult"), dict) else None
        return {
            "id": public_run_id,
            "createdUtc": safe_text(active.get("startedUtc") or "", limit=50),
            "updatedUtc": safe_text(active.get("updatedUtc") or "", limit=50),
            "heartbeatAgeSeconds": active.get("heartbeatAgeSeconds"),
            "stale": bool(active.get("stale")),
            "model": safe_text(active.get("model") or "Unknown model", limit=120),
            "status": "stale" if active.get("stale") else safe_text(active.get("status") or "running", limit=40),
            "actionCount": active.get("actionCount") or 0,
            "goal": safe_text(active.get("goal") or "No goal recorded.", limit=800),
            "chapter": {
                "id": safe_text(chapter.get("id") or "unknown", limit=100),
                "title": safe_text(chapter.get("title") or "Unknown chapter", limit=160),
                "objective": safe_text(chapter.get("objective") or active.get("goal") or "No goal recorded.", limit=800),
                "success": bool(chapter.get("success")),
            },
            "position": _compact_position(snapshot),
            "mode": safe_text(snapshot.get("mode") or "unknown", limit=40),
            "party": _compact_party(snapshot),
            "inventory": _compact_inventory(snapshot),
            "lastDecision": sanitized_value(last_decision),
            "lastSkillResult": sanitized_value(last_result),
            "checkpoint": matching.get("checkpoint") if matching else None,
            "timeline": matching.get("timeline", []) if matching else [],
            "failure": matching.get("failure") if matching else None,
            "reviewItems": matching.get("reviewItems", []) if matching else [],
            "artifacts": {
                "screenshot": f"/api/operations/artifacts/{public_run_id}/screenshot",
                "summary": matching.get("artifacts", {}).get("summary") if matching else None,
                "video": matching.get("artifacts", {}).get("video") if matching else None,
            },
            "dropbox": matching.get("dropbox") if matching else {"status": "not_available", "playable": False},
            "nuzlocke": sanitized_value(
                active.get("nuzlocke")
                if isinstance(active.get("nuzlocke"), dict)
                else (matching.get("nuzlocke") if matching else None)
            ),
        }

    @staticmethod
    def _is_same_director_session(report: dict[str, Any] | None, director_payload: dict[str, Any]) -> bool:
        if not report:
            return False
        try:
            report_time = datetime.fromisoformat(str(report.get("createdUtc") or "").replace("Z", "+00:00"))
            started_time = datetime.fromisoformat(str(director_payload.get("startedUtc") or "").replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return False
        return report_time >= started_time

    def _director_public(
        self,
        payload: dict[str, Any],
        latest_report: dict[str, Any] | None,
    ) -> dict[str, Any]:
        snapshot = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else {}
        recent_report = latest_report if self._is_same_director_session(latest_report, payload) else None
        last_result = payload.get("lastResult") if isinstance(payload.get("lastResult"), dict) else None
        control = payload.get("control") if isinstance(payload.get("control"), dict) else {}
        status = safe_text(control.get("state") or ("executing_action" if payload.get("busy") else "running"), limit=40)
        goal = safe_text(
            recent_report.get("goal") if recent_report else "Awaiting the browser Director's next goal.",
            limit=800,
        )
        chapter = _chapter_from_snapshot(snapshot, goal)
        safe_result = None
        if last_result:
            safe_result = {
                "skillId": safe_text(last_result.get("skillId") or "unknown", limit=80),
                "status": safe_text(last_result.get("status") or "unknown", limit=30),
                "summary": safe_text(last_result.get("summary") or "No result summary.", limit=500),
                "evidence": _safe_text_list(last_result.get("evidence"), limit=8, item_limit=240),
                "warnings": _safe_text_list(last_result.get("warnings"), limit=8, item_limit=160),
            }
        history = payload.get("history") if isinstance(payload.get("history"), list) else []
        return {
            "id": "live-director",
            "source": "live_director",
            "createdUtc": safe_text(payload.get("startedUtc") or "", limit=50),
            "updatedUtc": utc_now(),
            "model": recent_report.get("model") if recent_report else "Browser Director idle",
            "status": status,
            "actionCount": len(history),
            "goal": goal,
            "chapter": chapter,
            "position": _compact_position(snapshot),
            "mode": safe_text(snapshot.get("mode") or "unknown", limit=40),
            "party": _compact_party(snapshot),
            "inventory": _compact_inventory(snapshot),
            "lastDecision": recent_report.get("lastDecision") if recent_report else None,
            "lastSkillResult": safe_result,
            "checkpoint": None,
            "timeline": recent_report.get("timeline", []) if recent_report else [],
            "failure": None,
            "reviewItems": [],
            "artifacts": {
                "screenshot": "/api/operations/artifacts/live-director/screenshot",
                "summary": None,
                "video": None,
            },
            "dropbox": {"status": "not_available", "playable": False},
        }

    def _supervisor_public(
        self,
    ) -> tuple[dict[str, Any], dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
        root = self.paths.supervisor_root
        lineages_root = root / "lineages" if root else None
        if not lineages_root or not lineages_root.is_dir():
            return (
                {
                    "id": "supervisor",
                    "label": "Segment supervisor",
                    "status": "idle",
                    "detail": "No lineage has started",
                },
                None,
                [],
                [],
            )
        candidates: list[tuple[int, Path, dict[str, Any]]] = []
        for directory in lineages_root.iterdir():
            if not directory.is_dir() or not SAFE_RUN_ID.fullmatch(directory.name):
                continue
            state_path = directory / "state.json"
            state = read_json(state_path)
            if not state:
                continue
            try:
                modified = state_path.stat().st_mtime_ns
            except OSError:
                modified = 0
            candidates.append((modified, directory, state))
        if not candidates:
            return (
                {
                    "id": "supervisor",
                    "label": "Segment supervisor",
                    "status": "idle",
                    "detail": "No durable state available",
                },
                None,
                [],
                [],
            )
        _, directory, state = max(candidates, key=lambda item: item[0])
        heartbeat = read_json(directory / "heartbeat.json") or {}
        manifest = read_json(directory / "manifest.json") or {}
        try:
            heartbeat_age = max(time.time() - float(heartbeat.get("updatedEpoch")), 0.0)
        except (TypeError, ValueError):
            heartbeat_age = self.active_stale_seconds + 1
        supervisor_state = safe_text(state.get("state") or "idle", limit=40)
        connected_state = supervisor_state in {"idle", "starting", "running", "checkpointing", "paused"}
        stale = connected_state and (
            heartbeat_age > self.active_stale_seconds
        )
        connected = connected_state and not stale
        segments = manifest.get("segments") if isinstance(manifest.get("segments"), list) else []
        latest_segment = segments[-1] if segments and isinstance(segments[-1], dict) else {}
        public = {
            "lineageId": safe_text(directory.name, limit=80),
            "state": "stale" if stale else supervisor_state,
            "reason": safe_text(state.get("reason") or "No reason recorded", limit=160),
            "currentSegment": safe_text(state.get("currentSegment") or "", limit=80) or None,
            "heartbeatAgeSeconds": round(heartbeat_age, 1),
            "stale": stale,
            "connected": connected,
            "segmentCount": len(segments),
            "nextSequence": int(manifest.get("nextSequence") or 1),
            "latestVerdict": safe_text(latest_segment.get("verdict") or "", limit=60) or None,
            "updatedUtc": safe_text(state.get("updatedUtc") or "", limit=50),
        }
        reviews: list[dict[str, Any]] = []
        review_dir = directory / "review-queue"
        if review_dir.is_dir():
            for path in sorted(review_dir.glob("*.json"), reverse=True)[:30]:
                item = read_json(path)
                if not item or item.get("status") != "queued":
                    continue
                reviews.append(
                    {
                        "id": safe_text(item.get("id") or path.stem, limit=120),
                        "runId": safe_text(item.get("segmentId") or directory.name, limit=100),
                        "title": safe_text(item.get("kind") or "Supervisor review", limit=160),
                        "detail": safe_text(item.get("summary") or "Review queued.", limit=500),
                        "severity": "review",
                    }
                )
        failures: list[dict[str, Any]] = []
        failure_dir = directory / "failures"
        if failure_dir.is_dir():
            for path in sorted(failure_dir.glob("*.json"), reverse=True)[:20]:
                item = read_json(path)
                if not item:
                    continue
                checkpoint = (
                    item.get("checkpoint") if isinstance(item.get("checkpoint"), dict) else {}
                )
                failures.append(
                    {
                        "runId": safe_text(item.get("segmentId") or directory.name, limit=100),
                        "category": safe_text(checkpoint.get("verdict") or "supervisor_failure", limit=100),
                        "summary": safe_text(checkpoint.get("summary") or "Supervisor failure.", limit=500),
                        "createdUtc": safe_text(item.get("createdUtc") or "", limit=50),
                    }
                )
        service_status = "stale" if stale else ("online" if connected else supervisor_state)
        return (
            {
                "id": "supervisor",
                "label": "Segment supervisor",
                "status": service_status,
                "detail": safe_text(state.get("reason") or supervisor_state, limit=120),
            },
            public,
            reviews,
            failures,
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            now = time.monotonic()
            if self._snapshot_cache is not None and now - self._snapshot_cache_at < 1.5:
                return self._snapshot_cache
            local_reports = self.report_summaries()
            supervisor_reports = self.supervisor_report_summaries()
            director_reports = self.director_report_summaries()
            reports = sorted(
                [*local_reports[:10], *supervisor_reports[:15], *director_reports[:10]],
                key=lambda report: str(report.get("createdUtc") or ""),
                reverse=True,
            )
            active = self._active()
            if active and (
                active.get("stale")
                or str(active.get("status") or "")
                in {"checkpoint", "completed", "failed", "stopped_after_action", "emergency_stopped"}
            ) and any(
                report["id"] == active.get("runId")
                or report.get("sourceSegmentId") == active.get("runId")
                for report in reports
            ):
                active = None
            director_service, director_payload = self._director_health()
            supervisor_service, supervisor, supervisor_reviews, supervisor_failures = (
                self._supervisor_public()
            )
            dropbox_ready = bool(self.paths.dropbox_root and self.paths.dropbox_root.exists())
            latest_director = director_reports[0] if director_reports else None
            if active:
                current = self._active_public(active, [*supervisor_reports, *local_reports])
            elif director_payload:
                current = self._director_public(director_payload, latest_director)
            else:
                current = reports[0] if reports else None
            if current and active is None and director_payload is None:
                current = {**current, "status": "checkpoint"}
            reviews = (
                supervisor_reviews
                + [item for report in reports for item in report.get("reviewItems", [])]
            )[:30]
            failures = (supervisor_failures + [
                {"runId": report["id"], **report["failure"], "createdUtc": report["createdUtc"]}
                for report in reports
                if report.get("failure")
            ])[:20]
            director_online = director_payload is not None
            self._snapshot_cache = {
                "schema": "operations_snapshot_v1",
                "generatedUtc": utc_now(),
                "connection": "online",
                "control": self.public_control(self.read_control()),
                "supervisor": supervisor,
                "services": [
                    {"id": "operations", "label": "Operations service", "status": "online", "detail": "Healthy"},
                    supervisor_service,
                    director_service,
                    {
                        "id": "runner",
                        "label": "Chapter runner",
                        "status": "stale" if active and active.get("stale") else ("online" if active else "idle"),
                        "detail": "Heartbeat stale" if active and active.get("stale") else ("Active" if active else "No active run"),
                    },
                    {
                        "id": "dropbox",
                        "label": "Dropbox folder",
                        "status": "online" if dropbox_ready else "unavailable",
                        "detail": "Local sync folder available" if dropbox_ready else "Not configured on this host",
                    },
                ],
                "currentRun": current,
                "runHistory": reports,
                "failures": failures,
                "reviewQueue": reviews,
                "audit": self.audit_events(),
                "capabilities": {
                    "controls": sorted(CONTROL_ACTIONS),
                    "directorConnected": director_online,
                    "supervisorConnected": bool(supervisor and supervisor.get("connected")),
                    "rawButtonsExposed": False,
                },
            }
            self._snapshot_cache_at = now
            return self._snapshot_cache

    def artifact_path(self, run_id: str, kind: str) -> tuple[Path, str, str]:
        if not SAFE_RUN_ID.fullmatch(run_id):
            raise FileNotFoundError("Unknown run")
        supervisor_dir = self._supervisor_run_dir(run_id)
        if supervisor_dir:
            if kind == "video":
                video = supervisor_dir / "segment.mp4"
                if not video.is_file():
                    raise FileNotFoundError("Video is not available")
                return video, "video/mp4", f"{run_id}.mp4"
            if kind == "summary":
                raise ValueError("summary is generated JSON, not a file")
            if kind != "screenshot":
                raise FileNotFoundError("Unknown artifact")
            active = self._active()
            raw = active.get("screenshotPath") if active and active.get("runId") == supervisor_dir.name else None
            candidate = Path(str(raw)).resolve() if raw else None
            if not candidate or not candidate.is_file():
                report = read_json(supervisor_dir / "report.json") or {}
                report_raw = report.get("finalScreenshot")
                candidate = Path(str(report_raw)).resolve() if report_raw else supervisor_dir / "final.png"
            try:
                candidate.relative_to(supervisor_dir.resolve())
            except ValueError as exc:
                raise FileNotFoundError("Artifact is outside the segment") from exc
            if not candidate.is_file():
                raise FileNotFoundError("Screenshot is not available")
            return candidate, "image/png", f"{run_id}.png"
        if run_id == "live-director" and kind == "screenshot" and self.paths.director_status_dir:
            candidate = (self.paths.director_status_dir / "current.png").resolve()
            if candidate.parent != self.paths.director_status_dir.resolve() or not candidate.is_file():
                raise FileNotFoundError("Live Director screenshot is not available")
            return candidate, "image/png", "live-director.png"
        run_dir = (self.paths.report_root / run_id).resolve()
        report_root = self.paths.report_root.resolve()
        if run_dir.parent != report_root:
            raise FileNotFoundError("Unknown run")
        if kind == "video":
            video = self._video_path(run_id)
            if not video:
                raise FileNotFoundError("Video is not available")
            return video, "video/mp4", f"{run_id}.mp4"
        if kind == "summary":
            raise ValueError("summary is generated JSON, not a file")
        if kind != "screenshot":
            raise FileNotFoundError("Unknown artifact")
        active = self._active()
        candidate: Path | None = None
        if active and active.get("runId") == run_id and active.get("screenshotPath"):
            candidate = Path(str(active["screenshotPath"])).resolve()
        if not candidate or not candidate.is_file():
            report = read_json(run_dir / "report.json") or {}
            raw = report.get("finalScreenshot")
            candidate = Path(str(raw)).resolve() if raw else run_dir / "final.png"
        try:
            candidate.relative_to(run_dir)
        except ValueError as exc:
            raise FileNotFoundError("Artifact is outside the run") from exc
        if not candidate.is_file():
            raise FileNotFoundError("Screenshot is not available")
        return candidate, "image/png", f"{run_id}.png"

    def summary_payload(self, run_id: str) -> dict[str, Any]:
        if not SAFE_RUN_ID.fullmatch(run_id):
            raise FileNotFoundError("Unknown run")
        supervisor_dir = self._supervisor_run_dir(run_id)
        if supervisor_dir:
            report = read_json(supervisor_dir / "report.json")
            if not report:
                raise FileNotFoundError("Unknown run")
            summary = report_summary(
                report,
                run_id,
                video_available=(supervisor_dir / "segment.mp4").is_file(),
            )
            summary.update(
                {
                    "source": "segment_supervisor",
                    "sourceSegmentId": supervisor_dir.name,
                }
            )
            return summary
        if run_id.startswith("director-") and self.paths.director_report_root:
            directory_name = run_id.removeprefix("director-")
            if not SAFE_RUN_ID.fullmatch(directory_name):
                raise FileNotFoundError("Unknown run")
            report_path = self.paths.director_report_root / directory_name / "report.json"
            report = read_json(report_path)
            if not report or report.get("schema") != "llm_director_run_v1":
                raise FileNotFoundError("Unknown run")
            try:
                created = datetime.fromtimestamp(report_path.stat().st_mtime, UTC).isoformat()
            except OSError as exc:
                raise FileNotFoundError("Unknown run") from exc
            return director_report_summary(report, run_id, created_utc=created)
        report = read_json(self.paths.report_root / run_id / "report.json")
        if not report:
            raise FileNotFoundError("Unknown run")
        return report_summary(report, run_id, video_available=self._video_path(run_id) is not None)


class OperationsRunControl:
    """File-backed run control that remains authoritative when every remote client disconnects."""

    def __init__(self, store: OperationsStore, run_id: str) -> None:
        if not SAFE_RUN_ID.fullmatch(run_id):
            raise ValueError("Invalid run id")
        self.store = store
        self.run_id = run_id
        self.started_utc = utc_now()

    def begin(self, **fields: Any) -> None:
        """Claim the active-run slot with a fresh record for this run."""
        payload = {
            **fields,
            "schema": "operations_active_run_v1",
            "runId": self.run_id,
            "startedUtc": self.started_utc,
            "updatedUtc": utc_now(),
            "updatedEpoch": time.time(),
        }
        atomic_write_json(self.store.paths.active_run, payload)

    def update(self, **fields: Any) -> None:
        current = read_json(self.store.paths.active_run) or {}
        current_run_id = current.get("runId")
        if current_run_id and current_run_id != self.run_id:
            raise RuntimeError(f"Active run was replaced by {current_run_id}")
        payload = {
            **current,
            **fields,
            "schema": "operations_active_run_v1",
            "runId": self.run_id,
            "startedUtc": current.get("startedUtc") or self.started_utc,
            "updatedUtc": utc_now(),
            "updatedEpoch": time.time(),
        }
        atomic_write_json(self.store.paths.active_run, payload)

    def boundary(self, *, after_action: bool = False, poll_seconds: float = 0.25) -> str:
        while True:
            control = self.store.read_control()
            state = str(control.get("state") or "running")
            if state == "emergency_stopped":
                self.update(status="emergency_stopped")
                return "emergency_stop"
            if after_action and bool(control.get("stopAfterAction")):
                self.update(status="stopped_after_action")
                return "stop_after_action"
            if state != "paused":
                return "continue"
            self.update(status="paused")
            time.sleep(max(poll_seconds, 0.01))

    def finish(self, status: str) -> None:
        self.update(status=status, finishedUtc=utc_now())
