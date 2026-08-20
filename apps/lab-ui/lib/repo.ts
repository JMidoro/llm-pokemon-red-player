import { existsSync, promises as fs, statSync } from "fs";
import path from "path";
import type {
  DirectiveDeck,
  PromotionAssertionEvidenceResult,
  PromotionAssertionValidationResult,
  PromotionAssertionResult,
  PromotionCatalog,
  PromotionRecord,
  PromotionValidationResult,
  SkillCatalog,
  SkillStateRecord,
  StateRecord,
} from "@/lib/types";

export const repoRoot = findRepoRoot(process.cwd());
const goldenDir = path.join(repoRoot, "research", "golden-states");
const artifactsDir = path.join(repoRoot, "research", "artifacts");
const skillStatesDir = path.join(repoRoot, "research", "skill-states");
const skillCatalogPath = path.join(skillStatesDir, "catalog.json");
const directiveDeckPath = path.join(repoRoot, "research", "directives", "v0_directive_deck.json");
const promotionManifestPath = path.join(repoRoot, "research", "promotions", "mvp-skill-promotions.json");
const promotionEvidenceStepsPath = path.join(repoRoot, "research", "promotions", "evidence-collection-steps.json");

type JsonObject = Record<string, unknown>;

export async function loadDirectiveDeck(): Promise<DirectiveDeck> {
  const raw = await fs.readFile(directiveDeckPath, "utf-8");
  return JSON.parse(raw) as DirectiveDeck;
}

export async function loadStateRecords(): Promise<StateRecord[]> {
  const [golden, generated] = await Promise.all([loadGoldenStates(), loadGeneratedStates()]);
  return [...golden, ...generated].sort((a, b) => a.name.localeCompare(b.name));
}

export async function loadSkillCatalog(): Promise<SkillCatalog> {
  const raw = await fs.readFile(skillCatalogPath, "utf-8");
  return JSON.parse(raw) as SkillCatalog;
}

export async function loadSkillStateRecords(): Promise<SkillStateRecord[]> {
  const metadataPaths = await findFiles(skillStatesDir, (file) => file.endsWith(".skill.json"));
  const records = await Promise.all(
    metadataPaths.map(async (metadataPath) => {
      const raw = JSON.parse(await fs.readFile(metadataPath, "utf-8")) as JsonObject;
      return normalizeSkillState(metadataPath, raw);
    }),
  );
  return records.filter((record): record is SkillStateRecord => Boolean(record));
}

export async function loadPromotionCatalog(): Promise<PromotionCatalog> {
  const raw = JSON.parse(await fs.readFile(promotionManifestPath, "utf-8")) as JsonObject;
  const evidenceSteps = await loadPromotionEvidenceSteps();
  const promotions = Array.isArray(raw.promotions)
    ? (
        await Promise.all(
          raw.promotions.map((item) => normalizePromotion(item as JsonObject, evidenceSteps)),
        )
      ).filter((item): item is PromotionRecord => Boolean(item))
    : [];
  return {
    schema: String(raw.schema ?? "mvp_skill_promotion_manifest_v1"),
    description: String(raw.description ?? ""),
    promotions,
  };
}

export async function updatePromotionReview(input: {
  promotionId: string;
  status: PromotionRecord["status"];
  reviewedBy: string;
  notes: string;
}): Promise<PromotionCatalog> {
  const raw = await loadRawPromotionManifest();
  const promotion = findRawPromotion(raw, input.promotionId);
  promotion.status = input.status;
  promotion.review = {
    reviewed_by: input.reviewedBy || "Joey",
    reviewed_at: new Date().toISOString(),
    notes: input.notes,
  };
  await writeRawPromotionManifest(raw);
  return loadPromotionCatalog();
}

