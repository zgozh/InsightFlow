import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";

rs.mock("@/core/analytics/api", () => ({
  listDatasources: rs.fn(),
  listMetrics: rs.fn(),
  listAudits: rs.fn(),
  listReports: rs.fn(),
  adminCreateMetric: rs.fn(),
  adminListMetricGrants: rs.fn(),
  adminGrantMetric: rs.fn(),
  adminRevokeMetric: rs.fn(),
  adminListDatasources: rs.fn(),
}));

rs.mock("@/core/auth/AuthProvider", () => ({
  useAuth: rs.fn(),
}));

import {
  adminCreateMetric,
  adminGrantMetric,
  adminListMetricGrants,
  adminRevokeMetric,
  listAudits,
  listDatasources,
  listReports,
} from "@/core/analytics/api";
import {
  ANALYTICS_QUERY_ROOT,
  analyticsKeys,
  useAdminMetricGrants,
  useAnalysisReports,
  useAnalyticsDatasources,
  useAnalyticsIsAdmin,
  useAuditHistory,
  useCreateMetric,
  useGrantMetric,
  useRevokeMetric,
} from "@/core/analytics/hooks";
import { useAuth } from "@/core/auth/AuthProvider";

const mockedListDatasources = rs.mocked(listDatasources);
const mockedListAudits = rs.mocked(listAudits);
const mockedListReports = rs.mocked(listReports);
const mockedCreateMetric = rs.mocked(adminCreateMetric);
const mockedListMetricGrants = rs.mocked(adminListMetricGrants);
const mockedGrantMetric = rs.mocked(adminGrantMetric);
const mockedRevokeMetric = rs.mocked(adminRevokeMetric);
const mockedUseAuth = rs.mocked(useAuth);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { queryClient, wrapper };
}

const DIGEST = "a".repeat(64);

/** 完整的审计行：mock 的返回类型就是真实返回类型，不能只造一个 `{id}`。 */
function auditRow(id: string) {
  return {
    id,
    principal_id: "user-1",
    datasource_id: "ds-1",
    phase: "plan" as const,
    status: "completed" as const,
    query_hash: DIGEST,
    risk: "low" as const,
    decision_code: "plan_created",
    schema_version: "s1",
    policy_version: "p1",
    estimated_rows: 10,
    engine_cost: "12.5",
    plan_digest: DIGEST,
    row_count: 3,
    byte_count: 128,
    truncated: false,
    latency_ms: 42,
    started_at: "2026-09-22T12:00:00+00:00",
    finished_at: "2026-09-22T12:00:00.042000+00:00",
  };
}

function auditPage(
  ids: string[],
  hasMore = false,
  nextId: string | null = null,
) {
  return {
    audits: ids.map(auditRow),
    has_more: hasMore,
    next_before_started_at: hasMore ? "2026-09-22T12:00:00+00:00" : null,
    next_before_id: nextId,
  };
}

