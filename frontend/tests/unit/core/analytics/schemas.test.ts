import { describe, expect, test } from "@rstest/core";

import {
  accessPolicyViewSchema,
  adminDatasourceViewSchema,
  analysisReportPageSchema,
  analysisReportViewSchema,
  AnalyticsParseError,
  assertCursorPairing,
  cursorPairIsConsistent,
  datasourceListSchema,
  datasourceViewSchema,
  metricViewSchema,
  parseExternal,
  queryAuditPageSchema,
  queryAuditViewSchema,
  schemaSnapshotViewSchema,
} from "@/core/analytics/schemas";

const DIGEST = "a".repeat(64);

function datasource(overrides: Record<string, unknown> = {}) {
  return {
    id: "ds-1",
    name: "Warehouse",
    engine: "postgresql",
    default_schema: "public",
    status: "active",
    ...overrides,
  };
}

function audit(overrides: Record<string, unknown> = {}) {
  return {
    id: "audit-1",
    principal_id: "user-1",
    datasource_id: "ds-1",
    phase: "plan",
    status: "completed",
    query_hash: DIGEST,
    risk: "low",
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
    ...overrides,
  };
}

function report(overrides: Record<string, unknown> = {}) {
  return {
    id: "report-1",
    principal_id: "user-1",
    thread_id: "thread-1",
    run_id: "run-1",
    artifact_path: "/mnt/user-data/outputs/business-analysis.md",
    title: "2026 Q3 经营分析",
    status: "published",
    evidence_ids: [DIGEST],
    created_at: "2026-09-22T12:00:00+00:00",
    ...overrides,
  };
}