export async function addPromotionEvidence(input: {
  promotionId: string;
  reference: {
    id?: string;
    label: string;
    kind: string;
    metadataPath?: string | null;
    statePath?: string | null;
    screenshotPath?: string | null;
    captureCommand?: string | null;
    expectedObservation?: string;
    notes?: string | null;
  };
}): Promise<PromotionCatalog> {
  const raw = await loadRawPromotionManifest();
  const promotion = findRawPromotion(raw, input.promotionId);
  const refs = Array.isArray(promotion.verification_refs) ? promotion.verification_refs : [];
  const id = sanitizeId(input.reference.id || input.reference.label);
  const reference: JsonObject = {
    id,
    label: input.reference.label,
    kind: input.reference.kind || "reference",
    expected_observation: input.reference.expectedObservation || "",
  };
  const metadataPath = normalizeRepoRelativePath(input.reference.metadataPath);
  const statePath = normalizeRepoRelativePath(input.reference.statePath);
  const screenshotPath = normalizeRepoRelativePath(input.reference.screenshotPath);
  if (metadataPath) {
    reference.metadata_path = metadataPath;
  }
  if (statePath) {
    reference.state_path = statePath;
  }
  if (screenshotPath) {
    reference.screenshot_path = screenshotPath;
  }
  if (input.reference.captureCommand) {
    reference.capture_command = input.reference.captureCommand;
  }
  if (input.reference.notes) {
    reference.notes = input.reference.notes;
  }

  const existingIndex = refs.findIndex((item) => {
    const rawRef = item as JsonObject;
    return rawRef.id === id;
  });
  if (existingIndex >= 0) {
    refs[existingIndex] = reference;
  } else {
    refs.push(reference);
  }
  promotion.verification_refs = refs;
  promotion.review = {
    reviewed_by: "Lab UI",
    reviewed_at: new Date().toISOString(),
    notes: `Evidence '${id}' added or updated.`,
  };
  await writeRawPromotionManifest(raw);
  return loadPromotionCatalog();
}

