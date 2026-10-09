import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

import {
  mergeAnalysisStageEvents,
  parseAnalysisStageRunEventRecord,
  readRunEventRecordSeq,
} from "./analysis-stages";
import type { AnalysisStageEvent, AnalysisStreamMetadata } from "./types";

const RUN_EVENT_PAGE_SIZE = 100;
const RUN_EVENT_MAX_PAGES = 20;
const RUN_EVENT_MAX_RECORDS = 2000;

export async function fetchAnalysisStageEvents(
  threadId: string,
  runId: string,
): Promise<AnalysisStageEvent[]> {
  const scope = {
    thread_id: threadId,
    run_id: runId,
  } satisfies AnalysisStreamMetadata;
  const records: AnalysisStageEvent[] = [];
  let afterSeq: number | undefined;
  let recordsRead = 0;
  const base =
    getBackendBaseURL() +
    "/api/threads/" +
    encodeURIComponent(threadId) +
    "/runs/" +
    encodeURIComponent(runId) +
    "/events";

  for (let page = 0; page < RUN_EVENT_MAX_PAGES; page += 1) {
    const params = new URLSearchParams({ limit: String(RUN_EVENT_PAGE_SIZE) });
    if (afterSeq !== undefined) {
      params.set("after_seq", String(afterSeq));
    }

    let response: Response;
    try {
      response = await fetch(base + "?" + params.toString());
    } catch {
      throw new Error("analysis_stage_events_unavailable");
    }
    if (!response.ok) {
      throw new Error("analysis_stage_events_unavailable");
    }

    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      throw new Error("analysis_stage_events_unavailable");
    }
    if (!Array.isArray(payload)) {
      throw new Error("analysis_stage_events_unavailable");
    }

    recordsRead += payload.length;
    for (const record of payload) {
      const parsed = parseAnalysisStageRunEventRecord(record, scope);
      if (parsed) {
        records.push(parsed.event);
      }
    }

    const lastSeq = readRunEventRecordSeq(payload[payload.length - 1]);
    if (
      payload.length < RUN_EVENT_PAGE_SIZE ||
      recordsRead >= RUN_EVENT_MAX_RECORDS ||
      lastSeq === null ||
      (afterSeq !== undefined && lastSeq <= afterSeq)
    ) {
      break;
    }
    afterSeq = lastSeq;
  }

  return mergeAnalysisStageEvents([], records);
}
