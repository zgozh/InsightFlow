import { describe, expect, test } from "@rstest/core";

import { aboutMarkdown } from "@/components/workspace/settings/about-content";
import { enUS } from "@/core/i18n/locales/en-US";
import { zhCN } from "@/core/i18n/locales/zh-CN";

/**
 * 可见品牌契约（Phase 4 Fix 01）。
 *
 * 认证入口与最终保留的 Workspace / 设置 / 定时任务界面使用 InsightFlow
 * 品牌；上游许可证、版权和派生归属继续保留在 About 页面。
 */

const PRODUCT = "InsightFlow";
const UPSTREAM = "DeerFlow";

/** 最终保留界面的 copy：必须是 InsightFlow，且不得出现上游产品名。 */
const RETAINED_KEYS = [
  "inputBox.disclaimer",
  "backgroundTasks.cancellationRetrying",
  "backgroundTasks.notificationRetrying",
  "backgroundTasks.trackingDegraded",
  "scheduledTasks.context.reuseNoticeDescription",
  "toolCalls.skillInstallTooltip",
  "shortcuts.keyboardShortcutsDescription",
  "settings.description",
  "settings.memory.description",
  "settings.notification.description",
  "settings.notification.testTitle",
  "settings.skills.emptyDescription",
  "settings.account.ssoPasswordMessage",
  "login.rememberMeDescription",
  "login.adminSetupRequiredDescription",
  "workspace.about",
] as const;

type Locale = { name: string; t: unknown };

const LOCALES: Locale[] = [
  { name: "zh-CN", t: zhCN },
  { name: "en-US", t: enUS },
];

function readKey(translations: unknown, path: string): string {
  let current: unknown = translations;
  for (const segment of path.split(".")) {
    if (typeof current !== "object" || current === null) {
      return "";
    }
    current = (current as Record<string, unknown>)[segment];
  }
  if (typeof current === "function") {
    return String((current as (attempt: number) => unknown)(2));
  }
  return typeof current === "string" ? current : "";
}

describe("visible InsightFlow branding", () => {
  for (const locale of LOCALES) {
    test(`${locale.name}: retained copy names InsightFlow and never DeerFlow`, () => {
      const missingProductName = RETAINED_KEYS.filter(
        (path) => !readKey(locale.t, path).includes(PRODUCT),
      );
      const stillUpstream = RETAINED_KEYS.filter((path) =>
        readKey(locale.t, path).includes(UPSTREAM),
      );

      expect(missingProductName).toEqual([]);
      expect(stillUpstream).toEqual([]);
    });

    test(`${locale.name}: the chat input disclaimer names the product`, () => {
      const disclaimer = readKey(locale.t, "inputBox.disclaimer");

      expect(disclaimer).toContain(PRODUCT);
      expect(disclaimer).not.toContain(UPSTREAM);
    });
  }

  test("the About page shows InsightFlow and the license", () => {
    expect(aboutMarkdown).toContain("MIT License");
    expect(aboutMarkdown).toContain("InsightFlow");
    expect(aboutMarkdown).toContain("LICENSE");
    expect(aboutMarkdown).not.toContain(UPSTREAM);
  });

  test("both locales expose the same retained keys", () => {
    for (const path of RETAINED_KEYS) {
      expect(readKey(zhCN, path).length, path).toBeGreaterThan(0);
      expect(readKey(enUS, path).length, path).toBeGreaterThan(0);
    }
  });
});
