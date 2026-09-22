/**
 * Analytics HTTP 客户端（Phase 4 §5）。
 *
 * 两条不可让步的规则：
 *
 * 1. 所有请求都走 `@/core/api/fetcher` 的认证 fetcher——它自动带上 cookie 凭证，并在
 *    POST/PUT/DELETE/PATCH 上继承 CSRF 双提交头。这里**绝不**直接调用 `globalThis.fetch`。
 * 2. 所有响应都经 Zod 严格解析；解析失败给稳定的通用错误，绝不把未知 payload 交给 UI。
 *
 * 另外三条自我约束：
 *
 * - 错误对象只携带 HTTP 状态与**稳定错误码**，不携带响应体、URL 查询串或服务端 detail 文本；
 * - 函数签名里没有任何"由调用方指定 principal/owner/limit"的参数——身份与限额都由服务端决定
 *   （管理员端点显式要求 `principal_id`，这是唯一例外，且它走 admin 路由依赖）；
 * - 不做本地策略判断：`403` 就是 `403`，不由前端推断"我应该有权限"。
 */

import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

import {
  accessPolicyViewSchema,
  adminDatasourceListSchema,
  adminDatasourceViewSchema,
  analysisReportPageSchema,
  analyticsErrorBodySchema,
  type AccessPolicyViewParsed,
  type AdminDatasourceViewParsed,
  type AnalysisReportPageParsed,
  assertCursorPairing,
  type DatasourceViewParsed,
  datasourceListSchema,
  metricListSchema,
  metricViewSchema,
  type MetricViewParsed,
  parseExternal,
  queryAuditPageSchema,
  type QueryAuditPageParsed,
  schemaSnapshotViewSchema,
  type SchemaSnapshotViewParsed,
} from "./schemas";
import type {
  AccessPolicyRequest,
  AuditCursor,
  DatasourceCreateRequest,
  DatasourceUpdateRequest,
  MetricCreateRequest,
  MetricUpdateRequest,
  ReportCursor,
  SchemaSnapshotRequest,
} from "./types";

/** 请求失败：只暴露状态码与稳定错误码。 */
export class AnalyticsRequestError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(status: number, code: string | null) {
    super(code ?? `analytics_http_${status}`);
    this.name = "AnalyticsRequestError";
    this.status = status;
    this.code = code;
  }
}

const BASE = "/api/analytics";

function url(
  path: string,
  params?: Record<string, string | number | null | undefined>,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value === null || value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const suffix = search.toString();
  return `${getBackendBaseURL()}${BASE}${path}${suffix ? `?${suffix}` : ""}`;
}

/** 提取稳定错误码；识别不出来时返回 null，绝不回传服务端文本。 */
async function readErrorCode(response: Response): Promise<string | null> {
  try {
    const parsed = analyticsErrorBodySchema.safeParse(await response.json());
    return parsed.success ? parsed.data.detail.code : null;
  } catch {
    return null;
  }
}

async function ensureOk(response: Response): Promise<void> {
  if (response.ok) return;
  throw new AnalyticsRequestError(
    response.status,
    await readErrorCode(response),
  );
}

async function readJson(response: Response): Promise<unknown> {
  await ensureOk(response);
  try {
    return await response.json();
  } catch {
    throw new AnalyticsRequestError(
      response.status,
      "invalid_analytics_response",
    );
  }
}

