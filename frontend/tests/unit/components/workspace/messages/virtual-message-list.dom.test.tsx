import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { cleanup, render } from "@testing-library/react";

import { VirtualMessageList } from "@/components/workspace/messages/virtual-message-list";
import type { MessageGroup } from "@/core/messages/utils";

const scrollState = rs.hoisted(() => ({
  isAtBottom: true,
  scrollRef: { current: null as HTMLElement | null },
  scrollToBottom: rs.fn(),
  stopScroll: rs.fn(),
}));

rs.mock("use-stick-to-bottom", () => ({
  useStickToBottomContext: () => scrollState,
}));

function makeGroups(count: number): MessageGroup[] {
  return Array.from({ length: count }, (_, index) => ({
    type: "human",
    id: `group-${index}`,
    messages: [],
  }));
}

describe("VirtualMessageList tail following", () => {
  beforeEach(() => {
    scrollState.isAtBottom = true;
    scrollState.scrollRef.current = null;
    scrollState.scrollToBottom.mockClear();
    scrollState.stopScroll.mockClear();
  });

  afterEach(cleanup);

  it("keeps following when history growth clears the current bottom signal", () => {
    const initialGroups = makeGroups(2);
    const view = render(
      <VirtualMessageList
        groups={initialGroups}
        isLoading={false}
        renderGroup={(group) => <span>{group.id}</span>}
      />,
    );

    // 虚拟列表扩展历史页时，滚动上下文可能尚未发布新的位置；上一帧仍记录用户正跟随末尾。
    scrollState.isAtBottom = false;
    view.rerender(
      <VirtualMessageList
        groups={makeGroups(3)}
        isLoading={false}
        renderGroup={(group) => <span>{group.id}</span>}
      />,
    );

    expect(scrollState.scrollToBottom).toHaveBeenCalledWith({
      animation: "instant",
    });
  });

  it("does not pull the reader to the tail after they scroll up", () => {
    scrollState.isAtBottom = false;
    const view = render(
      <VirtualMessageList
        groups={makeGroups(2)}
        isLoading={false}
        renderGroup={(group) => <span>{group.id}</span>}
      />,
    );

    view.rerender(
      <VirtualMessageList
        groups={makeGroups(3)}
        isLoading={false}
        renderGroup={(group) => <span>{group.id}</span>}
      />,
    );

    expect(scrollState.scrollToBottom).not.toHaveBeenCalled();
  });
});
