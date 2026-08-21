"use client";

import {
  Activity,
  AlertTriangle,
  Archive,
  CircleStop,
  Clock3,
  ExternalLink,
  Gamepad2,
  HeartPulse,
  History,
  PackageOpen,
  Pause,
  Play,
  RefreshCcw,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

type ControlAction = "pause" | "resume" | "stop_after_action" | "emergency_stop";

type PartyMember = {
  slot?: number;
  species: string;
  nickname: string;
  level?: number;
  hp?: number;
  maxHp?: number;
  status?: number;
};

type InventoryItem = { item: string; quantity?: number };

type NuzlockeSummary = {
  lineageId: string;
  gameOver: boolean;
  eventCount: number;
  ruleset: {
    id: string;
    version: number;
    enabled: boolean;
    battleStyle: string;
    duplicateClause: string;
    nicknameRequired: boolean;
    blackout: string;
  };
  activeEncounter?: {
    areaId?: string;
    speciesName?: string;
    eligible?: boolean;
    reason?: string;
  } | null;
  consumedAreas: Array<{ areaId: string; outcome?: string; speciesDex?: number }>;
  nextEligibleAreas: string[];
  deaths: Array<{ pokemonId: string; nickname?: string; speciesName?: string }>;
  exceptions: Array<{ kind?: string; summary?: string; reason?: string }>;
  strategicAdvisories?: Array<{ code?: string; summary?: string; hardBlock?: boolean }>;
  recentGuardDecisions: Array<{
    allowed?: boolean;
    classification?: string;
    code?: string;
    summary?: string;
  }>;
};

type RunSummary = {
  id: string;
  source?: string;
  createdUtc: string;
  updatedUtc?: string;
  heartbeatAgeSeconds?: number;
  stale?: boolean;
  model: string;
  status: string;
  finishSummary?: string;
  actionCount: number;
  goal: string;
  chapter: { id: string; title: string; objective: string; success: boolean };
  position?: { map: string; x?: number; y?: number } | null;
  mode: string;
  party: PartyMember[];
  inventory: InventoryItem[];
  lastDecision?: { action?: number; skillId?: string; reasoning?: string; args?: Record<string, unknown> } | null;
  lastSkillResult?: {
    action?: number;
    skillId?: string;
    status?: string;
    summary?: string;
    evidence?: string[];
    warnings?: string[];
  } | null;
  checkpoint?: {
    verdict: string;
    confidence: string;
    continueRecommended: boolean;
    summary: string;
  } | null;
  timeline: Array<{
    chapterId: string;
    title: string;
    firstAction?: number;
    lastAction?: number;
    success: boolean;
  }>;
  failure?: { category: string; summary: string } | null;
  reviewItems: ReviewItem[];
  artifacts: { screenshot?: string | null; summary?: string | null; video?: string | null };
  dropbox: { status: string; playable: boolean };
  nuzlocke?: NuzlockeSummary | null;
};

type ReviewItem = {
  id: string;
  runId: string;
  title: string;
  detail: string;
  severity: string;
};

type SupervisorSummary = {
  lineageId: string;
  state: string;
  reason: string;
  currentSegment?: string | null;
  heartbeatAgeSeconds: number;
  stale: boolean;
  connected: boolean;
  segmentCount: number;
  nextSequence: number;
  latestVerdict?: string | null;
  updatedUtc: string;
};

type OperationsSnapshot = {
  schema: "operations_snapshot_v1";
  generatedUtc: string;
  connection: "online";
  control: { state: string; stopAfterAction: boolean; updatedUtc: string; revision: number };
  supervisor: SupervisorSummary | null;
  services: Array<{ id: string; label: string; status: string; detail: string }>;
  currentRun: RunSummary | null;
  runHistory: RunSummary[];
  failures: Array<{ runId: string; category: string; summary: string; createdUtc: string }>;
  reviewQueue: ReviewItem[];
  audit: Array<{ createdUtc: string; action: string; source: string; resultingState: string }>;
  capabilities: {
    controls: ControlAction[];
    directorConnected: boolean;
    supervisorConnected: boolean;
    rawButtonsExposed: false;
  };
};

const CONTROL_LABELS: Record<ControlAction, string> = {
  pause: "Pause",
  resume: "Resume",
  stop_after_action: "Stop after action",
  emergency_stop: "Emergency stop",
};

function formatTime(value?: string) {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not available";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function label(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function statusClass(status: string) {
  if (["online", "running", "ready_in_dropbox_folder", "healthy_continue"].includes(status)) return "is-good";
  if (["offline", "unavailable", "emergency_stopped", "unsafe_state", "model_error"].includes(status)) return "is-bad";
  return "is-neutral";
}

function ArtifactLinks({ run }: { run: RunSummary }) {
  return (
    <div className="operations-artifact-links" aria-label={`Artifacts for run ${run.id}`}>
      {run.artifacts.screenshot ? (
        <a href={run.artifacts.screenshot} target="_blank" rel="noreferrer">Screenshot <ExternalLink size={13} /></a>
      ) : null}
      {run.artifacts.video ? (
        <a href={run.artifacts.video} target="_blank" rel="noreferrer">Play segment <Play size={13} /></a>
      ) : null}
      {run.artifacts.summary ? (
        <a href={run.artifacts.summary} target="_blank" rel="noreferrer">Safe summary <Archive size={13} /></a>
      ) : null}
    </div>
  );
}

export default function OperationsDashboard() {
  const [snapshot, setSnapshot] = useState<OperationsSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [pendingAction, setPendingAction] = useState<ControlAction | null>(null);

  const refresh = useCallback(async (showSpinner = false) => {
    if (showSpinner) setRefreshing(true);
    try {
      const response = await fetch("/api/operations", { cache: "no-store" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "Local operations services are unavailable.");
      setSnapshot(body as OperationsSnapshot);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Local operations services are unavailable.");
    } finally {
      if (showSpinner) setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const poll = window.setInterval(() => void refresh(), 4000);
    return () => window.clearInterval(poll);
  }, [refresh]);

  const sendControl = useCallback(async (action: ControlAction) => {
    if (action === "emergency_stop" && !window.confirm("Emergency-stop at the next safe action boundary? The checkpoint will still be saved.")) {
      return;
    }
    setPendingAction(action);
    try {
      const response = await fetch("/api/operations/control", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || `${CONTROL_LABELS[action]} was not accepted.`);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : `${CONTROL_LABELS[action]} was not accepted.`);
    } finally {
      setPendingAction(null);
    }
  }, [refresh]);

  const run = snapshot?.currentRun ?? null;
  const control = snapshot?.control;
  const supervisor = snapshot?.supervisor ?? null;
  const activeRun = Boolean(run && ["starting", "running", "executing_action", "paused"].includes(run.status));
  const canControl = activeRun || Boolean(snapshot?.capabilities.directorConnected || snapshot?.capabilities.supervisorConnected);
  const location = run?.position ? `${run.position.map}${run.position.x !== undefined ? ` · ${run.position.x}, ${run.position.y}` : ""}` : "Unknown";
  const generatedAge = useMemo(() => {
    if (!snapshot?.generatedUtc) return null;
    return Math.max(Math.round((Date.now() - new Date(snapshot.generatedUtc).getTime()) / 1000), 0);
  }, [snapshot?.generatedUtc]);

  return (
    <main className="operations-shell">
      <header className="operations-header">
        <div>
          <p className="eyebrow">Remote Operations</p>
          <h1>Pokemon Player</h1>
          <p className="operations-subtitle">A private, read-mostly view of the local Nuzlocke runner.</p>
        </div>
        <div className="operations-header-actions">
          <button className="operations-refresh" type="button" onClick={() => void refresh(true)} disabled={refreshing}>
            <RefreshCcw size={15} className={refreshing ? "is-spinning" : ""} /> Refresh
          </button>
          <div className={`operations-connection ${snapshot && !error ? "is-online" : "is-offline"}`}>
            <span className="operations-pulse" aria-hidden="true" />
            {snapshot && !error ? `Connected${generatedAge !== null ? ` · ${generatedAge}s` : ""}` : "Services offline"}
          </div>
        </div>
      </header>

      {error ? (
        <div className="operations-alert" role="alert">
          <AlertTriangle size={18} />
          <div><strong>Operations data is unavailable.</strong><span>{error} The local run is independent and will keep its last durable control state.</span></div>
        </div>
      ) : null}

      <section className="operations-hero" aria-labelledby="current-run-heading">
        <div className="operations-run-copy">
          <div className="operations-section-heading">
            <div>
              <p className="eyebrow">Current run</p>
              <h2 id="current-run-heading">{run?.chapter.title ?? (supervisor ? `Lineage ${supervisor.lineageId}` : "Waiting for the launcher")}</h2>
            </div>
            <span className={`operations-chip ${statusClass(supervisor?.state ?? control?.state ?? run?.status ?? "idle")}`}>
              {label(supervisor?.state ?? control?.state ?? run?.status ?? "idle")}
            </span>
          </div>
          <p className="operations-goal">{run?.chapter.objective ?? "Start the local services to see the active chapter and Director goal."}</p>
          <div className="operations-facts">
            <div><span>Location</span><strong>{run ? location : "Not running"}</strong></div>
            <div><span>Segments</span><strong>{supervisor?.segmentCount ?? "—"}</strong></div>
            <div><span>Checkpoint</span><strong>{run?.checkpoint ? label(run.checkpoint.verdict) : "No checkpoint yet"}</strong></div>
            <div><span>Actions</span><strong>{run ? run.actionCount : "—"}</strong></div>
            <div><span>Model</span><strong>{run?.model ?? "Not connected"}</strong></div>
          </div>
          <div className="operations-controls" aria-label="Safe run controls">
            <button type="button" disabled={!canControl || control?.state === "paused" || pendingAction !== null} onClick={() => void sendControl("pause")}>
              <Pause size={17} /> Pause
            </button>
            <button type="button" disabled={!canControl || control?.state === "running" || pendingAction !== null} onClick={() => void sendControl("resume")}>
              <Play size={17} /> Resume
            </button>
            <button type="button" disabled={!canControl || control?.stopAfterAction || pendingAction !== null} onClick={() => void sendControl("stop_after_action")}>
              <Clock3 size={17} /> {control?.stopAfterAction ? "Stop queued" : "Stop after action"}
            </button>
            <button type="button" className="is-danger" disabled={!canControl || pendingAction !== null} onClick={() => void sendControl("emergency_stop")}>
              <CircleStop size={17} /> Emergency stop
            </button>
          </div>
          <p className="operations-control-note">Controls take effect at safe action boundaries and remain durable if this page disconnects.</p>
        </div>

        <div className="operations-screen-card">
          {run?.artifacts.screenshot ? (
            // The URL is generated server-side from an exact run id and never accepts a filesystem path.
            <img src={run.artifacts.screenshot} alt={`Current game state for ${run.chapter.title}`} />
          ) : (
            <div className="operations-screen-placeholder"><Gamepad2 size={30} aria-hidden="true" /><span>No live screenshot</span></div>
          )}
          <small>{run ? `Updated ${formatTime(run.updatedUtc || run.createdUtc)}` : "Snapshots stay local behind a restricted artifact endpoint."}</small>
        </div>
      </section>

      <section className="operations-grid operations-grid-primary">
        <article className="operations-card">
          <div className="operations-card-title"><HeartPulse size={19} /><div><p className="eyebrow">System health</p><h2>Services</h2></div></div>
          <ul className="operations-service-list">
            {(snapshot?.services ?? [
              { id: "operations", label: "Operations service", status: "offline", detail: "Waiting for launcher" },
              { id: "director", label: "Director player", status: "unknown", detail: "Unknown" },
              { id: "runner", label: "Chapter runner", status: "unknown", detail: "Unknown" },
              { id: "dropbox", label: "Dropbox folder", status: "unknown", detail: "Unknown" },
            ]).map((service) => (
              <li key={service.id}><div><span>{service.label}</span><small>{service.detail}</small></div><strong className={statusClass(service.status)}>{label(service.status)}</strong></li>
            ))}
          </ul>
        </article>

        <article className="operations-card operations-card-wide">
          <div className="operations-card-title"><Sparkles size={19} /><div><p className="eyebrow">Director agency</p><h2>Latest decision</h2></div></div>
          {run?.lastDecision ? (
            <div className="operations-decision">
              <div><span>Selected intention</span><strong>{run.lastDecision.skillId ? label(run.lastDecision.skillId) : "Decision pending"}</strong></div>
              <p>{run.lastDecision.reasoning || "The decision has been recorded but no plain-language reasoning was available."}</p>
            </div>
          ) : <div className="operations-empty-state">No Director decision has been recorded.</div>}
          <div className="operations-result">
            <span>Latest skill result</span>
            <strong>{run?.lastSkillResult?.summary ?? "No skill result has been recorded."}</strong>
            {run?.lastSkillResult?.warnings?.length ? <small>{run.lastSkillResult.warnings.map(label).join(" · ")}</small> : null}
          </div>
        </article>

        <article className="operations-card">
          <div className="operations-card-title"><Users size={19} /><div><p className="eyebrow">Game state</p><h2>Party & inventory</h2></div></div>
          {run?.party.length ? (
            <ul className="operations-party-list">
              {run.party.map((member) => (
                <li key={`${member.slot}-${member.species}`}><div><strong>{member.nickname || member.species}</strong><span>{member.species} · Lv{member.level ?? "?"}</span></div><small>HP {member.hp ?? "?"}/{member.maxHp ?? "?"}</small></li>
              ))}
            </ul>
          ) : <div className="operations-empty-state compact">No party data available.</div>}
          <div className="operations-inventory">
            <PackageOpen size={15} />
            <span>{run?.inventory.length ? run.inventory.map((item) => `${item.item} ×${item.quantity ?? "?"}`).join(" · ") : "No inventory data"}</span>
          </div>
        </article>

        <article className="operations-card operations-card-wide">
          <div className="operations-card-title"><ShieldCheck size={19} /><div><p className="eyebrow">Run contract</p><h2>Rules & lineage</h2></div></div>
          {run?.nuzlocke ? (
            <div className="operations-decision">
              <div>
                <span>Ruleset</span>
                <strong>{label(run.nuzlocke.ruleset.id)} v{run.nuzlocke.ruleset.version} · {run.nuzlocke.ruleset.enabled ? "Enforced" : "Standard run"}</strong>
              </div>
              <p>
                {label(run.nuzlocke.ruleset.battleStyle)} battle style · {label(run.nuzlocke.ruleset.duplicateClause)} duplicate clause · {run.nuzlocke.ruleset.nicknameRequired ? "Nicknames required" : "Nicknames optional"}
              </p>
              <div className="operations-facts">
                <div><span>Deaths</span><strong>{run.nuzlocke.deaths.length}</strong></div>
                <div><span>Areas used</span><strong>{run.nuzlocke.consumedAreas.length}</strong></div>
                <div><span>Exceptions</span><strong>{run.nuzlocke.exceptions.length}</strong></div>
                <div><span>Lineage</span><strong>{run.nuzlocke.gameOver ? "Game over" : "Active"}</strong></div>
              </div>
              {run.nuzlocke.activeEncounter ? (
                <p>
                  Current encounter: {run.nuzlocke.activeEncounter.speciesName ?? "Unknown"} in {label(run.nuzlocke.activeEncounter.areaId ?? "unknown area")} · {label(run.nuzlocke.activeEncounter.reason ?? "unclassified")}
                </p>
              ) : null}
              {run.nuzlocke.strategicAdvisories?.length ? (
                <p>Advisory: {run.nuzlocke.strategicAdvisories[0].summary}</p>
              ) : null}
              <small>
                Next known eligible areas: {run.nuzlocke.nextEligibleAreas.length ? run.nuzlocke.nextEligibleAreas.slice(0, 6).map(label).join(" · ") : "None in configured area list"}
              </small>
              {run.nuzlocke.recentGuardDecisions.some((decision) => decision.allowed === false) ? (
                <div className="operations-result">
                  <span>Latest blocked action</span>
                  <strong>{[...run.nuzlocke.recentGuardDecisions].reverse().find((decision) => decision.allowed === false)?.summary}</strong>
                </div>
              ) : null}
            </div>
          ) : <div className="operations-empty-state">No durable rules ledger is attached to this run.</div>}
        </article>
      </section>

      <section className="operations-grid operations-grid-secondary">
        <article className="operations-card">
          <div className="operations-card-title"><Activity size={19} /><div><p className="eyebrow">Current lineage</p><h2>Chapter timeline</h2></div></div>
          {run?.timeline.length ? (
            <ol className="operations-timeline">
              {run.timeline.map((item, index) => (
                <li key={`${item.chapterId}-${index}`} className={item.success ? "is-complete" : ""}>
                  <span aria-hidden="true" />
                  <div><strong>{item.title}</strong><small>Actions {item.firstAction ?? "?"}–{item.lastAction ?? item.firstAction ?? "?"}</small></div>
                </li>
              ))}
            </ol>
          ) : <div className="operations-empty-state">Run events will appear here as compact updates.</div>}
        </article>

        <article className="operations-card">
          <div className="operations-card-title"><ShieldCheck size={19} /><div><p className="eyebrow">Deferred review</p><h2>Review queue</h2></div></div>
          {snapshot?.reviewQueue.length ? (
            <ul className="operations-review-list">
              {snapshot.reviewQueue.map((item) => <li key={item.id}><strong>{item.title}</strong><p>{item.detail}</p><small>{label(item.severity)} · {item.runId}</small></li>)}
            </ul>
          ) : <div className="operations-empty-state">No items are waiting for review.</div>}
        </article>

        <article className="operations-card">
          <div className="operations-card-title"><AlertTriangle size={19} /><div><p className="eyebrow">Triage</p><h2>Failure summaries</h2></div></div>
          {snapshot?.failures.length ? (
            <ul className="operations-review-list">
              {snapshot.failures.map((failure) => <li key={`${failure.runId}-${failure.category}`}><strong>{label(failure.category)}</strong><p>{failure.summary}</p><small>{formatTime(failure.createdUtc)} · {failure.runId}</small></li>)}
            </ul>
          ) : <div className="operations-empty-state">No classified failures in recent runs.</div>}
        </article>
      </section>

      <section className="operations-section-block">
        <div className="operations-card-title"><History size={19} /><div><p className="eyebrow">Recent evidence</p><h2>Run history</h2></div></div>
        {snapshot?.runHistory.length ? (
          <div className="operations-history-list">
            {snapshot.runHistory.map((historyRun) => (
              <article key={historyRun.id}>
                <div><strong>{historyRun.chapter.title}</strong><span>{formatTime(historyRun.createdUtc)} · {historyRun.actionCount} actions · {historyRun.model} · {historyRun.position?.map ?? "Unknown location"}</span></div>
                <span className={`operations-verdict ${statusClass(historyRun.checkpoint?.verdict ?? historyRun.status)}`}>{label(historyRun.checkpoint?.verdict ?? historyRun.status)}</span>
                <ArtifactLinks run={historyRun} />
              </article>
            ))}
          </div>
        ) : <div className="operations-empty-state">Completed run summaries will appear here.</div>}
      </section>

      <section className="operations-section-block">
        <div className="operations-card-title"><ShieldCheck size={19} /><div><p className="eyebrow">Command record</p><h2>Control audit</h2></div></div>
        {snapshot?.audit.length ? (
          <ul className="operations-audit-list">
            {snapshot.audit.map((event, index) => <li key={`${event.createdUtc}-${index}`}><strong>{label(event.action)}</strong><span>{formatTime(event.createdUtc)}</span><small>Result: {label(event.resultingState)}</small></li>)}
          </ul>
        ) : <div className="operations-empty-state compact">No remote control commands have been issued.</div>}
      </section>
    </main>
  );
}
