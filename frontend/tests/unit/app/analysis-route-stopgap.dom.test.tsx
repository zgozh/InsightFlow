import { afterEach, describe, expect, it, rs } from "@rstest/core";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";

import AnalysisThreadPage from "@/app/workspace/analysis/[thread_id]/page";
import type { Locale } from "@/core/i18n";
import { clientTranslations } from "@/core/i18n/client-translations";
import { I18nContext } from "@/core/i18n/context";
import type { I18nContextType } from "@/core/i18n/context";

const state = rs.hoisted(() => ({
  threadId: "ordinary-thread",
  metadata: {
    data: { metadata: { analysis_mode: false } } as unknown,
    isError: false,
    isFetching: false,
    isLoading: false,
  },
  mountedMode: undefined as string | undefined,
  metadataCalls: [] as string[],
}));

rs.mock("next/navigation", () => ({
  useParams: () => ({ thread_id: state.threadId }),
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

rs.mock("@/core/threads/hooks", () => ({
  useThreadMetadata: (threadId: string) => {
    state.metadataCalls.push(threadId);
    return state.metadata;
  },
}));

rs.mock("@/components/workspace/chats/chat-page", () => ({
  default: ({ mode }: { mode: string }) => {
    state.mountedMode = mode;
    return <div>analysis runtime mounted</div>;
  },
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
  state.threadId = "ordinary-thread";
  state.metadata = {
    data: { metadata: { analysis_mode: false } },
    isError: false,
    isFetching: false,
    isLoading: false,
  };
  state.mountedMode = undefined;
  state.metadataCalls = [];
});

describe("controlled analysis route admission", () => {
  it.each([
    ["en-US", "This ID belongs to a regular chat and will not be upgraded."],
    ["zh-CN", "此 ID 属于普通聊天线程，不会被提升为分析线程。"],
  ] as const)(
    "does not mount the chat runtime for an ordinary thread in %s",
    (locale, messagePrefix) => {
      renderAnalysisRoute(locale);

      expect(screen.getByText(new RegExp(messagePrefix))).toBeTruthy();
      expect(
        screen
          .getByRole("link", {
            name: clientTranslations[locale].analysisUnavailable
              .goToNewAnalysis,
          })
          .getAttribute("href"),
      ).toBe("/workspace/analysis/new");
      expect(screen.queryByText("analysis runtime mounted")).toBeNull();
      expect(state.metadataCalls).toEqual(["ordinary-thread"]);
      expect(state.mountedMode).toBeUndefined();
    },
  );

  it("mounts analysis runtime only after the persisted marker is confirmed", () => {
    state.threadId = "verified-analysis-thread";
    state.metadata = {
      data: { metadata: { analysis_mode: true } },
      isError: false,
      isFetching: false,
      isLoading: false,
    };

    renderAnalysisRoute("en-US");

    expect(screen.getByText("analysis runtime mounted")).toBeTruthy();
    expect(state.mountedMode).toBe("analysis");
    expect(state.metadataCalls).toEqual(["verified-analysis-thread"]);
  });

  it("keeps missing and corrupt analysis ids outside the chat runtime", () => {
    state.threadId = "missing-analysis-thread";
    state.metadata.data = null;
    renderAnalysisRoute("en-US");
    expect(screen.getByText(/This analysis thread was not found/)).toBeTruthy();
    expect(screen.queryByText("analysis runtime mounted")).toBeNull();
    cleanup();

    state.threadId = "corrupt-analysis-thread";
    state.metadata = {
      data: undefined,
      isError: true,
      isFetching: false,
      isLoading: false,
    };
    renderAnalysisRoute("en-US");
    expect(screen.getByText(/could not be verified/)).toBeTruthy();
    expect(screen.queryByText("analysis runtime mounted")).toBeNull();
  });

  it("opens the new analysis entry without reading an existing thread", () => {
    state.threadId = "new";

    renderAnalysisRoute("en-US");

    expect(screen.getByText("analysis runtime mounted")).toBeTruthy();
    expect(state.mountedMode).toBe("analysis");
    expect(state.metadataCalls).toEqual([]);
  });
});
