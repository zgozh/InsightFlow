import { afterEach, describe, expect, test, rs } from "@rstest/core";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { PropsWithChildren } from "react";

const mocks = rs.hoisted(() => ({
  runs: [] as Array<{
    run_id: string;
    thread_id: string;
    created_at: string;
    updated_at: string;
    status:
      | "pending"
      | "running"
      | "error"
      | "success"
      | "timeout"
      | "interrupted";
    assistant_id: string;
    metadata: Record<string, unknown>;
  }>,
  runQueryEnabled: [] as boolean[],
  refetch: rs.fn(async () => ({ data: [] })),
}));

rs.mock("@/core/api/fetcher", () => ({
  fetch: rs.fn(async () => new Response("[]", { status: 200 })),
}));
rs.mock("@/core/config", () => ({ getBackendBaseURL: () => "" }));
rs.mock("@/core/threads/hooks", () => ({
  useThreadRuns: (
    _threadId: string | undefined,
    options?: { enabled?: boolean },
  ) => {
    mocks.runQueryEnabled.push(options?.enabled ?? false);
    return {
      data: mocks.runs,
      isLoading: false,
      refetch: mocks.refetch,
    };
  },
}));

import type { AnalysisStageEvent } from "@/core/analytics/types";
import { useAnalysisStages } from "@/core/analytics/use-analysis-stages";
import { fetch as fetcher } from "@/core/api/fetcher";

const mockedFetch = rs.mocked(fetcher);
const RUN_ID = "run-1";
const THREAD_ID = "thread-1";

function event(runId = RUN_ID, seq = 1): AnalysisStageEvent {
  return {
    type: "analysis_stage",
    version: 1,
    run_id: runId,
    seq,
    stage: "workflow",
    status: "running",
  };
}

function Harness({
  threadId,
  enabled = true,
  backfillEnabled = false,
}: {
  threadId: string;
  enabled?: boolean;
  backfillEnabled?: boolean;
}) {
  const stages = useAnalysisStages({ threadId, enabled, backfillEnabled });
  const metadata = { thread_id: threadId, run_id: RUN_ID };
  const oldRunMetadata = { thread_id: threadId, run_id: "run-old" };
  const newRunMetadata = { thread_id: threadId, run_id: "run-new" };
  return (
    <div>
      <button
        onClick={() => stages.onCustomEvent(event(), metadata)}
        type="button"
      >
        accept
      </button>
      <button
        onClick={() => stages.onCustomEvent(event("foreign-run"), metadata)}
        type="button"
      >
        foreign
      </button>
      <button onClick={() => stages.onStreamMetadata(metadata)} type="button">
        metadata
      </button>
      <button onClick={() => stages.onRunSettled(metadata)} type="button">
        refresh
      </button>
      <button
        onClick={() => stages.onStreamMetadata(oldRunMetadata)}
        type="button"
      >
        old run
      </button>
      <button
        onClick={() => stages.onStreamMetadata(newRunMetadata)}
        type="button"
      >
        new run
      </button>
      <button
        onClick={() => stages.onCustomEvent(event("run-old"), oldRunMetadata)}
        type="button"
      >
        late old event
      </button>
      <button onClick={() => stages.onRunSettled(oldRunMetadata)} type="button">
        late old finish
      </button>
      <p data-testid="run-status">{stages.runStatus ?? ""}</p>
      <p data-testid="events">
        {stages.events.map((item) => item.run_id + ":" + item.seq).join(",")}
      </p>
    </div>
  );
}

function wrapper({ children }: PropsWithChildren) {
  return <>{children}</>;
}

afterEach(() => {
  cleanup();
  mocks.runs = [];
  mocks.runQueryEnabled.length = 0;
  mocks.refetch.mockClear();
  mockedFetch.mockClear();
});

describe("useAnalysisStages", () => {
  test("accepts only events bound to actual stream metadata and clears on thread switch", () => {
    const view = render(<Harness threadId={THREAD_ID} />, { wrapper });
    fireEvent.click(screen.getByText("metadata"));
    fireEvent.click(screen.getByText("accept"));
    fireEvent.click(screen.getByText("foreign"));
    expect(screen.getByTestId("events").textContent).toBe("run-1:1");

    view.rerender(<Harness threadId="thread-2" />);
    expect(screen.getByTestId("events").textContent).toBe("");
    view.rerender(<Harness threadId={THREAD_ID} />);
    expect(screen.getByTestId("events").textContent).toBe("");
    expect(mocks.runQueryEnabled.every((enabled) => !enabled)).toBe(true);
  });

  test("does not enable stage state for ordinary chat and refreshes runs after a gap or terminal", async () => {
    const view = render(
      <Harness threadId={THREAD_ID} enabled={false} backfillEnabled={false} />,
      { wrapper },
    );
    fireEvent.click(screen.getByText("accept"));
    expect(screen.getByTestId("events").textContent).toBe("");

    view.rerender(<Harness threadId={THREAD_ID} enabled backfillEnabled />);
    fireEvent.click(screen.getByText("metadata"));
    fireEvent.click(screen.getByText("refresh"));
    await waitFor(() => expect(mocks.refetch).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mockedFetch).toHaveBeenCalled());
    expect(mocks.runQueryEnabled.at(-1)).toBe(true);
  });

  test("does not revive an old run when its custom event or finish arrives late", () => {
    mocks.runs = [
      {
        run_id: "run-old",
        thread_id: THREAD_ID,
        created_at: "2026-10-08T10:00:00.000Z",
        updated_at: "2026-10-08T10:00:01.000Z",
        status: "success",
        assistant_id: "assistant",
        metadata: {},
      },
      {
        run_id: "run-new",
        thread_id: THREAD_ID,
        created_at: "2026-10-08T10:00:02.000Z",
        updated_at: "2026-10-08T10:00:03.000Z",
        status: "running",
        assistant_id: "assistant",
        metadata: {},
      },
    ];
    render(<Harness threadId={THREAD_ID} />);

    fireEvent.click(screen.getByText("old run"));
    fireEvent.click(screen.getByText("new run"));
    expect(screen.getByTestId("run-status").textContent).toBe("running");

    fireEvent.click(screen.getByText("late old event"));
    expect(screen.getByTestId("run-status").textContent).toBe("running");
    expect(screen.getByTestId("events").textContent).toBe("");

    fireEvent.click(screen.getByText("new run"));
    fireEvent.click(screen.getByText("late old finish"));
    expect(screen.getByTestId("run-status").textContent).toBe("running");
  });
});
