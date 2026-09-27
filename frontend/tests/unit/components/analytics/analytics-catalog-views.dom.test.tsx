import { afterEach, describe, expect, it, rs } from "@rstest/core";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";

import {
  AnalyticsConfirmDialog,
  AnalyticsPage,
  AuditHistoryList,
  DatasourceCatalogTable,
  isCatalogEmpty,
  ReportCatalogList,
} from "@/components/analytics/analytics-catalog-views";
import { AnalyticsRequestError } from "@/core/analytics/api";
import type {
  AnalysisReportView,
  DatasourceView,
  QueryAuditView,
} from "@/core/analytics/types";
import { DEFAULT_LOCALE } from "@/core/i18n";
import { I18nProvider } from "@/core/i18n/context";

/**
 * 只替换工作台外壳：真实的 `WorkspaceHeader` 依赖侧边栏 Provider 与路由上下文，
 * 而这里要钉的是页面自己的状态机与只读视图，不是外壳本身。
 * 直接返回 children 可以避免在 `rs.mock` 工厂里写 JSX（工厂会被提升到 import 之前）。
 */
rs.mock("@/components/workspace/workspace-container", () => ({
  WorkspaceContainer: ({ children }: { children?: ReactNode }) => children,
  WorkspaceHeader: () => null,
  WorkspaceBody: ({ children }: { children?: ReactNode }) => children,
}));

function wrap(node: ReactNode) {
  return <I18nProvider initialLocale={DEFAULT_LOCALE}>{node}</I18nProvider>;
}

/**
 * 用 `instanceof` 收窄而不是类型断言：仓库的 ESLint 会自动"修复"多余的断言，
 * 断言一旦被自动移除，`disabled` 就不再存在于 `HTMLElement` 上。
 */
function isDisabled(element: HTMLElement): boolean {
  return element instanceof HTMLButtonElement && element.disabled;
}

const DIGEST_A = "a".repeat(64);
const DIGEST_B = "b".repeat(64);

function auditView(overrides: Partial<QueryAuditView> = {}): QueryAuditView {
  return {
    id: "audit-1",
    principal_id: "user-1",
    datasource_id: "ds-1",
    phase: "execute",
    status: "completed",
    query_hash: DIGEST_A,
    risk: "low",
    decision_code: "executed",
    schema_version: "3",
    policy_version: "7",
    estimated_rows: 120,
    engine_cost: "12.5",
    plan_digest: DIGEST_B,
    row_count: 100,
    byte_count: 4096,
    truncated: false,
    latency_ms: 42,
    started_at: "2026-01-02T03:04:05Z",
    finished_at: "2026-01-02T03:04:06Z",
    ...overrides,
  };
}

function datasourceView(
  overrides: Partial<DatasourceView> = {},
): DatasourceView {
  return {
    id: "ds-1",
    name: "Orders warehouse",
    engine: "postgresql",
    default_schema: "public",
    status: "active",
    ...overrides,
  };
}

function reportView(
  overrides: Partial<AnalysisReportView> = {},
): AnalysisReportView {
  return {
    id: "report-1",
    principal_id: "user-1",
    thread_id: "thread-1",
    run_id: "run-1",
    artifact_path: "/mnt/user-data/outputs/revenue.md",
    title: "Revenue review",
    status: "published",
    evidence_ids: [DIGEST_A],
    created_at: "2026-01-02T03:04:05Z",
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  rs.restoreAllMocks();
});

