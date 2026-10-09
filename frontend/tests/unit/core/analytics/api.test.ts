import { beforeEach, describe, expect, test, rs } from "@rstest/core";

rs.mock("@/core/api/fetcher", () => ({ fetch: rs.fn() }));
rs.mock("@/core/config", () => ({ getBackendBaseURL: () => "" }));

import {
  adminCreateMetric,
  adminListDatasources,
  adminRemovePolicy,
  adminReplaceSchema,
  AnalyticsRequestError,
  adminGrantMetric,
  listAudits,
  listDatasources,
  listMetrics,
  listReports,
  adminListMetricGrants,
  adminRevokeMetric,
} from "@/core/analytics/api";
import { fetch as fetcher } from "@/core/api/fetcher";

const mockedFetch = rs.mocked(fetcher);

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function lastCall(): [string, RequestInit | undefined] {
  const call = mockedFetch.mock.calls.at(-1);
  if (!call) throw new Error("fetcher was not called");
  return call as [string, RequestInit | undefined];
}

/** 请求体一定是字符串：`String(object)` 会退化成 `[object Object]`，这类断言写不出有效证据。 */
function readJsonBody(init: RequestInit | undefined): unknown {
  if (typeof init?.body !== "string") {
    throw new Error("the request body was not a JSON string");
  }
  return JSON.parse(init.body) as unknown;
}

/** 请求地址可能是字符串或 Request；两种都要如实取出 URL 再断言。 */
function calledUrls(): string[] {
  return mockedFetch.mock.calls.map((call) => {
    const request = call[0];
    return typeof request === "string" ? request : request.url;
  });
}

beforeEach(() => {
  mockedFetch.mockReset();
});

