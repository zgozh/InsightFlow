import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";

import DatasourcesPage from "@/app/workspace/datasources/page";
import HistoryPage from "@/app/workspace/history/page";
import MetricsPage from "@/app/workspace/metrics/page";
import ReportsPage from "@/app/workspace/reports/page";
import { AnalyticsRequestError } from "@/core/analytics/api";
import type {
  AdminDatasourceView,
  AnalysisReportView,
  DatasourceView,
  MetricView,
  QueryAuditView,
} from "@/core/analytics/types";
import { DEFAULT_LOCALE, type Locale } from "@/core/i18n";
import { I18nProvider } from "@/core/i18n/context";

/**
 * 页面级测试：钉住四种状态、角色门禁与"不泄漏"边界。
 *
 * 数据层整体替换成受控替身，这样每个断言都只关于页面自己的行为；外壳同理（见下）。
 */
rs.mock("@/components/workspace/workspace-container", () => ({
  WorkspaceContainer: ({ children }: { children?: ReactNode }) => children,
  WorkspaceHeader: () => null,
  WorkspaceBody: ({ children }: { children?: ReactNode }) => children,
}));

const mocks = rs.hoisted(() => ({
  isAdmin: false,
  adminMetricsEnabled: [] as boolean[],
  metricGrantCalls: [] as unknown[][],
  catalogueDatasources: {
    datasources: [] as unknown[],
    isLoading: false,
    isError: false,
    error: null as unknown,
    refetch: rs.fn(),
  },
  adminDatasources: {
    datasources: [] as unknown[],
    isLoading: false,
    isError: false,
    refetch: rs.fn(),
  },
  catalogueMetrics: {
    metrics: [] as unknown[],
    isLoading: false,
    isError: false,
    error: null as unknown,
    refetch: rs.fn(),
  },
  adminMetrics: {
    metrics: [] as unknown[],
    isLoading: false,
    isError: false,
    refetch: rs.fn(),
  },
  auditHistory: {
    audits: [] as unknown[],
    isLoading: false,
    isError: false,
    error: null as unknown,
    isFetching: false,
    hasMore: false,
    loadMore: rs.fn(),
    refresh: rs.fn(),
  },
  reports: {
    reports: [] as unknown[],
    isLoading: false,
    isError: false,
    error: null as unknown,
    isFetching: false,
    hasMore: false,
    loadMore: rs.fn(),
    refresh: rs.fn(),
  },
  adminAuditLookup: {
    audits: [] as unknown[],
    isLoading: false,
    isError: false,
  },
}));

rs.mock("@/core/analytics/hooks", () => ({
  useAnalyticsIsAdmin: () => mocks.isAdmin,
  useAnalyticsDatasources: () => mocks.catalogueDatasources,
  useAdminDatasources: () => mocks.adminDatasources,
  useAnalyticsMetrics: () => mocks.catalogueMetrics,
  useAdminMetrics: (enabled: boolean) => {
    mocks.adminMetricsEnabled.push(enabled);
    return mocks.adminMetrics;
  },
  useAuditHistory: () => mocks.auditHistory,
  useAnalysisReports: () => mocks.reports,
  useAdminAuditLookup: () => mocks.adminAuditLookup,
  // 页面不直接使用这些变更 hook；管理员面板由专门的测试文件覆盖。
  useCreateDatasource: () => ({
    mutate: rs.fn(),
    isPending: false,
    error: null,
  }),
  useUpdateDatasource: () => ({
    mutate: rs.fn(),
    isPending: false,
    error: null,
  }),
  useAdminSchema: () => ({
    schema: null,
    isLoading: false,
    isError: false,
    refetch: rs.fn(),
  }),
  useReplaceSchema: () => ({ mutate: rs.fn(), isPending: false, error: null }),
  useAdminPolicy: () => ({
    policy: null,
    isLoading: false,
    isError: false,
    refetch: rs.fn(),
  }),
  useReplacePolicy: () => ({ mutate: rs.fn(), isPending: false, error: null }),
  useRemovePolicy: () => ({ mutate: rs.fn(), isPending: false, error: null }),
  useCreateMetric: () => ({ mutate: rs.fn(), isPending: false, error: null }),
  useUpdateMetric: () => ({ mutate: rs.fn(), isPending: false, error: null }),
  useRetireMetric: () => ({ mutate: rs.fn(), isPending: false, error: null }),
  useAdminMetricGrants: (metricKey: string, enabled: boolean) => {
    mocks.metricGrantCalls.push([metricKey, enabled]);
    return {
      principalIds: [],
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: rs.fn(),
    };
  },
  useGrantMetric: () => ({ mutate: rs.fn(), isPending: false, reset: rs.fn() }),
  useRevokeMetric: () => ({
    mutate: rs.fn(),
    isPending: false,
    reset: rs.fn(),
  }),
}));

