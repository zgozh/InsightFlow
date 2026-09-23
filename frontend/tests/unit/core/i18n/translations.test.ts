import { describe, expect, it } from "@rstest/core";

import { loadTranslations } from "@/core/i18n/translations";

describe("core copy loading", () => {
  it("loads only the requested overseas and domestic copy", async () => {
    const [english, chinese] = await Promise.all([
      loadTranslations("en-US"),
      loadTranslations("zh-CN"),
    ]);
    expect(english.inputBox.disclaimer).toBe(
      "InsightFlow is AI and can make mistakes",
    );
    expect(chinese.inputBox.disclaimer).toBe(
      "内容由 InsightFlow 生成，重要信息请务必核查",
    );
    for (const key of [
      "agents",
      "capabilities",
      "channels",
      "projects",
      "trash",
    ]) {
      expect(key in english).toBe(false);
      expect(key in chinese).toBe(false);
    }
  });
});
