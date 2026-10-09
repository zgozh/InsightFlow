"use client";

import type { Run } from "@langchain/langgraph-sdk";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useThreadRuns } from "@/core/threads/hooks";

import {
  mergeAnalysisStageEvents,
  parseAnalysisStagePayload,
} from "./analysis-stages";
import { fetchAnalysisStageEvents } from "./stage-events-api";
import type {
  AnalysisObservedRunStatus,
  AnalysisStageEvent,
  AnalysisStreamMetadata,
} from "./types";

type StageSnapshot = {
  threadId: string;
  runId: string;
  events: AnalysisStageEvent[];
};

type BackfillState = {
  threadId: string;
  runId: string;
  loading: boolean;
  unavailable: boolean;
};

export function useAnalysisStages({
  threadId,
  enabled,
  backfillEnabled,
}: {
  threadId: string | null | undefined;
  enabled: boolean;
  backfillEnabled: boolean;
}) {
  const runsQuery = useThreadRuns(threadId ?? undefined, {
    enabled: enabled && backfillEnabled && Boolean(threadId),
  });
  const refetchRuns = runsQuery.refetch;
  const latestRun = useMemo(
    () => latestThreadRun(runsQuery.data, threadId),
    [runsQuery.data, threadId],
  );
  const [streamMetadata, setStreamMetadata] =
    useState<AnalysisStreamMetadata | null>(null);
  const [snapshot, setSnapshot] = useState<StageSnapshot | null>(null);
  const [backfill, setBackfill] = useState<BackfillState | null>(null);
  const [backfillRevision, setBackfillRevision] = useState(0);
  const streamMetadataRef = useRef<AnalysisStreamMetadata | null>(null);
  const priorThreadId = useRef(threadId);

  useEffect(() => {
    if (priorThreadId.current !== threadId) {
      priorThreadId.current = threadId;
      streamMetadataRef.current = null;
      setStreamMetadata(null);
      setSnapshot(null);
      setBackfill(null);
    }
  }, [threadId]);

  const activeStreamMetadata =
    streamMetadata?.thread_id === threadId ? streamMetadata : null;
  const runId = activeStreamMetadata?.run_id ?? latestRun?.run_id ?? null;
  const currentRun =
    runId && latestRun?.run_id === runId ? latestRun : undefined;
  const visibleEvents =
    snapshot && snapshot.threadId === threadId && snapshot.runId === runId
      ? snapshot.events
      : [];
  const currentBackfill =
    backfill && backfill.threadId === threadId && backfill.runId === runId
      ? backfill
      : null;

  const onStreamMetadata = useCallback(
    (metadata: AnalysisStreamMetadata) => {
      if (
        enabled &&
        metadata.thread_id === threadId &&
        metadata.run_id.length > 0
      ) {
        streamMetadataRef.current = metadata;
        setStreamMetadata(metadata);
      }
    },
    [enabled, threadId],
  );

  const onCustomEvent = useCallback(
    (payload: unknown, metadata: AnalysisStreamMetadata | null) => {
      const currentMetadata = streamMetadataRef.current;
      if (
        !enabled ||
        !metadata ||
        metadata.thread_id !== threadId ||
        metadata.run_id.length === 0 ||
        currentMetadata?.thread_id !== metadata.thread_id ||
        currentMetadata?.run_id !== metadata.run_id
      ) {
        return;
      }
      const event = parseAnalysisStagePayload(payload);
      if (event?.run_id !== metadata.run_id) {
        return;
      }
      setSnapshot((previous) => {
        const previousEvents =
          previous?.threadId === threadId && previous?.runId === metadata.run_id
            ? previous.events
            : [];
        return {
          threadId: metadata.thread_id,
          runId: metadata.run_id,
          events: mergeAnalysisStageEvents(previousEvents, [event]),
        };
      });
    },
    [enabled, threadId],
  );

  const refreshBackfill = useCallback(async () => {
    if (!enabled || !backfillEnabled || !threadId) {
      return;
    }
    await refetchRuns();
    setBackfillRevision((revision) => revision + 1);
  }, [backfillEnabled, enabled, refetchRuns, threadId]);

  const onRunSettled = useCallback(
    (metadata: AnalysisStreamMetadata | null) => {
      const currentMetadata = streamMetadataRef.current;
      if (
        metadata &&
        (metadata.thread_id !== threadId ||
          (currentMetadata !== null &&
            (currentMetadata.thread_id !== metadata.thread_id ||
              currentMetadata.run_id !== metadata.run_id)))
      ) {
        return;
      }
      void refreshBackfill();
    },
    [refreshBackfill, threadId],
  );

  useEffect(() => {
    if (!enabled || !backfillEnabled || !threadId || !runId) {
      return;
    }

    let cancelled = false;
    setBackfill({
      threadId,
      runId,
      loading: true,
      unavailable: false,
    });
    void fetchAnalysisStageEvents(threadId, runId)
      .then((events) => {
        if (cancelled) {
          return;
        }
        setSnapshot((previous) => {
          const previousEvents =
            previous?.threadId === threadId && previous.runId === runId
              ? previous.events
              : [];
          return {
            threadId,
            runId,
            events: mergeAnalysisStageEvents(previousEvents, events),
          };
        });
        setBackfill({
          threadId,
          runId,
          loading: false,
          unavailable: false,
        });
      })
      .catch(() => {
        if (!cancelled) {
          setBackfill({
            threadId,
            runId,
            loading: false,
            unavailable: true,
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [backfillEnabled, backfillRevision, enabled, runId, threadId]);

  const runStatus = currentRun?.status as AnalysisObservedRunStatus | undefined;
  const isLoading =
    enabled && (runsQuery.isLoading || Boolean(currentBackfill?.loading));

  return {
    events: visibleEvents,
    runStatus,
    isLoading,
    unavailable: Boolean(currentBackfill?.unavailable),
    onStreamMetadata,
    onCustomEvent,
    onRunSettled,
  };
}

function latestThreadRun(
  runs: Run[] | undefined,
  threadId: string | null | undefined,
): Run | undefined {
  if (!runs || !threadId) {
    return undefined;
  }
  return runs
    .filter(
      (run) =>
        run.thread_id === threadId &&
        typeof run.run_id === "string" &&
        run.run_id.length > 0,
    )
    .reduce<Run | undefined>((latest, run) => {
      if (!latest) {
        return run;
      }
      const runCreated = Date.parse(run.created_at);
      const latestCreated = Date.parse(latest.created_at);
      if (runCreated > latestCreated) {
        return run;
      }
      if (runCreated === latestCreated && run.updated_at > latest.updated_at) {
        return run;
      }
      return latest;
    }, undefined);
}