function wrap(node: ReactNode, locale: Locale = DEFAULT_LOCALE) {
  return <I18nProvider initialLocale={locale}>{node}</I18nProvider>;
}

const DIGEST = "c".repeat(64);

function datasourceView(): DatasourceView {
  return {
    id: "ds-1",
    name: "Orders warehouse",
    engine: "postgresql",
    default_schema: "public",
    status: "active",
  };
}

function adminDatasourceView(): AdminDatasourceView {
  return {
    ...datasourceView(),
    owner_id: "user-7",
    secret_ref: "prod-secret-ref",
  };
}

function metricView(): MetricView {
  return {
    key: "revenue",
    name: "Revenue",
    description: "Net revenue",
    expression: "SUM(orders.amount)",
    dimensions: ["country"],
    version: 3,
    status: "active",
  };
}

function auditView(): QueryAuditView {
  return {
    id: "audit-1",
    principal_id: "user-1",
    datasource_id: "ds-1",
    phase: "execute",
    status: "completed",
    query_hash: DIGEST,
    risk: "low",
    decision_code: "executed",
    schema_version: "3",
    policy_version: "7",
    estimated_rows: 120,
    engine_cost: "12.5",
    plan_digest: DIGEST,
    row_count: 100,
    byte_count: 4096,
    truncated: false,
    latency_ms: 42,
    started_at: "2026-01-02T03:04:05Z",
    finished_at: "2026-01-02T03:04:06Z",
  };
}

function reportView(): AnalysisReportView {
  return {
    id: "report-1",
    principal_id: "user-1",
    thread_id: "thread 1/two",
    run_id: "run-1",
    artifact_path: "/mnt/user-data/outputs/revenue.md",
    title: "Revenue review",
    status: "published",
    evidence_ids: [DIGEST],
    created_at: "2026-01-02T03:04:05Z",
  };
}

beforeEach(() => {
  mocks.isAdmin = false;
  mocks.adminMetricsEnabled = [];
  mocks.metricGrantCalls = [];
  Object.assign(mocks.catalogueDatasources, {
    datasources: [],
    isLoading: false,
    isError: false,
    error: null,
    refetch: rs.fn(),
  });
  Object.assign(mocks.adminDatasources, {
    datasources: [],
    isLoading: false,
    isError: false,
    refetch: rs.fn(),
  });
  Object.assign(mocks.catalogueMetrics, {
    metrics: [],
    isLoading: false,
    isError: false,
    error: null,
    refetch: rs.fn(),
  });
  Object.assign(mocks.adminMetrics, {
    metrics: [],
    isLoading: false,
    isError: false,
    refetch: rs.fn(),
  });
  Object.assign(mocks.auditHistory, {
    audits: [],
    isLoading: false,
    isError: false,
    error: null,
    isFetching: false,
    hasMore: false,
    loadMore: rs.fn(),
    refresh: rs.fn(),
  });
  Object.assign(mocks.reports, {
    reports: [],
    isLoading: false,
    isError: false,
    error: null,
    isFetching: false,
    hasMore: false,
    loadMore: rs.fn(),
    refresh: rs.fn(),
  });
  Object.assign(mocks.adminAuditLookup, {
    audits: [],
    isLoading: false,
    isError: false,
  });
});

afterEach(() => {
  cleanup();
  document.cookie = "locale=; max-age=0; path=/";
  rs.restoreAllMocks();
});