export async function validatePromotionManifest(promotionId?: string): Promise<PromotionValidationResult> {
  const raw = await loadRawPromotionManifest();
  const evidenceSteps = await loadPromotionEvidenceSteps();
  const rawPromotions = Array.isArray(raw.promotions) ? (raw.promotions as JsonObject[]) : [];
  const promotions = promotionId
    ? rawPromotions.filter((promotion) => promotion.id === promotionId)
    : rawPromotions;
  const issues: PromotionValidationResult["issues"] = [];

  if (!rawPromotions.length) {
    issues.push({
      promotionId: null,
      severity: "error",
      message: "Manifest does not contain any promotions.",
    });
  }
  if (promotionId && !promotions.length) {
    issues.push({
      promotionId,
      severity: "error",
      message: "Promotion id was not found in the manifest.",
    });
  }

  for (const promotion of promotions) {
    const id = typeof promotion.id === "string" ? promotion.id : null;
    const status = normalizePromotionStatus(promotion.status);
    const sourceRefs = Array.isArray(promotion.source_refs) ? promotion.source_refs : [];
    const verificationRefs = Array.isArray(promotion.verification_refs) ? promotion.verification_refs : [];
    const steps = evidenceSteps.get(id ?? "");

    if (!id) {
      issues.push({ promotionId: null, severity: "error", message: "Promotion is missing an id." });
      continue;
    }
    if (typeof promotion.title !== "string" || !promotion.title.trim()) {
      issues.push({ promotionId: id, severity: "error", message: "Promotion is missing a title." });
    }
    if (promotion.status !== status) {
      issues.push({ promotionId: id, severity: "error", message: "Promotion has an invalid status." });
    }
    if (!["p0", "p1", "p2"].includes(String(promotion.priority))) {
      issues.push({ promotionId: id, severity: "error", message: "Promotion has an invalid priority." });
    }
    if (!steps?.length) {
      issues.push({
        promotionId: id,
        severity: "warning",
        message: "Promotion does not have step-by-step evidence collection instructions.",
      });
    }
    if (!sourceRefs.length && !verificationRefs.length) {
      issues.push({
        promotionId: id,
        severity: status === "verified" ? "error" : "warning",
        message: "Promotion has no source refs or verification evidence.",
      });
    }
    if (status === "verified" && !verificationRefs.length) {
      issues.push({
        promotionId: id,
        severity: "error",
        message: "Verified promotions must have at least one verification evidence ref.",
      });
    }
    if ((status === "verified" || status === "candidate") && !sourceRefs.length) {
      issues.push({
        promotionId: id,
        severity: status === "verified" ? "error" : "warning",
        message: "Candidate or verified promotions should cite a canonical source or explicit local derivation.",
      });
    }

    sourceRefs.forEach((source, index) => {
      const ref = source as JsonObject;
      if (typeof ref.label !== "string" || !ref.label.trim()) {
        issues.push({
          promotionId: id,
          severity: "warning",
          message: `Source ref ${index + 1} is missing a label.`,
        });
      }
      if (ref.url !== undefined && ref.url !== null && !isHttpUrl(String(ref.url))) {
        issues.push({
          promotionId: id,
          severity: "warning",
          message: `Source ref ${String(ref.label ?? index + 1)} does not look like an HTTP URL.`,
        });
      }
    });

    for (const [index, reference] of verificationRefs.entries()) {
      const ref = reference as JsonObject;
      const refId = String(ref.id ?? `ref-${index + 1}`);
      if (typeof ref.label !== "string" || !ref.label.trim()) {
        issues.push({
          promotionId: id,
          refId,
          severity: "warning",
          message: "Evidence ref is missing a label.",
        });
      }
      for (const [key, label] of [
        ["metadata_path", "metadata"],
        ["state_path", "state"],
        ["screenshot_path", "screenshot"],
      ] as const) {
        const value = ref[key];
        if (typeof value !== "string" || !value.trim()) {
          continue;
        }
        const absolutePath = resolveRepoPath(value);
        if (!absolutePath || !fileIsFileSyncish(absolutePath)) {
          issues.push({
            promotionId: id,
            refId,
            severity: status === "verified" && key !== "screenshot_path" ? "error" : "warning",
            message: `Evidence ${label} path is recorded but missing locally: ${value}`,
          });
        }
      }
      if (ref.kind === "pending_capture" && typeof ref.capture_command !== "string") {
        issues.push({
          promotionId: id,
          refId,
          severity: "warning",
          message: "Pending capture evidence should include a capture command.",
        });
      }
      if (status === "verified" && typeof ref.expected_observation !== "string") {
        issues.push({
          promotionId: id,
          refId,
          severity: "warning",
          message: "Verified evidence should state the expected observation.",
        });
      }
      if (ref.kind === "promotion_evidence") {
        const metadataPath = resolveRepoPath(ref.metadata_path);
        const assertionResults = await loadPromotionAssertionResults(metadataPath);
        if (!assertionResults.length && (id === "battle-enemy-facts" || id === "battle_enemy_facts")) {
          issues.push({
            promotionId: id,
            refId,
            severity: status === "verified" ? "error" : "warning",
            message: "Battle enemy fact evidence has no machine-checkable WRAM assertions.",
          });
        }
        for (const result of assertionResults) {
          if (!result.passed) {
            issues.push({
              promotionId: id,
              refId,
              severity: "error",
              message: `Assertion '${result.id}' failed: ${result.actualPath} was ${String(
                result.actual,
              )}, expected ${String(result.expected)}.`,
            });
          }
        }
      }
    }
  }

  return {
    schema: "promotion_validation_result_v1",
    status: issues.some((issue) => issue.severity === "error") ? "needs_attention" : "passed",
    checked: promotions.length,
    issues,
  };
}

export async function validatePromotionAssertions(
  promotionId?: string,
): Promise<PromotionAssertionValidationResult> {
  const catalog = await loadPromotionCatalog();
  const promotions = promotionId
    ? catalog.promotions.filter((promotion) => promotion.id === promotionId)
    : catalog.promotions;
  const evidence: PromotionAssertionEvidenceResult[] = promotions.flatMap((promotion) =>
    promotion.verificationRefs
      .filter((reference) => reference.kind === "promotion_evidence" || reference.assertionResults.length > 0)
      .map((reference) => {
        const failed = reference.assertionResults.some((result) => !result.passed);
        const status: PromotionAssertionEvidenceResult["status"] =
          reference.assertionResults.length === 0 ? "not_asserted" : failed ? "failed" : "passed";
        return {
          promotionId: promotion.id,
          refId: reference.id,
          label: reference.label,
          metadataPath: reference.metadataPath,
          status,
          results: reference.assertionResults,
        };
      }),
  );
  const failed = evidence.filter((item) => item.status === "failed").length;
  const notAsserted = evidence.filter((item) => item.status === "not_asserted").length;
  const passed = evidence.filter((item) => item.status === "passed").length;

  return {
    schema: "promotion_assertion_validation_v1",
    status: failed > 0 ? "needs_attention" : "passed",
    checked: evidence.length,
    asserted: evidence.length - notAsserted,
    passed,
    failed,
    notAsserted,
    evidence,
  };
}

