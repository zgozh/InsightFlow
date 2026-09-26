/**
 * 分析轨迹：现有 LangGraph 消息的**纯投影**（Phase 4 §8）。
 *
 * 这里没有第二套运行状态源：输入是 thread 已有的消息数组，输出是可渲染的结构化步骤。
 * 刷新后从 checkpoint 消息重建的轨迹与流式增量走的是同一个函数，因此两者天然一致。
 *
 * 安全边界（本模块最重要的事）：
 *
 * - **绝不**读取 `query_business_data` 的 `args.sql`、`present_files` 之外的任何 args、
 *   ToolMessage 里的结果 rows、plan token 或异常原文；
 * - 只接受已批准的工具名与已批准的 JSON 字段；`code`/`risk` 等取值再经白名单校验；
 * - 未知或畸形 payload 不渲染原对象，而是变成一条"无法解析的安全事件"；
 * - 不展示、不推断、也不命名 chain-of-thought——轨迹只有工具与状态。
 *
 * 之所以要在解析层做白名单而不是在渲染层"记得别渲染"：渲染层会随 UI 演进变化，
 * 而这里一旦不放行，敏感字段就没有任何到达 DOM 的路径。
 */

import type { Message } from "@langchain/langgraph-sdk";

import { extractTextFromMessage } from "@/core/messages/utils";

export const TRACE_TOOL_NAMES = [
  "write_todos",
  "inspect_business_catalog",
  "query_business_data",
  "task",
  "present_files",
  "write_analysis_report",
  "publish_analysis_report",
] as const;
export type TraceToolName = (typeof TRACE_TOOL_NAMES)[number];

export type AnalyticsTraceStepKind =
  | "plan"
  | "catalog"
  | "query"
  | "delegate"
  | "artifact"
  | "report"
  | "unknown";

export type AnalyticsTraceStatus =
  | "running"
  | "completed"
  | "failed"
  | "rejected";

export type AnalyticsReportReviewerStatus =
  | "approved"
  | "rejected"
  | "failed"
  | "limited";

export type AnalyticsReportReviewerReasonCode =
  | "unsupported_claim"
  | "evidence_mismatch"
  | "missing_citation"
  | "insufficient_evidence";

/** 受控查询卡片允许展示的安全事实：白名单，多一个字段都不行。 */
export interface AnalyticsQueryFacts {
  code: string;
  risk: string | null;
  row_count: number | null;
  byte_count: number | null;
  estimated_rows: number | null;
  /** 十进制精确值，保持字符串；前端不做浮点运算。 */
  engine_cost: string | null;
  truncated: boolean | null;
  schema_version: string | null;
  policy_version: string | null;
  evidence_id: string | null;
  result_digest: string | null;
}

export interface AnalyticsTraceStep {
  /** 工具调用 ID：稳定的去重与 React key 身份。 */
  id: string;
  kind: AnalyticsTraceStepKind;
  toolName: string;
  status: AnalyticsTraceStatus;
  /** 计划阶段的待办条数（不展示待办正文）。 */
  todoCount: number | null;
  /** `present_files` 已交付的 outputs 路径；其他工具恒为空。 */
  artifactPaths: string[];
  /** 委派类型（已按稳定模式校验）。 */
  subagentType: string | null;
  facts: AnalyticsQueryFacts | null;
  /** 仅由当前 writer 的投影回执推导；不代表独立持久状态。 */
  reviewerStatus: AnalyticsReportReviewerStatus | null;
  reviewerReasonCode: AnalyticsReportReviewerReasonCode | null;
  /** 未知工具或畸形 payload：UI 显示"无法解析的安全事件"，而不是原对象。 */
  unparsed: boolean;
}

const KIND_BY_TOOL: Record<string, AnalyticsTraceStepKind> = {
  write_todos: "plan",
  inspect_business_catalog: "catalog",
  query_business_data: "query",
  task: "delegate",
  present_files: "artifact",
  write_analysis_report: "report",
  publish_analysis_report: "report",
};

