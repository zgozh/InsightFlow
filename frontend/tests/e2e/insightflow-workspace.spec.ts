import { expect, test, type Page } from "@playwright/test";

import { MOCK_THREAD_ID, mockLangGraphAPI } from "./utils/mock-api";

/**
 * InsightFlow 产品工作台的端到端关键路径（Phase 4 §10）。
 *
 * 全部后端调用都由 `page.route()` 拦截：fixture 里**没有** token、凭据或真实 PII，
 * 只有稳定 id、安全元数据与已脱敏的决定码。
 */

const DIGEST = "a".repeat(64);
const RESULT_DIGEST = "b".repeat(64);
const OTHER_DIGEST = "c".repeat(64);
const SQL = "SELECT region FROM orders LIMIT 10";
const REPORT_PATH = "/mnt/user-data/outputs/business-analysis.md";

/** 一段会话消息：受控查询的调用与结果配对，外加一次报告登记。 */
function traceMessages() {
  return [
    {
      type: "human",
      id: "mock-human",
      content: [{ type: "text", text: "帮我看一下各区域的经营情况" }],
    },
    {
      type: "ai",
      id: "mock-ai-tool",
      content: "",
      tool_calls: [
        {
          id: "call-query-1",
          name: "query_business_data",
          args: { datasource_id: "ds-1", sql: SQL },
          type: "tool_call",
        },
      ],
    },
    {
      type: "tool",
      id: "mock-tool-1",
      name: "query_business_data",
      tool_call_id: "call-query-1",
      content: JSON.stringify({
        code: "executed",
        columns: ["region"],
        rows: [["EU"]],
        row_count: 1,
        byte_count: 12,
        truncated: false,
        evidence: {
          evidence_id: DIGEST,
          risk: "low",
          schema_version: "s1",
          policy_version: "p1",
          estimated_rows: 10,
          engine_cost: "12.5",
          row_count: 1,
          byte_count: 12,
          truncated: false,
          result_digest: RESULT_DIGEST,
          decision_code: "executed",
        },
      }),
    },
    {
      type: "ai",
      id: "mock-ai-report",
      content: "",
      tool_calls: [
        {
          id: "call-report-1",
          name: "publish_analysis_report",
          args: { title: "2026 Q3 经营分析", artifact_path: REPORT_PATH },
          type: "tool_call",
        },
      ],
    },
    {
      type: "tool",
      id: "mock-tool-2",
      name: "publish_analysis_report",
      tool_call_id: "call-report-1",
      content: JSON.stringify({
        code: "published",
        report: {
          id: "report-1",
          title: "2026 Q3 经营分析",
          artifact_path: REPORT_PATH,
          status: "published",
          evidence_ids: [DIGEST],
          created_at: "2026-09-22T12:00:00+00:00",
        },
      }),
    },
  ];
}

const auditRecord = {
  id: "audit-1",
  principal_id: "default",
  datasource_id: "ds-1",
  phase: "execute",
  status: "completed",
  query_hash: DIGEST,
  risk: "low",
  decision_code: "executed",
  schema_version: "s1",
  policy_version: "p1",
  estimated_rows: 10,
  engine_cost: "12.5",
  plan_digest: OTHER_DIGEST,
  row_count: 1,
  byte_count: 12,
  truncated: false,
  latency_ms: 42,
  started_at: "2026-09-22T12:00:00+00:00",
  finished_at: "2026-09-22T12:00:00.042000+00:00",
};

const reportRecord = {
  id: "report-1",
  principal_id: "default",
  thread_id: MOCK_THREAD_ID,
  run_id: "run-1",
  artifact_path: REPORT_PATH,
  title: "2026 Q3 经营分析",
  status: "published",
  evidence_ids: [DIGEST],
  created_at: "2026-09-22T12:00:00+00:00",
};

const datasourceView = {
  id: "ds-1",
  name: "Warehouse",
  engine: "postgresql",
  default_schema: "public",
  status: "active",
};

const metricView = {
  key: "revenue",
  name: "Revenue",
  description: "Total revenue",
  expression: "sum(amount)",
  dimensions: ["region"],
  version: 2,
  status: "active",
};

async function mockAnalyticsAPI(page: Page) {
  await page.route("**/api/analytics/datasources", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ datasources: [datasourceView] }),
    }),
  );
  await page.route("**/api/analytics/metrics", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ metrics: [metricView] }),
    }),
  );
  await page.route(/\/api\/analytics\/reports(?:\?|$)/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        reports: [reportRecord],
        has_more: false,
        next_before_created_at: null,
        next_before_id: null,
      }),
    }),
  );
  await page.route(/\/api\/analytics\/audits(?:\?|$)/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        audits: [auditRecord],
        has_more: false,
        next_before_started_at: null,
        next_before_id: null,
      }),
    }),
  );
  // 管理员视图是唯一会出现 opaque `secret_ref` 与 `owner_id` 的投影。
  await page.route(/\/api\/analytics\/admin\/datasources(?:\?|$)/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        datasources: [
          {
            ...datasourceView,
            owner_id: "default",
            secret_ref: "env://ANALYTICS_DS",
          },
        ],
      }),
    }),
  );
  await page.route(/\/api\/analytics\/admin\/metrics(?:\?|$)/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ metrics: [metricView] }),
    }),
  );
}