export async function loadStateRecord(id: string): Promise<StateRecord | null> {
  const states = await loadStateRecords();
  return states.find((state) => state.id === id) ?? null;
}

export async function updateGeneratedApproval(
  reportPath: string,
  approval: { status: "approved" | "rejected"; approvedBy: string; notes: string },
): Promise<StateRecord> {
  const absoluteReportPath = path.resolve(reportPath);
  assertWithin(absoluteReportPath, artifactsDir);

  const record = JSON.parse(await fs.readFile(absoluteReportPath, "utf-8")) as JsonObject;
  if (record.schema !== "generated_state_report_v1") {
    throw new Error("Only generated state reports can be approved from the lab UI.");
  }

  record.approval = {
    status: approval.status,
    approved_by: approval.approvedBy || "Joey",
    approved_at: new Date().toISOString(),
    notes: approval.notes,
  };

  await fs.writeFile(absoluteReportPath, JSON.stringify(record, null, 2), "utf-8");
  const normalized = normalizeGeneratedState(absoluteReportPath, record);
  if (!normalized) {
    throw new Error("Updated report could not be normalized.");
  }
  return normalized;
}

async function loadGoldenStates(): Promise<StateRecord[]> {
  const files = await safeReadDir(goldenDir);
  const records = await Promise.all(
    files
      .filter((file) => file.endsWith(".expected.json"))
      .map(async (file) => {
        const metadataPath = path.join(goldenDir, file);
        const raw = JSON.parse(await fs.readFile(metadataPath, "utf-8")) as JsonObject;
        return normalizeGoldenState(metadataPath, raw);
      }),
  );
  return records.filter((record): record is StateRecord => Boolean(record));
}

async function loadGeneratedStates(): Promise<StateRecord[]> {
  const reportPaths = await findFiles(artifactsDir, (file) => file.endsWith(".report.json"));
  const records = await Promise.all(
    reportPaths.map(async (metadataPath) => {
      const raw = JSON.parse(await fs.readFile(metadataPath, "utf-8")) as JsonObject;
      return normalizeGeneratedState(metadataPath, raw);
    }),
  );
  return records.filter((record): record is StateRecord => Boolean(record));
}

function normalizeGoldenState(metadataPath: string, raw: JsonObject): StateRecord | null {
  if (raw.schema !== "golden_state_expected_v1") {
    return null;
  }
  const snapshot = raw.snapshot as StateRecord["snapshot"];
  const name = String(raw.name ?? path.basename(metadataPath, ".expected.json"));
  const statePath = resolveRepoPath(raw.local_state_file);
  const screenshotPath = resolveRepoPath(raw.screenshot_file);
  const humanVerified = raw.human_verified === true;

  return {
    id: `golden:${name}`,
    type: "golden",
    name,
    statePath,
    metadataPath,
    localStateExists: statePath ? fileExistsSyncish(statePath) : false,
    screenshotPath,
    screenshotExists: screenshotPath ? fileExistsSyncish(screenshotPath) : false,
    goal: null,
    note: typeof raw.note === "string" ? raw.note : null,
    approval: {
      status: humanVerified ? "human_verified" : "unverified",
      notes: humanVerified ? "Human verified golden state." : "Golden state has not been marked verified.",
    },
    snapshot,
    snapshotHash: String(raw.snapshot_hash ?? ""),
    createdUtc: typeof raw.created_utc === "string" ? raw.created_utc : null,
  };
}

function normalizeGeneratedState(metadataPath: string, raw: JsonObject): StateRecord | null {
  if (raw.schema !== "generated_state_report_v1") {
    return null;
  }
  const snapshot = raw.snapshot as StateRecord["snapshot"];
  const statePath = resolveRepoPath(raw.output_state);
  const screenshotPath = resolveRepoPath(raw.screenshot_file);
  const name = statePath
    ? path.basename(statePath).replace(/\.state$/, "")
    : path.basename(metadataPath).replace(/\.state\.report\.json$/, "");
  const approval = (raw.approval ?? {}) as Record<string, unknown>;

  return {
    id: `generated:${name}`,
    type: "generated",
    name,
    statePath,
    metadataPath,
    localStateExists: statePath ? fileExistsSyncish(statePath) : false,
    screenshotPath,
    screenshotExists: screenshotPath ? fileExistsSyncish(screenshotPath) : false,
    goal: typeof raw.goal === "string" ? raw.goal : null,
    note: typeof raw.description === "string" ? raw.description : null,
    approval: {
      status:
        approval.status === "approved" || approval.status === "rejected"
          ? approval.status
          : "loadable_unapproved",
      approved_by: typeof approval.approved_by === "string" ? approval.approved_by : null,
      approved_at: typeof approval.approved_at === "string" ? approval.approved_at : null,
      notes: typeof approval.notes === "string" ? approval.notes : "",
    },
    snapshot,
    snapshotHash: String(raw.snapshot_hash ?? ""),
    createdUtc: typeof raw.created_utc === "string" ? raw.created_utc : null,
  };
}