/** 成功决定码白名单：只认服务端真的会用来表示"拿到了有界结果"的两个码。 */
const QUERY_SUCCESS_CODES = new Set(["executed", "result_limit_reached"]);
/** 报告发布的成功码白名单。 */
const REPORT_SUCCESS_CODES = new Set(["published", "existing"]);
const REPORT_KNOWN_FAILURE_CODES = new Set([
  "report_conflict",
  "invalid_request",
  "analytics_unavailable",
  "analysis_evidence_unavailable",
  "analysis_review_rejected",
  "analysis_review_unavailable",
  "analysis_review_input_too_large",
  "analysis_review_attempt_limit",
  "analysis_report_result_unavailable",
]);
const REVIEW_REASON_CODES = new Set<AnalyticsReportReviewerReasonCode>([
  "unsupported_claim",
  "evidence_mismatch",
  "missing_citation",
  "insufficient_evidence",
]);
const RISK_VALUES = new Set(["low", "medium", "high", "blocked"]);
const OUTPUTS_PREFIX = "/mnt/user-data/outputs/";
const SUBAGENT_TYPE_RE = /^[a-z0-9][a-z0-9-]{0,31}$/;
const REPORT_ID_RE = /^[A-Za-z0-9_-]{1,64}$/;
const WRITER_ARTIFACT_PATH_RE =
  /^\/mnt\/user-data\/outputs\/analysis-report-[A-Za-z0-9_-]{1,64}\.md$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** 只接受安全标量：字符串有长度上限，数字必须是有限整数，布尔原样。 */
function readBoundedString(value: unknown, max = 128): string | null {
  if (typeof value !== "string" || value.length === 0 || value.length > max) {
    return null;
  }
  return value;
}

function readCount(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    return null;
  }
  return value;
}

function readDigest(value: unknown): string | null {
  const text = readBoundedString(value, 64);
  return text !== null && /^[0-9a-f]{64}$/.test(text) ? text : null;
}

function readDecimal(value: unknown): string | null {
  if (typeof value === "number") {
    return Number.isFinite(value) ? String(value) : null;
  }
  const text = readBoundedString(value, 64);
  return text !== null && /^-?\d+(\.\d+)?$/.test(text) ? text : null;
}