describe("/workspace/datasources", () => {
  it("加载状态用 role=status", () => {
    mocks.catalogueDatasources.isLoading = true;
    render(wrap(<DatasourcesPage />));
    expect(screen.getByRole("status").textContent).toBe("Loading…");
  });

  it("错误状态给出 role=alert 与可重试按钮", () => {
    mocks.catalogueDatasources.isError = true;
    mocks.catalogueDatasources.error = new Error("boom");
    render(wrap(<DatasourcesPage />));
    expect(screen.getByRole("alert")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(mocks.catalogueDatasources.refetch).toHaveBeenCalledTimes(1);
  });

  it("普通用户的空目录说明需要管理员登记并授权", () => {
    render(wrap(<DatasourcesPage />));
    expect(screen.getByRole("status").textContent).toBe(
      "No data sources are currently available to your account. Ask an administrator to register a source and grant access.",
    );
  });

  it("管理员的空目录指向数据源、模型与策略配置", () => {
    mocks.isAdmin = true;
    render(wrap(<DatasourcesPage />));
    expect(screen.getByRole("status").textContent).toBe(
      "No data sources are registered yet. Create a source, then configure its schema and access policy.",
    );
    expect(screen.getByTestId("datasource-create-form")).toBeTruthy();
  });

  it("中文普通用户空目录也说明授权前提", () => {
    document.cookie = "locale=zh-CN; path=/; SameSite=Lax";
    render(wrap(<DatasourcesPage />, "zh-CN"));
    expect(screen.getByRole("status").textContent).toBe(
      "当前账号还没有可用的数据源。请联系管理员登记数据源并授予访问权限。",
    );
  });

  it("服务端 403 渲染禁止态，客户端身份不是授权结论", () => {
    mocks.catalogueDatasources.isError = true;
    mocks.catalogueDatasources.error = new AnalyticsRequestError(403, null);
    render(wrap(<DatasourcesPage />));
    expect(document.body.textContent).toContain(
      "The server refused this action (403)",
    );
    // 被拒绝时既不显示目录表，也不显示管理员面板。
    expect(screen.queryByTestId("datasource-engine-select")).toBeNull();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("非管理员看不到 secret_ref 与 owner_id，也没有管理员入口", () => {
    mocks.catalogueDatasources.datasources = [datasourceView()];
    mocks.adminDatasources.datasources = [adminDatasourceView()];
    render(wrap(<DatasourcesPage />));
    const text = document.body.textContent ?? "";
    expect(text).toContain("Orders warehouse");
    expect(text).not.toContain("prod-secret-ref");
    expect(text).not.toContain("user-7");
    expect(screen.queryByTestId("datasource-engine-select")).toBeNull();
    expect(screen.queryByRole("button", { name: /^Edit/ })).toBeNull();
  });

  it("管理员额外看到管理员列表（含 secret_ref）与创建表单的引擎选择器", () => {
    mocks.isAdmin = true;
    mocks.catalogueDatasources.datasources = [datasourceView()];
    mocks.adminDatasources.datasources = [adminDatasourceView()];
    render(wrap(<DatasourcesPage />));
    expect(document.body.textContent).toContain("prod-secret-ref");
    expect(screen.getByTestId("datasource-engine-select")).toBeTruthy();
    expect(screen.getByTestId("datasource-create-form")).toBeTruthy();
  });
});

describe("/workspace/metrics", () => {
  it("加载状态用 role=status", () => {
    mocks.catalogueMetrics.isLoading = true;
    render(wrap(<MetricsPage />));
    expect(screen.getByRole("status").textContent).toBe("Loading…");
  });

  it("错误状态给出 role=alert 与可重试按钮", () => {
    mocks.catalogueMetrics.isError = true;
    mocks.catalogueMetrics.error = new Error("boom");
    render(wrap(<MetricsPage />));
    expect(screen.getByRole("alert")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(mocks.catalogueMetrics.refetch).toHaveBeenCalledTimes(1);
  });

  it("普通用户的空指标目录说明管理员配置前提", () => {
    render(wrap(<MetricsPage />));
    expect(screen.getByRole("status").textContent).toBe(
      "No active metrics are available to your account. Ask an administrator to define one, activate it, and grant you access.",
    );
  });

  it("管理员的空指标目录说明新建与启用", () => {
    mocks.isAdmin = true;
    render(wrap(<MetricsPage />));
    expect(screen.getByRole("status").textContent).toBe(
      "No metrics are defined yet. Create a metric and activate it before analyses can use it.",
    );
    expect(screen.getByTestId("metric-create-form")).toBeTruthy();
  });

  it("expression 作为纯文本展示，不执行也不包装成 SQL", () => {
    mocks.catalogueMetrics.metrics = [metricView()];
    render(wrap(<MetricsPage />));
    const expression = screen.getByTestId("metric-expression-revenue");
    expect(expression.tagName).toBe("CODE");
    expect(expression.textContent).toBe("SUM(orders.amount)");
    // 状态标签同时给出本地化文字。
    expect(screen.getByTestId("metric-status-active").textContent).toContain(
      "Active",
    );
  });

  it("非管理员看不到创建/编辑/下线入口", () => {
    mocks.catalogueMetrics.metrics = [metricView()];
    render(wrap(<MetricsPage />));
    expect(screen.queryByTestId("metric-create-form")).toBeNull();
    expect(screen.queryByRole("button", { name: /^Retire metric/ })).toBeNull();
    expect(mocks.adminMetricsEnabled).toEqual([false]);
    expect(mocks.metricGrantCalls).toEqual([]);
  });

  it("管理员看到指标管理面板", () => {
    mocks.isAdmin = true;
    mocks.catalogueMetrics.metrics = [metricView()];
    mocks.adminMetrics.metrics = [metricView()];
    render(wrap(<MetricsPage />));
    expect(screen.getByTestId("metric-create-form")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Retire metric Revenue" }),
    ).toBeTruthy();
  });
});

describe("/workspace/history", () => {
  it("加载状态用 role=status", () => {
    mocks.auditHistory.isLoading = true;
    render(wrap(<HistoryPage />));
    expect(screen.getByRole("status").textContent).toBe("Loading…");
  });

  it("错误状态给出 role=alert 与可重试按钮", () => {
    mocks.auditHistory.isError = true;
    mocks.auditHistory.error = new Error("boom");
    render(wrap(<HistoryPage />));
    expect(screen.getByRole("alert")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(mocks.auditHistory.refresh).toHaveBeenCalledTimes(1);
  });

  it("空历史说明受控查询后才会生成审计记录", () => {
    render(wrap(<HistoryPage />));
    expect(screen.getByRole("status").textContent).toBe(
      "No audit entries yet. A record appears after a governed query runs.",
    );
  });

  it("只渲染安全字段，绝不出现 SQL、凭据或令牌", () => {
    mocks.auditHistory.audits = [
      {
        ...auditView(),
        sql: "SELECT password FROM users",
        secret_ref: "prod-credential",
        token: "header.payload.signature",
        result_rows: [{ email: "analyst@example.com" }],
      } as unknown as QueryAuditView,
    ];
    render(wrap(<HistoryPage />));
    const text = document.body.textContent ?? "";
    expect(text).not.toContain("SELECT");
    expect(text).not.toContain("secret_ref");
    expect(text).not.toContain("token");
    expect(text).not.toContain("prod-credential");
    expect(text).not.toContain("header.payload.signature");
    expect(text).not.toContain("analyst@example.com");
    expect(text).toContain("execute");
    expect(text).toContain("Completed");
  });

  it("非管理员看不到按主体查询的入口", () => {
    mocks.auditHistory.audits = [auditView()];
    render(wrap(<HistoryPage />));
    expect(screen.queryByTestId("audit-principal")).toBeNull();
  });

  it("管理员的跨主体查询默认不发起，提交主体后才查询", () => {
    mocks.isAdmin = true;
    mocks.auditHistory.audits = [auditView()];
    render(wrap(<HistoryPage />));
    // 默认空值：查询保持 disabled，结果区不渲染。
    expect(screen.queryByTestId("audit-lookup-result")).toBeNull();
    const field = screen.getByTestId("audit-principal");
    fireEvent.change(field, { target: { value: "user-9" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(screen.getByTestId("audit-lookup-result")).toBeTruthy();
  });

  it("还有下一页时给出加载更多", () => {
    mocks.auditHistory.audits = [auditView()];
    mocks.auditHistory.hasMore = true;
    render(wrap(<HistoryPage />));
    fireEvent.click(screen.getByTestId("audit-load-more"));
    expect(mocks.auditHistory.loadMore).toHaveBeenCalledTimes(1);
  });
});

describe("/workspace/reports", () => {
  it("加载状态用 role=status", () => {
    mocks.reports.isLoading = true;
    render(wrap(<ReportsPage />));
    expect(screen.getByRole("status").textContent).toBe("Loading…");
  });

  it("错误状态给出 role=alert 与可重试按钮", () => {
    mocks.reports.isError = true;
    mocks.reports.error = new Error("boom");
    render(wrap(<ReportsPage />));
    expect(screen.getByRole("alert")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(mocks.reports.refresh).toHaveBeenCalledTimes(1);
  });

  it("空状态使用报告专属文案", () => {
    render(wrap(<ReportsPage />));
    expect(screen.getByRole("status").textContent).toBe(
      "No reports published yet. Reports appear here after an analysis writes and publishes one.",
    );
  });

  it("分析链接指向分析会话并百分号编码 thread id", () => {
    mocks.reports.reports = [reportView()];
    render(wrap(<ReportsPage />));
    const link = screen.getByRole("link", { name: "Open the analysis" });
    expect(link.getAttribute("href")).toBe(
      `/workspace/analysis/${encodeURIComponent("thread 1/two")}`,
    );
    expect(document.body.textContent).toContain(
      "/mnt/user-data/outputs/revenue.md",
    );
  });

  it("还有下一页时给出加载更多", () => {
    mocks.reports.reports = [reportView()];
    mocks.reports.hasMore = true;
    render(wrap(<ReportsPage />));
    fireEvent.click(screen.getByTestId("report-load-more"));
    expect(mocks.reports.loadMore).toHaveBeenCalledTimes(1);
  });
});