describe("analytics hooks", () => {
  beforeEach(() => {
    mockedUseAuth.mockReturnValue({ user: { system_role: "admin" } } as never);
  });

  afterEach(() => {
    cleanup();
    rs.resetAllMocks();
  });

  it("roots every query key at analytics", () => {
    expect(analyticsKeys.root).toEqual([ANALYTICS_QUERY_ROOT]);
    for (const key of [
      analyticsKeys.datasources(),
      analyticsKeys.metrics(),
      analyticsKeys.auditPages(20),
      analyticsKeys.reportPages(20),
      analyticsKeys.adminDatasources(),
      analyticsKeys.adminMetrics(),
      analyticsKeys.adminMetricGrants("revenue"),
      analyticsKeys.adminSchema("ds-1"),
      analyticsKeys.adminPolicy("ds-1", "user-1"),
    ]) {
      expect(key[0]).toBe(ANALYTICS_QUERY_ROOT);
    }
  });

  it("keeps sensitive values out of the audit query keys", () => {
    // keyset 游标由 pageParam 承载，因此 key 里只有页码大小；这既避免重复缓存，
    // 也保证任何 SQL／token 都不可能出现在 key 中。
    for (const key of analyticsKeys.auditPages(20)) {
      expect(typeof key === "string" ? key : JSON.stringify(key)).not.toContain(
        "SELECT",
      );
      expect(JSON.stringify(key)).not.toContain("secret");
      expect(JSON.stringify(key)).not.toContain("token");
    }
  });

  it("loads the datasource catalogue", async () => {
    mockedListDatasources.mockResolvedValue([
      {
        id: "ds-1",
        name: "Warehouse",
        engine: "postgresql",
        default_schema: "public",
        status: "active",
      },
    ]);

    const { result } = renderHook(() => useAnalyticsDatasources(), {
      wrapper: createWrapper().wrapper,
    });

    await waitFor(() => expect(result.current.datasources).toHaveLength(1));
    expect(result.current.isError).toBe(false);
  });

  it("walks the audit keyset one page at a time and dedupes by id", async () => {
    mockedListAudits
      .mockResolvedValueOnce(auditPage(["a", "b"], true, "b"))
      .mockResolvedValueOnce(auditPage(["b", "c"], false));

    const { result } = renderHook(() => useAuditHistory({ limit: 2 }), {
      wrapper: createWrapper().wrapper,
    });

    await waitFor(() => expect(result.current.audits).toHaveLength(2));
    expect(result.current.hasMore).toBe(true);

    await result.current.loadMore();

    await waitFor(() => expect(result.current.audits).toHaveLength(3));
    expect(result.current.audits.map((record) => record.id)).toEqual([
      "a",
      "b",
      "c",
    ]);
    expect(mockedListAudits).toHaveBeenLastCalledWith({
      limit: 2,
      cursor: { started_at: "2026-09-22T12:00:00+00:00", id: "b" },
    });
  });

  it("does not silently replay loaded report pages on window focus", async () => {
    mockedListReports.mockResolvedValue({
      reports: [],
      has_more: false,
      next_before_created_at: null,
      next_before_id: null,
    });

    const { result } = renderHook(() => useAnalysisReports({ limit: 20 }), {
      wrapper: createWrapper().wrapper,
    });

    await waitFor(() => expect(mockedListReports).toHaveBeenCalledTimes(1));
    expect(result.current.reports).toEqual([]);
  });

  it("invalidates only the affected analytics keys after a metric mutation", async () => {
    mockedCreateMetric.mockResolvedValue({
      key: "revenue",
      name: "Revenue",
      description: "Total revenue",
      expression: "sum(amount)",
      dimensions: [],
      version: 2,
      status: "active",
    });

    const { queryClient, wrapper } = createWrapper();
    const invalidate = rs.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useCreateMetric(), { wrapper });

    await result.current.mutateAsync({
      key: "revenue",
      name: "Revenue",
      description: "Total revenue",
      expression: "sum(amount)",
      dimensions: [],
      version: 2,
      status: "active",
    });

    const invalidated = invalidate.mock.calls.map((call) => call[0]?.queryKey);
    expect(invalidated).toEqual([
      analyticsKeys.adminMetrics(),
      analyticsKeys.metrics(),
    ]);
    // 绝不整树失效：那会让无关的目录与历史读取一起重放。
    expect(invalidated).not.toContainEqual(analyticsKeys.root);
  });

  it("does not request metric grants while the panel is closed", () => {
    const { result } = renderHook(
      () => useAdminMetricGrants("revenue", false),
      { wrapper: createWrapper().wrapper },
    );

    expect(result.current.principalIds).toEqual([]);
    expect(mockedListMetricGrants).not.toHaveBeenCalled();
  });

  it("invalidates only the submitted metric grants and public metric directory", async () => {
    mockedGrantMetric.mockResolvedValue({
      principal_id: "user-1",
      granted: true,
    });
    mockedRevokeMetric.mockResolvedValue({ removed: true });
    const { queryClient, wrapper } = createWrapper();
    const invalidate = rs.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(
      () => ({ grant: useGrantMetric(), revoke: useRevokeMetric() }),
      { wrapper },
    );

    await result.current.grant.mutateAsync({
      metricKey: "revenue",
      principalId: "user-1",
    });
    await result.current.revoke.mutateAsync({
      metricKey: "margin",
      principalId: "user-2",
    });

    expect(invalidate.mock.calls.map((call) => call[0])).toEqual([
      { queryKey: analyticsKeys.adminMetricGrants("revenue"), exact: true },
      { queryKey: analyticsKeys.metrics(), exact: true },
      { queryKey: analyticsKeys.adminMetricGrants("margin"), exact: true },
      { queryKey: analyticsKeys.metrics(), exact: true },
    ]);
  });

  it("exposes the server error on admin reads so a 403 is distinguishable from a 500", async () => {
    const { adminListDatasources } = await import("@/core/analytics/api");
    const { useAdminDatasources } = await import("@/core/analytics/hooks");
    rs.mocked(adminListDatasources).mockRejectedValue(
      Object.assign(new Error("forbidden"), { status: 403 }),
    );

    const { result } = renderHook(() => useAdminDatasources(true), {
      wrapper: createWrapper().wrapper,
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    // 只有拿到 status 才能把服务端 403 渲染成"禁止访问"，而不是与 500 一起退化成通用失败。
    expect((result.current.error as { status?: number } | null)?.status).toBe(
      403,
    );
  });

  it("treats only the admin role as an administrator", () => {
    mockedUseAuth.mockReturnValue({ user: { system_role: "user" } } as never);
    const { result, rerender } = renderHook(() => useAnalyticsIsAdmin(), {
      wrapper: createWrapper().wrapper,
    });
    expect(result.current).toBe(false);

    mockedUseAuth.mockReturnValue({ user: { system_role: "admin" } } as never);
    rerender();
    expect(result.current).toBe(true);
  });
});