function readBool(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

/**
 * 从 `query_business_data` 的 ToolMessage 内容里提取安全事实。
 *
 * 拒绝码（策略拒绝、限额、不可用）同样是**结论**：这里把 code 原样带出，但不带任何
 * 服务端元数据，因此 UI 能显示"被拒绝 + 稳定码"，而拒绝原因里可能夹带的内部信息不会出现。
 */
function readQueryFacts(payload: Record<string, unknown>): AnalyticsQueryFacts {
  const evidence = isRecord(payload.evidence) ? payload.evidence : {};
  return {
    code: readBoundedString(payload.code, 64) ?? "unknown",
    risk: RISK_VALUES.has(String(evidence.risk)) ? String(evidence.risk) : null,
    row_count: readCount(evidence.row_count),
    byte_count: readCount(evidence.byte_count),
    estimated_rows: readCount(evidence.estimated_rows),
    engine_cost: readDecimal(evidence.engine_cost),
    truncated: readBool(evidence.truncated),
    schema_version: readBoundedString(evidence.schema_version, 64),
    policy_version: readBoundedString(evidence.policy_version, 64),
    evidence_id: readDigest(evidence.evidence_id),
    result_digest: readDigest(evidence.result_digest),
  };
}

function readPresentedPaths(args: Record<string, unknown>): string[] {
  const filepaths = args.filepaths;
  if (!Array.isArray(filepaths)) return [];
  const paths: string[] = [];
  for (const entry of filepaths) {
    // 只接受 outputs 下的绝对虚拟路径：其余一律不进入轨迹。
    if (typeof entry !== "string" || !entry.startsWith(OUTPUTS_PREFIX))
      continue;
    if (entry.length > 512 || entry.includes("\\")) continue;
    const relative = entry.slice(OUTPUTS_PREFIX.length);
    if (
      !relative ||
      relative
        .split("/")
        .some(
          (segment) => segment === "" || segment === "." || segment === "..",
        )
    ) {
      continue;
    }
    paths.push(entry);
    if (paths.length >= 8) break;
  }
  return paths;
}

function readTodoCount(args: Record<string, unknown>): number | null {
  return Array.isArray(args.todos) ? Math.min(args.todos.length, 99) : null;
}

function readSubagentType(args: Record<string, unknown>): string | null {
  const value = readBoundedString(args.subagent_type, 32);
  return value !== null && SUBAGENT_TYPE_RE.test(value) ? value : null;
}

function statusFromToolResult(
  kind: AnalyticsTraceStepKind,
  isError: boolean,
  parsed: Record<string, unknown> | null,
): AnalyticsTraceStatus {
  if (isError) return "failed";
  if (kind === "query") {
    const code = typeof parsed?.code === "string" ? parsed.code : null;
    if (code === null) return "failed";
    return QUERY_SUCCESS_CODES.has(code) ? "completed" : "rejected";
  }
  if (kind === "report") {
    const code = typeof parsed?.code === "string" ? parsed.code : null;
    if (code === null) return "failed";
    return REPORT_SUCCESS_CODES.has(code) ? "completed" : "rejected";
  }
  return "completed";
}

interface WriterReceiptProjection {
  status: AnalyticsTraceStatus;
  reviewerStatus: AnalyticsReportReviewerStatus | null;
  reviewerReasonCode: AnalyticsReportReviewerReasonCode | null;
  artifactPaths: string[];
  unparsed: boolean;
}

function hasOnlyKeys(
  payload: Record<string, unknown>,
  allowed: readonly string[],
): boolean {
  return Object.keys(payload).every((key) => allowed.includes(key));
}

function isEvidenceIdList(value: unknown): value is string[] {
  return (
    Array.isArray(value) &&
    value.length > 0 &&
    value.length <= 20 &&
    value.every((item) => readDigest(item) !== null) &&
    new Set(value).size === value.length
  );
}

/** 只把安全投影中的成功回执解释为审核通过；失败码不能暗示通过或产物存在。 */
function readWriterReceipt(
  payload: Record<string, unknown>,
  isError: boolean,
): WriterReceiptProjection {
  const failed = (unparsed = false): WriterReceiptProjection => ({
    status: "failed",
    reviewerStatus: null,
    reviewerReasonCode: null,
    artifactPaths: [],
    unparsed,
  });
  if (isError) return failed();

  const code = typeof payload.code === "string" ? payload.code : null;
  if (code === null) return failed(true);

  if (REPORT_SUCCESS_CODES.has(code)) {
    const evidenceIds = payload.evidence_ids;
    if (
      !hasOnlyKeys(payload, [
        "code",
        "report_id",
        "artifact_path",
        "evidence_ids",
      ]) ||
      typeof payload.report_id !== "string" ||
      !REPORT_ID_RE.test(payload.report_id) ||
      typeof payload.artifact_path !== "string" ||
      !WRITER_ARTIFACT_PATH_RE.test(payload.artifact_path) ||
      !isEvidenceIdList(evidenceIds)
    ) {
      return failed(true);
    }
    return {
      status: "completed",
      reviewerStatus: "approved",
      reviewerReasonCode: null,
      artifactPaths: [payload.artifact_path],
      unparsed: false,
    };
  }

  if (code === "analysis_review_rejected") {
    const reason = payload.reason_code;
    const validReason =
      typeof reason === "string" &&
      REVIEW_REASON_CODES.has(reason as AnalyticsReportReviewerReasonCode);
    return {
      status: "rejected",
      reviewerStatus: "rejected",
      reviewerReasonCode: validReason
        ? (reason as AnalyticsReportReviewerReasonCode)
        : null,
      artifactPaths: [],
      unparsed:
        !hasOnlyKeys(payload, ["code", "reason_code"]) ||
        (reason !== undefined && !validReason),
    };
  }

  if (code === "analysis_review_unavailable") {
    return {
      status: "failed",
      reviewerStatus: "failed",
      reviewerReasonCode: null,
      artifactPaths: [],
      unparsed: !hasOnlyKeys(payload, ["code"]),
    };
  }

  if (
    code === "analysis_review_input_too_large" ||
    code === "analysis_review_attempt_limit"
  ) {
    return {
      status: "failed",
      reviewerStatus: "limited",
      reviewerReasonCode: null,
      artifactPaths: [],
      unparsed: !hasOnlyKeys(payload, ["code"]),
    };
  }

  if (REPORT_KNOWN_FAILURE_CODES.has(code)) {
    return {
      status: "rejected",
      reviewerStatus: null,
      reviewerReasonCode: null,
      artifactPaths: [],
      unparsed: !hasOnlyKeys(payload, ["code"]),
    };
  }

  return failed(true);
}

interface PendingStep {
  step: AnalyticsTraceStep;
  /** 结果消息是否已经合并过：只有先到先得的"有结果"版本才更新状态。 */
  resolved: boolean;
}

function parseToolCallArguments(raw: unknown): Record<string, unknown> {
  if (isRecord(raw)) return raw;
  // 有些 provider 会把 args 发成 JSON 字符串；只在这一种情况下解析，失败即为空对象。
  if (typeof raw === "string" && raw.length <= 4096) {
    try {
      const parsed: unknown = JSON.parse(raw);
      return isRecord(parsed) ? parsed : {};
    } catch {
      return {};
    }
  }
  return {};
}

/**
 * 把消息数组投影成分析轨迹。
 *
 * 顺序即消息顺序；同一 `tool_call_id` 只出现一次（保留信息量更大的那一条）。
 */
export function projectAnalyticsTrace(
  messages: Message[],
): AnalyticsTraceStep[] {
  const order: string[] = [];
  const byId = new Map<string, PendingStep>();

  for (const message of messages) {
    if (message.type === "ai") {
      for (const toolCall of message.tool_calls ?? []) {
        const name = typeof toolCall.name === "string" ? toolCall.name : "";
        const id =
          typeof toolCall.id === "string" && toolCall.id.length > 0
            ? toolCall.id
            : `${name}:${order.length}`;
        if (byId.has(id)) continue;
        const kind = KIND_BY_TOOL[name] ?? "unknown";
        const args = parseToolCallArguments(toolCall.args);
        byId.set(id, {
          resolved: false,
          step: {
            id,
            kind,
            toolName: name,
            status: "running",
            todoCount: kind === "plan" ? readTodoCount(args) : null,
            artifactPaths: kind === "artifact" ? readPresentedPaths(args) : [],
            subagentType: kind === "delegate" ? readSubagentType(args) : null,
            facts: null,
            reviewerStatus: null,
            reviewerReasonCode: null,
            unparsed: kind === "unknown",
          },
        });
        order.push(id);
      }
      continue;
    }

    if (message.type !== "tool") continue;
    const id =
      typeof message.tool_call_id === "string" ? message.tool_call_id : "";
    const pending = byId.get(id);
    if (pending === undefined || pending.resolved) continue;

    const isError = (message as { status?: unknown }).status === "error";
    const text = extractTextFromMessage(message);
    let parsed: Record<string, unknown> | null = null;
    if (typeof text === "string" && text.length > 0 && text.length <= 65536) {
      try {
        const candidate: unknown = JSON.parse(text);
        parsed = isRecord(candidate) ? candidate : null;
      } catch {
        parsed = null;
      }
    }

    pending.resolved = true;

    if (
      pending.step.kind === "report" &&
      pending.step.toolName === "write_analysis_report"
    ) {
      if (parsed === null) {
        pending.step.status = "failed";
        pending.step.unparsed = true;
      } else {
        const result = readWriterReceipt(parsed, isError);
        pending.step.status = result.status;
        pending.step.reviewerStatus = result.reviewerStatus;
        pending.step.reviewerReasonCode = result.reviewerReasonCode;
        pending.step.artifactPaths = result.artifactPaths;
        pending.step.unparsed = result.unparsed;
      }
      continue;
    }

    pending.step.status = statusFromToolResult(
      pending.step.kind,
      isError,
      parsed,
    );

    if (pending.step.kind === "query") {
      if (parsed === null) {
        // 结果不是可解析的 JSON：不给任何原值机会，只标成"无法解析的安全事件"。
        pending.step.unparsed = true;
        pending.step.status = "failed";
      } else {
        pending.step.facts = readQueryFacts(parsed);
      }
      continue;
    }

    if (pending.step.kind === "report") {
      if (parsed === null) {
        pending.step.unparsed = true;
        pending.step.status = "failed";
        continue;
      }
      const report = isRecord(parsed.report) ? parsed.report : {};
      if (!isError && REPORT_SUCCESS_CODES.has(String(parsed.code))) {
        const paths = readPresentedPaths({ filepaths: [report.artifact_path] });
        if (paths.length === 1) pending.step.artifactPaths = paths;
      }
      pending.step.facts = null;
      continue;
    }

    if (pending.step.kind === "catalog" && parsed === null) {
      // 目录结果同样必须是可解析 JSON；否则只显示"无法解析"。
      pending.step.unparsed = true;
    }
  }

  return order.map((id) => byId.get(id)!.step);
}

/** 轨迹中是否存在受控查询步骤：只有分析页需要挂轨迹面板。 */
export function hasAnalyticsTrace(steps: AnalyticsTraceStep[]): boolean {
  return steps.some((step) => step.kind !== "unknown" || step.unparsed);
}

/** 受控查询步骤（evidence 卡片只渲染这些）。 */
export function querySteps(steps: AnalyticsTraceStep[]): AnalyticsTraceStep[] {
  return steps.filter((step) => step.kind === "query");
}

// --- 展示辅助 ---------------------------------------------------------------
//
// 放在这里而不是再开一个模块：它们只服务于轨迹面板，且必须与投影规则一起被同一份
// 测试钉住（尤其是"缩略值只用于扫读，复制按钮永远复制完整值"这条）。

/** 只用于扫读的缩略 digest；完整值仍由复制按钮提供。 */
export function abbreviateDigest(value: string, head = 8, tail = 4): string {
  if (value.length <= head + tail + 1) return value;
  return `${value.slice(0, head)}…${value.slice(-tail)}`;
}

/** 成本是服务端给的十进制字符串：这里只做空值判断，绝不重新计算或四舍五入。 */
export function formatEngineCost(value: string | null): string | null {
  return value === null || value.length === 0 ? null : value;
}