function normalizeSkillState(metadataPath: string, raw: JsonObject): SkillStateRecord | null {
  if (raw.schema !== "skill_state_capture_v1") {
    return null;
  }
  const snapshot = raw.snapshot as SkillStateRecord["snapshot"];
  const statePath = resolveRepoPath(raw.local_state_file);
  const screenshotPath = resolveRepoPath(raw.screenshot_file);
  const skillId = String(raw.skill_id ?? "");
  const captureId = String(raw.capture_id ?? "");

  return {
    id: `${skillId}:${captureId}`,
    skillId,
    captureId,
    phase: String(raw.phase ?? "single"),
    expectedStatus: String(raw.expected_status ?? ""),
    expectedReason: String(raw.expected_reason ?? ""),
    manualAction: String(raw.manual_action ?? ""),
    pairedCaptureId: typeof raw.paired_capture_id === "string" ? raw.paired_capture_id : null,
    statePath,
    screenshotPath,
    metadataPath,
    localStateExists: statePath ? fileExistsSyncish(statePath) : false,
    screenshotExists: screenshotPath ? fileExistsSyncish(screenshotPath) : false,
    note: typeof raw.note === "string" ? raw.note : null,
    snapshot,
    snapshotHash: String(raw.snapshot_hash ?? ""),
    createdUtc: typeof raw.created_utc === "string" ? raw.created_utc : null,
  };
}

async function normalizePromotion(
  raw: JsonObject,
  evidenceStepMap: Map<string, PromotionRecord["evidenceSteps"]>,
): Promise<PromotionRecord | null> {
  const id = typeof raw.id === "string" ? raw.id : null;
  const title = typeof raw.title === "string" ? raw.title : null;
  if (!id || !title) {
    return null;
  }
  const refs = Array.isArray(raw.verification_refs) ? raw.verification_refs : [];
  const status = normalizePromotionStatus(raw.status);
  const priority = normalizePromotionPriority(raw.priority);

  const verificationRefs = await Promise.all(
    refs.map((item) => normalizePromotionReference(item as JsonObject)),
  );

  return {
    id,
    title,
    category: String(raw.category ?? "uncategorized"),
    status,
    priority,
    skillIds: asStringArray(raw.skill_ids),
    summary: String(raw.summary ?? ""),
    currentSurface: String(raw.current_surface ?? ""),
    promoteTo: asStringArray(raw.promote_to),
    neededWork: asStringArray(raw.needed_work),
    evidenceSteps: evidenceStepMap.get(id) ?? [],
    sourceRefs: Array.isArray(raw.source_refs)
      ? raw.source_refs.map((item) => normalizePromotionSourceRef(item as JsonObject))
      : [],
    verificationRefs,
    review: normalizePromotionReview(raw.review),
  };
}

function normalizePromotionSourceRef(raw: JsonObject) {
  return {
    label: String(raw.label ?? "Source"),
    url: typeof raw.url === "string" ? raw.url : null,
    notes: String(raw.notes ?? ""),
  };
}

