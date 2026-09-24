import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

test.describe("Sidebar navigation", () => {
  test("sidebar contains the InsightFlow workspace nav links", async ({
    page,
  }) => {
    mockLangGraphAPI(page);

    await page.goto("/workspace/chats/new");

    // Sidebar uses data-sidebar="menu-button" with asChild rendering on <Link>
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
      await expect(sidebar.locator(`a[href='${href}']`)).toBeVisible({
        timeout: 15_000,
      });
    }
    // Phase 5 删除了上游的 Agents 与 Capability Center 入口：它们不再可达。
    await expect(sidebar.locator("a[href='/workspace/agents']")).toHaveCount(0);
    await expect(
      sidebar.locator("a[href='/workspace/capabilities']"),
    ).toHaveCount(0);
  });

  test("Metrics link navigates to the metrics page", async ({ page }) => {
    mockLangGraphAPI(page);

    await page.goto("/workspace/chats/new");

    const sidebar = page.locator("[data-sidebar='sidebar']");
    const metricsLink = sidebar.locator("a[href='/workspace/metrics']");
    await expect(metricsLink).toBeVisible({ timeout: 15_000 });
    await metricsLink.click();

    await page.waitForURL("**/workspace/metrics");
    await expect(page).toHaveURL(/\/workspace\/metrics/);
  });

  test("mobile welcome layout stays within viewport and opens sidebar", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 664 });
    mockLangGraphAPI(page);

    await page.goto("/workspace/chats/new");
    await page.evaluate(() => {
      document.cookie = "locale=zh-CN; path=/; SameSite=Lax";
    });
    await page.reload();

    const viewportWidth = page.viewportSize()?.width ?? 390;
    const expectInsideViewport = async (
      locator: ReturnType<typeof page.locator>,
    ) => {
      await expect(locator).toBeVisible({ timeout: 15_000 });
      const box = await locator.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(-1);
      expect(box!.x + box!.width).toBeLessThanOrEqual(viewportWidth + 1);
    };

    await expectInsideViewport(page.getByText(/从受控经营数据分析/).first());
    await expectInsideViewport(page.getByRole("textbox").first());
    await expectInsideViewport(page.locator("[data-slot='suggestions-list']"));

    const mobileSidebarTrigger = page
      .locator("[data-sidebar='trigger']:visible")
      .first();
    await expect(mobileSidebarTrigger).toBeVisible();
    const triggerBox = await mobileSidebarTrigger.boundingBox();
    expect(triggerBox).not.toBeNull();
    const triggerReceivesPointerEvents = await page.evaluate(
      ({ x, y }) => {
        const trigger = document.elementFromPoint(x, y);
        return trigger?.closest("[data-sidebar='trigger']") !== null;
      },
      {
        x: triggerBox!.x + triggerBox!.width / 2,
        y: triggerBox!.y + triggerBox!.height / 2,
      },
    );
    expect(triggerReceivesPointerEvents).toBe(true);
    await page.mouse.click(
      triggerBox!.x + triggerBox!.width / 2,
      triggerBox!.y + triggerBox!.height / 2,
    );

    const mobileSidebar = page.locator(
      "[data-mobile='true'][data-sidebar='sidebar']",
    );
    await expect(mobileSidebar).toBeVisible();
    await expect(
      mobileSidebar.locator("a[href='/workspace/chats']"),
    ).toBeVisible();
    await expect(
      mobileSidebar.locator("a[href='/workspace/metrics']"),
    ).toBeVisible();
    await expect(
      mobileSidebar.locator("a[href='/workspace/agents']"),
    ).toHaveCount(0);
  });
});
