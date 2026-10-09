import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

test.describe("Landing page", () => {
  test("renders Chinese-first landing content without changing the locale cookie", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/");
    await page
      .context()
      .addCookies([{ name: "locale", value: "en-US", url: page.url() }]);
    await page.reload();

    await expect(page.locator('[lang="zh-CN"]')).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("lang", "en-US");
    const brand = page
      .locator("header")
      .first()
      .getByRole("link", { name: "InsightFlow", exact: true });
    await expect(brand).toBeVisible();
    await expect(brand).toHaveAttribute("href", "/");
    await expect(page.locator("h1")).toHaveCount(1);
    await expect(page.locator("h1")).toHaveText("InsightFlow");
    await expect(
      page.getByText("让每一个数据结论都有据可查", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("InsightFlow 把自然语言分析落在受控 SQL 与语义授权之上", {
        exact: false,
      }),
    ).toBeVisible();

    await expect(
      page.getByRole("link", { name: "进入工作台", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("治理先于自动化", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("数据源凭据只以密钥引用形式登记", { exact: false }),
    ).toBeVisible();
    await expect(
      page.getByText("从问题到可复核的结论", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("提出问题后，系统先规划取数路径", { exact: false }),
    ).toBeVisible();
    await expect(
      page.getByText("受控分析，结论可追溯。", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("InsightFlow 由个人开发者持续维护", {
        exact: false,
      }),
    ).toBeVisible();
    await expect(
      page.getByText("InsightFlow 按 MIT 许可证发布", { exact: false }),
    ).toBeVisible();
    await expect(page.locator('meta[name="description"]')).toHaveAttribute(
      "content",
      "受治理的企业数据分析工作台",
    );
    await expect(
      page.locator('meta[property="og:description"]'),
    ).toHaveAttribute("content", "受治理的企业数据分析工作台");

    await page.setViewportSize({ width: 375, height: 812 });
    await expect(
      page.getByText("让每一个数据结论都有据可查", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("InsightFlow 把自然语言分析落在受控 SQL 与语义授权之上", {
        exact: false,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "进入工作台", exact: true }),
    ).toBeVisible();
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth))
      .toBeLessThanOrEqual(375);
  });

  test("uses the product repository as an external desktop and mobile entry", async ({
    page,
  }) => {
    await page.goto("/");

    const desktopRepository = page
      .locator("header nav")
      .getByRole("link", { name: "GitHub 仓库", exact: true });
    await expect(desktopRepository).toHaveAttribute(
      "href",
      "https://github.com/zgozh/InsightFlow",
    );
    await expect(desktopRepository).toHaveAttribute("target", "_blank");
    await expect(desktopRepository).toHaveAttribute(
      "rel",
      "noopener noreferrer",
    );

    await page.setViewportSize({ width: 375, height: 812 });
    await page.getByRole("button", { name: "打开菜单" }).click();
    const mobileRepository = page.getByRole("link", {
      name: "GitHub 仓库",
      exact: true,
    });
    await expect(mobileRepository).toBeVisible();
    await expect(mobileRepository).toHaveAttribute(
      "href",
      "https://github.com/zgozh/InsightFlow",
    );
    await expect(mobileRepository).toHaveAttribute("target", "_blank");
    await expect(mobileRepository).toHaveAttribute(
      "rel",
      "noopener noreferrer",
    );
  });

  test("fills the hero with an immersive background at desktop and mobile sizes", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/");

    const copy = page.getByTestId("hero-copy");
    const art = page.getByTestId("hero-background");
    await expect(copy).toBeVisible();
    await expect(art).toBeVisible();

    const desktopCopy = await copy.boundingBox();
    const desktopArt = await art.boundingBox();
    if (!desktopCopy || !desktopArt) {
      throw new Error("Desktop hero regions must have visible bounds");
    }
    expect(desktopArt.width).toBe(1280);
    expect(desktopArt.height).toBeGreaterThan(600);
    expect(desktopCopy.x).toBeGreaterThanOrEqual(desktopArt.x);
    await expect(page.getByTestId("black-hole-motion")).toHaveAttribute(
      "data-motion-active",
      "true",
    );
    await page.screenshot({
      path: "test-results/phase-06f3f21-desktop-1280x720.png",
      fullPage: true,
    });

    await page.setViewportSize({ width: 375, height: 812 });
    const mobileCopy = await copy.boundingBox();
    const mobileArt = await art.boundingBox();
    if (!mobileCopy || !mobileArt) {
      throw new Error("Mobile hero regions must have visible bounds");
    }
    expect(mobileArt.width).toBe(375);
    expect(mobileArt.height).toBeGreaterThan(700);
    expect(mobileCopy.y).toBeGreaterThanOrEqual(mobileArt.y);
    await expect(page.getByTestId("black-hole-static")).toBeVisible();
    await page.screenshot({
      path: "test-results/phase-06f3f21-mobile-375x812.png",
      fullPage: true,
    });
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
      page.locator('head link[rel~="icon"][href="/favicon.png"]'),
    ).toHaveCount(1);
    await expect(
      page.locator('head link[rel~="icon"][href*="favicon.ico"]'),
    ).toHaveCount(0);
    const icon = await page.evaluate(async () => {
      const link = document.querySelector<HTMLLinkElement>(
        'head link[rel~="icon"][href="/favicon.png"]',
      );
      if (!link) throw new Error("EHT favicon link is missing");
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
    expect(icon.contentType).toContain("image/png");
    expect(icon.width).toBe(32);
    expect(icon.height).toBe(32);
    const legacyIcon = await page.request.get("/favicon.ico");
    expect(legacyIcon.status()).toBe(200);
    await expect(
      page.getByRole("link", { name: "原图 / ESO" }),
    ).toHaveAttribute("href", "https://www.eso.org/public/images/eso1907a/");
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

  test("keeps legacy project links out of the product UI", async ({ page }) => {
    await page.goto("/");

    // 产品外链指向当前仓库；旧站点和旧仓库不属于用户入口。
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

    await page.getByRole("link", { name: "进入工作台", exact: true }).click();

    // `/workspace` 是既有的默认入口，会重定向到新建会话。
    await page.waitForURL("**/workspace/chats/new");
    await expect(page).toHaveURL(/\/workspace\/chats\/new/);
  });
});
