/**
 * Analytics 外部 JSON 的严格解析（Phase 4 §5）。
 *
 * 三条硬规则：
 *
 * 1. **每个对象都 `.strict()`**：未知字段直接解析失败，绝不原样渲染。
 *    `z.passthrough()` 与未声明的字段在这里是禁止的——一个"顺手把整个 payload 交给 UI"的
 *    宽松 schema，正是敏感字段泄漏最常见的入口。
 * 2. **只声明服务端真的会发的字段**：普通用户的数据源视图没有 `owner_id`/`secret_ref`，
 *    管理员视图才有；两者用不同的 schema 表达，避免"管理员字段漏进普通视图"。
 * 3. **解析失败给稳定的通用错误**：`AnalyticsParseError` 只携带稳定 reason，不带上游 payload，
 *    因此未知响应不会被渲染，也不会被写进日志。
 *
 * Decimal 字段（`engine_cost`）在服务端以字符串发出（Pydantic JSON 模式），但客户端历史版本
 * 或代理可能给出数字；这里两者都接受并统一归一化成字符串，绝不做浮点运算。
 */

import { z } from "zod";

import {
  COLUMN_ACCESSES,
  COLUMN_SENSITIVITIES,
  ANALYSIS_STAGE_CODES,
  ANALYSIS_STAGE_RISKS,
  ANALYSIS_STAGE_STATUSES,
  ANALYSIS_STAGES,
  DATASOURCE_ENGINES,
  DATASOURCE_STATUSES,
  METRIC_STATUSES,
  QUERY_AUDIT_PHASES,
  QUERY_AUDIT_STATUSES,
  QUERY_RISKS,
  REPORT_STATUSES,
} from "./types";

/** 解析失败时对外暴露的唯一错误类型：只带稳定 reason。 */
export class AnalyticsParseError extends Error {
  readonly reason: string;

  constructor(reason: string) {
    super(reason);
    this.name = "AnalyticsParseError";
    this.reason = reason;
  }
}

const trimmed = z.string().min(1).max(64);
/** SHA-256 只可能是 64 位小写十六进制。 */
const digest = z
  .string()
  .regex(/^[0-9a-f]{64}$/, "digest must be 64 lowercase hex characters");
const decimal = z
  .union([z.string().regex(/^-?\d+(\.\d+)?$/), z.number()])
  .transform((value) => String(value));

const OUTPUTS_ROOT = "/mnt/user-data/outputs/";

/**
 * 报告 artifact 路径只允许是 outputs 下的规范化相对目标。
 *
 * 光靠 `startsWith` 不够：`/mnt/user-data/outputs/../uploads/x` 也"以它开头"。因此这里逐段
 * 检查空段、`.`、`..` 与反斜杠——与服务端领域层同一条规则，前端只是拒绝渲染明显越界的值。
 */
export function isOutputsScopedPath(value: string): boolean {
  if (!value.startsWith(OUTPUTS_ROOT)) return false;
  const relative = value.slice(OUTPUTS_ROOT.length);
  if (!relative || relative.includes("\\")) return false;
  return !relative
    .split("/")
    .some((segment) => segment === "" || segment === "." || segment === "..");
}

const artifactPath = z
  .string()
  .min(1)
  .max(512)
  .refine(isOutputsScopedPath, "artifact_path must be under the outputs root");

/**
 * 游标必须成对出现：`has_more` 为真时必须给出完整游标，为假时必须两个都是 null。
 *
 * 服务端就是这么发的。这里刻意**不**写成 Zod `.refine()`：`ZodEffects` 包裹带 `.transform()`
 * 的对象时，TypeScript 会退化成结构比较并把 transform 的**输入**类型（`string | number`）
 * 泄漏到推断结果里，最终表现为"同名类型互不兼容"的假报错。校验放在解析之后的独立函数里，
 * 既保持 schema 只负责形状，也让这条规则可以被单独测试。
 */
export function cursorPairIsConsistent(value: {
  has_more: boolean;
  next_before_started_at?: string | null;
  next_before_created_at?: string | null;
  next_before_id: string | null;
}): boolean {
  const anchor =
    value.next_before_started_at ?? value.next_before_created_at ?? null;
  const both = anchor !== null && value.next_before_id !== null;
  const neither = anchor === null && value.next_before_id === null;
  return value.has_more ? both : neither;
}

/** 校验游标成对语义；不满足时抛只带稳定 reason 的解析错误。 */
export function assertCursorPairing(value: {
  has_more: boolean;
  next_before_started_at?: string | null;
  next_before_created_at?: string | null;
  next_before_id: string | null;
}): void {
  if (!cursorPairIsConsistent(value)) {
    throw new AnalyticsParseError("invalid_analytics_cursor");
  }
}

