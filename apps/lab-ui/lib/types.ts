export type DirectiveCategory =
  | "strategic"
  | "cosmetic"
  | "constraint"
  | "playful"
  | "ambiguous"
  | "impossible"
  | "destructive"
  | "derailing";

export type DirectiveDecision = "accept" | "reject" | "defer" | "reinterpret" | "ask_clarification";

export type DirectiveCase = {
  id: string;
  state_summary: string;
  objective: string;
  directive: string;
  expected: {
    category: DirectiveCategory;
    decision: DirectiveDecision;
  };
};

export type DirectiveDeck = {
  schema: string;
  description?: string;
  cases: DirectiveCase[];
};

export type DirectorVerdict = {
  directive: string;
  category: DirectiveCategory;
  risk: "low" | "medium" | "high";
  decision: DirectiveDecision;
  explanation: string;
  bounded_goal: string | null;
  constraints: string[];
  warnings: string[];
  raw_model_output: Record<string, unknown>;
};

export type SnapshotMove = {
  move_id: number;
  move_name: string;
  pp: number | null;
};

export type SnapshotPartyMember = {
  slot: number;
  species_id: number;
  species_name: string;
  nickname: string | null;
  level: number;
  hp: number;
  max_hp: number;
  status: number;
  moves: SnapshotMove[];
};

export type SnapshotItem = {
  item_id: number;
  item_name: string;
  quantity: number;
};

export type SnapshotBattleEnemy = {
  species_id: number;
  species_name: string;
  level: number;
  hp: number;
  max_hp: number;
  status: number;
  catch_rate: number | null;
};

export type SnapshotPosition = {
  map_id: number;
  map_name: string;
  x: number;
  y: number;
};

export type Snapshot = {
  mode: string;
  position: SnapshotPosition | null;
  party: SnapshotPartyMember[];
  inventory: SnapshotItem[];
  money: number | null;
  badges: number | null;
  badge_names: string[];
  active_party_slot?: number | null;
  active_party_member?: SnapshotPartyMember | null;
  enemy?: SnapshotBattleEnemy | null;
  facts: string[];
  plaintext_summary: string;
  warnings: string[];
};

export type Approval = {
  status: "approved" | "rejected" | "loadable_unapproved" | "human_verified" | "unverified";
  approved_by?: string | null;
  approved_at?: string | null;
  notes?: string;
};

export type StateRecord = {
  id: string;
  type: "golden" | "generated";
  name: string;
  statePath: string | null;
  screenshotPath: string | null;
  metadataPath: string;
  localStateExists: boolean;
  screenshotExists: boolean;
  goal: string | null;
  note: string | null;
  approval: Approval;
  snapshot: Snapshot;
  snapshotHash: string;
  createdUtc: string | null;
};

export type InterrogationAnswer = {
  answer: string;
  status: "answered" | "deferred";
  phase: string;
  evidence: string[];
};

export type SkillRecommendedStartState = {
  id: string;
  label: string;
  state_path: string | null;
  screenshot_path?: string | null;
  reason?: string;
  capture_hint?: string;
};

export type SkillCaptureNeed = {
  id: string;
  expected_status: string;
  condition: string;
  manual_action: string;
  recommended_start_states?: SkillRecommendedStartState[];
};

export type SkillDefinition = {
  id: string;
  name: string;
  status: string;
  purpose: string;
  result_statuses: string[];
  needed_captures: SkillCaptureNeed[];
  flagging_evidence: string[];
};

export type SkillCatalog = {
  schema: string;
  description: string;
  skills: SkillDefinition[];
};

export type SkillStateRecord = {
  id: string;
  skillId: string;
  captureId: string;
  phase: string;
  expectedStatus: string;
  expectedReason: string;
  manualAction: string;
  pairedCaptureId: string | null;
  statePath: string | null;
  screenshotPath: string | null;
  metadataPath: string;
  localStateExists: boolean;
  screenshotExists: boolean;
  note: string | null;
  snapshot: Snapshot;
  snapshotHash: string;
  createdUtc: string | null;
};

export type PromotionReference = {
  id: string;
  label: string;
  kind: string;
  metadataPath: string | null;
  statePath: string | null;
  screenshotPath: string | null;
  localStateExists: boolean;
  screenshotExists: boolean;
  command: string | null;
  captureCommand: string | null;
  expectedObservation: string;
  notes: string | null;
  assertionResults: PromotionAssertionResult[];
};

export type PromotionSourceRef = {
  label: string;
  url: string | null;
  notes: string;
};

export type PromotionReview = {
  reviewedBy: string | null;
  reviewedAt: string | null;
  notes: string;
};

