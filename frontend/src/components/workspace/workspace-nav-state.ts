export function getWorkspaceNavigationActiveState(pathname: string) {
  const isNewChat = pathname === "/workspace/chats/new";
  const isAnalysisList = pathname === "/workspace/chats";
  const isNewAnalysis = pathname === "/workspace/analysis/new";
  const isAnalysisThread =
    pathname.startsWith("/workspace/analysis/") && !isNewAnalysis;

  return {
    newChat: isNewChat,
    newAnalysis: isNewAnalysis,
    analysis: isAnalysisList || isAnalysisThread,
  };
}