async function normalizePromotionReference(raw: JsonObject) {
  const metadataPath = resolveRepoPath(raw.metadata_path);
  const statePath = resolveRepoPath(raw.state_path);
  const screenshotPath = resolveRepoPath(raw.screenshot_path);
  const captureCommand = typeof raw.capture_command === "string" ? raw.capture_command : null;

  return {
    id: String(raw.id ?? raw.label ?? "promotion-ref"),
    label: String(raw.label ?? raw.id ?? "Promotion reference"),
    kind: String(raw.kind ?? "reference"),
    metadataPath,
    statePath,
    screenshotPath,
    localStateExists: statePath ? fileExistsSyncish(statePath) : false,
    screenshotExists: screenshotPath ? fileExistsSyncish(screenshotPath) : false,
    command: statePath ? `.\\.venv\\Scripts\\python scripts\\play_state.py "${statePath}"` : null,
    captureCommand,
    expectedObservation: String(raw.expected_observation ?? ""),
    notes: typeof raw.notes === "string" ? raw.notes : null,
    assertionResults: await loadPromotionAssertionResults(metadataPath),
  };
}

function normalizePromotionReview(raw: unknown) {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const review = raw as JsonObject;
  return {
    reviewedBy: typeof review.reviewed_by === "string" ? review.reviewed_by : null,
    reviewedAt: typeof review.reviewed_at === "string" ? review.reviewed_at : null,
    notes: typeof review.notes === "string" ? review.notes : "",
  };
}

async function loadPromotionAssertionResults(metadataPath: string | null): Promise<PromotionAssertionResult[]> {
  if (!metadataPath || !fileIsFileSyncish(metadataPath)) {
    return [];
  }
  const raw = JSON.parse(await fs.readFile(metadataPath, "utf-8")) as JsonObject;
  if (raw.schema !== "promotion_evidence_capture_v1" || !Array.isArray(raw.assertions)) {
    return [];
  }
  return raw.assertions.map((assertion) => evaluatePromotionAssertion(raw, assertion as JsonObject));
}

function evaluatePromotionAssertion(record: JsonObject, assertion: JsonObject): PromotionAssertionResult {
  const actualPath = String(assertion.actual_path ?? "");
  const op = String(assertion.op ?? "");
  const actual = valueAtPath(record, actualPath);
  let expected: unknown = assertion.expected;
  let passed = false;

  if (op === "equals") {
    passed = actual === expected;
  } else if (op === "equals_path") {
    expected = valueAtPath(record, String(assertion.expected_path ?? ""));
    passed = actual === expected;
  } else if (op === "less_than_path") {
    expected = valueAtPath(record, String(assertion.expected_path ?? ""));
    passed = typeof actual === "number" && typeof expected === "number" && actual < expected;
  } else if (op === "greater_than_path") {
    expected = valueAtPath(record, String(assertion.expected_path ?? ""));
    passed = typeof actual === "number" && typeof expected === "number" && actual > expected;
  } else if (op === "contains") {
    passed =
      (typeof actual === "string" && typeof expected === "string" && actual.includes(expected)) ||
      (Array.isArray(actual) && actual.some((item) => item === expected));
  } else if (op === "not_contains") {
    passed =
      (typeof actual === "string" && typeof expected === "string" && !actual.includes(expected)) ||
      (Array.isArray(actual) && !actual.some((item) => item === expected));
  }

  return {
    id: String(assertion.id ?? "assertion"),
    description: String(assertion.description ?? ""),
    actualPath,
    op,
    expected,
    actual,
    passed,
  };
}

function valueAtPath(record: unknown, rawPath: string): unknown {
  let current = record;
  for (const part of rawPath.split(".")) {
    if (!part) {
      continue;
    }
    if (Array.isArray(current) && /^\d+$/.test(part)) {
      current = current[Number(part)];
      continue;
    }
    if (current && typeof current === "object" && part in current) {
      current = (current as Record<string, unknown>)[part];
      continue;
    }
    return null;
  }
  return current;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}

function normalizePromotionStatus(value: unknown): PromotionRecord["status"] {
  if (value === "verified" || value === "candidate" || value === "needed" || value === "blocked") {
    return value;
  }
  return "needed";
}

function normalizePromotionPriority(value: unknown): PromotionRecord["priority"] {
  if (value === "p0" || value === "p1" || value === "p2") {
    return value;
  }
  return "p1";
}

function resolveRepoPath(value: unknown): string | null {
  if (typeof value !== "string" || !value) {
    return null;
  }
  const normalized = value.replace(/\\/g, "/");
  const parts = normalized.split("/").filter(Boolean);
  const anchorIndex = parts.findIndex((part) =>
    ["apps", "research", "scripts", "src", "tests"].includes(part.toLowerCase()),
  );
  if (anchorIndex >= 0) {
    const remapped = path.join(repoRoot, ...parts.slice(anchorIndex));
    if (existsSync(remapped) || !path.isAbsolute(value) || !existsSync(value)) {
      return remapped;
    }
  }
  return path.isAbsolute(value) ? path.resolve(value) : path.resolve(repoRoot, normalized);
}

