"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BadgeCheck,
  Beaker,
  Bot,
  Check,
  CircleHelp,
  ClipboardCheck,
  Copy,
  Database,
  FlaskConical,
  Gamepad2,
  Hammer,
  Image as ImageIcon,
  ListChecks,
  MapPinned,
  Plus,
  Play,
  RefreshCcw,
  Save,
  Search,
  ShieldAlert,
  ShieldCheck,
  Swords,
  X,
} from "lucide-react";
import type {
  DirectiveCase,
  DirectiveDeck,
  DirectorPlayerStatus,
  DirectorSkillAvailability,
  DirectorVerdict,
  LlmDirectorChatMessage,
  LlmDirectorRunResult,
  InterrogationAnswer,
  PromotionAssertionValidationResult,
  PromotionCatalog,
  PromotionRecord,
  PromotionReference,
  PromotionValidationResult,
  SkillCatalog,
  SkillDefinition,
  SkillStateRecord,
  StateRecord,
} from "@/lib/types";

type Tab = "directives" | "states" | "skills" | "promotions" | "interrogate" | "director" | "llm-player";

type DashboardProps = {
  directiveDeck: DirectiveDeck;
  states: StateRecord[];
  skillCatalog: SkillCatalog;
  skillStates: SkillStateRecord[];
  promotionCatalog: PromotionCatalog;
};

type EvidenceOption = {
  id: string;
  label: string;
  kind: string;
  metadataPath: string;
  statePath: string;
  screenshotPath: string;
  expectedObservation: string;
  captureCommand: string;
  localStateExists: boolean;
};

const validTabs = new Set<Tab>([
  "directives",
  "states",
  "skills",
  "promotions",
  "interrogate",
  "director",
  "llm-player",
]);

export function Dashboard({
  directiveDeck,
  states: initialStates,
  skillCatalog,
  skillStates,
  promotionCatalog,
}: DashboardProps) {
  const [activeTab, setActiveTab] = useState<Tab>("directives");
  const [states, setStates] = useState(initialStates);
  const [selectedCaseId, setSelectedCaseId] = useState(directiveDeck.cases[0]?.id ?? "");
  const [selectedStateId, setSelectedStateId] = useState(initialStates[0]?.id ?? "");
  const [selectedSkillId, setSelectedSkillId] = useState(skillCatalog.skills[0]?.id ?? "");
  const [selectedPromotionId, setSelectedPromotionId] = useState(promotionCatalog.promotions[0]?.id ?? "");
  const [promotionCatalogState, setPromotionCatalogState] = useState(promotionCatalog);
  const [workspaceStateRestored, setWorkspaceStateRestored] = useState(false);
  const selectedCase = directiveDeck.cases.find((item) => item.id === selectedCaseId) ?? directiveDeck.cases[0];
  const selectedState = states.find((item) => item.id === selectedStateId) ?? states[0];
  const selectedSkill =
    skillCatalog.skills.find((item) => item.id === selectedSkillId) ?? skillCatalog.skills[0];
  const selectedPromotion =
    promotionCatalogState.promotions.find((item) => item.id === selectedPromotionId) ??
    promotionCatalogState.promotions[0];

  useEffect(() => {
    setActiveTab(readStoredTab("lab-ui.activeTab", "directives"));
    setSelectedCaseId(readStoredValue("lab-ui.selectedCaseId", directiveDeck.cases[0]?.id ?? ""));
    setSelectedStateId(readStoredValue("lab-ui.selectedStateId", initialStates[0]?.id ?? ""));
    setSelectedSkillId(readStoredValue("lab-ui.selectedSkillId", skillCatalog.skills[0]?.id ?? ""));
    setSelectedPromotionId(readStoredValue("lab-ui.selectedPromotionId", promotionCatalog.promotions[0]?.id ?? ""));
    setWorkspaceStateRestored(true);
  }, [directiveDeck.cases, initialStates, promotionCatalog.promotions, skillCatalog.skills]);

  useEffect(() => {
    if (workspaceStateRestored) {
      persistValue("lab-ui.activeTab", activeTab);
    }
  }, [activeTab, workspaceStateRestored]);
  useEffect(() => {
    if (workspaceStateRestored) {
      persistValue("lab-ui.selectedCaseId", selectedCaseId);
    }
  }, [selectedCaseId, workspaceStateRestored]);
  useEffect(() => {
    if (workspaceStateRestored) {
      persistValue("lab-ui.selectedStateId", selectedStateId);
    }
  }, [selectedStateId, workspaceStateRestored]);
  useEffect(() => {
    if (workspaceStateRestored) {
      persistValue("lab-ui.selectedSkillId", selectedSkillId);
    }
  }, [selectedSkillId, workspaceStateRestored]);
  useEffect(() => {
    if (workspaceStateRestored) {
      persistValue("lab-ui.selectedPromotionId", selectedPromotionId);
    }
  }, [selectedPromotionId, workspaceStateRestored]);

  useEffect(() => {
    if (selectedCase && selectedCase.id !== selectedCaseId) {
      setSelectedCaseId(selectedCase.id);
    }
  }, [selectedCase, selectedCaseId]);

  useEffect(() => {
    if (selectedState && selectedState.id !== selectedStateId) {
      setSelectedStateId(selectedState.id);
    }
  }, [selectedState, selectedStateId]);

  useEffect(() => {
    if (selectedSkill && selectedSkill.id !== selectedSkillId) {
      setSelectedSkillId(selectedSkill.id);
    }
  }, [selectedSkill, selectedSkillId]);

  useEffect(() => {
    if (selectedPromotion && selectedPromotion.id !== selectedPromotionId) {
      setSelectedPromotionId(selectedPromotion.id);
    }
  }, [selectedPromotion, selectedPromotionId]);

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Pokemon Player Research Rig</p>
          <h1>Lab Console</h1>
        </div>
        <div className="score-strip" aria-label="Current lab counts">
          <Metric icon={<ClipboardCheck size={16} />} label="Directives" value={directiveDeck.cases.length} />
          <Metric icon={<Database size={16} />} label="States" value={states.length} />
          <Metric icon={<Hammer size={16} />} label="Skills" value={skillCatalog.skills.length} />
          <Metric icon={<ShieldCheck size={16} />} label="Promotions" value={promotionCatalogState.promotions.length} />
          <Metric icon={<BadgeCheck size={16} />} label="Approved" value={countApproved(states)} />
        </div>
      </header>

      <nav className="tabs" aria-label="Lab workspaces">
        <TabButton active={activeTab === "directives"} onClick={() => setActiveTab("directives")} icon={<Bot size={17} />} label="Directives" />
        <TabButton active={activeTab === "states"} onClick={() => setActiveTab("states")} icon={<Database size={17} />} label="States" />
        <TabButton active={activeTab === "skills"} onClick={() => setActiveTab("skills")} icon={<Hammer size={17} />} label="Skills" />
        <TabButton active={activeTab === "promotions"} onClick={() => setActiveTab("promotions")} icon={<ShieldCheck size={17} />} label="Promotions" />
        <TabButton active={activeTab === "interrogate"} onClick={() => setActiveTab("interrogate")} icon={<CircleHelp size={17} />} label="Interrogate" />
        <TabButton active={activeTab === "director"} onClick={() => setActiveTab("director")} icon={<Gamepad2 size={17} />} label="Director" />
        <TabButton active={activeTab === "llm-player"} onClick={() => setActiveTab("llm-player")} icon={<Bot size={17} />} label="LLM Player" />
      </nav>

      {activeTab === "directives" && selectedCase ? (
        <DirectiveWorkspace deck={directiveDeck} selectedCase={selectedCase} onSelectCase={setSelectedCaseId} />
      ) : null}

      {activeTab === "states" && selectedState ? (
        <StateWorkspace
          states={states}
          selectedState={selectedState}
          onSelectState={setSelectedStateId}
          onStateUpdated={(updated) => setStates((current) => current.map((state) => (state.id === updated.id ? updated : state)))}
        />
      ) : null}

      {activeTab === "interrogate" && selectedState ? (
        <InterrogateWorkspace states={states} selectedState={selectedState} onSelectState={setSelectedStateId} />
      ) : null}

      {activeTab === "skills" && selectedSkill ? (
        <SkillsWorkspace
          skills={skillCatalog.skills}
          skillStates={skillStates}
          selectedSkill={selectedSkill}
          onSelectSkill={setSelectedSkillId}
        />
      ) : null}

      {activeTab === "promotions" && selectedPromotion ? (
        <PromotionsWorkspace
          promotions={promotionCatalogState.promotions}
          selectedPromotion={selectedPromotion}
          states={states}
          skillStates={skillStates}
          onSelectPromotion={setSelectedPromotionId}
          onPromotionCatalogUpdated={setPromotionCatalogState}
        />
      ) : null}

      {activeTab === "director" ? <DirectorWorkspace states={states} /> : null}

      {activeTab === "llm-player" ? <LlmPlayerWorkspace /> : null}
    </main>
  );
}