describe("AnalyticsPage 的四种显式状态", () => {
  it("加载中给出 role=status", () => {
    render(wrap(<AnalyticsPage title="T" description="D" isLoading />));
    expect(screen.getByRole("status").textContent).toBe("Loading…");
  });

  it("错误时给出 role=alert 与键盘可达的重试按钮", () => {
    const onRetry = rs.fn();
    render(
      wrap(
        <AnalyticsPage
          title="T"
          description="D"
          isError
          error={new Error("boom")}
          onRetry={onRetry}
        />,
      ),
    );
    expect(screen.getByRole("alert")).toBeTruthy();
    const retry = screen.getByRole("button", { name: "Retry" });
    expect(retry.tagName).toBe("BUTTON");
    fireEvent.click(retry);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("服务端 403 渲染禁止态，而不是错误态或空表", () => {
    render(
      wrap(
        <AnalyticsPage
          title="T"
          description="D"
          isError
          error={new AnalyticsRequestError(403, null)}
          onRetry={rs.fn()}
        />,
      ),
    );
    expect(screen.getByRole("alert").textContent).toContain(
      "The server refused this action (403)",
    );
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it("空状态不渲染子节点", () => {
    render(
      wrap(
        <AnalyticsPage title="T" description="D" isEmpty emptyMessage="nothing">
          <span data-testid="child" />
        </AnalyticsPage>,
      ),
    );
    expect(screen.getByRole("status").textContent).toBe("nothing");
    expect(screen.queryByTestId("child")).toBeNull();
  });

  it("有数据时渲染子节点", () => {
    render(
      wrap(
        <AnalyticsPage title="T" description="D" isEmpty={false}>
          <span data-testid="child" />
        </AnalyticsPage>,
      ),
    );
    expect(screen.getByTestId("child")).toBeTruthy();
  });
});

describe("isCatalogEmpty", () => {
  it("只有成功读取且为空才算空", () => {
    expect(isCatalogEmpty({ isLoading: false, isError: false, count: 0 })).toBe(
      true,
    );
    expect(isCatalogEmpty({ isLoading: true, isError: false, count: 0 })).toBe(
      false,
    );
    expect(isCatalogEmpty({ isLoading: false, isError: true, count: 0 })).toBe(
      false,
    );
    expect(isCatalogEmpty({ isLoading: false, isError: false, count: 1 })).toBe(
      false,
    );
  });
});

describe("AnalyticsConfirmDialog", () => {
  it("打开时焦点落在取消按钮，Escape 走取消路径且不触发确认", () => {
    const onCancel = rs.fn();
    const onConfirm = rs.fn();
    render(
      wrap(
        <AnalyticsConfirmDialog
          open
          title="Remove?"
          description="Body"
          confirmLabel="Remove"
          onCancel={onCancel}
          onConfirm={onConfirm}
        />,
      ),
    );
    const dialog = screen.getByRole("alertdialog");
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    const cancel = screen.getByRole("button", { name: "Cancel" });
    // 原生 button 才能被键盘激活；div 伪按钮在这里就会被抓到。
    expect(cancel.tagName).toBe("BUTTON");
    expect(document.activeElement).toBe(cancel);

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("确认按钮一次点击触发一次确认", () => {
    const onConfirm = rs.fn();
    render(
      wrap(
        <AnalyticsConfirmDialog
          open
          title="Remove?"
          description="Body"
          confirmLabel="Remove"
          onCancel={rs.fn()}
          onConfirm={onConfirm}
        />,
      ),
    );
    const confirm = screen.getByRole("button", { name: "Remove" });
    expect(confirm.tagName).toBe("BUTTON");
    fireEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("提交中禁止关闭：两个按钮都禁用且 Escape 无效", () => {
    const onCancel = rs.fn();
    const onConfirm = rs.fn();
    render(
      wrap(
        <AnalyticsConfirmDialog
          open
          pending
          title="Remove?"
          description="Body"
          confirmLabel="Remove"
          onCancel={onCancel}
          onConfirm={onConfirm}
        />,
      ),
    );
    expect(isDisabled(screen.getByRole("button", { name: "Cancel" }))).toBe(
      true,
    );
    expect(isDisabled(screen.getByRole("button", { name: "Saving…" }))).toBe(
      true,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onCancel).not.toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});

describe("DatasourceCatalogTable", () => {
  it("只渲染目录列；即使宿主对象被塞进管理员字段也不会进入 DOM", () => {
    // 故意把管理员字段挂在同一个对象上：视图按具名字段渲染，因此它们没有渲染路径。
    const hostile = {
      ...datasourceView(),
      owner_id: "user-7",
      secret_ref: "prod-secret-ref",
    } as unknown as DatasourceView;
    render(wrap(<DatasourceCatalogTable datasources={[hostile]} />));
    const text = document.body.textContent ?? "";
    expect(text).toContain("Orders warehouse");
    expect(text).toContain("postgresql");
    expect(text).toContain("public");
    expect(text).toContain("Active");
    expect(text).not.toContain("prod-secret-ref");
    expect(text).not.toContain("user-7");
    // 状态不只靠颜色：本地化文字必须出现。
    expect(
      screen.getByTestId("datasource-status-active").textContent,
    ).toContain("Active");
  });

  it("缺少默认 schema 时展示本地化的不可用文案", () => {
    render(
      wrap(
        <DatasourceCatalogTable
          datasources={[datasourceView({ default_schema: null })]}
        />,
      ),
    );
    expect(document.body.textContent).toContain("Not available");
  });

  it("宽表放在可聚焦的内部滚动容器里，横向滚动不撑宽页面", () => {
    render(wrap(<DatasourceCatalogTable datasources={[datasourceView()]} />));
    const region = screen.getByRole("region", { name: "Data sources" });
    // 容器自己滚：页面宽度不随表格最小宽度增长。
    expect(region.className).toContain("overflow-x-auto");
    expect(region.className).toContain("min-w-0");
    // 键盘可达：容器可聚焦，因此不依赖鼠标滚轮就能横向滚动。
    expect(region.getAttribute("tabindex")).toBe("0");
    region.focus();
    expect(document.activeElement).toBe(region);
    const table = screen.getByRole("table");
    expect(region.contains(table)).toBe(true);
    expect(table.className).toContain("min-w-");
  });
});

describe("AuditHistoryList", () => {
  it("只渲染安全字段：没有 SQL、凭据与内部字段", () => {
    const hostile = {
      ...auditView(),
      // 审计解析类型里根本不存在这些字段；这里模拟"上游硬塞进来"，证明渲染层不会顺带输出。
      sql: "SELECT id, email FROM customers",
      secret_ref: "prod-credential",
      token: "header.payload.signature",
      rows: [{ email: "analyst@example.com" }],
    } as unknown as QueryAuditView;

    render(
      wrap(
        <AuditHistoryList
          audits={[hostile]}
          hasMore={false}
          isFetching={false}
          onLoadMore={rs.fn()}
        />,
      ),
    );

    const text = document.body.textContent ?? "";
    expect(text).not.toContain("SELECT");
    expect(text).not.toContain("secret_ref");
    expect(text).not.toContain("token");
    expect(text).not.toContain("prod-credential");
    expect(text).not.toContain("header.payload.signature");
    expect(text).not.toContain("analyst@example.com");

    // 安全字段确实渲染了：阶段、状态文字、缩略摘要与完整值复制动作。
    expect(text).toContain("execute");
    expect(text).toContain("Completed");
    expect(text).toContain("executed");
    expect(text).toContain("aaaaaaaa…aaaa");
    expect(text).toContain("bbbbbbbb…bbbb");
    const copyButtons = screen.getAllByRole("button", { name: /Copy/ });
    expect(copyButtons.length).toBe(2);
    for (const button of copyButtons) {
      expect(button.tagName).toBe("BUTTON");
    }
  });

  it("keyset 分页：有下一页给出加载更多，没有下一页显示没有更多", () => {
    const onLoadMore = rs.fn();
    const view = render(
      wrap(
        <AuditHistoryList
          audits={[auditView()]}
          hasMore
          isFetching={false}
          onLoadMore={onLoadMore}
        />,
      ),
    );
    fireEvent.click(screen.getByTestId("audit-load-more"));
    expect(onLoadMore).toHaveBeenCalledTimes(1);
    // 界面里没有 offset／页码概念，只有"加载更多"。
    expect(document.body.textContent).not.toContain("page");

    view.rerender(
      wrap(
        <AuditHistoryList
          audits={[auditView()]}
          hasMore={false}
          isFetching={false}
          onLoadMore={onLoadMore}
        />,
      ),
    );
    expect(screen.queryByTestId("audit-load-more")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("No more results");
  });
});

describe("ReportCatalogList", () => {
  it("提供基于受保护产物路由的报告下载，同时保留分析链接", () => {
    render(
      wrap(
        <ReportCatalogList
          reports={[reportView({ thread_id: "thread 1/two" })]}
        />,
      ),
    );
    const analysisLink = screen.getByRole("link", {
      name: "Open the analysis",
    });
    expect(analysisLink.getAttribute("href")).toBe(
      `/workspace/analysis/${encodeURIComponent("thread 1/two")}`,
    );
    const downloadLink = screen.getByRole("link", {
      name: "Download report",
    });
    expect(downloadLink.getAttribute("href")).toBe(
      "/api/threads/thread%201%2Ftwo/artifacts/mnt/user-data/outputs/revenue.md?download=true",
    );
    expect(downloadLink.getAttribute("download")).toBe("");
    expect(screen.getAllByRole("link")).toHaveLength(2);
  });

  it("报告下载链接在中英文环境均有明确标签并保留登记信息", () => {
    const previousLocaleCookie = document.cookie
      .split(";")
      .map((cookie) => cookie.trim())
      .find((cookie) => cookie.startsWith("locale="));
    try {
      for (const [locale, downloadLabel, analysisLabel] of [
        ["zh-CN", "下载报告", "打开对应分析"],
        ["en-US", "Download report", "Open the analysis"],
      ] as const) {
        document.cookie = `locale=${locale}; path=/`;
        const { unmount } = render(
          <I18nProvider initialLocale={locale}>
            <ReportCatalogList reports={[reportView()]} />
          </I18nProvider>,
        );
        expect(screen.getByRole("link", { name: downloadLabel })).toBeTruthy();
        expect(screen.getByRole("link", { name: analysisLabel })).toBeTruthy();
        expect(document.body.textContent).toContain("Revenue review");
        expect(document.body.textContent).toContain(
          "/mnt/user-data/outputs/revenue.md",
        );
        expect(document.body.textContent).toContain("aaaaaaaa…aaaa");
        unmount();
      }
    } finally {
      document.cookie = previousLocaleCookie
        ? `${previousLocaleCookie}; path=/`
        : "locale=; max-age=0; path=/";
    }
  });
});
