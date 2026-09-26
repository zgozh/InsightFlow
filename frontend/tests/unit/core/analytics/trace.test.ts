import type { Message } from "@langchain/langgraph-sdk";
import { describe, expect, test } from "@rstest/core";

import {
  hasAnalyticsTrace,
  projectAnalyticsTrace,
  querySteps,
} from "@/core/analytics/trace";

const DIGEST = "a".repeat(64);
const RESULT_DIGEST = "b".repeat(64);
const SQL = "SELECT id FROM orders WHERE region = 'EU'";

function ai(
  toolCalls: Array<{ id: string; name: string; args: unknown }>,
): Message {
  return {
    type: "ai",
    content: "",
    tool_calls: toolCalls,
  } as unknown as Message;
}

function tool(
  toolCallId: string,
  content: string,
  status?: "success" | "error",
): Message {
  return {
    type: "tool",
    tool_call_id: toolCallId,
    content,
    ...(status ? { status } : {}),
  } as unknown as Message;
}

function querySuccessPayload() {
  return JSON.stringify({
    code: "executed",
    columns: ["id"],
    rows: [[1], [2]],
    row_count: 2,
    byte_count: 42,
    truncated: false,
    evidence: {
      evidence_id: DIGEST,
      datasource_id: "ds-1",
      query_hash: "c".repeat(64),
      risk: "low",
      schema_version: "s1",
      policy_version: "p1",
      plan_digest: "d".repeat(64),
      estimated_rows: 10,
      engine_cost: "12.5",
      row_count: 2,
      byte_count: 42,
      truncated: false,
      result_digest: RESULT_DIGEST,
      decision_code: "executed",
    },
  });
}

