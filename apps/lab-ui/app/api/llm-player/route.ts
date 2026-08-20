import { promises as fs } from "fs";
import path from "path";
import { NextResponse } from "next/server";
import { repoRoot } from "@/lib/repo";

const directorPlayerUrl = process.env.DIRECTOR_PLAYER_URL || "http://127.0.0.1:8765";
const openaiUrl = "https://api.openai.com/v1/responses";
const defaultModel = process.env.OPENAI_LLM_PLAYER_MODEL || "gpt-5.4-nano";
const defaultReasoningEffort = process.env.OPENAI_REASONING_EFFORT || "low";
const runRoot = path.join(repoRoot, "research", "artifacts", "llm-director-runs");
const capsulePath = path.join(repoRoot, "research", "capsules", "viridian_forest_catching.json");

type ChatMessage = {
  role: "user" | "assistant" | "tool";
  content: string;
  createdUtc?: string;
  kind?: string;
};

type LlmPlayerRequest = {
  goal?: string;
  messages?: ChatMessage[];
  tick?: number;
  model?: string;
  reasoningEffort?: string;
  messageLimit?: number;
};

type ResponseOutputItem = {
  id?: string;
  type: string;
  call_id?: string;
  name?: string;
  arguments?: string;
  content?: Array<{ type?: string; text?: string }>;
};

type OpenAIResponse = {
  id: string;
  output?: ResponseOutputItem[];
  output_text?: string;
  usage?: Record<string, unknown>;
};

type OpenAIRequestDebug = {
  url: string;
  body: Record<string, unknown>;
};

export async function POST(request: Request) {
  const body = (await request.json()) as LlmPlayerRequest;
  const goal = (body.goal || "").trim();
  if (!goal) {
    return NextResponse.json({ error: "goal is required" }, { status: 400 });
  }
  const selectedModel = sanitizeModel(body.model);
  const reasoningEffort = sanitizeReasoningEffort(body.reasoningEffort);
  const messageLimit = sanitizeMessageLimit(body.messageLimit);

  const apiKey = await loadOpenAIKey();
  if (!apiKey) {
    return NextResponse.json({ error: "OPENAI_API_KEY is not set." }, { status: 500 });
  }

  const messages = truncateMessages(
    body.messages?.length
      ? body.messages
      : [
          {
            role: "user" as const,
            content: goal,
            createdUtc: new Date().toISOString(),
            kind: "goal",
          },
        ],
    messageLimit,
  );
  const steps: Array<Record<string, unknown>> = [];
  const runDir = path.join(runRoot, timestampForPath(new Date()));
  await fs.mkdir(runDir, { recursive: true });
  const reportPath = path.join(runDir, "report.json");

  try {
    const capsule = JSON.parse(await fs.readFile(capsulePath, "utf-8")) as Record<string, unknown>;
    const playerStatusRaw = await directorStatus({ fresh: true });
    const playerStatus = compactPlayerStatus(playerStatusRaw);
    const screenshotPath = typeof playerStatusRaw.screenshotPath === "string" ? playerStatusRaw.screenshotPath : null;
    const screenshotDataUrl = screenshotPath ? await screenshotDataUrlFromPath(screenshotPath) : null;
    const input = buildOpenAIInput({
      goal,
      messages,
      capsule: compactCapsuleSpec(capsule),
      playerStatus,
      screenshotDataUrl,
      tick: Number(body.tick ?? 0),
    });
    let assistantMessage = "";
    let finalStatus: "completed" | "stopped" = "stopped";
    let latestPlayerStatus: unknown = playerStatus;

    const { response, requestPayload } = await createResponse(apiKey, input, {
      model: selectedModel,
      reasoningEffort,
    });
    const functionCall = (response.output || []).find((item) => item.type === "function_call");
    assistantMessage = responseText(response) || assistantMessage;
    if (!functionCall) {
      finalStatus = "completed";
    } else {
      const toolName = String(functionCall.name || "");
      const args = parseJsonObject(functionCall.arguments || "{}");
      const toolResult = await executeDirectorTool(toolName, args);
      if (toolName === "execute_skill") {
        latestPlayerStatus = toolResult.playerStatus ?? latestPlayerStatus;
      }
      steps.push({
        kind: "tool",
        name: toolName,
        args,
        status: String(toolResult.status || "ok"),
        summary: String(toolResult.summary || toolName),
        plaintextReasoning: String(toolResult.plaintextReasoning || ""),
        result: toolResult,
      });
      if (!assistantMessage) {
        assistantMessage = directorToolNarration(toolName, toolResult);
      }
      if (toolName === "finish_run") {
        assistantMessage = String(toolResult.summary || assistantMessage);
        finalStatus = "completed";
      }
    }

    const result = {
      schema: "llm_director_run_v1",
      status: finalStatus,
      model: selectedModel,
      reasoningEffort,
      goal,
      assistantMessage: assistantMessage || "LLM Director run stopped without a final message.",
      messages: truncateMessages(
        [
          ...messages,
          {
            role: "assistant" as const,
            content: assistantMessage || "Run stopped before a final natural-language response.",
            createdUtc: new Date().toISOString(),
            kind: "llm_director_result",
          },
        ],
        messageLimit,
      ),
      steps,
      reportPath,
      playerStatus: latestPlayerStatus,
      tick: Number(body.tick ?? 0),
      envSnapshot: playerStatus,
      screenshotPath,
      screenshotSent: Boolean(screenshotDataUrl),
      messageLimit,
      requestMessages: messages,
      openaiRequest: requestPayload,
      openaiUsage: normalizeUsage(response.usage),
    };
    await fs.writeFile(reportPath, JSON.stringify(result, null, 2), "utf-8");
    return NextResponse.json(result);
  } catch (error) {
    const result = {
      schema: "llm_director_run_v1",
      status: "error",
      model: selectedModel,
      reasoningEffort,
      goal,
      assistantMessage: "LLM Director run failed.",
      messages,
      steps,
      reportPath,
      error: error instanceof Error ? error.message : "Unknown LLM Director error",
    };
    await fs.writeFile(reportPath, JSON.stringify(result, null, 2), "utf-8");
    return NextResponse.json(result, { status: 500 });
  }
}