export type PromotionEvidenceStep = {
  title: string;
  detail: string;
  command: string | null;
  expectedEvidence: string | null;
};

export type PromotionAssertionResult = {
  id: string;
  description: string;
  actualPath: string;
  op: string;
  expected: unknown;
  actual: unknown;
  passed: boolean;
};

export type PromotionRecord = {
  id: string;
  title: string;
  category: string;
  status: "verified" | "candidate" | "needed" | "blocked";
  priority: "p0" | "p1" | "p2";
  skillIds: string[];
  summary: string;
  currentSurface: string;
  promoteTo: string[];
  neededWork: string[];
  evidenceSteps: PromotionEvidenceStep[];
  sourceRefs: PromotionSourceRef[];
  verificationRefs: PromotionReference[];
  review: PromotionReview | null;
};

export type PromotionCatalog = {
  schema: string;
  description: string;
  promotions: PromotionRecord[];
};

export type PromotionValidationIssue = {
  promotionId: string | null;
  severity: "error" | "warning";
  message: string;
  refId?: string;
};

export type PromotionValidationResult = {
  schema: "promotion_validation_result_v1";
  status: "passed" | "needs_attention";
  checked: number;
  issues: PromotionValidationIssue[];
};

export type PromotionAssertionEvidenceResult = {
  promotionId: string;
  refId: string;
  label: string;
  metadataPath: string | null;
  status: "passed" | "failed" | "not_asserted";
  results: PromotionAssertionResult[];
};

export type PromotionAssertionValidationResult = {
  schema: "promotion_assertion_validation_v1";
  status: "passed" | "needs_attention";
  checked: number;
  asserted: number;
  passed: number;
  failed: number;
  notAsserted: number;
  evidence: PromotionAssertionEvidenceResult[];
};

export type DirectorSignal = {
  id: string;
  label: string;
  value: unknown;
  promotion: string;
};

export type DirectorSkillAvailability = {
  id: string;
  label: string;
  enabled: boolean;
  reason: string;
  status: string;
  params: Record<string, unknown>;
};

export type DirectorSkillResult = {
  createdUtc: string;
  skillId: string;
  status: string;
  summary: string;
  evidence: string[];
  warnings: string[];
  runDir: string | null;
  reportPath: string | null;
  args: Record<string, unknown>;
};

export type DirectorPlayerStatus = {
  schema: "director_player_status_v1";
  running: boolean;
  busy: boolean;
  startedUtc: string;
  session: {
    id: string;
    dir: string;
    eventLogPath: string;
    manifestPath: string;
  };
  rom: {
    path: string;
    title: string;
    sha256: string;
  };
  player: {
    window: string;
    render: boolean;
    runRoot: string;
    statusDir: string;
    statusPeriodSeconds: number;
  };
  snapshotHash: string;
  snapshot: Snapshot;
  screenshotPath: string;
  signals: DirectorSignal[];
  skills: DirectorSkillAvailability[];
  lastResult: DirectorSkillResult | null;
  history: DirectorSkillResult[];
  performance?: {
    freshStatusMs?: number;
    statusAgeSeconds?: number;
  };
};

export type LlmDirectorChatMessage = {
  role: "user" | "assistant" | "tool";
  content: string;
  createdUtc?: string;
  kind?: string;
};

export type LlmDirectorStep = {
  kind: "model" | "tool";
  name: string;
  summary: string;
  plaintextReasoning?: string;
  status?: string;
  args?: Record<string, unknown>;
  result?: Record<string, unknown>;
};

export type LlmDirectorRunResult = {
  schema: "director_segment_run_v1";
  status: "completed" | "checkpoint" | "stopped" | "failed" | "error";
  provider?: {
    provider?: string;
    apiFamily?: string;
    model?: string;
    capabilities?: Record<string, boolean>;
  };
  model: string;
  reasoningEffort?: string;
  goal: string;
  assistantMessage: string;
  messages: LlmDirectorChatMessage[];
  steps: LlmDirectorStep[];
  reportPath: string | null;
  playerStatus?: (Partial<DirectorPlayerStatus> & Record<string, unknown>) | null;
  tick?: number;
  envSnapshot?: Record<string, unknown>;
  screenshotPath?: string | null;
  screenshotSent?: boolean;
  messageLimit?: number;
  requestMessages?: LlmDirectorChatMessage[];
  requestSummary?: Record<string, unknown>;
  usage?: {
    inputTokens?: number | null;
    outputTokens?: number | null;
    totalTokens?: number | null;
    reasoningTokens?: number | null;
    cachedInputTokens?: number | null;
    estimatedCostUsd?: number | null;
  };
  error?: string;
};