function LlmPlayerWorkspace() {
  const defaultGoal = "Complete Capsule A: catch a Pikachu or another allowed early wild Pokemon in or near Viridian Forest without blacking out.";
  const [goal, setGoal] = useState(defaultGoal);
  const [selectedProvider, setSelectedProvider] = useState("openai-responses");
  const [selectedModel, setSelectedModel] = useState("gpt-5.4-nano");
  const [reasoningEffort, setReasoningEffort] = useState("low");
  const [tickIntervalSeconds, setTickIntervalSeconds] = useState(30);
  const [messageLimit, setMessageLimit] = useState(20);
  const [userMessage, setUserMessage] = useState("");
  const [debugPayload, setDebugPayload] = useState<{ title: string; payload: unknown } | null>(null);
  const [lastRequestMessages, setLastRequestMessages] = useState<LlmDirectorChatMessage[]>([]);
  const [messageDebugPayloads, setMessageDebugPayloads] = useState<Record<string, unknown>>({});
  const [tokenTotals, setTokenTotals] = useState({ input: 0, output: 0, total: 0 });
  const [messages, setMessages] = useState<LlmDirectorChatMessage[]>([
    {
      role: "assistant",
      content: "Give me a Capsule A goal and I will act through the available Director skills.",
      kind: "system",
    },
  ]);
  const [result, setResult] = useState<LlmDirectorRunResult | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [autoTickEnabled, setAutoTickEnabled] = useState(false);
  const [tickCount, setTickCount] = useState(0);
  const [lastTickAt, setLastTickAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const runningRef = useRef(false);
  const messagesRef = useRef(messages);
  const tickCountRef = useRef(0);

  useEffect(() => {
    runningRef.current = isRunning;
  }, [isRunning]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    if (!autoTickEnabled) {
      return;
    }
    const handle = window.setInterval(() => {
      if (!runningRef.current) {
        void runLlmDirector({ appendGoal: false });
      }
    }, Math.max(1, tickIntervalSeconds) * 1000);
    return () => window.clearInterval(handle);
  }, [autoTickEnabled, goal, messageLimit, reasoningEffort, selectedModel, selectedProvider, tickIntervalSeconds]);

  async function runLlmDirector(options: { appendGoal?: boolean } = {}) {
    const trimmedGoal = goal.trim();
    if (!trimmedGoal) {
      return;
    }
    if (runningRef.current) {
      return;
    }
    const appendGoal = options.appendGoal ?? true;
    const nextTick = tickCountRef.current + 1;
    tickCountRef.current = nextTick;
    const baseMessages = messagesRef.current;
    const nextMessages: LlmDirectorChatMessage[] = trimLlmMessages(
      appendGoal
      ? [
          ...baseMessages,
          { role: "user", content: trimmedGoal, createdUtc: new Date().toISOString(), kind: "goal" },
        ]
      : baseMessages,
      messageLimit,
    );
    setMessages(nextMessages);
    setLastRequestMessages(nextMessages);
    setTickCount(nextTick);
    setLastTickAt(new Date().toISOString());
    setIsRunning(true);
    setError(null);
    try {
      const response = await fetch("/api/llm-player", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          goal: trimmedGoal,
          provider: selectedProvider,
          messages: nextMessages,
          tick: nextTick,
          model: selectedModel,
          reasoningEffort,
          messageLimit,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error ?? "LLM Director run failed.");
      }
      const runResult = data as LlmDirectorRunResult;
      setResult(runResult);
      setMessages(runResult.messages);
      messagesRef.current = runResult.messages;
      setLastRequestMessages(runResult.requestMessages ?? nextMessages);
      if (runResult.requestSummary) {
        const debugPayload = {
          schema: "director_request_debug_v1",
          reportPath: runResult.reportPath,
          tick: runResult.tick,
          requestMessages: runResult.requestMessages ?? nextMessages,
          requestSummary: runResult.requestSummary,
          usage: runResult.usage ?? {},
          steps: runResult.steps,
        };
        const debugMessages = [
          ...(runResult.requestMessages ?? nextMessages),
          ...runResult.messages.filter((message) => message.kind === "llm_director_result").slice(-1),
        ];
        setMessageDebugPayloads((current) => {
          const next = { ...current };
          for (const message of debugMessages) {
            next[llmMessageKey(message)] = debugPayload;
          }
          return next;
        });
      }
      setTokenTotals((current) => addUsageToTotals(current, runResult.usage));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "LLM Director run failed.");
    } finally {
      setIsRunning(false);
    }
  }

  const playerStatus = result?.playerStatus ?? null;
  const snapshot = playerStatus?.snapshot;
  const enabledSkills = playerStatus?.skills?.filter((skill) => skill.enabled).map((skill) => skill.id) ?? [];

  function addUserMessage() {
    const content = userMessage.trim();
    if (!content) {
      return;
    }
    const nextMessages: LlmDirectorChatMessage[] = [
      ...messagesRef.current,
      { role: "user", content, createdUtc: new Date().toISOString(), kind: "steering" },
    ];
    const cappedMessages = trimLlmMessages(nextMessages, messageLimit);
    setMessages(cappedMessages);
    messagesRef.current = cappedMessages;
    setUserMessage("");
  }

  return (
    <section className="workspace llm-player-workspace">
      <aside className="llm-chat-panel">
        <div className="section-header compact-header">
          <div>
            <p className="eyebrow">LLM Director</p>
            <h2>Capsule Chat</h2>
          </div>
          <StatusPill status={isRunning ? "busy" : result?.status ?? "ready"} />
        </div>

        <label className="llm-goal-input">
          <span>Goal</span>
          <textarea value={goal} onChange={(event) => setGoal(event.target.value)} rows={5} />
        </label>
        <div className="llm-settings-grid">
          <label>
            <span>Provider</span>
            <select
              value={selectedProvider}
              onChange={(event) => {
                const provider = event.target.value;
                setSelectedProvider(provider);
                setSelectedModel(provider === "lmstudio-chat" ? "google/gemma-4-e4b" : "gpt-5.4-nano");
              }}
            >
              <option value="openai-responses">OpenAI Responses</option>
              <option value="lmstudio-chat">LM Studio Chat</option>
            </select>
          </label>
          <label>
            <span>Model</span>
            <input value={selectedModel} onChange={(event) => setSelectedModel(event.target.value)} />
          </label>
          <label>
            <span>Reasoning</span>
            <select value={reasoningEffort} onChange={(event) => setReasoningEffort(event.target.value)}>
              <option value="minimal">minimal</option>
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
            </select>
          </label>
          <label>
            <span>Tick Seconds</span>
            <input
              type="number"
              min={1}
              max={600}
              value={tickIntervalSeconds}
              onChange={(event) => setTickIntervalSeconds(clampInteger(event.target.value, 1, 600, 30))}
            />
          </label>
          <label>
            <span>Message Cap</span>
            <input
              type="number"
              min={1}
              max={100}
              value={messageLimit}
              onChange={(event) => {
                const nextLimit = clampInteger(event.target.value, 1, 100, 20);
                setMessageLimit(nextLimit);
                const cappedMessages = trimLlmMessages(messagesRef.current, nextLimit);
                setMessages(cappedMessages);
                messagesRef.current = cappedMessages;
              }}
            />
          </label>
        </div>
        <div className="llm-control-row">
          <button className="primary-action" disabled={isRunning || !goal.trim()} onClick={() => runLlmDirector()}>
            <Bot size={16} />
            {isRunning ? "Running" : "Run Tick"}
          </button>
          <button
            className="secondary-action"
            disabled={!goal.trim()}
            onClick={() => {
              const next = !autoTickEnabled;
              setAutoTickEnabled(next);
              if (next && !runningRef.current) {
                void runLlmDirector({
                  appendGoal: messagesRef.current.some((message) => message.kind === "goal") === false,
                });
              }
            }}
          >
            <RefreshCcw size={16} />
            {autoTickEnabled ? `Stop ${tickIntervalSeconds}s` : `Start ${tickIntervalSeconds}s`}
          </button>
        </div>
        <p className="muted">
          {autoTickEnabled
            ? `Prompting every ${tickIntervalSeconds} seconds; ticks are skipped while a tool call is in flight.`
            : "Manual tick mode."}
          {lastTickAt ? ` Last tick: ${new Date(lastTickAt).toLocaleTimeString()}.` : ""}
        </p>

        {error ? (
          <div className="callout danger">
            <ShieldAlert size={18} />
            <span>{error}</span>
          </div>
        ) : null}

        <div className="llm-message-list">
          {messages.map((message, index) => (
            <div className={`llm-message ${message.role}`} key={`${message.role}-${index}`}>
              <button
                className="llm-message-debug"
                onClick={() =>
                  setDebugPayload({
                    title: `Director Input For Message ${index + 1}`,
                    payload:
                      messageDebugPayloads[llmMessageKey(message)] ?? {
                        note: "No Director request summary has been recorded for this message yet.",
                        message,
                        lastRequestMessages,
                      },
                  })
                }
                title="Inspect Director input"
              >
                JSON
              </button>
              <span>
                {message.role}
                {message.kind ? ` / ${message.kind}` : ""}
              </span>
              <p>{message.content}</p>
            </div>
          ))}
        </div>
        <div className="llm-steering-box">
          <label>
            <span>Message The Agent</span>
            <textarea
              value={userMessage}
              onChange={(event) => setUserMessage(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                  event.preventDefault();
                  addUserMessage();
                }
              }}
              rows={3}
              placeholder="Add steering context for the next tick..."
            />
          </label>
          <div className="llm-chat-actions">
            <button className="secondary-action compact" onClick={addUserMessage} disabled={!userMessage.trim()}>
              <Plus size={16} />
              Add Message
            </button>
            <button
              className="secondary-action compact"
              onClick={() =>
                setDebugPayload({
                  title: "Last Director Request",
                  payload: result?.requestSummary
                    ? {
                        schema: "director_request_debug_v1",
                        reportPath: result.reportPath,
                        tick: result.tick,
                        requestMessages: result.requestMessages ?? lastRequestMessages,
                        requestSummary: result.requestSummary,
                        usage: result.usage ?? {},
                        steps: result.steps,
                      }
                    : { requestMessages: lastRequestMessages },
                })
              }
              disabled={!lastRequestMessages.length}
            >
              <Search size={16} />
              Debug Request
            </button>
          </div>
        </div>
        {debugPayload ? (
          <JsonDebugModal
            title={debugPayload.title}
            payload={debugPayload.payload}
            onClose={() => setDebugPayload(null)}
          />
        ) : null}
      </aside>

      <section className="detail llm-run-detail">
        <div className="section-header">
          <div>
            <p className="eyebrow">Autonomous Run</p>
            <h2>{result ? result.model : "Waiting"}</h2>
          </div>
          {result?.reportPath ? <StatusPill status={result.status} /> : null}
        </div>

        {result?.reportPath ? <RunCommandPanel label="LLM Run Report" command={result.reportPath} stateFileExists /> : null}

        {playerStatus?.screenshotPath ? (
          <div className="screenshot-panel llm-screenshot">
            <div className="command-header">
              <div>
                <span>Player Snapshot</span>
                <small>{snapshot?.position?.map_name ?? "unknown location"}</small>
              </div>
            </div>
            <ScreenshotImage
              path={playerStatus.screenshotPath}
              alt="LLM player current screenshot"
              cacheKey={`${result?.tick ?? tickCount}-${result?.screenshotPath ?? ""}-${lastTickAt ?? ""}`}
            />
          </div>
        ) : null}

        {snapshot ? (
          <div className="fact-grid compact-facts director-facts">
            <InfoBlock label="Mode" value={snapshot.mode} />
            <InfoBlock label="Location" value={snapshot.position?.map_name ?? "unknown"} />
            <InfoBlock label="Poke Balls" value={String(pokeBallCountFromSnapshot(snapshot))} />
            <InfoBlock label="Enabled" value={enabledSkills.length ? String(enabledSkills.length) : "none"} />
            <InfoBlock label="Screenshot" value={result?.screenshotSent ? "sent" : "not sent"} />
            <InfoBlock label="Tick" value={String(tickCount)} />
            <InfoBlock label="Input Tokens" value={String(tokenTotals.input)} />
            <InfoBlock label="Output Tokens" value={String(tokenTotals.output)} />
            <InfoBlock label="Total Tokens" value={String(tokenTotals.total)} />
          </div>
        ) : null}

        {result ? (
          <>
            <h3>Run Summary</h3>
            <div className={`verdict ${result.status === "completed" ? "pass" : "deferred"}`}>
              <div className="verdict-title">
                <Bot size={18} />
                <strong>{result.status}</strong>
                {result.provider?.provider ? <span>{result.provider.provider}</span> : null}
                <span>{result.model}</span>
                {result.reasoningEffort ? <span>{result.reasoningEffort}</span> : null}
              </div>
              <p>{result.assistantMessage}</p>
            </div>

            <h3>Tool Transcript</h3>
            <div className="director-history">
              {result.steps.length ? (
                result.steps.map((step, index) => (
                  <div className="history-row" key={`${step.name}-${index}`}>
                    <StatusPill status={step.status ?? step.kind} />
                    <strong>{step.name}</strong>
                    <span>
                      {step.plaintextReasoning ? `${step.plaintextReasoning} Procedural result: ` : ""}
                      {step.summary}
                    </span>
                  </div>
                ))
              ) : (
                <div className="callout">
                  <Activity size={18} />
                  <span>No tool calls were recorded.</span>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="callout">
            <Bot size={18} />
            <span>The LLM Director will use model-selected skills here; no manual controls are exposed on this page.</span>
          </div>
        )}
      </section>
    </section>
  );
}