async function createResponse(
  apiKey: string,
  input: Array<Record<string, unknown>>,
  settings: { model: string; reasoningEffort: string },
): Promise<{ response: OpenAIResponse; requestPayload: OpenAIRequestDebug }> {
  const body = {
    model: settings.model,
    reasoning: { effort: settings.reasoningEffort },
    instructions: directorInstructions(),
    input,
    tools: directorTools(),
    parallel_tool_calls: false,
    max_tool_calls: 1,
    max_output_tokens: 1400,
  };
  const response = await fetch(openaiUrl, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  const data = (await response.json()) as OpenAIResponse & { error?: { message?: string } };
  if (!response.ok) {
    throw new Error(data.error?.message || `OpenAI request failed with ${response.status}`);
  }
  return { response: data, requestPayload: { url: openaiUrl, body } };
}

function sanitizeModel(value: unknown): string {
  return typeof value === "string" && value.trim() ? value.trim() : defaultModel;
}

function sanitizeReasoningEffort(value: unknown): string {
  const effort = typeof value === "string" ? value.trim() : "";
  return ["minimal", "low", "medium", "high"].includes(effort) ? effort : defaultReasoningEffort;
}

function sanitizeMessageLimit(value: unknown): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return 20;
  }
  return Math.max(1, Math.min(100, Math.floor(parsed)));
}

function truncateMessages(messages: ChatMessage[], limit: number): ChatMessage[] {
  return messages.slice(-limit);
}

function normalizeUsage(usage: Record<string, unknown> | undefined): Record<string, number> {
  if (!usage) {
    return {};
  }
  const normalized: Record<string, number> = {};
  for (const [key, value] of Object.entries(usage)) {
    if (typeof value === "number") {
      normalized[key] = value;
    }
  }
  return normalized;
}