describe("analytics trace projection", () => {
  test("maps every approved tool name onto its phase", () => {
    const steps = projectAnalyticsTrace([
      ai([
        { id: "c1", name: "write_todos", args: { todos: [{ content: "a" }] } },
      ]),
      ai([{ id: "c2", name: "inspect_business_catalog", args: {} }]),
      ai([
        {
          id: "c3",
          name: "task",
          args: { subagent_type: "general-purpose", prompt: "x" },
        },
      ]),
      ai([
        {
          id: "c4",
          name: "present_files",
          args: { filepaths: ["/mnt/user-data/outputs/r.md"] },
        },
      ]),
      ai([
        {
          id: "c5-current",
          name: "write_analysis_report",
          args: { title: "t", markdown: "REPORT_BODY_SENTINEL" },
        },
      ]),
      ai([{ id: "c5", name: "publish_analysis_report", args: { title: "t" } }]),
    ]);

    expect(steps.map((step) => step.kind)).toEqual([
      "plan",
      "catalog",
      "delegate",
      "artifact",
      "report",
      "report",
    ]);
    expect(steps[0]?.todoCount).toBe(1);
    expect(steps[2]?.subagentType).toBe("general-purpose");
    expect(steps[3]?.artifactPaths).toEqual(["/mnt/user-data/outputs/r.md"]);
  });

  test("an unknown tool becomes an unparsed safe event instead of raw data", () => {
    const steps = projectAnalyticsTrace([
      ai([
        {
          id: "c1",
          name: "mystery_tool",
          args: { secret: "postgres://user:pw@host/db" },
        },
      ]),
    ]);

    expect(steps).toHaveLength(1);
    expect(steps[0]?.kind).toBe("unknown");
    expect(steps[0]?.unparsed).toBe(true);
    expect(JSON.stringify(steps)).not.toContain("postgres");
    expect(JSON.stringify(steps)).not.toContain("secret");
  });

  test("a query step never carries the tool arguments", () => {
    const steps = projectAnalyticsTrace([
      ai([
        {
          id: "c1",
          name: "query_business_data",
          args: { datasource_id: "ds-1", sql: SQL },
        },
      ]),
      tool("c1", querySuccessPayload()),
    ]);

    const serialized = JSON.stringify(steps);
    expect(serialized).not.toContain("SELECT");
    expect(serialized).not.toContain("orders");
    expect(serialized).not.toContain('"datasource_id"');
    // 结果 rows 与它们的列名都不进轨迹；`estimated_rows` 是另一回事（安全计数）。
    expect(serialized).not.toContain('"rows"');
    expect(serialized).not.toContain('"columns"');
    expect(serialized).not.toContain('"query_hash"');
    expect(serialized).not.toContain('"plan_digest"');
  });

  test("a successful query exposes only the whitelisted safe facts", () => {
    const steps = projectAnalyticsTrace([
      ai([
        {
          id: "c1",
          name: "query_business_data",
          args: { datasource_id: "ds-1", sql: SQL },
        },
      ]),
      tool("c1", querySuccessPayload()),
    ]);

    expect(steps[0]?.status).toBe("completed");
    expect(Object.keys(steps[0]?.facts ?? {}).sort()).toEqual([
      "byte_count",
      "code",
      "engine_cost",
      "estimated_rows",
      "evidence_id",
      "policy_version",
      "result_digest",
      "risk",
      "row_count",
      "schema_version",
      "truncated",
    ]);
    expect(steps[0]?.facts?.evidence_id).toBe(DIGEST);
    expect(steps[0]?.facts?.engine_cost).toBe("12.5");
    expect(steps[0]?.facts?.estimated_rows).toBe(10);
  });

  test("a rejected query keeps the stable code and carries no evidence", () => {
    const steps = projectAnalyticsTrace([
      ai([
        {
          id: "c1",
          name: "query_business_data",
          args: { datasource_id: "ds-1", sql: SQL },
        },
      ]),
      tool("c1", JSON.stringify({ code: "cost_limit_exceeded" })),
    ]);

    expect(steps[0]?.status).toBe("rejected");
    expect(steps[0]?.facts?.code).toBe("cost_limit_exceeded");
    expect(steps[0]?.facts?.evidence_id).toBeNull();
  });

  test("a malformed query payload becomes an unparsed safe event", () => {
    const steps = projectAnalyticsTrace([
      ai([
        {
          id: "c1",
          name: "query_business_data",
          args: { datasource_id: "ds-1", sql: SQL },
        },
      ]),
      tool("c1", "{not json at all"),
    ]);

    expect(steps[0]?.unparsed).toBe(true);
    expect(steps[0]?.status).toBe("failed");
    expect(steps[0]?.facts).toBeNull();
    expect(JSON.stringify(steps)).not.toContain("not json");
  });

  test("a tool error status marks the step failed", () => {
    const steps = projectAnalyticsTrace([
      ai([{ id: "c1", name: "inspect_business_catalog", args: {} }]),
      tool("c1", JSON.stringify({ code: "analytics_unavailable" }), "error"),
    ]);

    expect(steps[0]?.status).toBe("failed");
  });

  test("an unresolved tool call is still running", () => {
    const steps = projectAnalyticsTrace([
      ai([
        {
          id: "c1",
          name: "query_business_data",
          args: { datasource_id: "ds-1", sql: SQL },
        },
      ]),
    ]);

    expect(steps[0]?.status).toBe("running");
    expect(steps[0]?.facts).toBeNull();
  });

  test("replayed duplicate tool calls collapse onto one step", () => {
    const steps = projectAnalyticsTrace([
      ai([
        {
          id: "c1",
          name: "query_business_data",
          args: { datasource_id: "ds-1", sql: SQL },
        },
      ]),
      ai([
        {
          id: "c1",
          name: "query_business_data",
          args: { datasource_id: "ds-1", sql: SQL },
        },
      ]),
      tool("c1", querySuccessPayload()),
    ]);

    expect(steps).toHaveLength(1);
    expect(steps[0]?.status).toBe("completed");
  });

  test("a late duplicate result cannot overwrite the first one", () => {
    const steps = projectAnalyticsTrace([
      ai([
        {
          id: "c1",
          name: "query_business_data",
          args: { datasource_id: "ds-1", sql: SQL },
        },
      ]),
      tool(
        "c1",
        JSON.stringify({ code: "executed", evidence: { risk: "low" } }),
      ),
      tool("c1", querySuccessPayload()),
    ]);

    expect(steps).toHaveLength(1);
    // 第一条结果先到：状态已定，后到的重放不改变它。
    expect(steps[0]?.facts?.evidence_id).toBeNull();
  });

  test("out of order stream frames keep the message order, not the result order", () => {
    const steps = projectAnalyticsTrace([
      ai([
        {
          id: "c2",
          name: "query_business_data",
          args: { datasource_id: "ds-1", sql: SQL },
        },
      ]),
      ai([{ id: "c1", name: "inspect_business_catalog", args: {} }]),
      tool(
        "c2",
        JSON.stringify({ code: "executed", evidence: { risk: "low" } }),
      ),
      tool("c1", JSON.stringify({ code: "ok", datasources: [], metrics: [] })),
    ]);

    expect(steps.map((step) => step.id)).toEqual(["c2", "c1"]);
  });

  test("present_files only reports outputs scoped paths", () => {
    const steps = projectAnalyticsTrace([
      ai([
        {
          id: "c1",
          name: "present_files",
          args: {
            filepaths: [
              "/mnt/user-data/outputs/ok.md",
              "/mnt/user-data/uploads/leak.md",
              "/mnt/user-data/outputs/../leak.md",
              "/mnt/user-data/outputs/../",
              42,
            ],
          },
        },
      ]),
    ]);

    expect(steps[0]?.artifactPaths).toEqual(["/mnt/user-data/outputs/ok.md"]);
  });

  test("a report step exposes only the published path", () => {
    const steps = projectAnalyticsTrace([
      ai([
        {
          id: "c1",
          name: "publish_analysis_report",
          args: { title: "t", artifact_path: "/mnt/user-data/outputs/r.md" },
        },
      ]),
      tool(
        "c1",
        JSON.stringify({
          code: "published",
          report: {
            id: "report-1",
            title: "t",
            artifact_path: "/mnt/user-data/outputs/r.md",
            status: "published",
            evidence_ids: [DIGEST],
            created_at: "2026-09-22T12:00:00+00:00",
          },
        }),
      ),
    ]);

    expect(steps[0]?.status).toBe("completed");
    expect(steps[0]?.artifactPaths).toEqual(["/mnt/user-data/outputs/r.md"]);
    // 结果里的 evidence 列表与身份字段都不进轨迹。
    expect(JSON.stringify(steps)).not.toContain("evidence_ids");
    expect(JSON.stringify(steps)).not.toContain("report-1");
  });

  test("a report conflict is a rejection, not a success", () => {
    const steps = projectAnalyticsTrace([
      ai([
        {
          id: "c1",
          name: "publish_analysis_report",
          args: { title: "t", artifact_path: "/mnt/user-data/outputs/r.md" },
        },
      ]),
      tool(
        "c1",
        JSON.stringify({
          code: "report_conflict",
          report: { artifact_path: "/mnt/user-data/outputs/r.md" },
        }),
      ),
    ]);

    expect(steps[0]?.status).toBe("rejected");
  });

  test("an idempotent report retry counts as completed", () => {
    const steps = projectAnalyticsTrace([
      ai([
        {
          id: "c1",
          name: "publish_analysis_report",
          args: { title: "t", artifact_path: "/mnt/user-data/outputs/r.md" },
        },
      ]),
      tool(
        "c1",
        JSON.stringify({
          code: "existing",
          report: { artifact_path: "/mnt/user-data/outputs/r.md" },
        }),
      ),
    ]);

    expect(steps[0]?.status).toBe("completed");
  });

  test("the current writer derives review approval and artifact only from a complete safe receipt", () => {
    const path = "/mnt/user-data/outputs/analysis-report-run_1.md";
    const messages = ["published", "existing"].flatMap((code) => [
      ai([
        {
          id: `current-writer-${code}`,
          name: "write_analysis_report",
          args: {
            title: "Synthetic",
            markdown: "REPORT_BODY_SENTINEL",
            evidence_ids: [DIGEST],
          },
        },
      ]),
      tool(
        `current-writer-${code}`,
        JSON.stringify({
          code,
          report_id: "report_1",
          artifact_path: path,
          evidence_ids: [DIGEST],
        }),
      ),
    ]);

    const steps = projectAnalyticsTrace(messages);

    expect(steps.map((step) => step.kind)).toEqual(["report", "report"]);
    expect(steps.map((step) => step.status)).toEqual([
      "completed",
      "completed",
    ]);
    expect(steps.map((step) => step.reviewerStatus)).toEqual([
      "approved",
      "approved",
    ]);
    expect(steps.map((step) => step.reviewerReasonCode)).toEqual([null, null]);
    expect(steps.map((step) => step.artifactPaths)).toEqual([[path], [path]]);
    expect(JSON.stringify(steps)).not.toContain("REPORT_BODY_SENTINEL");
  });

  test("review rejection carries only a finite safe reason and never an artifact", () => {
    const steps = projectAnalyticsTrace([
      ai([
        {
          id: "review-rejected",
          name: "write_analysis_report",
          args: { markdown: "REPORT_BODY_SENTINEL" },
        },
      ]),
      tool(
        "review-rejected",
        JSON.stringify({
          code: "analysis_review_rejected",
          reason_code: "evidence_mismatch",
        }),
      ),
    ]);

    expect(steps[0]?.status).toBe("rejected");
    expect(steps[0]?.reviewerStatus).toBe("rejected");
    expect(steps[0]?.reviewerReasonCode).toBe("evidence_mismatch");
    expect(steps[0]?.artifactPaths).toEqual([]);
    expect(JSON.stringify(steps)).not.toContain("REPORT_BODY_SENTINEL");
  });

  test("review failure and limit receipts cannot imply approval, and evidence failures are not reviewer outcomes", () => {
    const cases = [
      {
        id: "unavailable",
        code: "analysis_review_unavailable",
        review: "failed",
      },
      {
        id: "oversized",
        code: "analysis_review_input_too_large",
        review: "limited",
      },
      {
        id: "exhausted",
        code: "analysis_review_attempt_limit",
        review: "limited",
      },
      { id: "evidence", code: "analysis_evidence_unavailable", review: null },
      { id: "conflict", code: "report_conflict", review: null },
    ] as const;
    const messages = cases.flatMap(({ id, code }) => [
      ai([
        {
          id,
          name: "write_analysis_report",
          args: { markdown: "BODY_SENTINEL" },
        },
      ]),
      tool(
        id,
        JSON.stringify({
          code,
          report_id: "report_1",
          artifact_path: "/mnt/user-data/outputs/analysis-report-run_1.md",
          evidence_ids: [DIGEST],
        }),
      ),
    ]);

    const steps = projectAnalyticsTrace(messages);

    expect(steps.map((step) => step.reviewerStatus)).toEqual(
      cases.map(({ review }) => review),
    );
    expect(steps.every((step) => step.artifactPaths.length === 0)).toBe(true);
    expect(steps.some((step) => step.reviewerStatus === "approved")).toBe(
      false,
    );
  });

  test("a malformed or errored writer receipt cannot masquerade as review approval", () => {
    const path = "/mnt/user-data/outputs/analysis-report-run_1.md";
    const validReceipt = JSON.stringify({
      code: "published",
      report_id: "report_1",
      artifact_path: path,
      evidence_ids: [DIGEST],
    });
    const steps = projectAnalyticsTrace([
      ai([{ id: "missing-fields", name: "write_analysis_report", args: {} }]),
      tool(
        "missing-fields",
        JSON.stringify({ code: "published", artifact_path: path }),
      ),
      ai([{ id: "extra-fields", name: "write_analysis_report", args: {} }]),
      tool(
        "extra-fields",
        JSON.stringify({
          code: "published",
          report_id: "report_1",
          artifact_path: path,
          evidence_ids: [DIGEST],
          markdown: "CORRUPT_BODY_SENTINEL",
        }),
      ),
      ai([{ id: "tool-error", name: "write_analysis_report", args: {} }]),
      {
        ...tool("tool-error", validReceipt),
        status: "error",
      } as unknown as Message,
      ai([{ id: "unknown-code", name: "write_analysis_report", args: {} }]),
      tool("unknown-code", JSON.stringify({ code: "provider_secret_leak" })),
    ]);

    expect(steps.map((step) => step.reviewerStatus)).toEqual([
      null,
      null,
      null,
      null,
    ]);
    expect(steps.map((step) => step.artifactPaths)).toEqual([[], [], [], []]);
    expect(steps[0]?.unparsed).toBe(true);
    expect(steps[1]?.unparsed).toBe(true);
    expect(steps[2]?.status).toBe("failed");
    expect(steps[3]?.unparsed).toBe(true);
    expect(JSON.stringify(steps)).not.toContain("provider_secret_leak");
    expect(JSON.stringify(steps)).not.toContain("CORRUPT_BODY_SENTINEL");
  });

  test("a malformed report payload is unparsed and never rendered", () => {
    const steps = projectAnalyticsTrace([
      ai([
        {
          id: "c1",
          name: "publish_analysis_report",
          args: { title: "t", artifact_path: "/mnt/user-data/outputs/r.md" },
        },
      ]),
      tool("c1", "Traceback: postgres://user:pw@host/db"),
    ]);

    expect(steps[0]?.unparsed).toBe(true);
    expect(JSON.stringify(steps)).not.toContain("postgres");
  });

  test("subagent type is only accepted when it matches the stable pattern", () => {
    const steps = projectAnalyticsTrace([
      ai([
        {
          id: "c1",
          name: "task",
          args: { subagent_type: "SELECT * FROM orders" },
        },
      ]),
      ai([
        { id: "c2", name: "task", args: { subagent_type: "general-purpose" } },
      ]),
    ]);

    expect(steps[0]?.subagentType).toBeNull();
    expect(steps[1]?.subagentType).toBe("general-purpose");
  });

  test("helpers identify analytics steps and query steps", () => {
    const steps = projectAnalyticsTrace([
      ai([
        {
          id: "c1",
          name: "query_business_data",
          args: { datasource_id: "ds-1", sql: SQL },
        },
      ]),
      tool("c1", querySuccessPayload()),
      ai([{ id: "c2", name: "present_files", args: { filepaths: [] } }]),
    ]);

    expect(hasAnalyticsTrace(steps)).toBe(true);
    expect(hasAnalyticsTrace([])).toBe(false);
    expect(querySteps(steps).map((step) => step.id)).toEqual(["c1"]);
  });

  test("an empty or non-analytics thread yields no steps", () => {
    expect(projectAnalyticsTrace([])).toEqual([]);
    expect(
      projectAnalyticsTrace([
        { type: "human", content: "hi" } as unknown as Message,
        { type: "ai", content: "hello" } as unknown as Message,
      ]),
    ).toEqual([]);
  });

  test("the projection is deterministic across repeated runs", () => {
    const messages = [
      ai([
        {
          id: "c1",
          name: "query_business_data",
          args: { datasource_id: "ds-1", sql: SQL },
        },
      ]),
      tool("c1", querySuccessPayload()),
    ];

    expect(projectAnalyticsTrace(messages)).toEqual(
      projectAnalyticsTrace(messages),
    );
  });
});
