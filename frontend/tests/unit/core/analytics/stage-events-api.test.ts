import { beforeEach, describe, expect, test, rs } from "@rstest/core";

rs.mock("@/core/api/fetcher", () => ({ fetch: rs.fn() }));
rs.mock("@/core/config", () => ({ getBackendBaseURL: () => "" }));

import { fetchAnalysisStageEvents } from "@/core/analytics/stage-events-api";
import type { AnalysisStageEvent } from "@/core/analytics/types";
import { fetch as fetcher } from "@/core/api/fetcher";

const mockedFetch = rs.mocked(fetcher);

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function stageEvent(seq: number): AnalysisStageEvent {
  return {
    type: "analysis_stage",
    version: 1,
    run_id: "run-1",
    seq,
    stage: "catalog",
    status: "succeeded",
  };
}

function record(recordSeq: number, event: AnalysisStageEvent) {
  return {
    seq: recordSeq,
    event_type: "analysis.stage",
    category: "analysis",
    content: "",
    metadata: event,
  };
}

beforeEach(() => {
  mockedFetch.mockReset();
});

describe("analysis stage event replay API", () => {
  test("pages with record.seq while returning metadata.seq as the stage cursor", async () => {
    const firstPage = Array.from({ length: 100 }, (_, index) => ({
      seq: index + 1,
      event_type: "run.lifecycle",
      category: "runtime",
      content: "",
      metadata: {},
    }));
    mockedFetch
      .mockResolvedValueOnce(jsonResponse(firstPage))
      .mockResolvedValueOnce(jsonResponse([record(107, stageEvent(1))]));

    const events = await fetchAnalysisStageEvents("thread-1", "run-1");
    const secondUrl = mockedFetch.mock.calls[1]?.[0] as string;

    expect(
      new URL(secondUrl, "http://localhost").searchParams.get("after_seq"),
    ).toBe("100");
    expect(events).toEqual([stageEvent(1)]);
  });

  test("caps replay at 20 pages and 2000 original run events", async () => {
    mockedFetch.mockImplementation(async () => {
      const page = mockedFetch.mock.calls.length;
      return jsonResponse(
        Array.from({ length: 100 }, (_, index) => ({
          seq: (page - 1) * 100 + index + 1,
          event_type: "run.lifecycle",
          category: "runtime",
          content: "",
          metadata: {},
        })),
      );
    });

    await fetchAnalysisStageEvents("thread-1", "run-1");

    expect(mockedFetch).toHaveBeenCalledTimes(20);
  });
});
