/**
 * Analytics 查询与变更 hooks（Phase 4 §5）。
 *
 * 设计约束：
 *
 * - 所有 query key 以 `analytics` 为根，且**只**含标识符、分页游标与页码等非敏感值；
 *   SQL、plan token、凭据、DSN、结果行永不进入 key（它们也永远不会进入这个模块）。
 * - 变更成功后只失效**受影响的精确 key**，不做一次性全量失效。
 * - 分页严格沿用服务端的 keyset 游标：页面只持有 `before_started_at` + `before_id`
 *   （审计）或 `before_created_at` + `before_id`（报告），绝不改成 offset 猜测。
 * - 管理员 UI 只是体验门禁：隐藏按钮不等于授权，服务器 403 仍是最终边界。
 */

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { useAuth } from "@/core/auth/AuthProvider";

import {
  adminCreateDatasource,
  adminCreateMetric,
  adminGetDatasource,
  adminGetPolicy,
  adminGetSchema,
  adminListAudits,
  adminListDatasources,
  adminListMetrics,
  adminListReports,
  adminRemovePolicy,
  adminReplacePolicy,
  adminReplaceSchema,
  adminRetireMetric,
  adminUpdateDatasource,
  adminUpdateMetric,
  listAudits,
  listDatasources,
  listMetrics,
  listReports,
} from "./api";
import type { AuditCursor, ReportCursor } from "./types";

export const ANALYTICS_QUERY_ROOT = "analytics" as const;

/** 服务端默认分页大小是 50；前端按 20 请求以缩短首屏。 */
export const ANALYTICS_PAGE_SIZE = 20;

export const analyticsKeys = {
  root: [ANALYTICS_QUERY_ROOT] as const,
  datasources: () => [ANALYTICS_QUERY_ROOT, "datasources"] as const,
  metrics: () => [ANALYTICS_QUERY_ROOT, "metrics"] as const,
  // keyset 分页用 `useInfiniteQuery`：游标由 pageParam 承载，因此不进 key。
  auditPages: (limit: number) =>
    [ANALYTICS_QUERY_ROOT, "audits", limit] as const,
  reportPages: (limit: number) =>
    [ANALYTICS_QUERY_ROOT, "reports", limit] as const,
  adminDatasources: () =>
    [ANALYTICS_QUERY_ROOT, "admin", "datasources"] as const,
  adminDatasource: (datasourceId: string) =>
    [ANALYTICS_QUERY_ROOT, "admin", "datasources", datasourceId] as const,
  adminSchema: (datasourceId: string) =>
    [
      ANALYTICS_QUERY_ROOT,
      "admin",
      "datasources",
      datasourceId,
      "schema",
    ] as const,
  adminPolicy: (datasourceId: string, principalId: string) =>
    [
      ANALYTICS_QUERY_ROOT,
      "admin",
      "datasources",
      datasourceId,
      "policies",
      principalId,
    ] as const,
  adminMetrics: () => [ANALYTICS_QUERY_ROOT, "admin", "metrics"] as const,
  adminAudits: (principalId: string) =>
    [ANALYTICS_QUERY_ROOT, "admin", "audits", principalId] as const,
  adminReports: (principalId: string) =>
    [ANALYTICS_QUERY_ROOT, "admin", "reports", principalId] as const,
};

/** 管理员身份只用于隐藏/禁用入口；真正的授权判断在服务器。 */
export function useAnalyticsIsAdmin(): boolean {
  const { user } = useAuth();
  return user?.system_role === "admin";
}

// --- 目录 -------------------------------------------------------------------

