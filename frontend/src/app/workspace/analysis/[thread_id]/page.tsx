import ChatPage from "@/components/workspace/chats/chat-page";
import { ChatProviders } from "@/components/workspace/chats/chat-providers";

/**
 * 一段经营分析会话，`/workspace/analysis/new` 也由这个动态段承接（与 `/workspace/chats/new` 同构）。
 *
 * 这里只做一件事：挂上与 `/workspace/chats/**` **完全相同**的 providers，然后渲染同一个
 * `ChatPage`。会话创建、SSE 流式、历史分页与 artifact 预览全部沿用既有主链，本路由不复制任何
 * 状态机；`ChatPage` 依据当前路径决定是否挂载分析轨迹面板。
 */
export default function AnalysisThreadPage() {
  return (
    <ChatProviders>
      <ChatPage />
    </ChatProviders>
  );
}
