/**
 * InsightFlow Analytics 数据层的类型契约（Phase 4 §5）。
 *
 * 这里是**纯类型与常量**，不引入运行时依赖：枚举值用 `as const` 元组声明，既能在
 * `schemas.ts` 里直接喂给 Zod，也能在展示层做穷尽映射。
 *
 * 为什么前端不重新定义安全语义：risk、限额、cost、hash/digest 全部由服务端计算。
 * 前端的类型只描述"服务端会发什么"，绝不实现策略判断。
 */

export const DATASOURCE_ENGINES = ["mysql", "postgresql"] as const;
export type DatasourceEngine = (typeof DATASOURCE_ENGINES)[number];

export const DATASOURCE_STATUSES = ["active", "disabled", "unhealthy"] as const;
export type DatasourceStatus = (typeof DATASOURCE_STATUSES)[number];

export const COLUMN_SENSITIVITIES = ["standard", "sensitive", "pii"] as const;
export type ColumnSensitivity = (typeof COLUMN_SENSITIVITIES)[number];

export const COLUMN_ACCESSES = ["allow", "deny"] as const;
export type ColumnAccess = (typeof COLUMN_ACCESSES)[number];

export const METRIC_STATUSES = ["draft", "active", "retired"] as const;
export type MetricStatus = (typeof METRIC_STATUSES)[number];

export const QUERY_AUDIT_PHASES = [
  "policy",
  "authorization",
  "plan",
  "execute",
] as const;
export type QueryAuditPhase = (typeof QUERY_AUDIT_PHASES)[number];

export const QUERY_AUDIT_STATUSES = ["started", "completed"] as const;
export type QueryAuditStatus = (typeof QUERY_AUDIT_STATUSES)[number];

export const QUERY_RISKS = ["low", "medium", "high", "blocked"] as const;
export type QueryRisk = (typeof QUERY_RISKS)[number];

/** 报告索引 V1 只有"已登记"一种状态。 */
export const REPORT_STATUSES = ["published"] as const;
export type ReportStatus = (typeof REPORT_STATUSES)[number];

export const ANALYSIS_STAGES = [
  "workflow",
  "catalog",
  "sql",
  "authorization",
  "execution",
  "data",
  "writer",
  "reviewer",
  "publish",
] as const;
export type AnalysisStage = (typeof ANALYSIS_STAGES)[number];

export const ANALYSIS_STAGE_STATUSES = [
  "running",
  "succeeded",
  "failed",
  "blocked",
  "cancelled",
] as const;
export type AnalysisStageStatus = (typeof ANALYSIS_STAGE_STATUSES)[number];

export const ANALYSIS_STAGE_RISKS = [
  "LOW",
  "MEDIUM",
  "HIGH",
  "BLOCKED",
] as const;
export type AnalysisStageRisk = (typeof ANALYSIS_STAGE_RISKS)[number];

export const ANALYSIS_STAGE_CODES = [
  "ok",
  "unavailable",
  "invalid_request",
  "invalid_response",
  "numeric_validation_failed",
  "attempt_limit",
  "input_too_large",
  "policy_denied",
  "cost_limit",
  "query_failed",
  "query_timeout",
  "result_limit_reached",
  "evidence_unavailable",
  "review_rejected",
  "report_conflict",
  "cancelled",
] as const;
export type AnalysisStageCode = (typeof ANALYSIS_STAGE_CODES)[number];

export interface AnalysisStageEvent {
  type: "analysis_stage";
  version: 1;
  run_id: string;
  seq: number;
  stage: AnalysisStage;
  status: AnalysisStageStatus;
  duration_ms?: number;
  row_count?: number;
  byte_count?: number;
  input_tokens?: number;
  output_tokens?: number;
  risk?: AnalysisStageRisk;
  cached?: boolean;
  code?: AnalysisStageCode;
  evidence_ids?: string[];
}

export interface AnalysisStreamMetadata {
  thread_id: string;
  run_id: string;
}

export type AnalysisObservedRunStatus =
  | "pending"
  | "running"
  | "error"
  | "success"
  | "timeout"
  | "interrupted";

