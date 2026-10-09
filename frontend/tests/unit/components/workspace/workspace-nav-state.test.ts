import { describe, expect, it } from "@rstest/core";

import { getWorkspaceNavigationActiveState } from "@/components/workspace/workspace-nav-state";

describe("workspace navigation active state", () => {
  it.each([
    [
      "/workspace/chats",
      { newChat: false, newAnalysis: false, analysis: true },
    ],
    [
      "/workspace/chats/new",
      { newChat: true, newAnalysis: false, analysis: false },
    ],
    [
      "/workspace/chats/thread-1",
      { newChat: false, newAnalysis: false, analysis: false },
    ],
    [
      "/workspace/analysis/new",
      { newChat: false, newAnalysis: true, analysis: false },
    ],
    [
      "/workspace/analysis/thread-1",
      { newChat: false, newAnalysis: false, analysis: true },
    ],
    [
      "/workspace/datasources",
      { newChat: false, newAnalysis: false, analysis: false },
    ],
    [
      "/workspace/history",
      { newChat: false, newAnalysis: false, analysis: false },
    ],
  ])("marks only the matching workflow active at %s", (pathname, expected) => {
    expect(getWorkspaceNavigationActiveState(pathname)).toEqual(expected);
  });
});
