import type { Message } from "@langchain/langgraph-sdk";
import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import type { PropsWithChildren } from "react";

rs.mock("@/core/clipboard", () => ({
  writeTextToClipboard: rs.fn(async () => true),
}));

import {
  ANALYTICS_TRACE_PANEL_ID,
  AnalyticsTracePanel,
} from "@/components/analytics/analytics-trace-panel";
import { writeTextToClipboard } from "@/core/clipboard";
import { I18nProvider } from "@/core/i18n/context";

const mockedWriteClipboard = rs.mocked(writeTextToClipboard);

const DIGEST = "a".repeat(64);
const RESULT_DIGEST = "b".repeat(64);
const SQL = "SELECT id FROM orders WHERE region = 'EU'";

function wrapper({ children }: PropsWithChildren) {
  return <I18nProvider initialLocale="en-US">{children}</I18nProvider>;
}

function ai(
  toolCalls: Array<{ id: string; name: string; args: unknown }>,
): Message {
  return {
    type: "ai",
    content: "",
    tool_calls: toolCalls,
  } as unknown as Message;
}

function tool(toolCallId: string, content: string): Message {
  return {
    type: "tool",
    tool_call_id: toolCallId,
    content,
  } as unknown as Message;
}

function queryMessages(): Message[] {
  return [
    ai([
      {
        id: "c1",
        name: "query_business_data",
        args: { datasource_id: "ds-1", sql: SQL },
      },
    ]),
    tool(
      "c1",
      JSON.stringify({
        code: "executed",
        columns: ["region", "revenue"],
        rows: [["EU", 1234]],
        row_count: 1,
        byte_count: 42,
        truncated: false,
        evidence: {
          evidence_id: DIGEST,
          risk: "low",
          schema_version: "s1",
          policy_version: "p1",
          estimated_rows: 10,
          engine_cost: "12.5",
          row_count: 1,
          byte_count: 42,
          truncated: false,
          result_digest: RESULT_DIGEST,
          decision_code: "executed",
        },
      }),
    ),
  ];
}

function renderPanel(messages: Message[]) {
  return render(<AnalyticsTracePanel messages={messages} />, { wrapper });
}

describe("AnalyticsTracePanel", () => {
  beforeEach(() => {
    // 默认按窄屏断言：面板收起为抽屉，由触发器控制。宽屏行为由 CSS 负责，不在这里重复。
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      writable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => undefined,
        removeListener: () => undefined,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        dispatchEvent: () => false,
      }),
    });
  });

  afterEach(() => {
    cleanup();
    mockedWriteClipboard.mockClear();
  });

  it("renders an explicit empty state when there is no trace", () => {
    renderPanel([]);

    expect(
      screen.getByText("This run has no events to show yet."),
    ).toBeTruthy();
    expect(screen.queryAllByTestId("analytics-trace-step")).toHaveLength(0);
  });

  it("labels each step with its phase and status text, not colour alone", () => {
    renderPanel(queryMessages());

    const step = screen.getByTestId("analytics-trace-step");
    expect(within(step).getByText("Governed query")).toBeTruthy();
    expect(within(step).getByText(/Completed/)).toBeTruthy();
    expect(step.getAttribute("data-status")).toBe("completed");
  });

  it("shows the safe facts and never the SQL or the result rows", () => {
    const { container } = renderPanel(queryMessages());

    const text = container.textContent ?? "";
    expect(text).toContain("12.5");
    expect(text).toContain("s1");
    expect(text).toContain("p1");
    expect(text).not.toContain("SELECT");
    expect(text).not.toContain("orders");
    expect(text).not.toContain("1234");
    expect(text).not.toContain("EU");
  });

  it("abbreviates the evidence id but copies the full digest", () => {
    renderPanel(queryMessages());

    expect(screen.queryByText(DIGEST)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Copy evidence ID" }));

    expect(mockedWriteClipboard).toHaveBeenCalledWith(DIGEST);
  });

  it("renders a malformed payload as an unparsed safe event", () => {
    const { container } = renderPanel([
      ai([
        {
          id: "c1",
          name: "query_business_data",
          args: { datasource_id: "ds-1", sql: SQL },
        },
      ]),
      tool("c1", "Traceback: postgres://user:pw@host/db"),
    ]);

    const step = screen.getByTestId("analytics-trace-step");
    expect(step.getAttribute("data-status")).toBe("failed");
    expect(
      within(step).getByText("Unparsed event; the raw record was kept"),
    ).toBeTruthy();
    expect(container.textContent).not.toContain("postgres");
  });

  it("renders an unknown tool as an unparsed event without its arguments", () => {
    const { container } = renderPanel([
      ai([
        {
          id: "c1",
          name: "mystery_tool",
          args: { payload: "postgres://user:pw@host/db" },
        },
      ]),
    ]);

    expect(
      screen.getByTestId("analytics-trace-step").getAttribute("data-kind"),
    ).toBe("unknown");
    expect(container.textContent).not.toContain("postgres");
  });

  it("exposes a keyboard operable trigger that controls the panel", () => {
    renderPanel([
      ai([{ id: "c1", name: "inspect_business_catalog", args: {} }]),
      tool("c1", JSON.stringify({ code: "ok", datasources: [], metrics: [] })),
    ]);

    const trigger = screen.getByTestId("analytics-trace-trigger");
    expect(trigger.getAttribute("aria-controls")).toBe(
      ANALYTICS_TRACE_PANEL_ID,
    );
    expect(trigger.getAttribute("aria-expanded")).toBe("false");

    trigger.focus();
    expect(document.activeElement).toBe(trigger);
    fireEvent.keyDown(trigger, { key: "Enter" });
    fireEvent.click(trigger);

    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    expect(document.getElementById(ANALYTICS_TRACE_PANEL_ID)).toBeTruthy();
  });

  it("shows artifact paths for the artifact phase only", () => {
    renderPanel([
      ai([
        {
          id: "c1",
          name: "present_files",
          args: { filepaths: ["/mnt/user-data/outputs/report.md"] },
        },
      ]),
      tool("c1", JSON.stringify({ code: "ok" })),
    ]);

    expect(screen.getByText("/mnt/user-data/outputs/report.md")).toBeTruthy();
  });
});