export const datasourceViewSchema = z
  .object({
    id: trimmed,
    name: z.string().min(1).max(255),
    engine: z.enum(DATASOURCE_ENGINES),
    default_schema: z.string().min(1).max(255).nullable(),
    status: z.enum(DATASOURCE_STATUSES),
  })
  .strict();

export const datasourceListSchema = z
  .object({ datasources: z.array(datasourceViewSchema) })
  .strict();

/** 管理员视图：唯一可以出现 `secret_ref` 的地方。 */
export const adminDatasourceViewSchema = datasourceViewSchema
  .extend({ owner_id: trimmed, secret_ref: z.string().min(1).max(512) })
  .strict();

export const adminDatasourceListSchema = z
  .object({ datasources: z.array(adminDatasourceViewSchema) })
  .strict();

export const metricViewSchema = z
  .object({
    key: z.string().min(1).max(64),
    name: z.string().min(1).max(255),
    description: z.string().max(2000),
    expression: z.string().min(1).max(2000),
    dimensions: z.array(z.string().min(1).max(255)),
    version: z.number().int().positive(),
    status: z.enum(METRIC_STATUSES),
  })
  .strict();

export const metricListSchema = z
  .object({ metrics: z.array(metricViewSchema) })
  .strict();

/** Principal 标识可用于权限路由，但不能包含首尾空白或控制字符。 */
export const metricPrincipalIdSchema = z
  .string()
  .min(1)
  .max(64)
  .refine(
    (value) =>
      value.trim() === value && !/[\u0000-\u001f\u007f-\u009f]/.test(value),
    "invalid principal identifier",
  );

export const metricGrantListSchema = z
  .object({ principal_ids: z.array(metricPrincipalIdSchema) })
  .strict();

export const metricGrantResponseSchema = z
  .object({
    principal_id: metricPrincipalIdSchema,
    granted: z.literal(true),
  })
  .strict();

export const metricGrantRemovalSchema = z
  .object({ removed: z.literal(true) })
  .strict();

export const columnSchemaViewSchema = z
  .object({
    name: z.string().min(1).max(255),
    data_type: z.string().min(1).max(128),
    sensitivity: z.enum(COLUMN_SENSITIVITIES),
  })
  .strict();

export const relationSchemaViewSchema = z
  .object({
    name: z.string().min(1).max(255),
    schema: z.string().min(1).max(255),
    catalog: z.string().min(1).max(255).nullable(),
    columns: z.array(columnSchemaViewSchema),
  })
  .strict();

export const schemaSnapshotViewSchema = z
  .object({
    datasource_id: trimmed,
    engine: z.enum(DATASOURCE_ENGINES),
    version: z.string().min(1).max(64),
    default_schema: z.string().min(1).max(255),
    relations: z.array(relationSchemaViewSchema),
  })
  .strict();

export const columnAccessRuleViewSchema = z
  .object({ name: z.string().min(1).max(255), access: z.enum(COLUMN_ACCESSES) })
  .strict();

export const relationAccessRuleViewSchema = z
  .object({
    name: z.string().min(1).max(255),
    schema: z.string().min(1).max(255),
    catalog: z.string().min(1).max(255).nullable(),
    columns: z.array(columnAccessRuleViewSchema),
  })
  .strict();

export const accessPolicyViewSchema = z
  .object({
    datasource_id: trimmed,
    principal_id: trimmed,
    version: z.string().min(1).max(64),
    relations: z.array(relationAccessRuleViewSchema),
    allowed_functions: z.array(z.string().min(1).max(128)),
  })
  .strict();

export const queryAuditViewSchema = z
  .object({
    id: trimmed,
    principal_id: trimmed,
    datasource_id: trimmed.nullable(),
    phase: z.enum(QUERY_AUDIT_PHASES),
    status: z.enum(QUERY_AUDIT_STATUSES),
    query_hash: digest.nullable(),
    risk: z.enum(QUERY_RISKS).nullable(),
    decision_code: z.string().min(1).max(64).nullable(),
    schema_version: z.string().min(1).max(64).nullable(),
    policy_version: z.string().min(1).max(64).nullable(),
    estimated_rows: z.number().int().nonnegative().nullable(),
    engine_cost: decimal.nullable(),
    plan_digest: digest.nullable(),
    row_count: z.number().int().nonnegative().nullable(),
    byte_count: z.number().int().nonnegative().nullable(),
    truncated: z.boolean().nullable(),
    latency_ms: z.number().int().nonnegative().nullable(),
    started_at: z.string().min(1),
    finished_at: z.string().min(1).nullable(),
  })
  .strict();

