import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

test.describe("Landing page", () => {
  test("renders the InsightFlow header and hero section", async ({ page }) => {
    await page.goto("/");

    const brand = page
      .locator("header")
      .first()
      .getByRole("link", { name: "InsightFlow", exact: true });
    await expect(brand).toBeVisible();
    await expect(brand).toHaveAttribute("href", "/");
    await expect(page.locator("h1")).toHaveCount(1);
    await expect(page.locator("h1")).toContainText("InsightFlow");

    // Hero 的唯一 CTA：进入工作台。
    await expect(
      page.getByRole("link", { name: /enter the workspace/i }),
    ).toBeVisible();
  });

  test("uses the product repository as an external desktop and mobile entry", async ({
    page,
  }) => {
    await page.goto("/");

    const desktopWorkspace = page
      .locator("header nav")
      .getByRole("link", { name: "Workspace", exact: true });
    await expect(desktopWorkspace).toHaveAttribute(
      "href",
      "https://github.com/zgozh/InsightFlow",
    );
    await expect(desktopWorkspace).toHaveAttribute("target", "_blank");
    await expect(desktopWorkspace).toHaveAttribute(
      "rel",
      "noopener noreferrer",
    );

    await page.setViewportSize({ width: 375, height: 812 });
    await page.getByRole("button", { name: "Open menu" }).click();
    const mobileWorkspace = page.getByRole("link", {
      name: "Workspace",
      exact: true,
    });
    await expect(mobileWorkspace).toBeVisible();
    await expect(mobileWorkspace).toHaveAttribute(
      "href",
      "https://github.com/zgozh/InsightFlow",
    );
    await expect(mobileWorkspace).toHaveAttribute("target", "_blank");
    await expect(mobileWorkspace).toHaveAttribute("rel", "noopener noreferrer");
  });

  test("loads the red-orange favicon and keeps static art without canvas", async ({
    page,
  }) => {
    await page.addInitScript(() => {
      Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
        configurable: true,
        value: () => null,
      });
    });
    await page.goto("/");

    await expect(
      page.locator('head link[rel~="icon"][href="/favicon.svg"]'),
    ).toHaveCount(1);
    await expect(
      page.locator('head link[rel~="icon"][href*="favicon.ico"]'),
    ).toHaveCount(0);
    const icon = await page.evaluate(async () => {
      const link = document.querySelector<HTMLLinkElement>(
        'head link[rel~="icon"][href="/favicon.svg"]',
      );
      if (!link) throw new Error("SVG favicon link is missing");
      const response = await fetch(link.href, { cache: "no-store" });
      const image = new Image();
      image.src = link.href;
      await image.decode();
      return {
        status: response.status,
        contentType: response.headers.get("content-type"),
        width: image.naturalWidth,
        height: image.naturalHeight,
      };
    });
    expect(icon.status).toBe(200);
    expect(icon.contentType).toContain("image/svg+xml");
    expect(icon.width).toBe(32);
    expect(icon.height).toBe(32);
    await expect(page.getByTestId("black-hole-static")).toBeVisible();
    await expect(page.getByTestId("black-hole-motion")).toHaveAttribute(
      "data-motion-active",
      "false",
    );
  });

  test("pauses hero particles for reduced motion and when scrolled offscreen", async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");

    await expect(page.getByTestId("black-hole-static")).toBeVisible();
    await expect(page.getByTestId("black-hole-motion")).toHaveAttribute(
      "data-motion-active",
      "false",
    );

    await page.emulateMedia({ reducedMotion: "no-preference" });
    await expect(page.getByTestId("black-hole-motion")).toHaveAttribute(
      "data-motion-active",
      "true",
    );
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await expect(page.getByTestId("black-hole-motion")).toHaveAttribute(
      "data-motion-active",
      "false",
    );
  });

  test("keeps upstream CTAs out of the product UI", async ({ page }) => {
    await page.goto("/");

    // 产品仓库入口是上方明确配置的 GitHub 链接；此处只禁止上游官网、上游仓库等旧导流。
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