async function executeDirectorTool(name: string, args: Record<string, unknown>): Promise<Record<string, unknown>> {
  if (name === "get_capsule_spec") {
    const capsule = JSON.parse(await fs.readFile(capsulePath, "utf-8")) as Record<string, unknown>;
    return {
      status: "ok",
      summary: "Loaded Capsule A spec.",
      plaintextReasoning: "I need the capsule rules before deciding the next action.",
      capsule: compactCapsuleSpec(capsule),
    };
  }
  if (name === "get_player_status") {
    const status = await directorFetch("/status", { method: "GET" });
    return {
      status: "ok",
      summary: summarizeStatus(status),
      plaintextReasoning: "I need the current game state before choosing a skill.",
      playerStatus: compactPlayerStatus(status),
    };
  }
  if (name === "execute_skill") {
    const skillId = String(args.skillId || "");
    const skillArgs = isRecord(args.args) ? args.args : {};
    const plaintextReasoning = plaintextReasoningFromArgs(args, `I am using ${skillId || "a skill"} because it appears to be the next useful action.`);
    if (!skillId) {
      return { status: "error", summary: "skillId is required.", plaintextReasoning };
    }
    const normalizedSkillArgs = normalizeSkillArgs(skillId, skillArgs);
    const before = await directorFetch("/status", { method: "GET" });
    const available = enabledSkillIds(before);
    if (!available.includes(skillId)) {
      return {
        status: "blocked",
        summary: `${skillId} is not currently enabled.`,
        plaintextReasoning,
        enabledSkills: available,
        playerStatus: compactPlayerStatus(before),
      };
    }
    const status = await directorFetch("/skill", {
      method: "POST",
      body: JSON.stringify({ skillId, args: normalizedSkillArgs }),
    });
    const lastResult = isRecord(status.lastResult) ? status.lastResult : {};
    return {
      status: String(lastResult.status || "unknown"),
      summary: String(lastResult.summary || `Executed ${skillId}.`),
      plaintextReasoning,
      skillId,
      args: normalizedSkillArgs,
      lastResult,
      playerStatus: compactPlayerStatus(status),
    };
  }
  if (name === "finish_run") {
    const plaintextReasoning = plaintextReasoningFromArgs(args, String(args.summary || "I am finishing this run based on the current state."));
    return {
      status: String(args.status || "completed"),
      summary: String(args.summary || "LLM Director finished the run."),
      plaintextReasoning,
      success: Boolean(args.success),
      failureCategory: args.failureCategory ?? null,
    };
  }
  return { status: "error", summary: `Unknown tool: ${name}`, plaintextReasoning: `I attempted to call an unknown tool: ${name}.` };
}

