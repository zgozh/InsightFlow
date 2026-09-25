import { afterEach, describe, expect, it, rs } from "@rstest/core";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";

import AnalysisThreadPage from "@/app/workspace/analysis/[thread_id]/page";
import type { Locale } from "@/core/i18n";
import { clientTranslations } from "@/core/i18n/client-translations";
import { I18nContext } from "@/core/i18n/context";
import type { I18nContextType } from "@/core/i18n/context";

// Keep the route boundary real while making any accidental ordinary-chat mount
// observable as the thread/run requests and chat-path redirect it would enable.
rs.mock("@/components/workspace/chats/chat-providers", () => ({
  ChatProviders: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

rs.mock("@/components/workspace/chats/chat-page", () => ({
  default: function OrdinaryChatSentinel() {
    void fetch("/api/langgraph/threads", { method: "POST" });
    void fetch("/api/langgraph/threads/ordinary-chat/runs/stream", {
      method: "POST",
    });
    window.history.replaceState(null, "", "/workspace/chats/ordinary-chat");
    return <div>ordinary chat runtime mounted</div>;
  },
}));

rs.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: {
    children: ReactNode;
    href: string;
    className?: string;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

function renderAnalysisRoute(locale: Locale) {
  const contextValue: I18nContextType = {
    locale,
    setLocale: () => undefined,
    t: clientTranslations[locale],
  };

  return render(
    <I18nContext.Provider value={contextValue}>
      <AnalysisThreadPage />
    </I18nContext.Provider>,
  );
}

afterEach(() => {
  cleanup();
  rs.restoreAllMocks();
});

describe("analysis route stopgap", () => {
  it.each([
    [
      "en-US",
      "Controlled analysis is temporarily unavailable",
      "The controlled-analysis runtime has not completed its safety review. This page will not create an ordinary chat or start a chat run.",
      "Go to regular chat",
    ],
    [
      "zh-CN",
      "受控分析暂不可用",
      "受控分析运行环境尚未通过安全验证。此页面不会创建普通聊天，也不会启动聊天任务。",
      "前往普通聊天",
    ],
  ] as const)(
    "shows an explicit unavailable state in %s",
    (locale, title, description, linkLabel) => {
      const fetchSpy = rs
        .spyOn(globalThis, "fetch")
        .mockResolvedValue(new Response(null, { status: 204 }));
      const replaceStateSpy = rs
        .spyOn(window.history, "replaceState")
        .mockImplementation(() => undefined);
      const pushStateSpy = rs
        .spyOn(window.history, "pushState")
        .mockImplementation(() => undefined);

      renderAnalysisRoute(locale);

      expect(screen.getByRole("heading", { name: title }).textContent).toBe(
        title,
      );
      expect(screen.getByText(description).textContent).toBe(description);
      expect(
        screen.getByRole("link", { name: linkLabel }).getAttribute("href"),
      ).toBe("/workspace/chats/new");
      expect(screen.queryByText("ordinary chat runtime mounted")).toBeNull();
      expect(fetchSpy).not.toHaveBeenCalled();
      expect(replaceStateSpy).not.toHaveBeenCalled();
      expect(pushStateSpy).not.toHaveBeenCalled();
    },
  );
});