export function useAnalyticsDatasources() {
  const query = useQuery({
    queryKey: analyticsKeys.datasources(),
    queryFn: listDatasources,
  });
  return {
    datasources: query.data ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
}

export function useAnalyticsMetrics() {
  const query = useQuery({
    queryKey: analyticsKeys.metrics(),
    queryFn: listMetrics,
  });
  return {
    metrics: query.data ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
}

// --- keyset 分页（纯函数 + useInfiniteQuery 薄封装） ------------------------

/** 合并一页新数据；`reset` 为真时丢弃已累积内容，用于"刷新后重试"。 */
export function mergeAuditPage<T extends { id: string }>(
  existing: T[],
  page: T[],
  reset: boolean,
): T[] {
  if (reset) return [...page];
  const seen = new Set(existing.map((record) => record.id));
  return [...existing, ...page.filter((record) => !seen.has(record.id))];
}

/** 把已加载的页展平成一条列表，并按 `id` 去重（服务端 keyset 理论上不会重复）。 */
export function flattenPages<TPage, TItem extends { id: string }>(
  pages: TPage[] | undefined,
  select: (page: TPage) => TItem[],
): TItem[] {
  const merged: TItem[] = [];
  const seen = new Set<string>();
  for (const page of pages ?? []) {
    for (const item of select(page)) {
      if (seen.has(item.id)) continue;
      seen.add(item.id);
      merged.push(item);
    }
  }
  return merged;
}

/**
 * 下一个游标；返回 `null` 表示"没有下一页"。
 *
 * 调用方必须把 `null` 转成 `undefined` 再交给 TanStack Query：`getNextPageParam` 返回
 * `null` 会被当成"下一页的 pageParam 是 null"，也就是第一页，从而无限循环。
 */
export function nextAuditCursor(page: {
  has_more: boolean;
  next_before_started_at: string | null;
  next_before_id: string | null;
}): AuditCursor | null {
  if (!page.has_more || !page.next_before_started_at || !page.next_before_id) {
    return null;
  }
  return { started_at: page.next_before_started_at, id: page.next_before_id };
}

export function nextReportCursor(page: {
  has_more: boolean;
  next_before_created_at: string | null;
  next_before_id: string | null;
}): ReportCursor | null {
  if (!page.has_more || !page.next_before_created_at || !page.next_before_id) {
    return null;
  }
  return { created_at: page.next_before_created_at, id: page.next_before_id };
}

export function useAuditHistory(options: { limit?: number } = {}) {
  const limit = options.limit ?? ANALYTICS_PAGE_SIZE;
  const query = useInfiniteQuery({
    queryKey: analyticsKeys.auditPages(limit),
    queryFn: ({ pageParam }) =>
      listAudits({ limit, cursor: pageParam ?? undefined }),
    initialPageParam: null as AuditCursor | null,
    getNextPageParam: (lastPage) => nextAuditCursor(lastPage) ?? undefined,
    // 审计历史是持续追加的敏感读：只按用户显式操作刷新，不在聚焦/重连时静默重放已加载页。
    refetchOnWindowFocus: false,
  });
  return {
    audits: flattenPages(query.data?.pages, (page) => page.audits),
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    isFetching: query.isFetching,
    hasMore: query.hasNextPage,
    loadMore: query.fetchNextPage,
    refresh: query.refetch,
  };
}

export function useAnalysisReports(options: { limit?: number } = {}) {
  const limit = options.limit ?? ANALYTICS_PAGE_SIZE;
  const query = useInfiniteQuery({
    queryKey: analyticsKeys.reportPages(limit),
    queryFn: ({ pageParam }) =>
      listReports({ limit, cursor: pageParam ?? undefined }),
    initialPageParam: null as ReportCursor | null,
    getNextPageParam: (lastPage) => nextReportCursor(lastPage) ?? undefined,
    refetchOnWindowFocus: false,
  });
  return {
    reports: flattenPages(query.data?.pages, (page) => page.reports),
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    isFetching: query.isFetching,
    hasMore: query.hasNextPage,
    loadMore: query.fetchNextPage,
    refresh: query.refetch,
  };
}

// --- 管理员：数据源 ---------------------------------------------------------
//
// 管理员查询同样暴露 `error`：只有拿到 `AnalyticsRequestError.status` 才能把服务端的 403
// 渲染成"禁止访问"，而不是与 500 一起退化成通用"加载失败"。管理员标记本身只是入口门禁，
// 不足以判断授权结果。

export function useAdminDatasources(enabled: boolean) {
  const query = useQuery({
    queryKey: analyticsKeys.adminDatasources(),
    queryFn: adminListDatasources,
    enabled,
  });
  return {
    datasources: query.data ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
}

export function useAdminDatasource(
  datasourceId: string | null,
  enabled: boolean,
) {
  const query = useQuery({
    queryKey: analyticsKeys.adminDatasource(datasourceId ?? ""),
    queryFn: () => adminGetDatasource(datasourceId!),
    enabled: enabled && datasourceId !== null,
  });
  return {
    datasource: query.data ?? null,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
  };
}

export function useAdminSchema(datasourceId: string | null, enabled: boolean) {
  const query = useQuery({
    queryKey: analyticsKeys.adminSchema(datasourceId ?? ""),
    queryFn: () => adminGetSchema(datasourceId!),
    enabled: enabled && datasourceId !== null,
  });
  return {
    schema: query.data ?? null,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
}

export function useAdminPolicy(
  datasourceId: string | null,
  principalId: string | null,
  enabled: boolean,
) {
  const query = useQuery({
    queryKey: analyticsKeys.adminPolicy(datasourceId ?? "", principalId ?? ""),
    queryFn: () => adminGetPolicy(datasourceId!, principalId!),
    enabled: enabled && datasourceId !== null && principalId !== null,
    retry: false,
  });
  return {
    policy: query.data ?? null,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
}

export function useCreateDatasource() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: adminCreateDatasource,
    onSuccess: () => {
      void client.invalidateQueries({
        queryKey: analyticsKeys.adminDatasources(),
      });
      void client.invalidateQueries({ queryKey: analyticsKeys.datasources() });
    },
  });
}

export function useUpdateDatasource() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (variables: {
      datasourceId: string;
      request: Parameters<typeof adminUpdateDatasource>[1];
    }) => adminUpdateDatasource(variables.datasourceId, variables.request),
    onSuccess: (_data, variables) => {
      void client.invalidateQueries({
        queryKey: analyticsKeys.adminDatasources(),
      });
      void client.invalidateQueries({
        queryKey: analyticsKeys.adminDatasource(variables.datasourceId),
      });
      void client.invalidateQueries({ queryKey: analyticsKeys.datasources() });
    },
  });
}

