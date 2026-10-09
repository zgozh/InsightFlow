import { describe, expect, test } from "@rstest/core";

import {
  latestAnalysisStageEvents,
  mergeAnalysisStageEvents,
  parseAnalysisStagePayload,
  parseAnalysisStageRunEventRecord,
} from "@/core/analytics/analysis-stages";
import { analysisStagePayloadSchema } from "@/core/analytics/schemas";
import type { AnalysisStageEvent } from "@/core/analytics/types";

const SCOPE = { thread_id: "thread-1", run_id: "run-1" };

function stage(
  seq: number,
  overrides: Partial<AnalysisStageEvent> = {},
): AnalysisStageEvent {
  return {
    type: "analysis_stage",
    version: 1,
    run_id: SCOPE.run_id,
    seq,
    stage: "execution",
    status: "running",
    ...overrides,
  };
}

function record(
  seq: number,
  event: AnalysisStageEvent = stage(1),
  overrides: Record<string, unknown> = {},
) {
  return {
    seq,
    event_type: "analysis.stage",
    category: "analysis",
    content: "",
    metadata: event,
    ...overrides,
  };
}

describe("analysis stage contract", () => {
  test("strictly rejects extra payload fields and accepts only bounded contract values", () => {
    const accepted = stage(1, {
      status: "blocked",
      risk: "BLOCKED",
      row_count: 0,
      cached: true,
      evidence_ids: ["a".repeat(64)],
    });
    expect(analysisStagePayloadSchema.safeParse(accepted).success).toBe(true);
    expect(
      analysisStagePayloadSchema.safeParse({
        ...accepted,
        sql: "SELECT secret",
      }).success,
    ).toBe(false);
    expect(
      analysisStagePayloadSchema.safeParse({
        ...accepted,
        rows: [["customer@example.com"]],
      }).success,
    ).toBe(false);
    expect(
      analysisStagePayloadSchema.safeParse({
        ...accepted,
        freeerror: "postgres connection details",
      }).success,
    ).toBe(false);
    expect(
      analysisStagePayloadSchema.safeParse({ ...accepted, status: "skipped" })
        .success,
    ).toBe(false);
  });

  test("validates stage scope and preserves distinct record and per-run cursors", () => {
    const parsed = parseAnalysisStageRunEventRecord(
      record(84, stage(2, { status: "failed" })),
      SCOPE,
    );
    expect(parsed).toEqual({
      recordSeq: 84,
      event: stage(2, { status: "failed" }),
    });
    expect(
      parseAnalysisStageRunEventRecord(record(85, stage(2)), {
        ...SCOPE,
        run_id: "run-2",
      }),
    ).toBeNull();
    expect(
      parseAnalysisStageRunEventRecord(
        record(86, stage(3), { run_id: "run-2" }),
        SCOPE,
      ),
    ).toBeNull();
    expect(
      parseAnalysisStageRunEventRecord(
        record(86, stage(3), { thread_id: "thread-2" }),
        SCOPE,
      ),
    ).toBeNull();
    expect(
      parseAnalysisStageRunEventRecord(
        record(86, stage(3), { content: "unexpected" }),
        SCOPE,
      ),
    ).toBeNull();
  });

  test("merges replay and live events by run sequence without replacing an accepted conflict", () => {
    const accepted = stage(2, { status: "succeeded" });
    const merged = mergeAnalysisStageEvents(
      [stage(4), accepted],
      [stage(1), stage(2, { status: "failed" }), stage(3)],
    );
    expect(merged.map((event) => event.seq)).toEqual([1, 2, 3, 4]);
    expect(merged[1]).toEqual(accepted);
  });

  test("keeps only the latest 128 events and projects the latest status per stage", () => {
    const events = Array.from({ length: 130 }, (_, index) =>
      stage(index + 1, {
        stage: index === 129 ? "publish" : "execution",
        status:
          index === 129 ? "cancelled" : index === 128 ? "blocked" : "running",
      }),
    );
    const bounded = mergeAnalysisStageEvents([], events);
    expect(bounded).toHaveLength(128);
    expect(bounded[0]?.seq).toBe(3);
    expect(latestAnalysisStageEvents(bounded)).toEqual([
      stage(129, { status: "blocked" }),
      stage(130, { stage: "publish", status: "cancelled" }),
    ]);
    expect(
      parseAnalysisStagePayload(stage(131, { status: "cancelled" })),
    ).toEqual(stage(131, { status: "cancelled" }));
  });
});
