"use client";

import { Ban, Check, CircleDashed, CircleX, LoaderCircle } from "lucide-react";

import { latestAnalysisStageEvents } from "@/core/analytics/analysis-stages";
import type {
  AnalysisObservedRunStatus,
  AnalysisStageEvent,
} from "@/core/analytics/types";
import { useI18n } from "@/core/i18n/hooks";

export function AnalysisStagePanel({
  events,
  runStatus,
  isLoading = false,
  unavailable = false,
}: {
  events: readonly AnalysisStageEvent[];
  runStatus?: AnalysisObservedRunStatus;
  isLoading?: boolean;
  unavailable?: boolean;
}) {
  const { t } = useI18n();
  const copy = t.analytics.analysisStages;
  const latest = latestAnalysisStageEvents(events);

  return (
    <section
      aria-label={copy.title}
      data-testid="analysis-stage-panel"
      className="border-border bg-background/80 mx-3 mt-12 shrink-0 rounded-lg border px-3 py-2 shadow-xs sm:mx-4"
    >
      <header className="flex min-w-0 items-start gap-3">
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-medium">{copy.title}</h2>
          <p className="text-muted-foreground text-xs">{copy.description}</p>
        </div>
        {runStatus && (
          <p className="text-muted-foreground shrink-0 text-xs">
            {copy.runStatus}: {copy.runStatuses[runStatus]}
          </p>
        )}
      </header>

      {isLoading && (
        <p aria-live="polite" className="text-muted-foreground mt-2 text-xs">
          {copy.loading}
        </p>
      )}
      {unavailable && (
        <p role="status" className="text-muted-foreground mt-2 text-xs">
          {copy.unavailable}
        </p>
      )}
      {latest.length === 0 && !isLoading && !unavailable && (
        <p className="text-muted-foreground mt-2 text-xs">{copy.empty}</p>
      )}

      {latest.length > 0 && (
        <ol className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {latest.map((event) => {
            const StatusIcon = statusIcon(event.status);
            return (
              <li
                key={event.stage}
                data-testid="analysis-stage-item"
                data-status={event.status}
                className="border-border/70 bg-background flex min-w-0 flex-col gap-1 rounded-md border px-2 py-1.5"
              >
                <div className="flex min-w-0 items-center gap-1.5">
                  <StatusIcon
                    aria-hidden="true"
                    className="text-muted-foreground size-3.5 shrink-0"
                  />
                  <span className="min-w-0 flex-1 truncate text-xs font-medium">
                    {copy.stages[event.stage]}
                  </span>
                  <span className="text-muted-foreground shrink-0 text-xs">
                    {copy.statuses[event.status]}
                  </span>
                </div>

                {(event.duration_ms !== undefined ||
                  event.row_count !== undefined ||
                  event.byte_count !== undefined ||
                  event.input_tokens !== undefined ||
                  event.output_tokens !== undefined ||
                  event.risk !== undefined ||
                  event.cached === true ||
                  event.code !== undefined) && (
                  <dl className="text-muted-foreground grid grid-cols-2 gap-x-2 gap-y-0.5 text-[11px]">
                    <Fact
                      label={copy.duration}
                      value={
                        event.duration_ms === undefined
                          ? undefined
                          : String(event.duration_ms) + " ms"
                      }
                    />
                    <Fact label={copy.rows} value={event.row_count} />
                    <Fact label={copy.bytes} value={event.byte_count} />
                    <Fact label={copy.inputTokens} value={event.input_tokens} />
                    <Fact
                      label={copy.outputTokens}
                      value={event.output_tokens}
                    />
                    {event.risk !== undefined && (
                      <Fact label={copy.risk} value={copy.risks[event.risk]} />
                    )}
                    {event.code !== undefined && (
                      <div className="col-span-2 min-w-0">
                        <dt className="sr-only">{copy.code}</dt>
                        <dd className="truncate">{copy.codes[event.code]}</dd>
                      </div>
                    )}
                  </dl>
                )}
                {event.cached === true && (
                  <span className="text-muted-foreground text-[11px]">
                    {copy.reused}
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

function Fact({
  label,
  value,
}: {
  label: string;
  value: string | number | undefined;
}) {
  if (value === undefined) {
    return null;
  }
  return (
    <div className="flex min-w-0 gap-1">
      <dt className="shrink-0">{label}</dt>
      <dd className="min-w-0 truncate font-mono">{value}</dd>
    </div>
  );
}

function statusIcon(status: AnalysisStageEvent["status"]) {
  switch (status) {
    case "running":
      return LoaderCircle;
    case "succeeded":
      return Check;
    case "failed":
      return CircleX;
    case "blocked":
      return Ban;
    case "cancelled":
      return CircleDashed;
  }
}