function DirectorWorkspace({ states }: { states: StateRecord[] }) {
  const extraLoadableStates = [
    {
      id: "navigation:viridian_forest_mid_north",
      name: "Viridian Forest mid_north",
      statePath:
        "research/artifacts/director-player-runs/navigate_within_viridian_forest_region/20260624T191255Z/after.state",
      localStateExists: true,
    },
  ];
  const localStates = [
    ...extraLoadableStates,
    ...states
      .filter((state) => state.localStateExists && state.statePath)
      .map((state) => ({
        id: state.id,
        name: state.name,
        statePath: state.statePath ?? "",
        localStateExists: state.localStateExists,
      })),
  ];
  const [status, setStatus] = useState<DirectorPlayerStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [executingSkillId, setExecutingSkillId] = useState<string | null>(null);
  const [captureTitle, setCaptureTitle] = useState("");
  const [captureDescription, setCaptureDescription] = useState("");
  const [captureMessage, setCaptureMessage] = useState<string | null>(null);
  const [captureReportPath, setCaptureReportPath] = useState<string | null>(null);
  const [selectedStatePath, setSelectedStatePath] = useState(
    localStates.find((state) => state.localStateExists && state.statePath)?.statePath ?? "",
  );
  const [skillArgs, setSkillArgs] = useState<Record<string, string>>({
    button: "a",
    move: "",
    patch: "forest_grass",
    switchTarget: "",
    target: "forest_grass",
  });
  const startCommand = `.\\.venv\\Scripts\\python scripts\\director_player.py --status-period-seconds 5 --idle-tick-hz 60${
    selectedStatePath ? ` --state "${selectedStatePath}"` : ""
  }`;

  async function refreshStatus() {
    setIsRefreshing(true);
    try {
      const response = await fetch("/api/director-player", { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error ?? "Director player is offline.");
      }
      setStatus(data as DirectorPlayerStatus);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Director player is offline.");
      setStatus(null);
    } finally {
      setIsRefreshing(false);
    }
  }

  useEffect(() => {
    refreshStatus();
    const handle = window.setInterval(refreshStatus, 3000);
    return () => window.clearInterval(handle);
  }, []);

  async function executeSkill(skill: DirectorSkillAvailability) {
    setExecutingSkillId(skill.id);
    try {
      const response = await fetch("/api/director-player", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          skillId: skill.id,
          args: directorArgsForSkill(skill, skillArgs),
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error ?? "Skill execution failed.");
      }
      setStatus(data as DirectorPlayerStatus);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Skill execution failed.");
    } finally {
      setExecutingSkillId(null);
    }
  }

  async function loadSelectedState() {
    if (!selectedStatePath) {
      return;
    }
    setExecutingSkillId("load_state");
    try {
      const response = await fetch("/api/director-player", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "load_state", statePath: selectedStatePath }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error ?? "State load failed.");
      }
      setStatus(data as DirectorPlayerStatus);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "State load failed.");
    } finally {
      setExecutingSkillId(null);
    }
  }

  async function sendManualButton(button: string) {
    setExecutingSkillId(`manual_${button}`);
    try {
      const response = await fetch("/api/director-player", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "manual_input", button }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error ?? "Manual input failed.");
      }
      setStatus(data as DirectorPlayerStatus);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Manual input failed.");
    } finally {
      setExecutingSkillId(null);
    }
  }

  async function captureInterpretation() {
    setExecutingSkillId("capture_interpretation");
    setCaptureMessage(null);
    setCaptureReportPath(null);
    try {
      const response = await fetch("/api/director-player", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "capture_interpretation",
          title: captureTitle,
          description: captureDescription,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error ?? "Interpretation capture failed.");
      }
      const nextStatus = data as DirectorPlayerStatus;
      setStatus(nextStatus);
      setCaptureMessage(nextStatus.lastResult?.summary ?? "Interpretation captured.");
      setCaptureReportPath(nextStatus.lastResult?.reportPath ?? null);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Interpretation capture failed.");
    } finally {
      setExecutingSkillId(null);
    }
  }

  function updateSkillArg(key: string, value: string) {
    setSkillArgs((current) => ({ ...current, [key]: value }));
  }

  const snapshot = status?.snapshot;
  const skills = status?.skills ?? [];
  const availableSkills = skills.filter((skill) => skill.enabled);
  const enabledSkillCount = availableSkills.length;

  return (
    <section className="workspace director-workspace">
      <div className="director-grid">
        <aside className="director-panel">
          <div className="section-header compact-header">
            <div>
              <p className="eyebrow">Director Player</p>
              <h2>{status ? "Connected" : "Offline"}</h2>
            </div>
            <button className="icon-action" onClick={refreshStatus} disabled={isRefreshing} title="Refresh player status">
              <RefreshCcw size={16} />
              Refresh
            </button>
          </div>

          {error ? (
            <div className="callout danger">
              <ShieldAlert size={18} />
              <span>{error}</span>
            </div>
          ) : null}

          <RunCommandPanel
            label="Start Player"
            command={startCommand}
            stateFileExists
            disabledMessage=""
          />

          {status?.session ? (
            <RunCommandPanel
              label="Session Event Log"
              command={status.session.eventLogPath}
              stateFileExists
              disabledMessage=""
            />
          ) : null}

          <div className="state-load-panel">
            <label>
              <span>Load State</span>
              <select value={selectedStatePath} onChange={(event) => setSelectedStatePath(event.target.value)}>
                {localStates.map((state) => (
                  <option key={state.id} value={state.statePath ?? ""}>
                    {state.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="secondary-action"
              disabled={!status || !selectedStatePath || executingSkillId !== null}
              onClick={loadSelectedState}
            >
              <MapPinned size={16} />
              Load
            </button>
          </div>

          {status?.screenshotPath ? (
            <div className="screenshot-panel">
              <div className="command-header">
                <div>
                  <span>Live Snapshot</span>
                  <small>{status.busy ? "Skill execution in progress." : "Polling the sidecar player."}</small>
                </div>
              </div>
              <ScreenshotImage path={status.screenshotPath} alt="Director player current screenshot" />
            </div>
          ) : null}

          <div className="manual-input-panel">
            <div className="command-header">
              <div>
                <span>Manual Gap Log</span>
                <small>Captures before/after state, screenshots, and trace.</small>
              </div>
            </div>
            <div className="manual-input-grid">
              {["up", "left", "a", "right", "down", "b", "start", "select"].map((button) => (
                <button
                  className="secondary-action compact"
                  key={button}
                  disabled={!status || status.busy || executingSkillId !== null}
                  onClick={() => sendManualButton(button)}
                  title={`Press ${button} and capture diagnostic artifacts`}
                >
                  {button}
                </button>
              ))}
            </div>
          </div>

          {snapshot ? (
            <>
              <div className="fact-grid compact-facts director-facts">
                <InfoBlock label="Mode" value={snapshot.mode} />
                <InfoBlock label="Location" value={snapshot.position?.map_name ?? "unknown"} />
                <InfoBlock label="Skills" value={`${enabledSkillCount}/${skills.length} usable`} />
                <InfoBlock label="Poke Balls" value={String(pokeBallCountFromSnapshot(snapshot))} />
                <InfoBlock
                  label="Status"
                  value={
                    status?.performance?.freshStatusMs === undefined
                      ? "unknown"
                      : `${status.performance.freshStatusMs} ms / ${status.performance.statusAgeSeconds ?? 0}s old`
                  }
                />
              </div>
              {snapshot.enemy ? (
                <div className="party-row">
                  <strong>{snapshot.enemy.species_name}</strong>
                  <span>
                    Lv{snapshot.enemy.level} HP {snapshot.enemy.hp}/{snapshot.enemy.max_hp}
                  </span>
                  <small>Battle enemy facts</small>
                </div>
              ) : null}
              {snapshot.active_party_member ? (
                <div className="party-row">
                  <strong>{snapshot.active_party_member.species_name}</strong>
                  <span>
                    Lv{snapshot.active_party_member.level} HP {snapshot.active_party_member.hp}/
                    {snapshot.active_party_member.max_hp}
                  </span>
                  <small>Active party slot {snapshot.active_party_slot ?? "unknown"}</small>
                </div>
              ) : null}
            </>
          ) : null}
        </aside>

        <section className="detail director-detail">
          <div className="section-header">
            <div>
              <p className="eyebrow">Context Signals</p>
              <h2>Promoted Facts</h2>
            </div>
            <div className="status-pair">
              <StatusPill status={status?.busy ? "busy" : status ? "connected" : "offline"} />
            </div>
          </div>

          <div className="interpretation-capture-panel">
            <div className="section-header director-subheader">
              <div>
                <p className="eyebrow">Audit Capture</p>
                <h2>Freeze Interpretation</h2>
              </div>
              <StatusPill status={captureReportPath ? "captured" : status ? "available" : "offline"} />
            </div>
            <div className="capture-form-grid">
              <label>
                <span>Title</span>
                <input
                  value={captureTitle}
                  onChange={(event) => setCaptureTitle(event.target.value)}
                  placeholder="Post-catch prompt misread as action menu"
                />
              </label>
              <label>
                <span>Description</span>
                <textarea
                  value={captureDescription}
                  onChange={(event) => setCaptureDescription(event.target.value)}
                  placeholder="What looked wrong, what skill was offered, or what you expected the Director to see."
                  rows={3}
                />
              </label>
            </div>
            <button
              className="primary-action compact"
              disabled={!status || !captureTitle.trim() || status.busy || executingSkillId !== null}
              onClick={captureInterpretation}
            >
              <Save size={16} />
              {executingSkillId === "capture_interpretation" ? "Capturing" : "Capture Interpretation"}
            </button>
            {captureMessage ? <p className="muted">{captureMessage}</p> : null}
            {captureReportPath ? <RunCommandPanel label="Captured Report" command={captureReportPath} stateFileExists /> : null}
          </div>

          {status ? (
            <>
              <div className="signal-grid">
                {status.signals.map((signal) => (
                  <div className="signal-card" key={signal.id}>
                    <span>{signal.label}</span>
                    <strong>{formatSignalValue(signal.value)}</strong>
                    <small>{signal.promotion}</small>
                  </div>
                ))}
              </div>

              <div className="section-header director-subheader">
                <div>
                  <p className="eyebrow">Skill Calls</p>
                  <h2>Available Actions</h2>
                </div>
              </div>
              <div className="director-skill-grid">
                {availableSkills.length ? (
                  availableSkills.map((skill) => (
                    <DirectorSkillCard
                      key={skill.id}
                      skill={skill}
                      args={skillArgs}
                      executingSkillId={executingSkillId}
                      playerBusy={status.busy}
                      onArgChange={updateSkillArg}
                      onExecute={executeSkill}
                    />
                  ))
                ) : (
                  <div className="callout">
                    <Gamepad2 size={18} />
                    <span>No skill is currently valid for this exact screen. Use manual input to capture the gap.</span>
                  </div>
                )}
              </div>

              {status.lastResult ? (
                <>
                  <h3>Last Skill Result</h3>
                  <div className={`verdict ${status.lastResult.status === "succeeded" ? "pass" : "deferred"}`}>
                    <div className="verdict-title">
                      <Activity size={18} />
                      <strong>{status.lastResult.skillId}</strong>
                      <span>{status.lastResult.status}</span>
                    </div>
                    <p>{status.lastResult.summary}</p>
                    {status.lastResult.reportPath ? <p className="muted">{status.lastResult.reportPath}</p> : null}
                  </div>
                </>
              ) : null}

              {status.history.length ? (
                <>
                  <h3>Execution Log</h3>
                  <div className="director-history">
                    {status.history.map((item, index) => (
                      <div className="history-row" key={`${item.createdUtc}-${item.skillId}-${index}`}>
                        <StatusPill status={item.status} />
                        <strong>{item.skillId}</strong>
                        <span>{item.summary}</span>
                      </div>
                    ))}
                  </div>
                </>
              ) : null}
            </>
          ) : (
            <div className="callout">
              <Gamepad2 size={18} />
              <span>Start the director player sidecar, then this page will show live signals and skill buttons.</span>
            </div>
          )}
        </section>
      </div>
    </section>
  );
}

function DirectorSkillCard({
  skill,
  args,
  executingSkillId,
  playerBusy,
  onArgChange,
  onExecute,
}: {
  skill: DirectorSkillAvailability;
  args: Record<string, string>;
  executingSkillId: string | null;
  playerBusy: boolean;
  onArgChange: (key: string, value: string) => void;
  onExecute: (skill: DirectorSkillAvailability) => void;
}) {
  const disabled = !skill.enabled || playerBusy || executingSkillId !== null;
  return (
    <div className={`director-skill-card ${skill.enabled ? "enabled" : "disabled"}`}>
      <div className="capture-card-head">
        <strong>{skill.label}</strong>
        <StatusPill status={skill.enabled ? "available" : skill.status} />
      </div>
      <DirectorSkillParams skill={skill} args={args} onArgChange={onArgChange} />
      <p className="muted">{skill.reason}</p>
      <button className="primary-action compact" disabled={disabled} onClick={() => onExecute(skill)}>
        {skill.id === "use_move" ? <Swords size={16} /> : <Play size={16} />}
        {executingSkillId === skill.id ? "Running" : "Run Skill"}
      </button>
    </div>
  );
}

function DirectorSkillParams({
  skill,
  args,
  onArgChange,
}: {
  skill: DirectorSkillAvailability;
  args: Record<string, string>;
  onArgChange: (key: string, value: string) => void;
}) {
  if (skill.id === "literal_button_press") {
    const buttons = directorStringOptions(skill.params.buttons);
    const value = args.button && buttons.includes(args.button) ? args.button : buttons[0] ?? "a";
    return (
      <select value={value} onChange={(event) => onArgChange("button", event.target.value)}>
        {buttons.length ? (
          buttons.map((button) => (
            <option key={button} value={button}>
              {button}
            </option>
          ))
        ) : (
          <option value="a">
            a
          </option>
        )}
      </select>
    );
  }
  if (skill.id === "use_move") {
    const moves = directorMoveOptions(skill);
    return (
      <select value={args.move || moves[0]?.name || ""} onChange={(event) => onArgChange("move", event.target.value)}>
        {moves.length ? (
          moves.map((move) => (
            <option key={`${move.slot}-${move.name}`} value={move.name}>
              {move.name} / {move.pp} PP
            </option>
          ))
        ) : (
          <option value="">No move available</option>
        )}
      </select>
    );
  }
  if (skill.id === "switch_party_member") {
    const targets = directorSwitchTargets(skill);
    return (
      <select
        value={args.switchTarget || String(targets[0]?.slot ?? "")}
        onChange={(event) => onArgChange("switchTarget", event.target.value)}
      >
        {targets.length ? (
          targets.map((target) => (
            <option key={target.slot} value={String(target.slot)}>
              Slot {target.slot}: {target.nickname || target.species} / HP {target.hp}
            </option>
          ))
        ) : (
          <option value="">No target available</option>
        )}
      </select>
    );
  }
  if (skill.id === "overworld_rearrange_party") {
    const targets = directorSwitchTargets(skill);
    const destinations = directorDestinationSlots(skill);
    return (
      <div className="inline-fields">
        <select
          value={args.reorderTarget || String(targets[0]?.slot ?? "")}
          onChange={(event) => onArgChange("reorderTarget", event.target.value)}
        >
          {targets.length ? (
            targets.map((target) => (
              <option key={target.slot} value={String(target.slot)}>
                Slot {target.slot}: {target.nickname || target.species}
              </option>
            ))
          ) : (
            <option value="">No target available</option>
          )}
        </select>
        <select
          value={args.destinationSlot || String(destinations[0] ?? "")}
          onChange={(event) => onArgChange("destinationSlot", event.target.value)}
        >
          {destinations.length ? (
            destinations.map((slot) => (
              <option key={slot} value={String(slot)}>
                To slot {slot}
              </option>
            ))
          ) : (
            <option value="">No slot available</option>
          )}
        </select>
      </div>
    );
  }
  if (skill.id === "navigate_within_viridian_forest_region") {
    const targets = directorStringOptions(skill.params.targets);
    const value = args.target && targets.includes(args.target) ? args.target : targets[0] ?? "";
    return (
      <select value={value} onChange={(event) => onArgChange("target", event.target.value)}>
        {targets.length ? (
          targets.map((target) => (
            <option key={target} value={target}>
              {target}
            </option>
          ))
        ) : (
          <option value="">No target available</option>
        )}
      </select>
    );
  }
  if (skill.id === "navigate_within_pallet_region") {
    const targets = directorStringOptions(skill.params.targetIds);
    const value = args.target && targets.includes(args.target) ? args.target : targets[0] ?? "";
    return (
      <select value={value} onChange={(event) => onArgChange("target", event.target.value)}>
        {targets.length ? (
          targets.map((target) => (
            <option key={target} value={target}>
              {target}
            </option>
          ))
        ) : (
          <option value="">No target available</option>
        )}
      </select>
    );
  }
  if (skill.id === "enter_grass_search_loop") {
    const patches = directorStringOptions(skill.params.patches);
    const value = args.patch && patches.includes(args.patch) ? args.patch : patches[0] ?? "";
    return (
      <select value={value} onChange={(event) => onArgChange("patch", event.target.value)}>
        {patches.length ? (
          patches.map((patch) => (
            <option key={patch} value={patch}>
              {patch}
            </option>
          ))
        ) : (
          <option value="">No patch available</option>
        )}
      </select>
    );
  }
  if (skill.id === "handle_nickname_prompt") {
    const choices = directorStringOptions(skill.params.choices);
    const defaultChoice = typeof skill.params.defaultChoice === "string" ? skill.params.defaultChoice : "decline";
    const value = args.nicknameChoice && choices.includes(args.nicknameChoice) ? args.nicknameChoice : defaultChoice;
    return (
      <select value={value} onChange={(event) => onArgChange("nicknameChoice", event.target.value)}>
        {choices.length ? (
          choices.map((choice) => (
            <option key={choice} value={choice}>
              {choice}
            </option>
          ))
        ) : (
          <option value="decline">decline</option>
        )}
      </select>
    );
  }
  if (skill.id === "enter_nickname_text") {
    const defaultNickname = typeof skill.params.defaultNickname === "string" ? skill.params.defaultNickname : "ABK";
    return (
      <input
        value={args.nicknameText || defaultNickname}
        onChange={(event) => onArgChange("nicknameText", event.target.value.toUpperCase().replace(/[^A-Z]/g, ""))}
        maxLength={10}
        placeholder="ABK"
      />
    );
  }
  return null;
}

function DirectiveWorkspace({
  deck,
  selectedCase,
  onSelectCase,
}: {
  deck: DirectiveDeck;
  selectedCase: DirectiveCase;
  onSelectCase: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"auto" | "offline" | "openai">("auto");
  const [verdict, setVerdict] = useState<DirectorVerdict | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const filtered = useMemo(() => {
    const needle = query.toLowerCase();
    return deck.cases.filter((item) => `${item.id} ${item.directive} ${item.expected.category}`.toLowerCase().includes(needle));
  }, [deck.cases, query]);

  async function validateCase() {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/director", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          directive: selectedCase.directive,
          stateSummary: selectedCase.state_summary,
          objective: selectedCase.objective,
          mode,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error ?? "Director validation failed");
      }
      setVerdict(data);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Director validation failed");
    } finally {
      setIsLoading(false);
    }
  }

  const matched =
    verdict?.decision === selectedCase.expected.decision && verdict?.category === selectedCase.expected.category;

  return (
    <section className="workspace two-column">
      <aside className="rail">
        <SearchBox value={query} onChange={setQuery} placeholder="Filter directive cases" />
        <div className="list">
          {filtered.map((item) => (
            <button
              className={`list-row ${item.id === selectedCase.id ? "selected" : ""}`}
              key={item.id}
              onClick={() => {
                onSelectCase(item.id);
                setVerdict(null);
                setError(null);
              }}
            >
              <span>{item.id}</span>
              <small>{item.expected.category} / {item.expected.decision}</small>
            </button>
          ))}
        </div>
      </aside>

      <section className="detail">
        <div className="section-header">
          <div>
            <p className="eyebrow">Directive Case</p>
            <h2>{selectedCase.id}</h2>
          </div>
          <div className="segmented">
            {(["auto", "offline", "openai"] as const).map((item) => (
              <button className={mode === item ? "active" : ""} key={item} onClick={() => setMode(item)}>
                {item}
              </button>
            ))}
          </div>
        </div>

        <div className="fact-grid">
          <InfoBlock label="Directive" value={selectedCase.directive} />
          <InfoBlock label="Objective" value={selectedCase.objective} />
          <InfoBlock label="Expected" value={`${selectedCase.expected.category} / ${selectedCase.expected.decision}`} />
        </div>

        <pre className="summary">{selectedCase.state_summary}</pre>

        <button className="primary-action" onClick={validateCase} disabled={isLoading}>
          <FlaskConical size={18} />
          {isLoading ? "Validating" : "Validate Verdict"}
        </button>

        {error ? <div className="callout danger"><ShieldAlert size={18} />{error}</div> : null}
        {verdict ? (
          <div className={`verdict ${matched ? "pass" : "fail"}`}>
            <div className="verdict-title">
              {matched ? <Check size={20} /> : <X size={20} />}
              <strong>{verdict.category} / {verdict.decision}</strong>
              <span>{verdict.risk} risk</span>
            </div>
            <p>{verdict.explanation}</p>
            {verdict.bounded_goal ? <p className="muted">Bounded goal: {verdict.bounded_goal}</p> : null}
            {verdict.warnings.length ? <p className="muted">Warnings: {verdict.warnings.join(", ")}</p> : null}
          </div>
        ) : null}
      </section>
    </section>
  );
}

function StateWorkspace({
  states,
  selectedState,
  onSelectState,
  onStateUpdated,
}: {
  states: StateRecord[];
  selectedState: StateRecord;
  onSelectState: (id: string) => void;
  onStateUpdated: (state: StateRecord) => void;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "golden" | "generated" | "approved" | "pending">("all");
  const [notes, setNotes] = useState(selectedState.approval.notes ?? "");
  const [message, setMessage] = useState<string | null>(null);
  const filtered = useMemo(() => {
    const needle = query.toLowerCase();
    return states.filter((state) => {
      const matchesQuery = `${state.name} ${state.snapshot.position?.map_name ?? ""} ${state.goal ?? ""}`.toLowerCase().includes(needle);
      const matchesFilter =
        filter === "all" ||
        state.type === filter ||
        (filter === "approved" && ["approved", "human_verified"].includes(state.approval.status)) ||
        (filter === "pending" && ["loadable_unapproved", "unverified"].includes(state.approval.status));
      return matchesQuery && matchesFilter;
    });
  }, [filter, query, states]);

  async function updateApproval(status: "approved" | "rejected") {
    setMessage(null);
    const response = await fetch("/api/states/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reportPath: selectedState.metadataPath,
        status,
        approvedBy: "Joey",
        notes,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      setMessage(data.error ?? "Approval update failed");
      return;
    }
    onStateUpdated(data);
    setMessage(`Marked ${status}`);
  }

  return (
    <section className="workspace two-column">
      <aside className="rail">
        <SearchBox value={query} onChange={setQuery} placeholder="Filter states" />
        <div className="segmented full">
          {(["all", "golden", "generated", "approved", "pending"] as const).map((item) => (
            <button className={filter === item ? "active" : ""} key={item} onClick={() => setFilter(item)}>
              {item}
            </button>
          ))}
        </div>
        <div className="list">
          {filtered.map((state) => (
            <button
              className={`list-row ${state.id === selectedState.id ? "selected" : ""}`}
              key={state.id}
              onClick={() => {
                onSelectState(state.id);
                setNotes(state.approval.notes ?? "");
                setMessage(null);
              }}
            >
              <span>{state.name}</span>
              <small>{state.type} / {state.approval.status}</small>
            </button>
          ))}
        </div>
      </aside>

      <section className="detail">
        <StateDetail
          state={selectedState}
          onStateUpdated={(updated) => onStateUpdated(updated)}
        />
        {selectedState.type === "generated" ? (
          <div className="approval-box">
            <label htmlFor="approval-notes">Approval notes</label>
            <textarea id="approval-notes" value={notes} onChange={(event) => setNotes(event.target.value)} />
            <div className="approval-actions">
              <button className="primary-action compact" onClick={() => updateApproval("approved")}>
                <Check size={17} />
                Approve
              </button>
              <button className="secondary-action compact" onClick={() => updateApproval("rejected")}>
                <X size={17} />
                Reject
              </button>
            </div>
            {message ? <p className="muted">{message}</p> : null}
          </div>
        ) : null}
      </section>
    </section>
  );
}

function InterrogateWorkspace({
  states,
  selectedState,
  onSelectState,
}: {
  states: StateRecord[];
  selectedState: StateRecord;
  onSelectState: (id: string) => void;
}) {
  const [question, setQuestion] = useState("Have we Pokedex-seen Pikachu?");
  const [answer, setAnswer] = useState<InterrogationAnswer | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function ask() {
    setIsLoading(true);
    const response = await fetch("/api/interrogate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stateId: selectedState.id, question }),
    });
    setAnswer(await response.json());
    setIsLoading(false);
  }

  return (
    <section className="workspace single">
      <div className="detail">
        <div className="section-header">
          <div>
            <p className="eyebrow">State Interrogation</p>
            <h2>{selectedState.name}</h2>
          </div>
          <select value={selectedState.id} onChange={(event) => onSelectState(event.target.value)}>
            {states.map((state) => (
              <option key={state.id} value={state.id}>
                {state.name}
              </option>
            ))}
          </select>
        </div>

        <div className="callout">
          <Beaker size={18} />
          Pokedex-seen questions are deferred until the Pokedex read surface is promoted.
        </div>

        <label htmlFor="question">Question</label>
        <input id="question" value={question} onChange={(event) => setQuestion(event.target.value)} />
        <button className="primary-action" onClick={ask} disabled={isLoading}>
          <CircleHelp size={18} />
          {isLoading ? "Checking" : "Check State"}
        </button>

        {answer ? (
          <div className={`verdict ${answer.status === "answered" ? "pass" : "deferred"}`}>
            <div className="verdict-title">
              <strong>{answer.status}</strong>
              <span>{answer.phase}</span>
            </div>
            <p>{answer.answer}</p>
            <ul>
              {answer.evidence.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function PromotionsWorkspace({
  promotions,
  selectedPromotion,
  states,
  skillStates,
  onSelectPromotion,
  onPromotionCatalogUpdated,
}: {
  promotions: PromotionRecord[];
  selectedPromotion: PromotionRecord;
  states: StateRecord[];
  skillStates: SkillStateRecord[];
  onSelectPromotion: (id: string) => void;
  onPromotionCatalogUpdated: (catalog: PromotionCatalog) => void;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "p0" | "needed" | "candidate" | "verified">("all");
  const [reviewStatus, setReviewStatus] = useState<PromotionRecord["status"]>(selectedPromotion.status);
  const [reviewNotes, setReviewNotes] = useState(selectedPromotion.review?.notes ?? "");
  const [reviewMessage, setReviewMessage] = useState<string | null>(null);
  const [isSavingReview, setIsSavingReview] = useState(false);
  const [validation, setValidation] = useState<PromotionValidationResult | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [assertionValidation, setAssertionValidation] = useState<PromotionAssertionValidationResult | null>(null);
  const [isCheckingAssertions, setIsCheckingAssertions] = useState(false);
  const [evidenceSourceId, setEvidenceSourceId] = useState("");
  const [evidenceLabel, setEvidenceLabel] = useState("");
  const [evidenceKind, setEvidenceKind] = useState("skill_state");
  const [evidenceMetadataPath, setEvidenceMetadataPath] = useState("");
  const [evidenceStatePath, setEvidenceStatePath] = useState("");
  const [evidenceScreenshotPath, setEvidenceScreenshotPath] = useState("");
  const [evidenceExpectedObservation, setEvidenceExpectedObservation] = useState("");
  const [evidenceNotes, setEvidenceNotes] = useState("");
  const [evidenceCaptureCommand, setEvidenceCaptureCommand] = useState("");
  const [evidenceMessage, setEvidenceMessage] = useState<string | null>(null);
  const [isAddingEvidence, setIsAddingEvidence] = useState(false);
  const [stepStartStatePaths, setStepStartStatePaths] = useState<Record<string, string>>({});

  useEffect(() => {
    setReviewStatus(selectedPromotion.status);
    setReviewNotes(selectedPromotion.review?.notes ?? "");
    setReviewMessage(null);
    setValidation(null);
    setAssertionValidation(null);
    setEvidenceMessage(null);
  }, [selectedPromotion.id, selectedPromotion.review?.notes, selectedPromotion.status]);

  const attachedEvidenceOptions = useMemo<EvidenceOption[]>(
    () =>
      selectedPromotion.verificationRefs
        .filter((reference) => reference.statePath)
        .map((reference) => ({
          id: `promotion:${reference.id}`,
          label: `${reference.label} (${reference.kind})`,
          kind: reference.kind,
          metadataPath: reference.metadataPath ?? "",
          statePath: reference.statePath ?? "",
          screenshotPath: reference.screenshotPath ?? "",
          expectedObservation:
            reference.expectedObservation ||
            reference.notes ||
            "Promotion evidence should demonstrate the promotion contract.",
          captureCommand: reference.captureCommand ?? "",
          localStateExists: reference.localStateExists,
        })),
    [selectedPromotion.verificationRefs],
  );

  const skillEvidenceOptions = useMemo<EvidenceOption[]>(
    () =>
      skillStates.map((state) => ({
      id: `skill:${state.id}`,
      label: `${state.skillId} / ${state.captureId}`,
      kind: "skill_state",
      metadataPath: state.metadataPath,
      statePath: state.statePath ?? "",
      screenshotPath: state.screenshotPath ?? "",
      expectedObservation:
        state.expectedReason ||
        state.note ||
        state.snapshot.plaintext_summary.split("\n")[0] ||
        "Skill state should demonstrate the promotion contract.",
      captureCommand: `.\\.venv\\Scripts\\python scripts\\play_and_capture_skill_state.py ${state.skillId} --state-in "${state.statePath ?? "<state path>"}"`,
      localStateExists: state.localStateExists,
    })),
    [skillStates],
  );

  const stateEvidenceOptions = useMemo<EvidenceOption[]>(
    () =>
      states.map((state) => ({
      id: `state:${state.id}`,
      label: `${state.type} / ${state.name}`,
      kind: state.type === "golden" ? "golden_state" : "derivative_state",
      metadataPath: state.metadataPath,
      statePath: state.statePath ?? "",
      screenshotPath: state.screenshotPath ?? "",
      expectedObservation:
        state.goal ||
        state.note ||
        state.snapshot.plaintext_summary.split("\n")[0] ||
        "State should demonstrate the promotion contract.",
      captureCommand: "",
      localStateExists: state.localStateExists,
    })),
    [states],
  );

  const evidenceOptions = useMemo(
    () =>
      [...attachedEvidenceOptions, ...skillEvidenceOptions, ...stateEvidenceOptions].sort((a, b) =>
      a.label.localeCompare(b.label),
      ),
    [attachedEvidenceOptions, skillEvidenceOptions, stateEvidenceOptions],
  );

  const startStateOptionByPath = useMemo(() => {
    const optionsByPath = new Map<string, EvidenceOption>();
    for (const option of [...attachedEvidenceOptions, ...skillEvidenceOptions, ...stateEvidenceOptions]) {
      if (option.statePath && !optionsByPath.has(option.statePath)) {
        optionsByPath.set(option.statePath, option);
      }
    }
    return optionsByPath;
  }, [attachedEvidenceOptions, skillEvidenceOptions, stateEvidenceOptions]);

  const filtered = useMemo(() => {
    const needle = query.toLowerCase();
    return promotions.filter((promotion) => {
      const matchesQuery = `${promotion.id} ${promotion.title} ${promotion.category} ${promotion.skillIds.join(" ")}`.toLowerCase().includes(needle);
      const matchesFilter =
        filter === "all" ||
        promotion.priority === filter ||
        promotion.status === filter;
      return matchesQuery && matchesFilter;
    });
  }, [filter, promotions, query]);

  function applyEvidenceSource(optionId: string) {
    setEvidenceSourceId(optionId);
    const option = evidenceOptions.find((item) => item.id === optionId);
    if (!option) {
      return;
    }
    setEvidenceLabel(option.label);
    setEvidenceKind(option.kind);
    setEvidenceMetadataPath(option.metadataPath);
    setEvidenceStatePath(option.statePath);
    setEvidenceScreenshotPath(option.screenshotPath);
    setEvidenceExpectedObservation(option.expectedObservation);
    setEvidenceCaptureCommand(option.captureCommand);
  }

  async function savePromotionReview() {
    setIsSavingReview(true);
    setReviewMessage(null);
    try {
      const response = await fetch("/api/promotions/status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          promotionId: selectedPromotion.id,
          status: reviewStatus,
          reviewedBy: "Joey",
          notes: reviewNotes,
        }),
      });
      const payload = (await response.json()) as PromotionCatalog & { error?: string };
      if (!response.ok) {
        throw new Error(payload.error ?? "Promotion review update failed");
      }
      onPromotionCatalogUpdated(payload);
      setReviewMessage("Review saved.");
    } catch (error) {
      setReviewMessage(error instanceof Error ? error.message : "Promotion review update failed");
    } finally {
      setIsSavingReview(false);
    }
  }

  async function addEvidence() {
    setIsAddingEvidence(true);
    setEvidenceMessage(null);
    try {
      if (!evidenceLabel.trim()) {
        throw new Error("Evidence label is required.");
      }
      const response = await fetch("/api/promotions/evidence", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          promotionId: selectedPromotion.id,
          reference: {
            label: evidenceLabel,
            kind: evidenceKind,
            metadataPath: evidenceMetadataPath,
            statePath: evidenceStatePath,
            screenshotPath: evidenceScreenshotPath,
            captureCommand: evidenceCaptureCommand,
            expectedObservation: evidenceExpectedObservation,
            notes: evidenceNotes,
          },
        }),
      });
      const payload = (await response.json()) as PromotionCatalog & { error?: string };
      if (!response.ok) {
        throw new Error(payload.error ?? "Promotion evidence update failed");
      }
      onPromotionCatalogUpdated(payload);
      setEvidenceMessage("Evidence added or updated.");
    } catch (error) {
      setEvidenceMessage(error instanceof Error ? error.message : "Promotion evidence update failed");
    } finally {
      setIsAddingEvidence(false);
    }
  }

  async function runValidation(scope: "selected" | "all") {
    setIsValidating(true);
    setValidation(null);
    try {
      const response = await fetch("/api/promotions/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(scope === "selected" ? { promotionId: selectedPromotion.id } : {}),
      });
      const payload = (await response.json()) as PromotionValidationResult & { error?: string };
      if (!response.ok) {
        throw new Error(payload.error ?? "Promotion validation failed");
      }
      setValidation(payload);
    } catch (error) {
      setValidation({
        schema: "promotion_validation_result_v1",
        status: "needs_attention",
        checked: 0,
        issues: [
          {
            promotionId: selectedPromotion.id,
            severity: "error",
            message: error instanceof Error ? error.message : "Promotion validation failed",
          },
        ],
      });
    } finally {
      setIsValidating(false);
    }
  }

  async function runAssertionValidation(scope: "selected" | "all") {
    setIsCheckingAssertions(true);
    setAssertionValidation(null);
    try {
      const response = await fetch("/api/promotions/assertions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(scope === "selected" ? { promotionId: selectedPromotion.id } : {}),
      });
      const payload = (await response.json()) as PromotionAssertionValidationResult & { error?: string };
      if (!response.ok) {
        throw new Error(payload.error ?? "Promotion assertion validation failed");
      }
      setAssertionValidation(payload);
    } catch (error) {
      setAssertionValidation({
        schema: "promotion_assertion_validation_v1",
        status: "needs_attention",
        checked: 1,
        asserted: 0,
        passed: 0,
        failed: 1,
        notAsserted: 0,
        evidence: [
          {
            promotionId: selectedPromotion.id,
            refId: "assertion-check",
            label: error instanceof Error ? error.message : "Promotion assertion validation failed",
            metadataPath: null,
            status: "failed",
            results: [],
          },
        ],
      });
    } finally {
      setIsCheckingAssertions(false);
    }
  }

  return (
    <section className="workspace two-column">
      <aside className="rail">
        <SearchBox value={query} onChange={setQuery} placeholder="Filter promotions" />
        <div className="segmented full">
          {(["all", "p0", "needed", "candidate", "verified"] as const).map((item) => (
            <button className={filter === item ? "active" : ""} key={item} onClick={() => setFilter(item)}>
              {item}
            </button>
          ))}
        </div>
        <div className="list">
          {filtered.map((promotion) => (
            <button
              className={`list-row ${promotion.id === selectedPromotion.id ? "selected" : ""}`}
              key={promotion.id}
              onClick={() => onSelectPromotion(promotion.id)}
            >
              <span>{promotion.title}</span>
              <small>{promotion.priority} / {promotion.status}</small>
            </button>
          ))}
        </div>
      </aside>

      <section className="detail">
        <div className="section-header">
          <div>
            <p className="eyebrow">Promotion</p>
            <h2>{selectedPromotion.title}</h2>
          </div>
          <div className="status-pair">
            <StatusPill status={selectedPromotion.priority} />
            <StatusPill status={selectedPromotion.status} />
          </div>
        </div>

        <div className="fact-grid">
          <InfoBlock label="Category" value={selectedPromotion.category} />
          <InfoBlock label="Status" value={selectedPromotion.status} />
          <InfoBlock label="Priority" value={selectedPromotion.priority} />
          <InfoBlock label="Evidence" value={String(selectedPromotion.verificationRefs.length)} />
        </div>

        <p>{selectedPromotion.summary}</p>
        {selectedPromotion.currentSurface ? (
          <div className="callout">
            <ListChecks size={18} />
            {selectedPromotion.currentSurface}
          </div>
        ) : null}

        <h3>Evidence Collection Steps</h3>
        {selectedPromotion.evidenceSteps.length ? (
          <>
            <div className="callout">
              <ListChecks size={18} />
              Use the step command to collect new evidence. Captures are saved under
              research/promotions/evidence and attached to this promotion automatically.
            </div>
          <ol className="step-list">
            {selectedPromotion.evidenceSteps.map((step, index) => {
              const stepKey = `${selectedPromotion.id}:${index + 1}`;
              const selectedStartStatePath = stepStartStatePaths[stepKey] ?? "";
              const selectedStartOption = startStateOptionByPath.get(selectedStartStatePath);
              const selectedStateExists = selectedStartOption?.localStateExists ?? false;
              return (
              <li className="step-card" key={`${selectedPromotion.id}-${step.title}`}>
                <span className="step-index">{index + 1}</span>
                <div>
                  <strong>{step.title}</strong>
                  <p>{step.detail}</p>
                  {step.expectedEvidence ? (
                    <p className="muted">Expected evidence: {step.expectedEvidence}</p>
                  ) : null}
                  <label>Start From</label>
                  <select
                    data-testid={`promotion-step-start-state-${index + 1}`}
                    value={selectedStartStatePath}
                    onChange={(event) =>
                      setStepStartStatePaths((current) => ({
                        ...current,
                        [stepKey]: event.target.value,
                      }))
                    }
                  >
                    <option value="">Choose a start state</option>
                    {attachedEvidenceOptions.length ? (
                      <optgroup label="Attached to this promotion">
                        {attachedEvidenceOptions.map((option) => (
                          <option value={option.statePath} key={`${selectedPromotion.id}-${index}-${option.id}`}>
                            {option.label}
                          </option>
                        ))}
                      </optgroup>
                    ) : null}
                    {skillEvidenceOptions.length ? (
                      <optgroup label="Skill states">
                        {skillEvidenceOptions
                          .filter((option) => option.statePath)
                          .map((option) => (
                            <option value={option.statePath} key={`${selectedPromotion.id}-${index}-${option.id}`}>
                              {option.label}
                            </option>
                          ))}
                      </optgroup>
                    ) : null}
                    {stateEvidenceOptions.length ? (
                      <optgroup label="Golden and generated states">
                        {stateEvidenceOptions
                          .filter((option) => option.statePath)
                          .map((option) => (
                            <option value={option.statePath} key={`${selectedPromotion.id}-${index}-${option.id}`}>
                              {option.label}
                            </option>
                          ))}
                      </optgroup>
                    ) : null}
                  </select>
                  {selectedStartOption ? (
                    <p className="muted">
                      Selected: {selectedStartOption.label}
                    </p>
                  ) : null}
                  <RunCommandPanel
                    label="Play Selected Start State"
                    command={playStateCommand(selectedStartStatePath)}
                    stateFileExists={selectedStateExists}
                    disabledMessage="Choose an attached or reusable start state above."
                  />
                  <RunCommandPanel
                    label="Unified Capture Command"
                    command={promotionEvidenceCaptureCommand(
                      selectedPromotion.id,
                      index + 1,
                      selectedStartStatePath,
                    )}
                    stateFileExists={selectedStateExists}
                    disabledMessage="Choose an attached or reusable start state above."
                  />
                </div>
              </li>
            );
            })}
          </ol>
          </>
        ) : (
          <div className="callout danger">
            <ShieldAlert size={18} />
            No evidence collection steps are recorded for this promotion yet.
          </div>
        )}

        <h3>Promotion Workbench</h3>
        <div className="workbench-grid">
          <div className="workbench-card">
            <div className="capture-card-head">
              <strong>Review</strong>
              <StatusPill status={reviewStatus} />
            </div>
            <label>Status</label>
            <select
              value={reviewStatus}
              onChange={(event) => setReviewStatus(event.target.value as PromotionRecord["status"])}
            >
              <option value="needed">needed</option>
              <option value="candidate">candidate</option>
              <option value="verified">verified</option>
              <option value="blocked">blocked</option>
            </select>
            <label>Review Notes</label>
            <textarea
              value={reviewNotes}
              onChange={(event) => setReviewNotes(event.target.value)}
              placeholder="What evidence changed your confidence in this promotion?"
            />
            {selectedPromotion.review ? (
              <p className="muted">
                Last reviewed by {selectedPromotion.review.reviewedBy ?? "unknown"} at{" "}
                {selectedPromotion.review.reviewedAt ?? "unknown time"}.
              </p>
            ) : null}
            <button className="primary-action compact" onClick={savePromotionReview} disabled={isSavingReview}>
              <Save size={16} />
              {isSavingReview ? "Saving" : "Save Review"}
            </button>
            {reviewMessage ? <p className="muted">{reviewMessage}</p> : null}
          </div>

          <div className="workbench-card">
            <div className="capture-card-head">
              <strong>Validate</strong>
              {validation ? <StatusPill status={validation.status} /> : <StatusPill status="not_run" />}
            </div>
            <p className="muted">
              Checks source refs, local metadata/state/screenshot paths, required evidence, and status readiness.
            </p>
            <div className="approval-actions">
              <button className="secondary-action compact" onClick={() => runValidation("selected")} disabled={isValidating}>
                <ShieldCheck size={16} />
                This Promotion
              </button>
              <button className="secondary-action compact" onClick={() => runValidation("all")} disabled={isValidating}>
                <ListChecks size={16} />
                All Promotions
              </button>
            </div>
            {validation ? (
              <div className={`validation-box ${validation.status}`}>
                <strong>{validation.checked} promotion{validation.checked === 1 ? "" : "s"} checked</strong>
                {validation.issues.length ? (
                  <ul>
                    {validation.issues.map((issue, index) => (
                      <li className={issue.severity} key={`${issue.promotionId ?? "manifest"}-${issue.refId ?? index}`}>
                        <AlertTriangle size={14} />
                        <span>
                          {issue.promotionId ? `${issue.promotionId}: ` : ""}
                          {issue.refId ? `[${issue.refId}] ` : ""}
                          {issue.message}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">No validation issues found.</p>
                )}
              </div>
            ) : null}
          </div>

          <div className="workbench-card">
            <div className="capture-card-head">
              <strong>Machine Assertion Check</strong>
              {assertionValidation ? (
                <StatusPill status={assertionValidation.status} />
              ) : (
                <StatusPill status="not_run" />
              )}
            </div>
            <p className="muted">
              Compares human-facing evidence claims against inspector snapshot values and visual classifier facts.
            </p>
            <div className="approval-actions">
              <button
                className="secondary-action compact"
                onClick={() => runAssertionValidation("selected")}
                disabled={isCheckingAssertions}
              >
                <ShieldCheck size={16} />
                This Promotion
              </button>
              <button
                className="secondary-action compact"
                onClick={() => runAssertionValidation("all")}
                disabled={isCheckingAssertions}
              >
                <ListChecks size={16} />
                All Promotions
              </button>
            </div>
            {assertionValidation ? (
              <div className={`validation-box ${assertionValidation.status}`}>
                <div className="fact-grid compact-facts">
                  <InfoBlock label="Evidence" value={String(assertionValidation.checked)} />
                  <InfoBlock label="Asserted" value={String(assertionValidation.asserted)} />
                  <InfoBlock label="Passed" value={String(assertionValidation.passed)} />
                  <InfoBlock label="Failed" value={String(assertionValidation.failed)} />
                </div>
                {assertionValidation.notAsserted ? (
                  <p className="muted">{assertionValidation.notAsserted} evidence refs have no assertions recorded.</p>
                ) : null}
                <div className="assertion-result-list">
                  {assertionValidation.evidence.map((item) => (
                    <div className={`assertion-evidence ${item.status}`} key={`${item.promotionId}-${item.refId}`}>
                      <div className="capture-card-head">
                        <strong>{item.label}</strong>
                        <StatusPill status={item.status} />
                      </div>
                      <p className="muted">
                        {item.promotionId} / {item.refId}
                      </p>
                      {item.results.length ? (
                        item.results.map((result) => (
                          <div className={`assertion-row ${result.passed ? "passed" : "failed"}`} key={result.id}>
                            <StatusPill status={result.passed ? "pass" : "fail"} />
                            <span>
                              {result.description || result.id}: actual={formatAssertionValue(result.actual)}{" "}
                              {result.op} expected={formatAssertionValue(result.expected)}
                            </span>
                          </div>
                        ))
                      ) : (
                        <p className="muted">No assertions recorded for this evidence.</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>

          <div className="workbench-card wide">
            <div className="capture-card-head">
              <strong>Attach Evidence</strong>
              <StatusPill status="manifest_edit" />
            </div>
            <p className="muted">
              Use this form for retroactive evidence that already exists. New promotion evidence should usually be
              captured with a unified step command above.
            </p>
            <label>Prefill From Existing State</label>
            <select value={evidenceSourceId} onChange={(event) => applyEvidenceSource(event.target.value)}>
              <option value="">Manual evidence entry</option>
              {evidenceOptions.map((option) => (
                <option value={option.id} key={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
            <div className="form-grid">
              <div>
                <label>Label</label>
                <input value={evidenceLabel} onChange={(event) => setEvidenceLabel(event.target.value)} />
              </div>
              <div>
                <label>Kind</label>
                <select value={evidenceKind} onChange={(event) => setEvidenceKind(event.target.value)}>
                  <option value="skill_state">skill_state</option>
                  <option value="golden_state">golden_state</option>
                  <option value="derivative_state">derivative_state</option>
                  <option value="policy_state">policy_state</option>
                  <option value="skill_run">skill_run</option>
                  <option value="pending_capture">pending_capture</option>
                  <option value="manual_note">manual_note</option>
                </select>
              </div>
            </div>
            <label>Metadata Path</label>
            <input value={evidenceMetadataPath} onChange={(event) => setEvidenceMetadataPath(event.target.value)} />
            <label>State Path</label>
            <input value={evidenceStatePath} onChange={(event) => setEvidenceStatePath(event.target.value)} />
            <label>Screenshot Path</label>
            <input value={evidenceScreenshotPath} onChange={(event) => setEvidenceScreenshotPath(event.target.value)} />
            <label>Expected Observation</label>
            <textarea
              value={evidenceExpectedObservation}
              onChange={(event) => setEvidenceExpectedObservation(event.target.value)}
              placeholder="What should a reviewer observe before promoting this contract?"
            />
            <label>Capture Command</label>
            <input value={evidenceCaptureCommand} onChange={(event) => setEvidenceCaptureCommand(event.target.value)} />
            <label>Notes</label>
            <textarea value={evidenceNotes} onChange={(event) => setEvidenceNotes(event.target.value)} />
            <button className="primary-action compact" onClick={addEvidence} disabled={isAddingEvidence}>
              <Plus size={16} />
              {isAddingEvidence ? "Attaching" : "Attach Evidence"}
            </button>
            {evidenceMessage ? <p className="muted">{evidenceMessage}</p> : null}
          </div>
        </div>

        <h3>Impacted Skills</h3>
        <div className="chips">
          {selectedPromotion.skillIds.map((skillId) => (
            <span className="chip" key={skillId}>{skillId}</span>
          ))}
        </div>

        <h3>Promote To</h3>
        <div className="capture-grid">
          {selectedPromotion.promoteTo.map((item) => (
            <div className="capture-card compact-card" key={item}>
              <strong>{item}</strong>
            </div>
          ))}
        </div>

        <h3>Needed Work</h3>
        <div className="capture-grid">
          {selectedPromotion.neededWork.map((item) => (
            <div className="capture-card compact-card" key={item}>
              <p>{item}</p>
            </div>
          ))}
        </div>

        {selectedPromotion.sourceRefs.length ? (
          <>
            <h3>Sources</h3>
            <div className="capture-grid">
              {selectedPromotion.sourceRefs.map((source) => (
                <div className="capture-card compact-card" key={`${source.label}-${source.url ?? "local"}`}>
                  <strong>{source.label}</strong>
                  {source.notes ? <p>{source.notes}</p> : null}
                  {source.url ? <a href={source.url}>{source.url}</a> : null}
                </div>
              ))}
            </div>
          </>
        ) : null}

        <h3>Verification Evidence</h3>
        <div className="capture-grid">
          {selectedPromotion.verificationRefs.map((reference) => (
            <PromotionReferenceCard
              reference={reference}
              key={reference.id}
              onPromotionCatalogUpdated={onPromotionCatalogUpdated}
            />
          ))}
        </div>
      </section>
    </section>
  );
}

function PromotionReferenceCard({
  reference,
  onPromotionCatalogUpdated,
}: {
  reference: PromotionReference;
  onPromotionCatalogUpdated: (catalog: PromotionCatalog) => void;
}) {
  const [screenshotMessage, setScreenshotMessage] = useState<string | null>(null);

  async function captureScreenshot() {
    if (!reference.metadataPath) {
      return;
    }
    setScreenshotMessage("Capturing screenshot...");
    try {
      const response = await fetch("/api/promotions/screenshot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ metadataPath: reference.metadataPath }),
      });
      const payload = (await response.json()) as { catalog?: PromotionCatalog; error?: string };
      if (!response.ok || !payload.catalog) {
        throw new Error(payload.error ?? "Screenshot capture failed");
      }
      onPromotionCatalogUpdated(payload.catalog);
      setScreenshotMessage("Screenshot refreshed.");
    } catch (error) {
      setScreenshotMessage(error instanceof Error ? error.message : "Screenshot capture failed");
    }
  }

  return (
    <div className="skill-capture expanded">
      <div className="capture-card-head">
        <strong>{reference.label}</strong>
        <StatusPill status={reference.kind} />
      </div>
      {reference.screenshotPath && reference.screenshotExists ? (
        <ScreenshotImage path={reference.screenshotPath} alt={`${reference.label} screenshot`} />
      ) : (
        <div className="missing-screenshot">
          <p className="muted">
            {reference.screenshotPath
              ? "Screenshot metadata exists, but the local image file is missing."
              : "No screenshot path is recorded for this evidence."}
          </p>
          {reference.metadataPath ? (
            <button className="icon-action" onClick={captureScreenshot} title="Capture screenshot">
              <ImageIcon size={16} />
              Capture
            </button>
          ) : null}
          {screenshotMessage ? <p className="muted">{screenshotMessage}</p> : null}
        </div>
      )}
      {reference.screenshotPath && reference.screenshotExists && reference.metadataPath ? (
        <button className="icon-action" onClick={captureScreenshot} title="Refresh screenshot">
          <ImageIcon size={16} />
          Refresh Screenshot
        </button>
      ) : null}
      {reference.expectedObservation ? <p>{reference.expectedObservation}</p> : null}
      {reference.notes ? <p className="muted">{reference.notes}</p> : null}
      {reference.assertionResults.length ? (
        <div className="assertion-list">
          <strong>Machine Assertions</strong>
          {reference.assertionResults.map((result) => (
            <div className={`assertion-row ${result.passed ? "passed" : "failed"}`} key={result.id}>
              <StatusPill status={result.passed ? "pass" : "fail"} />
              <span>
                {result.description || result.id}: {formatAssertionValue(result.actual)} {result.op}{" "}
                {formatAssertionValue(result.expected)}
              </span>
            </div>
          ))}
        </div>
      ) : reference.kind === "promotion_evidence" ? (
        <div className="callout danger compact-callout">
          <ShieldAlert size={16} />
          This promotion evidence has no machine-checkable assertions yet.
        </div>
      ) : null}
      {reference.metadataPath ? <InfoBlock label="Metadata" value={reference.metadataPath} /> : null}
      <RunCommandPanel command={reference.command} stateFileExists={reference.localStateExists} />
      {reference.captureCommand ? (
        <RunCommandPanel
          label="Capture Command"
          command={reference.captureCommand}
          stateFileExists
        />
      ) : null}
    </div>
  );
}

function SkillsWorkspace({
  skills,
  skillStates,
  selectedSkill,
  onSelectSkill,
}: {
  skills: SkillDefinition[];
  skillStates: SkillStateRecord[];
  selectedSkill: SkillDefinition;
  onSelectSkill: (id: string) => void;
}) {
  const captures = skillStates.filter((state) => state.skillId === selectedSkill.id);
  const requestedCaptureIds = new Set(selectedSkill.needed_captures.map((need) => need.id));
  const requestedCaptures = captures.filter((capture) => requestedCaptureIds.has(capture.captureId));
  const historicalCaptures = captures.filter((capture) => !requestedCaptureIds.has(capture.captureId));

  return (
    <section className="workspace two-column">
      <aside className="rail">
        <div className="list">
          {skills.map((skill) => (
            <button
              className={`list-row ${skill.id === selectedSkill.id ? "selected" : ""}`}
              key={skill.id}
              onClick={() => onSelectSkill(skill.id)}
            >
              <span>{skill.name}</span>
              <small>{skill.status}</small>
            </button>
          ))}
        </div>
      </aside>

      <section className="detail">
        <div className="section-header">
          <div>
            <p className="eyebrow">Skill</p>
            <h2>{selectedSkill.name}</h2>
          </div>
          <StatusPill status={selectedSkill.status} />
        </div>
        <InfoBlock label="Purpose" value={selectedSkill.purpose} />
        <RunCommandPanel
          label="Capture Command"
          command={`.\\.venv\\Scripts\\python scripts\\play_and_capture_skill_state.py ${selectedSkill.id} --state-in "<state path>" --reset-to-state-in`}
          stateFileExists
        />

        <h3>Needed Captures</h3>
        <div className="capture-grid">
          {selectedSkill.needed_captures.map((need) => {
            const matching = captures.find((capture) => capture.captureId === need.id);
            return (
              <div className="capture-card" key={need.id}>
                <div className="capture-card-head">
                  <strong>{need.id}</strong>
                  <StatusPill status={matching ? "captured" : "needed"} />
                </div>
                <p>{need.condition}</p>
                <p className="muted">{need.manual_action}</p>
                <small>Expected: {need.expected_status}</small>
                {need.recommended_start_states?.length ? (
                  <SkillRecommendedStartStates
                    captureId={need.id}
                    recommendations={need.recommended_start_states}
                    skillId={selectedSkill.id}
                  />
                ) : null}
                {matching ? <SkillCaptureSummary capture={matching} /> : null}
              </div>
            );
          })}
        </div>

        <h3>Flagging Evidence</h3>
        <div className="chips">
          {selectedSkill.flagging_evidence.map((item) => (
            <span className="chip" key={item}>{item}</span>
          ))}
        </div>

        {requestedCaptures.length ? (
          <>
            <h3>Captured States</h3>
            <div className="capture-grid">
              {requestedCaptures.map((capture) => (
                <SkillCaptureSummary capture={capture} key={capture.id} expanded />
              ))}
            </div>
          </>
        ) : null}

        {historicalCaptures.length ? (
          <>
            <h3>Historical Captures</h3>
            <p className="muted">
              These captured states no longer map to a current needed-capture ID, but remain available for audit.
            </p>
            <div className="capture-grid">
              {historicalCaptures.map((capture) => (
                <SkillCaptureSummary capture={capture} key={capture.id} expanded />
              ))}
            </div>
          </>
        ) : null}
      </section>
    </section>
  );
}

function SkillRecommendedStartStates({
  captureId,
  recommendations,
  skillId,
}: {
  captureId: string;
  recommendations: NonNullable<SkillDefinition["needed_captures"][number]["recommended_start_states"]>;
  skillId: string;
}) {
  return (
    <div className="recommended-start-states">
      <strong>Recommended Start States</strong>
      {recommendations.map((state) => {
        const runCommand = skillCaptureCommand(skillId, state.state_path ?? "");
        return (
          <div className="recommended-start-state" key={state.id}>
            <div className="recommended-start-state-copy">
              <span>{state.label}</span>
              {state.reason ? <p>{state.reason}</p> : null}
              <small>When ready, press Z and enter result code: {captureId}</small>
              {state.capture_hint ? <p>{state.capture_hint}</p> : null}
            </div>
            {state.screenshot_path ? (
              <ScreenshotImage path={state.screenshot_path} alt={`${state.label} screenshot`} />
            ) : null}
            <RunCommandPanel
              label="Capture From This State"
              command={runCommand}
              stateFileExists={Boolean(state.state_path)}
              disabledMessage="No local state path is recorded for this recommendation."
            />
          </div>
        );
      })}
    </div>
  );
}

function SkillCaptureSummary({
  capture,
  expanded = false,
}: {
  capture: SkillStateRecord;
  expanded?: boolean;
}) {
  const runCommand = capture.statePath
    ? `.\\.venv\\Scripts\\python scripts\\play_state.py "${capture.statePath}"`
    : null;
  const [screenshotMessage, setScreenshotMessage] = useState<string | null>(null);

  async function captureScreenshot() {
    setScreenshotMessage("Capturing screenshot...");
    const response = await fetch("/api/states/screenshot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ metadataPath: capture.metadataPath }),
    });
    const data = await response.json();
    if (!response.ok) {
      setScreenshotMessage(data.error ?? "Screenshot capture failed");
      return;
    }
    setScreenshotMessage("Screenshot captured. Reloading...");
    window.setTimeout(() => window.location.reload(), 600);
  }

  return (
    <div className={expanded ? "skill-capture expanded" : "skill-capture"}>
      {capture.screenshotPath && capture.screenshotExists ? (
        <ScreenshotImage path={capture.screenshotPath} alt={`${capture.captureId} screenshot`} />
      ) : (
        <div className="missing-screenshot">
          <button
            className="icon-action"
            onClick={captureScreenshot}
            disabled={!capture.localStateExists}
            title="Capture screenshot"
          >
            <ImageIcon size={16} />
            Capture
          </button>
          {screenshotMessage ? <p className="muted">{screenshotMessage}</p> : null}
        </div>
      )}
      <div>
        <strong>{capture.captureId}</strong>
        <p className="muted">{capture.phase} / {capture.expectedStatus}</p>
        {capture.expectedReason ? <p className="muted">Reason: {capture.expectedReason}</p> : null}
        {capture.manualAction ? <p>{capture.manualAction}</p> : null}
      </div>
      <RunCommandPanel command={runCommand} stateFileExists={capture.localStateExists} />
    </div>
  );
}

function StateDetail({
  state,
  onStateUpdated,
}: {
  state: StateRecord;
  onStateUpdated: (state: StateRecord) => void;
}) {
  const runCommand = state.statePath
    ? `.\\.venv\\Scripts\\python scripts\\play_state.py "${state.statePath}"`
    : null;
  const [screenshotMessage, setScreenshotMessage] = useState<string | null>(null);

  async function captureScreenshot() {
    setScreenshotMessage("Capturing screenshot...");
    const response = await fetch("/api/states/screenshot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ metadataPath: state.metadataPath }),
    });
    const data = await response.json();
    if (!response.ok) {
      setScreenshotMessage(data.error ?? "Screenshot capture failed");
      return;
    }
    setScreenshotMessage("Screenshot captured. Refreshing state metadata...");
    const refreshed = await fetch("/api/states/record", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stateId: state.id }),
    });
    const refreshedState = await refreshed.json();
    if (refreshed.ok) {
      onStateUpdated(refreshedState);
      setScreenshotMessage("Screenshot captured.");
    } else {
      setScreenshotMessage("Screenshot captured; reload the page to view it.");
    }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <p className="eyebrow">{state.type} state</p>
          <h2>{state.name}</h2>
        </div>
        <StatusPill status={state.approval.status} />
      </div>
      <div className="fact-grid">
        <InfoBlock label="Location" value={state.snapshot.position?.map_name ?? "unknown"} />
        <InfoBlock label="Mode" value={state.snapshot.mode} />
        <InfoBlock
          label="Active"
          value={
            state.snapshot.active_party_member
              ? `${state.snapshot.active_party_member.species_name} / slot ${state.snapshot.active_party_slot}`
              : "none"
          }
        />
        <InfoBlock label="Money" value={state.snapshot.money === null ? "unknown" : String(state.snapshot.money)} />
        <InfoBlock label="State File" value={state.localStateExists ? "present" : "missing"} />
      </div>
      {state.goal ? <InfoBlock label="Goal" value={state.goal} /> : null}
      {state.note ? <InfoBlock label="Note" value={state.note} /> : null}
      {state.screenshotPath && state.screenshotExists ? (
        <div className="screenshot-panel">
          <div className="command-header">
            <div>
              <span>Screenshot</span>
            </div>
          </div>
          <ScreenshotImage path={state.screenshotPath} alt={`${state.name} screenshot`} />
        </div>
      ) : (
        <div className="screenshot-panel">
          <div className="command-header">
            <div>
              <span>Screenshot</span>
              <small>
                {state.screenshotPath
                  ? "Screenshot metadata exists, but the local image file is missing."
                  : "No screenshot has been captured for this state."}
              </small>
            </div>
            <button
              className="icon-action"
              onClick={captureScreenshot}
              disabled={!state.localStateExists}
              title="Capture screenshot"
            >
              <ImageIcon size={16} />
              Capture
            </button>
          </div>
          {screenshotMessage ? <p className="muted">{screenshotMessage}</p> : null}
        </div>
      )}
      <RunCommandPanel command={runCommand} stateFileExists={state.localStateExists} />
      <h3>Party</h3>
      <div className="party-list">
        {state.snapshot.party.map((member) => (
          <div className="party-row" key={`${member.slot}-${member.species_id}`}>
            <strong>
              {member.slot}. {member.nickname || member.species_name}
              {state.snapshot.active_party_slot === member.slot ? " (active)" : ""}
            </strong>
            <span>Lv{member.level} HP {member.hp}/{member.max_hp}</span>
            <small>{member.moves.filter((move) => move.move_id).map((move) => move.move_name).join(", ") || "No moves"}</small>
          </div>
        ))}
      </div>
      <h3>Inventory</h3>
      <div className="chips">
        {state.snapshot.inventory.map((item) => (
          <span className="chip" key={`${item.item_id}-${item.item_name}`}>
            {item.item_name} x{item.quantity}
          </span>
        ))}
      </div>
      {state.snapshot.enemy ? (
        <>
          <h3>Battle Enemy</h3>
          <div className="party-row">
            <strong>{state.snapshot.enemy.species_name}</strong>
            <span>
              Lv{state.snapshot.enemy.level} HP {state.snapshot.enemy.hp}/{state.snapshot.enemy.max_hp}
            </span>
            <small>
              Status 0x{state.snapshot.enemy.status.toString(16).toUpperCase().padStart(2, "0")}
              {state.snapshot.enemy.catch_rate === null ? "" : ` / Catch rate ${state.snapshot.enemy.catch_rate}`}
            </small>
          </div>
        </>
      ) : null}
      <pre className="summary">{state.snapshot.plaintext_summary}</pre>
    </>
  );
}

function ScreenshotImage({ path, alt, cacheKey }: { path: string; alt: string; cacheKey?: string }) {
  const cacheParam = cacheKey ? `&v=${encodeURIComponent(cacheKey)}` : "";
  return (
    <img
      className="state-screenshot"
      src={`/api/local-image?path=${encodeURIComponent(path)}${cacheParam}`}
      alt={alt}
    />
  );
}

function RunCommandPanel({
  command,
  stateFileExists,
  label = "Validation Command",
  disabledMessage = "Local state file is missing.",
}: {
  command: string | null;
  stateFileExists: boolean;
  label?: string;
  disabledMessage?: string;
}) {
  const [copied, setCopied] = useState(false);

  async function copyCommand() {
    if (!command) {
      return;
    }
    await navigator.clipboard.writeText(command);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <div className="command-panel">
      <div className="command-header">
        <div>
          <span>{label}</span>
          {!stateFileExists ? <small>{disabledMessage}</small> : null}
        </div>
        <button className="icon-action" onClick={copyCommand} disabled={!command || !stateFileExists} title="Copy command">
          <Copy size={16} />
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre>{command ?? "No local state path is recorded for this state."}</pre>
    </div>
  );
}

function JsonDebugModal({
  title,
  payload,
  onClose,
}: {
  title: string;
  payload: unknown;
  onClose: () => void;
}) {
  return (
    <div className="debug-modal-backdrop" role="presentation" onClick={onClose}>
      <div className="debug-modal" role="dialog" aria-modal="true" aria-label={title} onClick={(event) => event.stopPropagation()}>
        <div className="command-header">
          <div>
            <span>{title}</span>
            <small>JSON payload</small>
          </div>
          <button className="icon-action" onClick={onClose} title="Close">
            <X size={16} />
          </button>
        </div>
        <pre>{JSON.stringify(payload, null, 2)}</pre>
      </div>
    </div>
  );
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <div className="metric">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button className={active ? "active" : ""} onClick={onClick}>
      {icon}
      {label}
    </button>
  );
}

function SearchBox({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <label className="search">
      <Search size={17} />
      <input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} />
    </label>
  );
}

function InfoBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="info-block">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  return <span className={`status ${status}`}>{status}</span>;
}

function clampInteger(value: string, min: number, max: number, fallback: number): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.max(min, Math.min(max, Math.floor(parsed)));
}

function trimLlmMessages(messages: LlmDirectorChatMessage[], limit: number): LlmDirectorChatMessage[] {
  return messages.slice(-Math.max(1, Math.min(100, limit)));
}

function llmMessageKey(message: LlmDirectorChatMessage): string {
  return [message.createdUtc ?? "", message.role, message.kind ?? "", message.content].join("::");
}

function addUsageToTotals(
  current: { input: number; output: number; total: number },
  usage: LlmDirectorRunResult["usage"],
): { input: number; output: number; total: number } {
  if (!usage) {
    return current;
  }
  const input = usage.inputTokens ?? 0;
  const output = usage.outputTokens ?? 0;
  const total = usage.totalTokens ?? input + output;
  return {
    input: current.input + input,
    output: current.output + output,
    total: current.total + total,
  };
}

function formatAssertionValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "null";
  }
  if (typeof value === "string") {
    return `"${value}"`;
  }
  return String(value);
}

function promotionEvidenceCaptureCommand(promotionId: string, stepNumber: number, statePath: string): string {
  const base = `.\\.venv\\Scripts\\python scripts\\play_and_capture_promotion_evidence.py ${promotionId} --step ${stepNumber}`;
  return statePath ? `${base} --state-in "${statePath}"` : `${base} --state-in "<choose a start state above>"`;
}

function playStateCommand(statePath: string): string | null {
  return statePath ? `.\\.venv\\Scripts\\python scripts\\play_state.py "${statePath}"` : null;
}

function skillCaptureCommand(skillId: string, statePath: string): string | null {
  return statePath
    ? `.\\.venv\\Scripts\\python scripts\\play_and_capture_skill_state.py ${skillId} --state-in "${statePath}" --reset-to-state-in`
    : null;
}

function directorArgsForSkill(
  skill: DirectorSkillAvailability,
  args: Record<string, string>,
): Record<string, unknown> {
  if (skill.id === "literal_button_press") {
    const firstButton = directorStringOptions(skill.params.buttons)[0] ?? "a";
    return { button: args.button || firstButton };
  }
  if (skill.id === "use_move") {
    const firstMove = directorMoveOptions(skill)[0]?.name ?? "";
    return { move: args.move || firstMove };
  }
  if (skill.id === "switch_party_member") {
    const firstTarget = directorSwitchTargets(skill)[0]?.slot ?? "";
    return { target: args.switchTarget || String(firstTarget) };
  }
  if (skill.id === "overworld_rearrange_party") {
    const targets = directorSwitchTargets(skill);
    const destinations = directorDestinationSlots(skill);
    return {
      target: args.reorderTarget || String(targets[0]?.slot ?? ""),
      destinationSlot: args.destinationSlot || String(destinations[0] ?? ""),
    };
  }
  if (skill.id === "navigate_within_viridian_forest_region") {
    const firstTarget = directorStringOptions(skill.params.targets)[0] ?? "forest_grass";
    return { target: args.target || firstTarget };
  }
  if (skill.id === "navigate_within_pallet_region") {
    const firstTarget = directorStringOptions(skill.params.targetIds)[0] ?? "pallet_grass_entrance";
    return { target: args.target || firstTarget };
  }
  if (skill.id === "enter_grass_search_loop") {
    const firstPatch = directorStringOptions(skill.params.patches)[0] ?? "forest_grass";
    return { patch: args.patch || firstPatch, maxSteps: 240 };
  }
  if (skill.id === "handle_nickname_prompt") {
    const choices = directorStringOptions(skill.params.choices);
    const defaultChoice = typeof skill.params.defaultChoice === "string" ? skill.params.defaultChoice : "decline";
    return { choice: args.nicknameChoice || choices[0] || defaultChoice };
  }
  if (skill.id === "enter_nickname_text") {
    const defaultNickname = typeof skill.params.defaultNickname === "string" ? skill.params.defaultNickname : "ABK";
    return { nickname: args.nicknameText || defaultNickname };
  }
  return {};
}

function directorStringOptions(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string" && item.length > 0);
}

function directorMoveOptions(skill: DirectorSkillAvailability): Array<{ slot: number; name: string; pp: number }> {
  const moves = skill.params.moves;
  if (!Array.isArray(moves)) {
    return [];
  }
  return moves
    .map((move) => {
      if (!isRecord(move)) {
        return null;
      }
      return {
        slot: Number(move.slot ?? 0),
        name: String(move.name ?? ""),
        pp: Number(move.pp ?? 0),
      };
    })
    .filter((move): move is { slot: number; name: string; pp: number } => Boolean(move?.name));
}

function directorSwitchTargets(
  skill: DirectorSkillAvailability,
): Array<{ slot: number; species: string; nickname: string | null; hp: number }> {
  const targets = skill.params.targets;
  if (!Array.isArray(targets)) {
    return [];
  }
  return targets
    .map((target) => {
      if (!isRecord(target)) {
        return null;
      }
      return {
        slot: Number(target.slot ?? 0),
        species: String(target.species ?? "unknown"),
        nickname: target.nickname === null || target.nickname === undefined ? null : String(target.nickname),
        hp: Number(target.hp ?? 0),
      };
    })
    .filter((target): target is { slot: number; species: string; nickname: string | null; hp: number } =>
      Boolean(target?.slot),
    );
}

function directorDestinationSlots(skill: DirectorSkillAvailability): number[] {
  const slots = skill.params.destinationSlots;
  if (!Array.isArray(slots)) {
    return directorSwitchTargets(skill).map((target) => target.slot);
  }
  return slots.map((slot) => Number(slot)).filter((slot) => Number.isInteger(slot) && slot > 0);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function formatSignalValue(value: unknown): string {
  if (typeof value === "boolean") {
    return value ? "yes" : "no";
  }
  if (value === null || value === undefined) {
    return "unknown";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function pokeBallCountFromSnapshot(snapshot: StateRecord["snapshot"]): number {
  return snapshot.inventory.find((item) => item.item_name === "Poke Ball")?.quantity ?? 0;
}

function countApproved(states: StateRecord[]): number {
  return states.filter((state) => ["approved", "human_verified"].includes(state.approval.status)).length;
}

function readStoredTab(key: string, fallback: Tab): Tab {
  const value = readStoredValue(key, fallback);
  return validTabs.has(value as Tab) ? (value as Tab) : fallback;
}

function readStoredValue(key: string, fallback: string): string {
  if (typeof window === "undefined") {
    return fallback;
  }
  return window.localStorage.getItem(key) || fallback;
}

function persistValue(key: string, value: string): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(key, value);
}