describe("analytics response schemas", () => {
  test("parses the user datasource catalogue", () => {
    const parsed = parseExternal(datasourceListSchema, {
      datasources: [datasource()],
    });
    expect(parsed.datasources).toHaveLength(1);
    expect(parsed.datasources[0]?.engine).toBe("postgresql");
  });

  test("accepts an explicit null default schema but rejects a missing one", () => {
    expect(
      datasourceViewSchema.safeParse(datasource({ default_schema: null }))
        .success,
    ).toBe(true);
    const missing = datasource();
    delete (missing as Record<string, unknown>).default_schema;
    expect(datasourceViewSchema.safeParse(missing).success).toBe(false);
  });

  test("rejects unknown fields instead of passing them through", () => {
    expect(() =>
      parseExternal(datasourceListSchema, {
        datasources: [datasource({ secret_ref: "env://LEAK" })],
      }),
    ).toThrow(AnalyticsParseError);
  });

  test("keeps owner and secret reference out of the non-admin datasource view", () => {
    expect(
      datasourceViewSchema.safeParse(
        datasource({ owner_id: "admin-1", secret_ref: "env://LEAK" }),
      ).success,
    ).toBe(false);
    expect(
      adminDatasourceViewSchema.safeParse(
        datasource({ owner_id: "admin-1", secret_ref: "env://OK" }),
      ).success,
    ).toBe(true);
  });

  test("rejects a response that omits a required datasource field", () => {
    const value = datasource();
    delete (value as Record<string, unknown>).name;
    expect(datasourceViewSchema.safeParse(value).success).toBe(false);
  });

  test("rejects a wrong engine literal", () => {
    expect(
      datasourceViewSchema.safeParse(datasource({ engine: "sqlite" })).success,
    ).toBe(false);
  });

  test("rejects wrong scalar types", () => {
    expect(
      datasourceViewSchema.safeParse(datasource({ name: 42 })).success,
    ).toBe(false);
    expect(
      metricViewSchema.safeParse({
        key: "revenue",
        name: "Revenue",
        description: "Total revenue",
        expression: "sum(amount)",
        dimensions: ["region"],
        version: "2",
        status: "active",
      }).success,
    ).toBe(false);
  });

  test("normalizes a decimal engine cost from string or number", () => {
    expect(
      queryAuditViewSchema.parse(audit({ engine_cost: "12.5" })).engine_cost,
    ).toBe("12.5");
    expect(
      queryAuditViewSchema.parse(audit({ engine_cost: 12.5 })).engine_cost,
    ).toBe("12.5");
    expect(
      queryAuditViewSchema.parse(audit({ engine_cost: null })).engine_cost,
    ).toBeNull();
  });

  test("rejects a non decimal cost instead of coercing it", () => {
    expect(
      queryAuditViewSchema.safeParse(audit({ engine_cost: "12.5 OR 1=1" }))
        .success,
    ).toBe(false);
  });

  test("requires 64 lowercase hex digests", () => {
    expect(
      queryAuditViewSchema.safeParse(
        audit({ query_hash: DIGEST.toUpperCase() }),
      ).success,
    ).toBe(false);
    expect(
      queryAuditViewSchema.safeParse(audit({ query_hash: "abc" })).success,
    ).toBe(false);
  });

  test("a half specified keyset cursor is rejected by the pairing check", () => {
    // 形状由 schema 负责；"两个游标字段必须成对"由独立断言负责，见下面的 helper 用例。
    const page = queryAuditPageSchema.parse({
      audits: [audit()],
      has_more: true,
      next_before_started_at: "2026-09-22T12:00:00+00:00",
      next_before_id: null,
    });
    expect(cursorPairIsConsistent(page)).toBe(false);
    expect(() => assertCursorPairing(page)).toThrow(AnalyticsParseError);
  });

  test("the pairing check accepts a complete cursor and a complete absence", () => {
    expect(
      cursorPairIsConsistent({
        has_more: true,
        next_before_started_at: "2026-09-22T12:00:00+00:00",
        next_before_id: "audit-1",
      }),
    ).toBe(true);
    expect(
      cursorPairIsConsistent({
        has_more: false,
        next_before_started_at: null,
        next_before_id: null,
      }),
    ).toBe(true);
    // has_more 为真却没有游标，或者反过来，都不是服务端会发出的形状。
    expect(
      cursorPairIsConsistent({
        has_more: true,
        next_before_started_at: null,
        next_before_id: null,
      }),
    ).toBe(false);
    expect(
      cursorPairIsConsistent({
        has_more: false,
        next_before_started_at: "2026-09-22T12:00:00+00:00",
        next_before_id: "audit-1",
      }),
    ).toBe(false);
  });

  test("accepts an explicit null pair for the last page", () => {
    const parsed = queryAuditPageSchema.parse({
      audits: [],
      has_more: false,
      next_before_started_at: null,
      next_before_id: null,
    });
    expect(parsed.has_more).toBe(false);
  });

  test("parses a schema snapshot with the aliased schema key", () => {
    const parsed = schemaSnapshotViewSchema.parse({
      datasource_id: "ds-1",
      engine: "mysql",
      version: "s2",
      default_schema: "public",
      relations: [
        {
          name: "orders",
          schema: "public",
          catalog: null,
          columns: [
            { name: "id", data_type: "integer", sensitivity: "standard" },
            { name: "email", data_type: "text", sensitivity: "pii" },
          ],
        },
      ],
    });
    expect(parsed.relations[0]?.columns[1]?.sensitivity).toBe("pii");
  });

  test("parses an access policy and rejects an unknown access value", () => {
    const policy = {
      datasource_id: "ds-1",
      principal_id: "user-1",
      version: "p1",
      relations: [
        {
          name: "orders",
          schema: "public",
          catalog: null,
          columns: [{ name: "id", access: "allow" }],
        },
      ],
      allowed_functions: ["count"],
    };
    expect(accessPolicyViewSchema.safeParse(policy).success).toBe(true);
    expect(
      accessPolicyViewSchema.safeParse({
        ...policy,
        relations: [
          {
            name: "orders",
            schema: "public",
            catalog: null,
            columns: [{ name: "id", access: "maybe" }],
          },
        ],
      }).success,
    ).toBe(false);
  });

  test("parses a report index entry and requires at least one evidence id", () => {
    expect(analysisReportViewSchema.safeParse(report()).success).toBe(true);
    expect(
      analysisReportViewSchema.safeParse(report({ evidence_ids: [] })).success,
    ).toBe(false);
  });

  test("rejects a report artifact path outside the outputs root", () => {
    for (const artifact_path of [
      "/mnt/user-data/uploads/leak.md",
      "/mnt/user-data/outputs/../uploads/leak.md",
      "business-analysis.md",
    ]) {
      expect(
        analysisReportViewSchema.safeParse(report({ artifact_path })).success,
      ).toBe(false);
    }
  });

  test("rejects a report page that tries to smuggle artifact content", () => {
    expect(
      analysisReportPageSchema.safeParse({
        reports: [report({ content: "whole report body" })],
        has_more: false,
        next_before_created_at: null,
        next_before_id: null,
      }).success,
    ).toBe(false);
  });

  test("the parse error carries only a stable reason", () => {
    try {
      parseExternal(datasourceViewSchema, {
        id: "ds-1",
        name: "x",
        engine: "postgresql",
      });
      throw new Error("expected a parse failure");
    } catch (error) {
      expect(error).toBeInstanceOf(AnalyticsParseError);
      const parseError = error as AnalyticsParseError;
      expect(parseError.reason).toBe("invalid_analytics_response");
      expect(parseError.message).toBe("invalid_analytics_response");
    }
  });

  test("the parse error never echoes the offending value", () => {
    const secret = "postgres://user:pw@host/db";
    try {
      parseExternal(datasourceViewSchema, { engine: secret });
      throw new Error("expected a parse failure");
    } catch (error) {
      expect((error as Error).message).not.toContain("postgres");
      expect(JSON.stringify(error)).not.toContain("postgres");
    }
  });
});
