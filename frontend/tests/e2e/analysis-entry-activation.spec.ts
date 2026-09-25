import { expect, test } from "@playwright/test";

import {
  handleRunStream,
  MOCK_THREAD_ID,
  mockLangGraphAPI,
} from "./utils/mock-api";

test.describe("controlled analysis entry", () => {
  test("persists analysis kind before streaming on the same thread id", async ({
    page,
  }) => {
    let createRequest: { kind?: string; thread_id?: string } | undefined;
    let runtimeThreadCreate: { kind?: string; thread_id?: string } | undefined;
    const streamedThreadIds: string[] = [];
    const streamPaths: string[] = [];

    mockLangGraphAPI(page);
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (
        request.method() !== "POST" ||
        !url.pathname.endsWith("/runs/stream")
      ) {
        return;
      }
      streamPaths.push(url.pathname);
      const threadId = /\/threads\/([^/]+)\/runs\/stream/.exec(
        url.pathname,
      )?.[1];
      if (threadId) {
        streamedThreadIds.push(decodeURIComponent(threadId));
      }
    });
    // Record the Gateway-specific create call, then let the shared mock retain
    // the returned analysis marker for subsequent metadata reads.
    await page.route("**/api/threads", async (route) => {
      if (route.request().method() === "POST") {
        createRequest = route.request().postDataJSON() as {
          kind?: string;
          thread_id?: string;
        };
      }
      await route.fallback();
    });
    await page.route("**/api/langgraph/threads", async (route) => {
      if (route.request().method() === "POST") {
        runtimeThreadCreate = route.request().postDataJSON() as {
          kind?: string;
          thread_id?: string;
        };
      }
      await route.fallback();
    });

    await page.goto("/workspace/analysis/new");
    const composer = page.getByPlaceholder(/how can i assist you/i);
    await expect(composer).toBeVisible();
    await composer.fill("Check a synthetic business question");
    await composer.press("Enter");

    await expect.poll(() => streamedThreadIds.length).toBeGreaterThan(0);
    expect(createRequest?.kind).toBe("analysis");
    expect(runtimeThreadCreate?.kind).toBe("analysis");
    expect(runtimeThreadCreate?.thread_id).toBe(createRequest?.thread_id);
    expect(streamedThreadIds).toEqual([createRequest?.thread_id]);
    expect(streamPaths).toEqual([
      `/api/langgraph/threads/${createRequest?.thread_id}/runs/stream`,
    ]);
    await expect(page.getByText("Hello from DeerFlow!")).toBeVisible();
    await expect(page).toHaveURL(
      new RegExp(`/workspace/analysis/${createRequest?.thread_id}$`),
    );
  });

  test("does not stream when analysis thread creation conflicts", async ({
    page,
  }) => {
    let streamed = false;
    mockLangGraphAPI(page, {
      runStreamHandler: async (route) => {
        streamed = true;
        await handleRunStream(route);
      },
    });
    await page.route("**/api/threads", async (route) => {
      if (route.request().method() === "POST") {
        return route.fulfill({
          status: 409,
          contentType: "application/json",
          body: JSON.stringify({ detail: { code: "thread_kind_conflict" } }),
        });
      }
      return route.fallback();
    });

    await page.goto("/workspace/analysis/new");
    const composer = page.getByPlaceholder(/how can i assist you/i);
    await expect(composer).toBeVisible();
    await composer.fill("This message must not be sent");
    await composer.press("Enter");

    await expect(
      page.getByText("This thread already has a different kind.", {
        exact: false,
      }),
    ).toBeVisible();
    await expect(page).toHaveURL(/\/workspace\/analysis\/new$/);
    expect(streamed).toBe(false);
  });

  test("does not mount analysis for a regular chat id", async ({ page }) => {
    let streamed = false;
    mockLangGraphAPI(page, {
      threads: [
        {
          thread_id: MOCK_THREAD_ID,
          title: "Synthetic ordinary chat",
          metadata: { analysis_mode: false },
          messages: [],
        },
      ],
      runStreamHandler: async (route) => {
        streamed = true;
        await handleRunStream(route);
      },
    });

    await page.goto(`/workspace/analysis/${MOCK_THREAD_ID}`);

    await expect(page.getByRole("status")).toContainText(
      "belongs to a regular chat",
    );
    await expect(page.getByPlaceholder(/how can i assist you/i)).toHaveCount(0);
    expect(streamed).toBe(false);
  });

  test("a report link cannot open analysis when its thread is not visible", async ({
    page,
  }) => {
    mockLangGraphAPI(page);
    await page.route(/\/api\/analytics\/reports(?:\?|$)/, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          reports: [
            {
              id: "synthetic-unowned-report",
              principal_id: "synthetic-other-principal",
              thread_id: MOCK_THREAD_ID,
              run_id: "synthetic-run",
              artifact_path: "/mnt/user-data/outputs/synthetic.md",
              title: "Synthetic report",
              status: "published",
              evidence_ids: ["e".repeat(64)],
              created_at: "2026-09-22T12:00:00+00:00",
            },
          ],
          has_more: false,
          next_before_created_at: null,
          next_before_id: null,
        }),
      }),
    );

    await page.goto("/workspace/reports");
    await page.getByTestId("report-open-analysis").click();

    await expect(page.getByRole("status")).toContainText(
      "This analysis thread was not found",
    );
    await expect(page.getByPlaceholder(/how can i assist you/i)).toHaveCount(0);
    await expect(page.locator("a[href*='/artifacts/']")).toHaveCount(0);
  });
});
