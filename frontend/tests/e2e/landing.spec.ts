import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

test.describe("Landing page", () => {
  test("renders the InsightFlow header and hero section", async ({ page }) => {
    await page.goto("/");

    await expect(
      page.locator("header").first().getByText("InsightFlow", { exact: true }),
    ).toBeVisible();
    await expect(page.locator("h1")).toHaveCount(1);
    await expect(page.locator("h1")).toContainText("InsightFlow");

    // Hero 的唯一 CTA：进入工作台。
    await expect(
      page.getByRole("link", { name: /enter the workspace/i }),
    ).toBeVisible();
  });

  test("keeps upstream CTAs out of the product UI", async ({ page }) => {
    await page.goto("/");

    // Phase 4 只替换用户可见品牌与默认入口：上游归属仍保留在 MIT LICENSE、README 与设置里的
    // 「关于」，但产品 UI 不再出现官网 / 仓库 / 问题反馈 / 支持邮箱 / star 导流。
    for (const banned of [
      "deerflow.tech",
      "support@deerflow.tech",
      "github.com/bytedance/deer-flow",
    ]) {
      await expect(page.locator(`a[href*="${banned}"]`)).toHaveCount(0);
      await expect(page.getByText(banned, { exact: false })).toHaveCount(0);
    }
    await expect(page.getByText(/star on github/i)).toHaveCount(0);
  });

  for (const width of [320, 375, 390]) {
    test(`does not overflow at ${width}px width`, async ({ page }) => {
      await page.setViewportSize({ width, height: 812 });
      await page.goto("/");

      await expect
        .poll(() => page.evaluate(() => document.documentElement.scrollWidth))
        .toBeLessThanOrEqual(width);
      await expect(page.locator("main").first()).toBeInViewport();
    });
  }

  test("the hero call to action navigates into the workspace", async ({
    page,
  }) => {
    mockLangGraphAPI(page);

    await page.goto("/");

    await page.getByRole("link", { name: /enter the workspace/i }).click();

    // `/workspace` 是既有的默认入口，会重定向到新建会话。
    await page.waitForURL("**/workspace/chats/new");
    await expect(page).toHaveURL(/\/workspace\/chats\/new/);
  });
});