/**
 * 服务端稳定错误码。它们只用于把 HTTP 结果翻译成本地化文案，
 * **不能**被当成授权结论使用——真正的授权边界始终是服务器。
 */
export const ANALYTICS_ERROR_CODES = [
  "invalid_analytics_request",
  "analytics_not_found",
  "analytics_version_conflict",
  "analytics_unavailable",
  "analytics_storage_unavailable",
] as const;
export type AnalyticsErrorCode = (typeof ANALYTICS_ERROR_CODES)[number];

/** 目录（普通用户只读）。 */
export interface DatasourceView {
  id: string;
  name: string;
  engine: DatasourceEngine;
  default_schema: string | null;
  status: DatasourceStatus;
}

export interface MetricView {
  key: string;
  name: string;
  description: string;
  expression: string;
  dimensions: string[];
  version: number;
  status: MetricStatus;
}

/** 管理员数据源视图：`secret_ref` 是 opaque reference，前端不解析、不探测。 */
export interface AdminDatasourceView extends DatasourceView {
  owner_id: string;
  secret_ref: string;
}

export interface ColumnSchemaView {
  name: string;
  data_type: string;
  sensitivity: ColumnSensitivity;
}

export interface RelationSchemaView {
  name: string;
  schema: string;
  catalog: string | null;
  columns: ColumnSchemaView[];
}

export interface SchemaSnapshotView {
  datasource_id: string;
  engine: DatasourceEngine;
  version: string;
  default_schema: string;
  relations: RelationSchemaView[];
}

export interface ColumnAccessRuleView {
  name: string;
  access: ColumnAccess;
}

export interface RelationAccessRuleView {
  name: string;
  schema: string;
  catalog: string | null;
  columns: ColumnAccessRuleView[];
}

export interface AccessPolicyView {
  datasource_id: string;
  principal_id: string;
  version: string;
  relations: RelationAccessRuleView[];
  allowed_functions: string[];
}

export interface QueryAuditView {
  id: string;
  principal_id: string;
  datasource_id: string | null;
  phase: QueryAuditPhase;
  status: QueryAuditStatus;
  query_hash: string | null;
  risk: QueryRisk | null;
  decision_code: string | null;
  schema_version: string | null;
  policy_version: string | null;
  estimated_rows: number | null;
  /** 十进制精确值：服务端以字符串发出，前端不做浮点运算。 */
  engine_cost: string | null;
  plan_digest: string | null;
  row_count: number | null;
  byte_count: number | null;
  truncated: boolean | null;
  latency_ms: number | null;
  started_at: string;
  finished_at: string | null;
}

export interface AnalysisReportView {
  id: string;
  principal_id: string;
  thread_id: string;
  run_id: string;
  artifact_path: string;
  title: string;
  status: ReportStatus;
  evidence_ids: string[];
  created_at: string;
}

/**
 * keyset 游标。两个字段要么都有、要么都没有：只用其一无法表达"严格更早"，
 * 服务端会直接 422。前端因此不允许把它改成 offset。
 */
export interface AuditCursor {
  started_at: string;
  id: string;
}

export interface ReportCursor {
  created_at: string;
  id: string;
}

/** 写请求。字段与服务端 DTO 一一对应，没有任何身份/授权/限额字段位。 */
export interface DatasourceCreateRequest {
  name: string;
  engine: DatasourceEngine;
  secret_ref: string;
  default_schema: string | null;
}

export interface DatasourceUpdateRequest {
  name: string;
  secret_ref: string;
  default_schema: string | null;
  status: DatasourceStatus;
}

export interface SchemaSnapshotRequest {
  version: string;
  expected_version: string | null;
  default_schema: string;
  relations: RelationSchemaView[];
}

export interface AccessPolicyRequest {
  version: string;
  expected_version: string | null;
  relations: RelationAccessRuleView[];
  allowed_functions: string[];
}

export interface MetricCreateRequest {
  key: string;
  name: string;
  description: string;
  expression: string;
  dimensions: string[];
  version: number;
  status: MetricStatus;
}

export interface MetricUpdateRequest {
  name: string;
  description: string;
  expression: string;
  dimensions: string[];
  version: number;
  status: MetricStatus;
}