function findRepoRoot(start: string): string {
  let candidate = path.resolve(start);
  for (;;) {
    if (existsSync(path.join(candidate, "pyproject.toml")) && existsSync(path.join(candidate, "research"))) {
      return candidate;
    }
    const parent = path.dirname(candidate);
    if (parent === candidate) {
      throw new Error(`Could not find the Pokemon Player repository root from ${start}.`);
    }
    candidate = parent;
  }
}

async function loadRawPromotionManifest(): Promise<JsonObject> {
  return JSON.parse(await fs.readFile(promotionManifestPath, "utf-8")) as JsonObject;
}

async function loadPromotionEvidenceSteps(): Promise<Map<string, PromotionRecord["evidenceSteps"]>> {
  const raw = JSON.parse(await fs.readFile(promotionEvidenceStepsPath, "utf-8")) as JsonObject;
  const stepsByPromotion = raw.steps_by_promotion as JsonObject | undefined;
  const normalized = new Map<string, PromotionRecord["evidenceSteps"]>();
  if (!stepsByPromotion) {
    return normalized;
  }
  for (const [promotionId, steps] of Object.entries(stepsByPromotion)) {
    if (!Array.isArray(steps)) {
      continue;
    }
    normalized.set(
      promotionId,
      steps.map((step) => {
        const rawStep = step as JsonObject;
        return {
          title: String(rawStep.title ?? "Evidence step"),
          detail: String(rawStep.detail ?? ""),
          command: typeof rawStep.command === "string" ? rawStep.command : null,
          expectedEvidence:
            typeof rawStep.expected_evidence === "string" ? rawStep.expected_evidence : null,
        };
      }),
    );
  }
  return normalized;
}

async function writeRawPromotionManifest(raw: JsonObject): Promise<void> {
  await fs.writeFile(promotionManifestPath, `${JSON.stringify(raw, null, 2)}\n`, "utf-8");
}

function findRawPromotion(raw: JsonObject, promotionId: string): JsonObject {
  const promotions = Array.isArray(raw.promotions) ? raw.promotions : [];
  const promotion = promotions.find((item) => {
    const record = item as JsonObject;
    return record.id === promotionId;
  });
  if (!promotion) {
    throw new Error(`Promotion '${promotionId}' was not found.`);
  }
  return promotion as JsonObject;
}

function normalizeRepoRelativePath(value: string | null | undefined): string | undefined {
  if (!value || !value.trim()) {
    return undefined;
  }
  const absolutePath = resolveRepoPath(value);
  if (!absolutePath) {
    return undefined;
  }
  assertWithin(absolutePath, repoRoot);
  return path.relative(repoRoot, absolutePath).replace(/\\/g, "/");
}

function sanitizeId(value: string): string {
  const sanitized = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return sanitized || "promotion-ref";
}

function isHttpUrl(value: string): boolean {
  return /^https?:\/\//i.test(value);
}

async function safeReadDir(directory: string): Promise<string[]> {
  try {
    return await fs.readdir(directory);
  } catch {
    return [];
  }
}

async function findFiles(directory: string, predicate: (file: string) => boolean): Promise<string[]> {
  const entries = await safeReadDir(directory);
  const found: string[] = [];

  await Promise.all(
    entries.map(async (entry) => {
      const fullPath = path.join(directory, entry);
      const stat = await fs.stat(fullPath).catch(() => null);
      if (!stat) {
        return;
      }
      if (stat.isDirectory()) {
        found.push(...(await findFiles(fullPath, predicate)));
      } else if (predicate(entry)) {
        found.push(fullPath);
      }
    }),
  );

  return found;
}

function fileExistsSyncish(filePath: string): boolean {
  return existsSync(filePath);
}

function fileIsFileSyncish(filePath: string): boolean {
  try {
    return statSync(filePath).isFile();
  } catch {
    return false;
  }
}

function assertWithin(candidate: string, parent: string): void {
  const relative = path.relative(parent, candidate);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error("Path is outside the generated artifacts directory.");
  }
}