export const queryAuditPageSchema = z
  .object({
    audits: z.array(queryAuditViewSchema),
    has_more: z.boolean(),
    next_before_started_at: z.string().min(1).nullable(),
    next_before_id: trimmed.nullable(),
  })
  .strict();

export const analysisReportViewSchema = z
  .object({
    id: trimmed,
    principal_id: trimmed,
    thread_id: trimmed,
    run_id: trimmed,
    artifact_path: artifactPath,
    title: z.string().min(1).max(200),
    status: z.enum(REPORT_STATUSES),
    evidence_ids: z.array(digest).min(1),
    created_at: z.string().min(1),
  })
  .strict();

export const analysisReportPageSchema = z
  .object({
    reports: z.array(analysisReportViewSchema),
    has_more: z.boolean(),
    next_before_created_at: z.string().min(1).nullable(),
    next_before_id: trimmed.nullable(),
  })
  .strict();

/** Analysis stage payload is shared by live custom SSE and persisted run events. */
export const analysisStagePayloadSchema = z
  .object({
    type: z.literal("analysis_stage"),
    version: z.literal(1),
    run_id: z.string().regex(/^[A-Za-z0-9_-]{1,64}$/),
    seq: z.number().int().min(1).max(2147483647),
    stage: z.enum(ANALYSIS_STAGES),
    status: z.enum(ANALYSIS_STAGE_STATUSES),
    duration_ms: z.number().int().min(0).max(86400000).optional(),
    row_count: z.number().int().min(0).max(1000000).optional(),
    byte_count: z.number().int().min(0).max(16777216).optional(),
    input_tokens: z.number().int().min(0).max(10000000).optional(),
    output_tokens: z.number().int().min(0).max(10000000).optional(),
    risk: z.enum(ANALYSIS_STAGE_RISKS).optional(),
    cached: z.boolean().optional(),
    code: z.enum(ANALYSIS_STAGE_CODES).optional(),
    evidence_ids: z
      .array(z.string().regex(/^[0-9a-f]{64}$/))
      .max(20)
      .refine((values) => new Set(values).size === values.length)
      .optional(),
  })
  .strict();

/** 服务端的稳定错误体：`{"detail": {"code": "..."}}`。 */
export const analyticsErrorBodySchema = z
  .object({
    detail: z.object({ code: z.string().min(1).max(64) }).strict(),
  })
  .strict();

export type DatasourceViewParsed = z.infer<typeof datasourceViewSchema>;
export type AdminDatasourceViewParsed = z.infer<
  typeof adminDatasourceViewSchema
>;
export type MetricViewParsed = z.infer<typeof metricViewSchema>;
export type MetricGrantListParsed = z.infer<typeof metricGrantListSchema>;
export type MetricGrantResponseParsed = z.infer<
  typeof metricGrantResponseSchema
>;
export type MetricGrantRemovalParsed = z.infer<typeof metricGrantRemovalSchema>;
export type SchemaSnapshotViewParsed = z.infer<typeof schemaSnapshotViewSchema>;
export type AccessPolicyViewParsed = z.infer<typeof accessPolicyViewSchema>;
export type QueryAuditViewParsed = z.infer<typeof queryAuditViewSchema>;
export type QueryAuditPageParsed = z.infer<typeof queryAuditPageSchema>;
export type AnalysisReportViewParsed = z.infer<typeof analysisReportViewSchema>;
export type AnalysisReportPageParsed = z.infer<typeof analysisReportPageSchema>;

/**
 * 解析外部 JSON；失败时抛出只带稳定 reason 的 `AnalyticsParseError`。
 *
 * 泛型刻意用 `z.output<S>` 而不是 `z.ZodType<T>`：带 `.transform()` 的 schema 输入类型与输出
 * 类型不同，写成 `z.ZodType<T>` 会让 TypeScript 把**输入**类型（例如 `engine_cost: string | number`）
 * 推断成结果类型，进而产生"同名类型互不兼容"的假报错。
 *
 * 刻意不把 Zod 的 issue 列表带进异常：那里面会包含收到的值。
 */
export function parseExternal<S extends z.ZodTypeAny>(
  schema: S,
  payload: unknown,
): z.output<S> {
  const result = schema.safeParse(payload);
  if (!result.success) {
    throw new AnalyticsParseError("invalid_analytics_response");
  }
  return result.data;
}