describe("analytics api client", () => {
  test("reads the catalogue through the authenticated fetcher", async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse(200, {
        datasources: [
          {
            id: "ds-1",
            name: "Warehouse",
            engine: "postgresql",
            default_schema: "public",
            status: "active",
          },
        ],
      }),
    );

    const datasources = await listDatasources();
    const [url, init] = lastCall();

    expect(datasources).toHaveLength(1);
    expect(url).toBe("/api/analytics/datasources");
    // GET 不带 CSRF 头：fetcher 只在写方法上继承它。
    expect(init?.method ?? "GET").toBe("GET");
  });

  test("requests metrics from the analytics prefix", async () => {
    mockedFetch.mockResolvedValueOnce(jsonResponse(200, { metrics: [] }));
    await listMetrics();
    expect(lastCall()[0]).toBe("/api/analytics/metrics");
  });

  test("sends the audit keyset cursor as query parameters", async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse(200, {
        audits: [],
        has_more: false,
        next_before_started_at: null,
        next_before_id: null,
      }),
    );

    await listAudits({
      limit: 20,
      cursor: { started_at: "2026-09-22T12:00:00+00:00", id: "audit-9" },
    });
    const query = new URLSearchParams(lastCall()[0].split("?")[1] ?? "");

    expect(query.get("limit")).toBe("20");
    expect(query.get("before_started_at")).toBe("2026-09-22T12:00:00+00:00");
    expect(query.get("before_id")).toBe("audit-9");
  });

  test("omits empty query parameters entirely", async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse(200, {
        audits: [],
        has_more: false,
        next_before_started_at: null,
        next_before_id: null,
      }),
    );

    await listAudits();
    expect(lastCall()[0]).toBe("/api/analytics/audits");
  });

  test("uses the report cursor field names, not the audit ones", async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse(200, {
        reports: [],
        has_more: false,
        next_before_created_at: null,
        next_before_id: null,
      }),
    );

    await listReports({
      cursor: { created_at: "2026-09-22T12:00:00+00:00", id: "report-9" },
    });
    const query = new URLSearchParams(lastCall()[0].split("?")[1] ?? "");

    expect(query.get("before_created_at")).toBe("2026-09-22T12:00:00+00:00");
    expect(query.get("before_started_at")).toBeNull();
  });

  test("sends the admin report lookup with an explicit principal", async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse(200, {
        reports: [],
        has_more: false,
        next_before_created_at: null,
        next_before_id: null,
      }),
    );

    const { adminListReports } = await import("@/core/analytics/api");
    await adminListReports("user-9");
    const query = new URLSearchParams(lastCall()[0].split("?")[1] ?? "");

    expect(lastCall()[0].startsWith("/api/analytics/admin/reports?")).toBe(
      true,
    );
    expect(query.get("principal_id")).toBe("user-9");
  });

  test("every write request carries a JSON content type", async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse(201, {
        key: "revenue",
        name: "Revenue",
        description: "Total revenue",
        expression: "sum(amount)",
        dimensions: [],
        version: 2,
        status: "active",
      }),
    );

    await adminCreateMetric({
      key: "revenue",
      name: "Revenue",
      description: "Total revenue",
      expression: "sum(amount)",
      dimensions: [],
      version: 2,
      status: "active",
    });

    const [url, init] = lastCall();
    expect(url).toBe("/api/analytics/admin/metrics");
    expect(init?.method).toBe("POST");
    expect((init?.headers as Record<string, string>)["Content-Type"]).toBe(
      "application/json",
    );
    expect(readJsonBody(init)).toMatchObject({
      key: "revenue",
      version: 2,
    });
  });

  test("percent encodes identifiers in the path", async () => {
    mockedFetch.mockResolvedValueOnce(jsonResponse(200, { datasources: [] }));
    await adminListDatasources();
    mockedFetch.mockResolvedValueOnce(
      jsonResponse(200, {
        datasource_id: "ds 1",
        engine: "postgresql",
        version: "s1",
        default_schema: "public",
        relations: [],
      }),
    );

    await adminReplaceSchema("ds 1", {
      version: "s1",
      expected_version: null,
      default_schema: "public",
      relations: [],
    });

    expect(lastCall()[0]).toBe(
      "/api/analytics/admin/datasources/ds%201/schema",
    );
  });

  test("reads metric grants without putting principal data in the query", async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse(200, { principal_ids: ["user/ 1"] }),
    );

    await adminListMetricGrants("revenue / net");

    expect(lastCall()[0]).toBe(
      "/api/analytics/admin/metrics/revenue%20%2F%20net/grants",
    );
    expect(lastCall()[1]?.method ?? "GET").toBe("GET");
    expect(lastCall()[0]).not.toContain("?");
  });

  test("grant and revoke use encoded paths and send no body", async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse(200, { principal_id: "user/ 1", granted: true }),
    );

    await adminGrantMetric("revenue / net", "user/ 1");

    expect(lastCall()[0]).toBe(
      "/api/analytics/admin/metrics/revenue%20%2F%20net/grants/user%2F%201",
    );
    expect(lastCall()[1]?.method).toBe("PUT");
    expect(lastCall()[1]?.body).toBeUndefined();

    mockedFetch.mockResolvedValueOnce(jsonResponse(200, { removed: true }));
    await adminRevokeMetric("revenue / net", "user/ 1");
    expect(lastCall()[0]).toBe(
      "/api/analytics/admin/metrics/revenue%20%2F%20net/grants/user%2F%201",
    );
    expect(lastCall()[1]?.method).toBe("DELETE");
    expect(lastCall()[1]?.body).toBeUndefined();
  });

  test("a grant acknowledgement must match the submitted principal and be strict", async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse(200, { principal_id: "another-user", granted: true }),
    );
    await expect(adminGrantMetric("revenue", "user-1")).rejects.toMatchObject({
      reason: "invalid_analytics_response",
    });

    mockedFetch.mockResolvedValueOnce(
      jsonResponse(200, { principal_id: "user-1", granted: true, extra: 1 }),
    );
    await expect(adminGrantMetric("revenue", "user-1")).rejects.toMatchObject({
      reason: "invalid_analytics_response",
    });
  });

  test("a bodyless delete never invents a JSON payload", async () => {
    mockedFetch.mockResolvedValueOnce(new Response(null, { status: 204 }));

    await adminRemovePolicy("ds-1", "user-1");
    const [url, init] = lastCall();

    expect(url).toBe("/api/analytics/admin/datasources/ds-1/policies/user-1");
    expect(init?.method).toBe("DELETE");
    expect(init?.body).toBeUndefined();
  });

  test("maps a stable server error body onto the error code", async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse(409, { detail: { code: "analytics_version_conflict" } }),
    );

    await expect(listDatasources()).rejects.toMatchObject({
      status: 409,
      code: "analytics_version_conflict",
    });
  });

  test("an unrecognised error body yields a null code instead of echoing it", async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse(500, { detail: "Traceback: postgres://user:pw@host/db" }),
    );

    try {
      await listDatasources();
      throw new Error("expected a rejection");
    } catch (error) {
      const requestError = error as AnalyticsRequestError;
      expect(requestError).toBeInstanceOf(AnalyticsRequestError);
      expect(requestError.code).toBeNull();
      expect(requestError.message).not.toContain("postgres");
    }
  });

  test("a malformed success body becomes a stable parse error", async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse(200, { datasources: [{ id: "ds-1" }] }),
    );

    await expect(listDatasources()).rejects.toMatchObject({
      reason: "invalid_analytics_response",
    });
  });

  test("a non-JSON success body becomes a stable error, not a crash", async () => {
    mockedFetch.mockResolvedValueOnce(
      new Response("<html>gateway</html>", {
        status: 200,
        headers: { "Content-Type": "text/html" },
      }),
    );

    await expect(listDatasources()).rejects.toBeInstanceOf(
      AnalyticsRequestError,
    );
  });

  test("no request URL carries sql, a token or a secret", async () => {
    mockedFetch.mockResolvedValue(
      jsonResponse(200, {
        audits: [],
        has_more: false,
        next_before_started_at: null,
        next_before_id: null,
      }),
    );

    await listAudits({ limit: 20 });
    for (const url of calledUrls()) {
      expect(url).not.toContain("sql");
      expect(url).not.toContain("plan_id");
      expect(url).not.toContain("secret");
      expect(url).not.toContain("token");
    }
  });
});
