import { expect, test, type Page } from "@playwright/test";

/**
 * 认证入口的可见品牌（Phase 4 Fix 01）。
 *
 * `/login` 与 `/setup` 是最先被用户看到的两个页面，属于"最终保留界面"：它们所有**可达**渲染
 * 分支的产品标题都必须是 InsightFlow，并且页面上不得再出现上游产品名。
 *
 * 页面正文里会出现 DeerFlow 的地方只剩上游归属（About），而这两个页面不渲染 About，
 * 因此整页文本扫描是安全的。
 */

const SERVICE_UNAVAILABLE_TITLE = "Service temporarily unavailable";

async function mockAuthSurfaces(
  page: Page,
  options: {
    needsSetup: boolean;
    registrationEnabled?: boolean;
    setupStatus?: "ok" | "unavailable";
  },
) {
  await page.route("**/api/v1/auth/providers", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ providers: [] }),
    }),
  );
  await page.route("**/api/v1/auth/setup-status", (route) => {
    if (options.setupStatus === "unavailable") {
      return route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Gateway unavailable" }),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        needs_setup: options.needsSetup,
        registration_enabled: options.registrationEnabled ?? false,
      }),
    });
  });
}

async function expectNoUpstreamProductName(page: Page) {
  const body = (await page.locator("body").innerText()) ?? "";
  expect(body).not.toContain("DeerFlow");
}

test.describe("visible brand on the auth entry points", () => {
  test("login shows InsightFlow in both sign-in and sign-up modes", async ({
    page,
  }) => {
    await mockAuthSurfaces(page, {
      needsSetup: false,
      registrationEnabled: true,
    });
    await page.goto("/login");

    await expect(page.locator("h1")).toHaveText("InsightFlow");
    await expectNoUpstreamProductName(page);

    await page.getByRole("button", { name: /Don't have an account/i }).click();

    await expect(page.locator("h1")).toHaveText("InsightFlow");
    await expectNoUpstreamProductName(page);
  });

  test("login shows InsightFlow while the gateway is unreachable", async ({
    page,
  }) => {
    await mockAuthSurfaces(page, {
      needsSetup: false,
      setupStatus: "unavailable",
    });
    await page.goto("/login");

    await expect(page.getByText(SERVICE_UNAVAILABLE_TITLE)).toBeVisible();
    await expect(page.locator("h1")).toHaveText("InsightFlow");
    await expectNoUpstreamProductName(page);
  });

  test("the administrator setup form shows InsightFlow", async ({ page }) => {
    await mockAuthSurfaces(page, { needsSetup: true });
    await page.goto("/setup");

    await expect(
      page.getByRole("button", { name: "Create Admin Account" }),
    ).toBeVisible();
    await expect(page.locator("h1")).toHaveText("InsightFlow");
    await expectNoUpstreamProductName(page);
  });

  test("the setup recovery branch never shows the upstream product name", async ({
    page,
  }) => {
    await mockAuthSurfaces(page, {
      needsSetup: true,
      setupStatus: "unavailable",
    });
    await page.goto("/setup");

    await expect(page.getByText(SERVICE_UNAVAILABLE_TITLE)).toBeVisible();
    await expectNoUpstreamProductName(page);
  });
});