function jsonInit(method: "POST" | "PUT", body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

function auditParams(
  limit: number | undefined,
  cursor: AuditCursor | undefined,
) {
  return {
    limit,
    before_started_at: cursor?.started_at,
    before_id: cursor?.id,
  };
}

function reportParams(
  limit: number | undefined,
  cursor: ReportCursor | undefined,
) {
  return {
    limit,
    before_created_at: cursor?.created_at,
    before_id: cursor?.id,
  };
}

// --- 目录（普通用户只读） ---------------------------------------------------

export async function listDatasources(): Promise<DatasourceViewParsed[]> {
  const payload = await readJson(await fetch(url("/datasources")));
  return parseExternal(datasourceListSchema, payload).datasources;
}

export async function listMetrics(): Promise<MetricViewParsed[]> {
  const payload = await readJson(await fetch(url("/metrics")));
  return parseExternal(metricListSchema, payload).metrics;
}

export async function listAudits(
  options: {
    limit?: number;
    cursor?: AuditCursor;
  } = {},
): Promise<QueryAuditPageParsed> {
  const payload = await readJson(
    await fetch(url("/audits", auditParams(options.limit, options.cursor))),
  );
  const page = parseExternal(queryAuditPageSchema, payload);
  assertCursorPairing(page);
  return page;
}

export async function listReports(
  options: {
    limit?: number;
    cursor?: ReportCursor;
  } = {},
): Promise<AnalysisReportPageParsed> {
  const payload = await readJson(
    await fetch(url("/reports", reportParams(options.limit, options.cursor))),
  );
  const page = parseExternal(analysisReportPageSchema, payload);
  assertCursorPairing(page);
  return page;
}

// --- 管理员：数据源 / schema / policy --------------------------------------

export async function adminListDatasources(): Promise<
  AdminDatasourceViewParsed[]
> {
  const payload = await readJson(await fetch(url("/admin/datasources")));
  return parseExternal(adminDatasourceListSchema, payload).datasources;
}

export async function adminGetDatasource(
  datasourceId: string,
): Promise<AdminDatasourceViewParsed> {
  const payload = await readJson(
    await fetch(url(`/admin/datasources/${encodeURIComponent(datasourceId)}`)),
  );
  return parseExternal(adminDatasourceViewSchema, payload);
}

export async function adminCreateDatasource(
  request: DatasourceCreateRequest,
): Promise<AdminDatasourceViewParsed> {
  const payload = await readJson(
    await fetch(url("/admin/datasources"), jsonInit("POST", request)),
  );
  return parseExternal(adminDatasourceViewSchema, payload);
}

/** engine 创建后不可变更，因此更新请求里没有这个字段位。 */
export async function adminUpdateDatasource(
  datasourceId: string,
  request: DatasourceUpdateRequest,
): Promise<AdminDatasourceViewParsed> {
  const payload = await readJson(
    await fetch(
      url(`/admin/datasources/${encodeURIComponent(datasourceId)}`),
      jsonInit("PUT", request),
    ),
  );
  return parseExternal(adminDatasourceViewSchema, payload);
}

export async function adminGetSchema(
  datasourceId: string,
): Promise<SchemaSnapshotViewParsed> {
  const payload = await readJson(
    await fetch(
      url(`/admin/datasources/${encodeURIComponent(datasourceId)}/schema`),
    ),
  );
  return parseExternal(schemaSnapshotViewSchema, payload);
}

export async function adminReplaceSchema(
  datasourceId: string,
  request: SchemaSnapshotRequest,
): Promise<SchemaSnapshotViewParsed> {
  const payload = await readJson(
    await fetch(
      url(`/admin/datasources/${encodeURIComponent(datasourceId)}/schema`),
      jsonInit("PUT", request),
    ),
  );
  return parseExternal(schemaSnapshotViewSchema, payload);
}

export async function adminGetPolicy(
  datasourceId: string,
  principalId: string,
): Promise<AccessPolicyViewParsed> {
  const payload = await readJson(
    await fetch(
      url(
        `/admin/datasources/${encodeURIComponent(datasourceId)}/policies/${encodeURIComponent(principalId)}`,
      ),
    ),
  );
  return parseExternal(accessPolicyViewSchema, payload);
}

export async function adminReplacePolicy(
  datasourceId: string,
  principalId: string,
  request: AccessPolicyRequest,
): Promise<AccessPolicyViewParsed> {
  const payload = await readJson(
    await fetch(
      url(
        `/admin/datasources/${encodeURIComponent(datasourceId)}/policies/${encodeURIComponent(principalId)}`,
      ),
      jsonInit("PUT", request),
    ),
  );
  return parseExternal(accessPolicyViewSchema, payload);
}

export async function adminRemovePolicy(
  datasourceId: string,
  principalId: string,
): Promise<void> {
  const response = await fetch(
    url(
      `/admin/datasources/${encodeURIComponent(datasourceId)}/policies/${encodeURIComponent(principalId)}`,
    ),
    { method: "DELETE" },
  );
  await ensureOk(response);
}

// --- 管理员：指标 -----------------------------------------------------------

export async function adminListMetrics(): Promise<MetricViewParsed[]> {
  const payload = await readJson(await fetch(url("/admin/metrics")));
  return parseExternal(metricListSchema, payload).metrics;
}

export async function adminCreateMetric(
  request: MetricCreateRequest,
): Promise<MetricViewParsed> {
  const payload = await readJson(
    await fetch(url("/admin/metrics"), jsonInit("POST", request)),
  );
  return parseExternal(metricViewSchema, payload);
}

export async function adminUpdateMetric(
  metricKey: string,
  request: MetricUpdateRequest,
): Promise<MetricViewParsed> {
  const payload = await readJson(
    await fetch(
      url(`/admin/metrics/${encodeURIComponent(metricKey)}`),
      jsonInit("PUT", request),
    ),
  );
  return parseExternal(metricViewSchema, payload);
}

/** 退役不是物理删除：服务端用 DELETE 表达 status 语义。 */
export async function adminRetireMetric(
  metricKey: string,
): Promise<MetricViewParsed> {
  const payload = await readJson(
    await fetch(url(`/admin/metrics/${encodeURIComponent(metricKey)}`), {
      method: "DELETE",
    }),
  );
  return parseExternal(metricViewSchema, payload);
}

export async function adminListAudits(
  principalId: string,
  options: { limit?: number; cursor?: AuditCursor } = {},
): Promise<QueryAuditPageParsed> {
  const payload = await readJson(
    await fetch(
      url("/admin/audits", {
        principal_id: principalId,
        ...auditParams(options.limit, options.cursor),
      }),
    ),
  );
  const page = parseExternal(queryAuditPageSchema, payload);
  assertCursorPairing(page);
  return page;
}

export async function adminListReports(
  principalId: string,
  options: { limit?: number; cursor?: ReportCursor } = {},
): Promise<AnalysisReportPageParsed> {
  const payload = await readJson(
    await fetch(
      url("/admin/reports", {
        principal_id: principalId,
        ...reportParams(options.limit, options.cursor),
      }),
    ),
  );
  const page = parseExternal(analysisReportPageSchema, payload);
  assertCursorPairing(page);
  return page;
}