async function directorFetch(endpoint: string, init: RequestInit): Promise<Record<string, unknown>> {
  const response = await fetch(`${directorPlayerUrl}${endpoint}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers || {}),
    },
    cache: "no-store",
  });
  const data = (await response.json()) as Record<string, unknown>;
  if (!response.ok) {
    throw new Error(String(data.error || `Director player request failed with ${response.status}`));
  }
  return data;
}

async function directorStatus({ fresh }: { fresh: boolean }): Promise<Record<string, unknown>> {
  if (!fresh) {
    return directorFetch("/status", { method: "GET" });
  }
  try {
    return await directorFetch("/status?fresh=1", { method: "GET" });
  } catch {
    return directorFetch("/status", { method: "GET" });
  }
}

function buildTickContent(input: {
  goal: string;
  messages: ChatMessage[];
  capsule: Record<string, unknown>;
  playerStatus: Record<string, unknown>;
  screenshotDataUrl: string | null;
  tick: number;
}): Array<Record<string, unknown>> {
  const text = buildTickPrompt(input);
  const content: Array<Record<string, unknown>> = [{ type: "input_text", text }];
  if (input.screenshotDataUrl) {
    content.push({ type: "input_image", image_url: input.screenshotDataUrl });
  }
  return content;
}

function buildOpenAIInput(input: {
  goal: string;
  messages: ChatMessage[];
  capsule: Record<string, unknown>;
  playerStatus: Record<string, unknown>;
  screenshotDataUrl: string | null;
  tick: number;
}): Array<Record<string, unknown>> {
  const observations = observationsFromStatus(input.playerStatus);
  return [
    {
      role: "system",
      content: [{ type: "input_text", text: buildPersistentSystemPrompt(input.goal, input.capsule) }],
    },
    ...observations.map((observation) => ({
      role: "system",
      content: [{ type: "input_text", text: `Observation: ${observation}` }],
    })),
    ...input.messages.map((message) => ({
      role: message.role,
      content: contentBlocksForMessage(message),
    })),
    {
      role: "user",
      content: buildTickContent(input),
    },
  ];
}

function contentBlocksForMessage(message: ChatMessage): Array<Record<string, unknown>> {
  if (message.role === "assistant") {
    return [{ type: "output_text", text: message.content }];
  }
  return [{ type: "input_text", text: message.content }];
}

function buildPersistentSystemPrompt(goal: string, capsule: Record<string, unknown>): string {
  return [
    "Persistent Capsule Context",
    "",
    "User goal:",
    goal,
    "",
    "Capsule spec:",
    JSON.stringify(compactForPrompt(capsule), null, 2),
  ].join("\n");
}

function buildTickPrompt(input: {
  goal: string;
  messages: ChatMessage[];
  capsule: Record<string, unknown>;
  playerStatus: Record<string, unknown>;
  tick: number;
}): string {
  return [
    `DIRECTOR TICK: ${input.tick}`,
    "CURRENT ENV SNAPSHOT:",
    JSON.stringify(compactForPrompt(input.playerStatus), null, 2),
    "",
    "A current screenshot is attached when available.",
    "Choose at most one enabled skill tool call for this tick, or finish_run if the capsule is complete/blocked.",
    "If the sidecar is busy or no safe skill is enabled, finish or wait with a clear reason instead of guessing.",
  ].join("\n");
}

function directorInstructions(): string {
  return [
    "You are the LLM Director for a Pokemon Red research agent.",
    "Your job is to complete Capsule A by choosing high-level skills, not by pressing raw buttons.",
    "Every tick includes the capsule spec, current env snapshot, enabled skills, and screenshot.",
    "Never invent skill names. Only call execute_skill for skills listed as enabled in the env snapshot.",
    "When calling use_move, pass args as {\"move\":\"Move Name\"} or {\"move\":33}; do not pass the full move option object from params.moves.",
    "When calling switch_party_member, pass args as {\"target\":2}, {\"target\":\"Squirtle\"}, or {\"target\":\"nickname\"}; do not pass the full target option object from params.targets.",
    "When calling handle_nickname_prompt, pass args as {\"choice\":\"accept\"} or {\"choice\":\"decline\"}. Accept only when the user asked for a nickname.",
    "When calling enter_nickname_text, pass args as {\"nickname\":\"JIMMY\"}; nickname text is uppercase A-Z, 1 to 10 characters.",
    "Every tool call must include plaintextReasoning: a concise natural-language explanation of why this tool is appropriate right now.",
    "Prefer explainable progress: navigate to Viridian Forest grass, enter grass, handle battle dialogue, use battle actions, attempt catches, resolve catch/nickname aftermath.",
    "For Capsule A success, catch an allowed wild Pokemon in or near Viridian Forest without blacking out or leaving the bounded region.",
    "If a nickname decision appears, prefer declining unless the chat explicitly asks for a nickname.",
    "If no safe skill is enabled, stop with a failure category instead of looping.",
    "Do not call literal_button_press unless it is the only enabled safe action for a transient prompt; prefer semantic skills.",
  ].join("\n");
}

function directorTools(): Array<Record<string, unknown>> {
  return [
    {
      type: "function",
      name: "execute_skill",
      description: "Execute one currently enabled Director skill on the sidecar player.",
      parameters: {
        type: "object",
        additionalProperties: false,
        properties: {
          skillId: { type: "string" },
          args: {
            type: "object",
            additionalProperties: true,
          },
          plaintextReasoning: {
            type: "string",
            description: "Concise natural-language reasoning for this skill choice in the current environment.",
          },
        },
        required: ["skillId", "args", "plaintextReasoning"],
      },
      strict: false,
    },
    {
      type: "function",
      name: "finish_run",
      description: "Finish the LLM Director attempt with a success/failure/stopped summary.",
      parameters: {
        type: "object",
        additionalProperties: false,
        properties: {
          status: { type: "string", enum: ["completed", "stopped", "failed"] },
          success: { type: "boolean" },
          summary: { type: "string" },
          failureCategory: { type: ["string", "null"] },
          plaintextReasoning: {
            type: "string",
            description: "Concise natural-language reasoning for why the run should finish now.",
          },
        },
        required: ["status", "success", "summary", "failureCategory", "plaintextReasoning"],
      },
      strict: true,
    },
  ];
}

function compactCapsuleSpec(capsule: Record<string, unknown>): Record<string, unknown> {
  return {
    id: capsule.id,
    name: capsule.name,
    objective: capsule.objective,
    success_conditions: capsule.success_conditions,
    failure_conditions: capsule.failure_conditions,
    abort_conditions: capsule.abort_conditions,
    budgets: capsule.budgets,
  };
}

function compactPlayerStatus(status: Record<string, unknown>): Record<string, unknown> {
  const snapshot = isRecord(status.snapshot) ? status.snapshot : {};
  const history = Array.isArray(status.history) ? status.history.filter(isRecord) : [];
  return {
    busy: status.busy,
    snapshot: {
      mode: snapshot.mode,
      position: snapshot.position,
      party: snapshot.party,
      inventory: snapshot.inventory,
      enemy: snapshot.enemy,
      active_party_member: snapshot.active_party_member,
      plaintext_summary: snapshot.plaintext_summary,
    },
    signals: compactSignals(status.signals),
    skills: compactEnabledSkills(status.skills),
    observations: compactObservations(history),
    lastResult: compactLastResult(status.lastResult),
  };
}

function compactSignals(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter(isRecord).map((signal) => ({
    label: signal.label,
    value: signal.value,
  }));
}

function compactEnabledSkills(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter(isRecord)
    .filter((skill) => skill.enabled === true)
    .map((skill) =>
      compactForPrompt({
        id: skill.id,
        label: skill.label,
        reason: skill.reason,
        params: skill.params,
      }) as Record<string, unknown>,
    );
}

function compactObservations(history: Array<Record<string, unknown>>): Array<Record<string, unknown>> {
  return history
    .filter((item) => item.skillId === "observation" || item.status === "info")
    .slice(0, 8)
    .map((item) =>
      compactForPrompt({
        summary: item.summary,
        evidence: item.evidence,
      }) as Record<string, unknown>,
    );
}

function compactLastResult(value: unknown): Record<string, unknown> | null {
  if (!isRecord(value)) {
    return null;
  }
  return compactForPrompt({
    skillId: value.skillId,
    status: value.status,
    summary: value.summary,
    args: value.args,
    evidence: value.evidence,
    warnings: value.warnings,
  }) as Record<string, unknown>;
}

function observationsFromStatus(status: Record<string, unknown>): string[] {
  const observations = Array.isArray(status.observations) ? status.observations.filter(isRecord) : [];
  return observations
    .map((item) => String(item.summary || ""))
    .filter(Boolean)
    .slice(0, 8);
}

function compactForPrompt(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(compactForPrompt).filter((item) => !isEmptyPromptValue(item));
  }
  if (!isRecord(value)) {
    return value;
  }
  const omittedKeys = new Set([
    "createdUtc",
    "eventLogPath",
    "manifestPath",
    "path",
    "reportPath",
    "runDir",
    "screenshotPath",
    "screenshot_file",
    "statePath",
    "state_path",
    "tracePath",
    "url",
  ]);
  const output: Record<string, unknown> = {};
  for (const [key, raw] of Object.entries(value)) {
    if (omittedKeys.has(key)) {
      continue;
    }
    const compacted = compactForPrompt(raw);
    if (!isEmptyPromptValue(compacted)) {
      output[key] = compacted;
    }
  }
  return output;
}

function isEmptyPromptValue(value: unknown): boolean {
  return (
    value === null ||
    value === undefined ||
    value === "" ||
    (Array.isArray(value) && value.length === 0) ||
    (isRecord(value) && Object.keys(value).length === 0)
  );
}

function summarizeStatus(status: Record<string, unknown>): string {
  const snapshot = isRecord(status.snapshot) ? status.snapshot : {};
  const position = isRecord(snapshot.position) ? snapshot.position : {};
  return `mode=${String(snapshot.mode || "unknown")}; location=${String(position.map_name || "unknown")}; enabled=${enabledSkillIds(status).join(", ") || "none"}`;
}

function enabledSkillIds(status: Record<string, unknown>): string[] {
  if (!Array.isArray(status.skills)) {
    return [];
  }
  return status.skills
    .filter(isRecord)
    .filter((skill) => skill.enabled === true)
    .map((skill) => String(skill.id || ""))
    .filter(Boolean);
}

function responseText(response: OpenAIResponse): string {
  if (response.output_text) {
    return response.output_text;
  }
  const chunks: string[] = [];
  for (const item of response.output || []) {
    for (const content of item.content || []) {
      if (content.type === "output_text" && content.text) {
        chunks.push(content.text);
      }
    }
  }
  return chunks.join("\n").trim();
}

function directorToolNarration(toolName: string, toolResult: Record<string, unknown>): string {
  const summary = String(toolResult.summary || toolName);
  const reasoning = String(toolResult.plaintextReasoning || "").trim();
  if (toolName === "execute_skill") {
    const skillId = String(toolResult.skillId || "skill");
    return reasoning ? `${reasoning}\n\nTool result: ${skillId}: ${summary}` : `${skillId}: ${summary}`;
  }
  return reasoning ? `${reasoning}\n\nTool result: ${summary}` : summary;
}

function plaintextReasoningFromArgs(args: Record<string, unknown>, fallback: string): string {
  const value = args.plaintextReasoning;
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function normalizeSkillArgs(skillId: string, args: Record<string, unknown>): Record<string, unknown> {
  if (skillId === "handle_nickname_prompt") {
    return { ...args, choice: normalizeNicknameChoiceArg(args) };
  }
  if (skillId === "enter_nickname_text") {
    return { ...args, nickname: normalizeNicknameTextArg(args) };
  }
  if (skillId === "switch_party_member") {
    const target = args.target;
    if (!isRecord(target)) {
      return args;
    }
    const slot = target.slot;
    if (typeof slot === "number" || typeof slot === "string") {
      return { ...args, target: slot };
    }
    const namedTarget = ["nickname", "species", "speciesName", "name"]
      .map((key) => target[key])
      .find((value) => typeof value === "string" && value.trim());
    return typeof namedTarget === "string" ? { ...args, target: namedTarget.trim() } : args;
  }
  if (skillId !== "use_move") {
    return args;
  }
  const move = args.move;
  if (!isRecord(move)) {
    return args;
  }
  const namedMove = ["name", "moveName", "move_name"]
    .map((key) => move[key])
    .find((value) => typeof value === "string" && value.trim());
  if (typeof namedMove === "string") {
    return { ...args, move: namedMove.trim() };
  }
  const moveId = ["moveId", "move_id", "id"].map((key) => move[key]).find((value) => typeof value === "number" || typeof value === "string");
  if (typeof moveId === "number" || typeof moveId === "string") {
    return { ...args, move: moveId };
  }
  return args;
}

function normalizeNicknameChoiceArg(args: Record<string, unknown>): string {
  const raw = args.choice ?? args.nicknameChoice ?? args.decision ?? args.answer ?? "decline";
  if (typeof raw === "boolean") {
    return raw ? "accept" : "decline";
  }
  const value = String(raw).trim().toLowerCase();
  return ["accept", "yes", "y", "true", "nickname", "name"].includes(value) ? "accept" : "decline";
}

function normalizeNicknameTextArg(args: Record<string, unknown>): string {
  let raw = args.nickname ?? args.nicknameText ?? args.text ?? args.name ?? "";
  if (isRecord(raw)) {
    raw = raw.nickname ?? raw.text ?? raw.name ?? "";
  }
  const match = String(raw).toUpperCase().match(/[A-Z]+/);
  return match ? match[0].slice(0, 10) : "";
}

async function screenshotDataUrlFromPath(imagePath: string): Promise<string | null> {
  const resolved = path.resolve(imagePath);
  const researchRoot = path.join(repoRoot, "research");
  if (!isWithin(resolved, researchRoot)) {
    return null;
  }
  try {
    const bytes = await fs.readFile(resolved);
    return `data:image/png;base64,${bytes.toString("base64")}`;
  } catch {
    return null;
  }
}

function isWithin(candidate: string, parent: string): boolean {
  const relative = path.relative(parent, candidate);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

function parseJsonObject(value: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(value) as unknown;
    return isRecord(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

async function loadOpenAIKey(): Promise<string | null> {
  if (process.env.OPENAI_API_KEY) {
    return process.env.OPENAI_API_KEY;
  }
  const envPath = path.join(repoRoot, ".env");
  try {
    const raw = await fs.readFile(envPath, "utf-8");
    for (const line of raw.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) {
        continue;
      }
      const [key, ...rest] = trimmed.split("=");
      if (key.trim() === "OPENAI_API_KEY") {
        return rest.join("=").trim().replace(/^["']|["']$/g, "") || null;
      }
    }
  } catch {
    return null;
  }
  return null;
}

function timestampForPath(date: Date): string {
  return date.toISOString().replace(/[-:.]/g, "").replace("T", "T").replace("Z", "Z");
}
