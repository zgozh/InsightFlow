import { afterEach, expect, test, rs } from "@rstest/core";

const original = process.env.NEXT_PUBLIC_APP_VERSION;

afterEach(() => {
  rs.resetModules();
  if (original === undefined) {
    delete process.env.NEXT_PUBLIC_APP_VERSION;
  } else {
    process.env.NEXT_PUBLIC_APP_VERSION = original;
  }
});

test("aboutMarkdown heading interpolates the app version", async () => {
  process.env.NEXT_PUBLIC_APP_VERSION = "9.9.9-test";
  const { aboutMarkdown } =
    await import("@/components/workspace/settings/about-content");
  // The heading carries the version stamp and the product name.
  expect(aboutMarkdown).toContain("[About InsightFlow 9.9.9-test]");
  // 上游归属必须保留：派生自哪个版本、哪个项目，是可核对的许可证义务。
  expect(aboutMarkdown).toContain("DeerFlow v2.1.0-rc0");
  expect(aboutMarkdown).toContain("MIT License");
  expect(aboutMarkdown).toContain("DeerFlow 1.0");
});

test("aboutMarkdown heading reflects the package version when env is unset", async () => {
  delete process.env.NEXT_PUBLIC_APP_VERSION;
  const { APP_VERSION } = await import("@/version");
  const { aboutMarkdown } =
    await import("@/components/workspace/settings/about-content");
  // Positive: the heading carries the real resolved version. This catches an
  // empty or undefined APP_VERSION interpolation (`About InsightFlow ]` /
  // `About InsightFlow undefined]`), not just removal of the old literal.
  expect(aboutMarkdown).toContain(`[About InsightFlow ${APP_VERSION}]`);
});

test("the about page keeps upstream attribution but drops upstream CTAs", async () => {
  const { aboutMarkdown } =
    await import("@/components/workspace/settings/about-content");

  // 归属：保留。
  expect(aboutMarkdown).toContain("DeerFlow");
  // 导流：Phase 4 从产品 UI 移除官网／仓库／问题反馈／支持邮箱／star 图表。
  for (const banned of [
    "deerflow.tech",
    "support@deerflow.tech",
    "github.com/bytedance/deer-flow",
    "star-history.com",
  ]) {
    expect(aboutMarkdown).not.toContain(banned);
  }
});