async function openWorkspacePage(page: Page, path: string) {
  mockLangGraphAPI(page, {
    threads: [
      {
        thread_id: MOCK_THREAD_ID,
        title: "2026 Q3 经营分析",
        messages: traceMessages(),
      },
    ],
  });
  await mockAnalyticsAPI(page);
  await page.goto(path);
}

test.describe("InsightFlow workspace", () => {
  test("the sidebar leads with the analysis workspace entries", async ({
    page,
  }) => {
    await openWorkspacePage(page, "/workspace/datasources");
    const sidebar = page.locator("[data-sidebar='sidebar']");

    for (const href of [
      "/workspace/analysis/new",
      "/workspace/chats",
      "/workspace/datasources",
      "/workspace/metrics",
      "/workspace/reports",
      "/workspace/scheduled-tasks",
      "/workspace/history",
    ]) {
      await expect(sidebar.locator(`a[href='${href}']`).first()).toBeVisible();
    }
  });

  test("a new analysis reuses the chat runtime and offers the trace panel", async ({
    page,
  }) => {
    await openWorkspacePage(page, "/workspace/analysis/new");

    await expect(page.getByRole("textbox").first()).toBeVisible();
    // 宽屏：轨迹是常驻右列，窄屏触发器不出现。
    await expect(page.getByTestId("analytics-trace-panel")).toBeVisible();
    await expect(page.getByTestId("analytics-trace-trigger")).toBeHidden();

    // 窄屏：轨迹默认收起为抽屉，由触发器打开。
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/workspace/analysis/new");
    const trigger = page.getByTestId("analytics-trace-trigger");
    await expect(trigger).toBeVisible();
    await expect(page.getByTestId("analytics-trace-panel")).toBeHidden();
    await trigger.click();
    await expect(page.getByTestId("analytics-trace-panel")).toBeVisible();
  });

  test("the analysis trace shows governed evidence and never the SQL", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await openWorkspacePage(page, `/workspace/analysis/${MOCK_THREAD_ID}`);

    const panel = page.getByTestId("analytics-trace-panel");
    const trigger = page.getByTestId("analytics-trace-trigger");
    if (!(await panel.isVisible())) {
      await trigger.click();
    }
    await expect(panel).toBeVisible();

    const queryStep = panel
      .locator("[data-testid='analytics-trace-step'][data-kind='query']")
      .first();
    await expect(queryStep).toBeVisible();
    await expect(queryStep).toHaveAttribute("data-status", "completed");

    const panelText = (await panel.textContent()) ?? "";
    expect(panelText).toContain("12.5");
    // SQL 与结果行都不进轨迹：这里是纯投影的安全边界。
    expect(panelText).not.toContain("SELECT");
    expect(panelText).not.toContain("orders");
    expect(panelText).not.toContain("EU");

    // evidence id 可复制，且复制的是完整摘要而不是缩略值。
    await expect(
      panel.getByRole("button", { name: /copy evidence/i }).first(),
    ).toBeVisible();
  });

  test("the report index links back into the analysis route", async ({
    page,
  }) => {
    await openWorkspacePage(page, "/workspace/reports");

    const record = page.getByTestId("report-record").first();
    await expect(record).toBeVisible();
    await expect(record).toContainText("2026 Q3 经营分析");
    await expect(record).toContainText(REPORT_PATH);

    const openAnalysis = page.getByTestId("report-open-analysis").first();
    await expect(openAnalysis).toHaveAttribute(
      "href",
      `/workspace/analysis/${MOCK_THREAD_ID}`,
    );
    // 报告索引不构造产物直链。
    await expect(record.locator("a[href*='/artifacts/']")).toHaveCount(0);
  });

  test("an administrator can manage datasources and metrics", async ({
    page,
  }) => {
    await openWorkspacePage(page, "/workspace/datasources");
    await expect(page.getByTestId("datasource-create-form")).toBeVisible();
    // engine 只在创建时可选择；编辑表单里没有这个字段。
    await expect(page.getByTestId("datasource-engine-select")).toBeVisible();

    await page.goto("/workspace/metrics");
    await expect(page.getByTestId("metric-create-form")).toBeVisible();
  });

  test("the audit history shows safe fields only", async ({ page }) => {
    await openWorkspacePage(page, "/workspace/history");

    const record = page.getByTestId("audit-record").first();
    await expect(record).toBeVisible();
    await expect(record).toContainText("executed");

    const text = (await record.textContent()) ?? "";
    expect(text).not.toContain("SELECT");
    expect(text).not.toContain("secret_ref");
    expect(text).not.toContain("plan_id");
  });

  for (const path of [
    "/workspace/datasources",
    "/workspace/metrics",
    "/workspace/reports",
    "/workspace/history",
  ]) {
    test(`${path} does not overflow at 375px`, async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 812 });
      await openWorkspacePage(page, path);

      await expect
        .poll(() => page.evaluate(() => document.documentElement.scrollWidth))
        .toBeLessThanOrEqual(375);
    });
  }
});
