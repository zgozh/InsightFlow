import { analysisStagePayloadSchema } from "./schemas";
import {
  ANALYSIS_STAGES,
  type AnalysisStageEvent,
  type AnalysisStreamMetadata,
} from "./types";

export const ANALYSIS_STAGE_EVENT_LIMIT = 128;
const MAX_RUN_EVENT_SEQ = Number.MAX_SAFE_INTEGER;

export function parseAnalysisStagePayload(
  payload: unknown,
): AnalysisStageEvent | null {
  const parsed = analysisStagePayloadSchema.safeParse(payload);
  return parsed.success ? parsed.data : null;
}

export function readRunEventRecordSeq(record: unknown): number | null {
  if (typeof record !== "object" || record === null || !("seq" in record)) {
    return null;
  }
  const seq = Reflect.get(record, "seq");
  return typeof seq === "number" &&
    Number.isSafeInteger(seq) &&
    seq > 0 &&
    seq <= MAX_RUN_EVENT_SEQ
    ? seq
    : null;
}

export function parseAnalysisStageRunEventRecord(
  record: unknown,
  scope: AnalysisStreamMetadata,
): { recordSeq: number; event: AnalysisStageEvent } | null {
  if (typeof record !== "object" || record === null) {
    return null;
  }

  const recordSeq = readRunEventRecordSeq(record);
  if (
    recordSeq === null ||
    Reflect.get(record, "event_type") !== "analysis.stage" ||
    Reflect.get(record, "category") !== "analysis" ||
    Reflect.get(record, "content") !== ""
  ) {
    return null;
  }

  if (
    ("run_id" in record && Reflect.get(record, "run_id") !== scope.run_id) ||
    ("thread_id" in record &&
      Reflect.get(record, "thread_id") !== scope.thread_id)
  ) {
    return null;
  }

  const event = parseAnalysisStagePayload(Reflect.get(record, "metadata"));
  if (event?.run_id !== scope.run_id) {
    return null;
  }

  return { recordSeq, event };
}

/** Merge trusted live and replay events; the first accepted value wins on key conflict. */
export function mergeAnalysisStageEvents(
  existing: readonly AnalysisStageEvent[],
  incoming: readonly AnalysisStageEvent[],
  limit: number = ANALYSIS_STAGE_EVENT_LIMIT,
): AnalysisStageEvent[] {
  const byKey = new Map<string, AnalysisStageEvent>();
  for (const event of existing) {
    byKey.set(eventKey(event), event);
  }
  for (const event of incoming) {
    const key = eventKey(event);
    if (!byKey.has(key)) {
      byKey.set(key, event);
    }
  }

  const boundedLimit = Math.max(0, Math.min(limit, ANALYSIS_STAGE_EVENT_LIMIT));
  const ordered = [...byKey.values()].sort(
    (left, right) => left.seq - right.seq,
  );
  return boundedLimit === 0 ? [] : ordered.slice(-boundedLimit);
}

export function latestAnalysisStageEvents(
  events: readonly AnalysisStageEvent[],
): AnalysisStageEvent[] {
  const latestByStage = new Map<
    AnalysisStageEvent["stage"],
    AnalysisStageEvent
  >();
  for (const event of events) {
    const current = latestByStage.get(event.stage);
    if (!current || event.seq > current.seq) {
      latestByStage.set(event.stage, event);
    }
  }
  return ANALYSIS_STAGES.flatMap((stage) => {
    const event = latestByStage.get(stage);
    return event ? [event] : [];
  });
}

function eventKey(event: AnalysisStageEvent): string {
  return event.run_id + ":" + event.seq;
}
