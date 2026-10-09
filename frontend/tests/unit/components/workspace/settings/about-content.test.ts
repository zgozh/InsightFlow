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

test("aboutMarkdown presents the maintained product and license", async () => {
  process.env.NEXT_PUBLIC_APP_VERSION = "9.9.9-test";
  const { aboutMarkdown } =
    await import("@/components/workspace/settings/about-content");
  // The heading carries the version stamp and the product name.
  expect(aboutMarkdown).toContain("[About InsightFlow 9.9.9-test]");
  expect(aboutMarkdown).toContain("MIT License");
  expect(aboutMarkdown).toContain("个人开发者持续维护");
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

test("the about page uses InsightFlow branding and no legacy links", async () => {
  const { aboutMarkdown } =
    await import("@/components/workspace/settings/about-content");

  expect(aboutMarkdown).toContain("InsightFlow");
  expect(aboutMarkdown).not.toMatch(
    /DeerFlow|ByteDance|deerflow\.tech|bytedance\/deer-flow/i,
  );
});
