import { describe, expect, test } from "@rstest/core";

import { aboutMarkdown } from "@/components/workspace/settings/about-content";
import { enUS } from "@/core/i18n/locales/en-US";
import { zhCN } from "@/core/i18n/locales/zh-CN";

/**
 * 可见品牌契约（Phase 4 Fix 01）。
 *
 * 复验结论：认证入口与最终保留的 Workspace / 设置 / 定时任务界面都属于"最终保留界面"，
 * 其中的产品名必须是 InsightFlow；而 Phase 5 将物理删除的模块（Capability Center、Channels、
 * Custom Agent、Voice）本阶段**不**改名——它们的文案是待删代码的一部分，机械替换只会制造
 * 无意义的 diff。
 *
 * 因此这里同时钉住两件事：
 *
 * 1. 保留界面不得再出现上游产品名（否则就是漏改）；
 * 2. 待删模块**必须仍然**保留上游产品名（否则就是为了让扫描归零而偷改，属于越界）。
 *
 * 上游归属（MIT、版权、"派生自 DeerFlow v2.1.0-rc0"）永远不得为品牌扫描删除。
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

/** Phase 5 待删模块的 copy：本阶段刻意保留上游产品名。 */
const PHASE_5_KEYS = [
  "capabilities.description",
  "inputBox.voiceInputStart",
  "channels.descriptions.buzz",
  "settings.channels.description",
  "agents.saveRequested",
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

    test(`${locale.name}: Phase 5 modules keep the upstream name untouched`, () => {
      // 这些文案属于 Phase 5 待删模块：本阶段改名等于偷改待删代码，会掩盖真实删除范围。
      const renamed = PHASE_5_KEYS.filter(
        (path) => !readKey(locale.t, path).includes(UPSTREAM),
      );

      expect(renamed).toEqual([]);
    });
  }

  test("the About page keeps the upstream attribution", () => {
    // 品牌扫描绝不能以删除开源来源为代价。
    expect(aboutMarkdown).toContain("DeerFlow v2.1.0-rc0");
    expect(aboutMarkdown).toContain("MIT License");
    expect(aboutMarkdown).toContain("InsightFlow");
  });

  test("both locales expose the same retained keys", () => {
    for (const path of [...RETAINED_KEYS, ...PHASE_5_KEYS]) {
      expect(readKey(zhCN, path).length, path).toBeGreaterThan(0);
      expect(readKey(enUS, path).length, path).toBeGreaterThan(0);
    }
  });
});