export function useReplaceSchema() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (variables: {
      datasourceId: string;
      request: Parameters<typeof adminReplaceSchema>[1];
    }) => adminReplaceSchema(variables.datasourceId, variables.request),
    onSuccess: (_data, variables) => {
      void client.invalidateQueries({
        queryKey: analyticsKeys.adminSchema(variables.datasourceId),
      });
    },
  });
}

export function useReplacePolicy() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (variables: {
      datasourceId: string;
      principalId: string;
      request: Parameters<typeof adminReplacePolicy>[2];
    }) =>
      adminReplacePolicy(
        variables.datasourceId,
        variables.principalId,
        variables.request,
      ),
    onSuccess: (_data, variables) => {
      void client.invalidateQueries({
        queryKey: analyticsKeys.adminPolicy(
          variables.datasourceId,
          variables.principalId,
        ),
      });
    },
  });
}

export function useRemovePolicy() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (variables: { datasourceId: string; principalId: string }) =>
      adminRemovePolicy(variables.datasourceId, variables.principalId),
    onSuccess: (_data, variables) => {
      void client.invalidateQueries({
        queryKey: analyticsKeys.adminPolicy(
          variables.datasourceId,
          variables.principalId,
        ),
      });
    },
  });
}

// --- 管理员：指标 -----------------------------------------------------------

export function useAdminMetrics(enabled: boolean) {
  const query = useQuery({
    queryKey: analyticsKeys.adminMetrics(),
    queryFn: adminListMetrics,
    enabled,
  });
  return {
    metrics: query.data ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
}

export function useCreateMetric() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: adminCreateMetric,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: analyticsKeys.adminMetrics() });
      void client.invalidateQueries({ queryKey: analyticsKeys.metrics() });
    },
  });
}

export function useUpdateMetric() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (variables: {
      metricKey: string;
      request: Parameters<typeof adminUpdateMetric>[1];
    }) => adminUpdateMetric(variables.metricKey, variables.request),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: analyticsKeys.adminMetrics() });
      void client.invalidateQueries({ queryKey: analyticsKeys.metrics() });
    },
  });
}

export function useRetireMetric() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (metricKey: string) => adminRetireMetric(metricKey),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: analyticsKeys.adminMetrics() });
      void client.invalidateQueries({ queryKey: analyticsKeys.metrics() });
    },
  });
}

export function useAdminReportLookup(principalId: string | null) {
  const query = useQuery({
    queryKey: analyticsKeys.adminReports(principalId ?? ""),
    queryFn: () => adminListReports(principalId!, { limit: 1 }),
    enabled: principalId !== null && principalId.length > 0,
    retry: false,
  });
  return {
    reports: query.data?.reports ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
  };
}

export function useAdminAuditLookup(principalId: string | null) {
  const query = useQuery({
    queryKey: analyticsKeys.adminAudits(principalId ?? ""),
    queryFn: () => adminListAudits(principalId!, { limit: 1 }),
    enabled: principalId !== null && principalId.length > 0,
    retry: false,
  });
  return {
    audits: query.data?.audits ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
  };
}
