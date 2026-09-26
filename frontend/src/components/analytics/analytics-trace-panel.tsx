"use client";

/**
 * 分析轨迹面板（Phase 4 §8）。
 *
 * 它渲染的是 `core/analytics/trace.ts` 投影出来的**结构化状态**：工具名、阶段、状态与
 * 受控查询的安全事实。面板本身不做任何解析，因此即使上游消息里带着 SQL、结果行或异常文本，
 * 它们也不会有渲染路径。
 *
 * 布局：
 *
 * - 宽屏（`lg` 以上）：作为对话主区右侧的常驻可折叠列；
 * - 窄屏：默认收起，点触发器后在 header 下方展开为抽屉，内部滚动，不产生水平溢出。
 */

import { ChevronRightIcon, ListTreeIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { CopyButton } from "@/components/workspace/copy-button";
import {
  abbreviateDigest,
  formatEngineCost,
  type AnalyticsReportReviewerReasonCode,
  type AnalyticsReportReviewerStatus,
  type AnalyticsTraceStatus,
  type AnalyticsTraceStepKind,
  projectAnalyticsTrace,
} from "@/core/analytics/trace";
import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

export const ANALYTICS_TRACE_PANEL_ID = "analytics-trace-panel";

/** 与 Tailwind 的 `lg` 断点一致：宽屏常驻展开，窄屏默认收起为抽屉。 */
const DESKTOP_QUERY = "(min-width: 1024px)";

type TraceStatusLabelKey =
  | "statusRunning"
  | "statusCompleted"
  | "statusFailed"
  | "statusRejected";

type TraceKindLabelKey =
  | "stepPlan"
  | "stepCatalog"
  | "stepQuery"
  | "stepDelegate"
  | "stepArtifact"
  | "stepPublish"
  | "unparsed";

type ReviewerStatusLabelKey =
  | "reviewerApproved"
  | "reviewerRejected"
  | "reviewerFailed"
  | "reviewerLimited";

type ReviewerReasonLabelKey =
  | "reviewReasonUnsupportedClaim"
  | "reviewReasonEvidenceMismatch"
  | "reviewReasonMissingCitation"
  | "reviewReasonInsufficientEvidence";

const STATUS_LABEL: Record<AnalyticsTraceStatus, TraceStatusLabelKey> = {
  running: "statusRunning",
  completed: "statusCompleted",
  failed: "statusFailed",
  rejected: "statusRejected",
};

const KIND_LABEL: Record<AnalyticsTraceStepKind, TraceKindLabelKey> = {
  plan: "stepPlan",
  catalog: "stepCatalog",
  query: "stepQuery",
  delegate: "stepDelegate",
  artifact: "stepArtifact",
  report: "stepPublish",
  unknown: "unparsed",
};

const REVIEWER_STATUS_LABEL: Record<
  AnalyticsReportReviewerStatus,
  ReviewerStatusLabelKey
> = {
  approved: "reviewerApproved",
  rejected: "reviewerRejected",
  failed: "reviewerFailed",
  limited: "reviewerLimited",
};

const REVIEWER_REASON_LABEL: Record<
  AnalyticsReportReviewerReasonCode,
  ReviewerReasonLabelKey
> = {
  unsupported_claim: "reviewReasonUnsupportedClaim",
  evidence_mismatch: "reviewReasonEvidenceMismatch",
  missing_citation: "reviewReasonMissingCitation",
  insufficient_evidence: "reviewReasonInsufficientEvidence",
};

const STATUS_CLASS: Record<string, string> = {
  running: "bg-muted text-muted-foreground",
  completed:
    "border-transparent bg-emerald-600/10 text-emerald-700 dark:text-emerald-400",
  failed: "border-transparent bg-destructive/10 text-destructive",
  rejected:
    "border-transparent bg-amber-600/10 text-amber-700 dark:text-amber-500",
};

/** 状态不能只靠颜色传达：这里同时给出文字与不同的图标/文本后缀。 */
const STATUS_TEXT_SUFFIX: Record<string, string> = {
  running: "…",
  completed: "",
  failed: "!",
  rejected: "×",
};

export function AnalyticsTracePanel({
  messages,
  className,
}: {
  messages: Parameters<typeof projectAnalyticsTrace>[0];
  className?: string;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const steps = useMemo(() => projectAnalyticsTrace(messages), [messages]);
  const queryStepCount = steps.filter((step) => step.kind === "query").length;

  // 宽屏默认展开（常驻右列），窄屏默认收起（抽屉）。挂载后再读媒体查询，避免 SSR 与首帧不一致。
  useEffect(() => {
    if (
      typeof window === "undefined" ||
      typeof window.matchMedia !== "function"
    ) {
      return;
    }
    if (window.matchMedia(DESKTOP_QUERY).matches) {
      setOpen(true);
    }
  }, []);

  return (
    <>
      <button
        type="button"
        data-testid="analytics-trace-trigger"
        aria-expanded={open}
        aria-controls={ANALYTICS_TRACE_PANEL_ID}
        onClick={() => setOpen((previous) => !previous)}
        className="border-border bg-background/80 absolute top-12 right-2 z-40 inline-flex min-h-11 min-w-11 items-center gap-1 rounded-md border px-2 text-xs backdrop-blur lg:hidden"
      >
        <ListTreeIcon aria-hidden="true" className="size-4" />
        <span>{t.analytics.trace.toggle}</span>
      </button>

      <aside
        id={ANALYTICS_TRACE_PANEL_ID}
        data-testid="analytics-trace-panel"
        aria-label={t.analytics.trace.title}
        className={cn(
          "border-border bg-background/95 min-h-0 shrink-0 flex-col border-l backdrop-blur",
          // 打开：窄屏是覆盖式抽屉，宽屏回到文档流成为常驻右列。
          open
            ? "absolute inset-y-12 right-0 z-30 flex w-[min(20rem,85vw)] shadow-lg lg:static lg:z-auto lg:w-80 lg:shadow-none"
            : "hidden",
          className,
        )}
      >
        <header className="border-border flex shrink-0 items-center gap-2 border-b px-3 py-2">
          <ListTreeIcon
            aria-hidden="true"
            className="text-muted-foreground size-4"
          />
          <h2 className="min-w-0 flex-1 truncate text-sm font-medium">
            {t.analytics.trace.title}
          </h2>
          {queryStepCount > 0 && (
            <Badge variant="secondary" className="shrink-0">
              {queryStepCount}
            </Badge>
          )}
          {/* 宽屏也可收起：与窄屏共用同一个状态，只是行为不同。 */}
          <button
            type="button"
            aria-expanded={open}
            aria-controls={ANALYTICS_TRACE_PANEL_ID}
            onClick={() => setOpen((previous) => !previous)}
            className="text-muted-foreground hover:text-foreground hidden min-h-11 min-w-11 items-center justify-center rounded-md lg:inline-flex"
            aria-label={t.analytics.trace.toggle}
          >
            <ChevronRightIcon
              aria-hidden="true"
              className={cn(
                "size-4 transition-transform motion-reduce:transition-none",
                open && "rotate-180",
              )}
            />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-3 py-2">
          {steps.length === 0 ? (
            <p
              role="status"
              className="text-muted-foreground py-6 text-center text-xs"
            >
              {t.analytics.trace.empty}
            </p>
          ) : (
            <ol className="flex flex-col gap-3">
              {steps.map((step) => {
                const statusKey = STATUS_LABEL[step.status];
                const statusLabel = t.analytics.trace[statusKey];
                const kindLabel = t.analytics.trace[KIND_LABEL[step.kind]];
                return (
                  <li
                    key={step.id}
                    data-testid="analytics-trace-step"
                    data-status={step.status}
                    data-kind={step.kind}
                    className="border-border flex flex-col gap-1 rounded-md border p-2"
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      <span className="min-w-0 flex-1 truncate text-xs font-medium">
                        {kindLabel}
                      </span>
                      <span
                        className={cn(
                          "shrink-0 rounded-full px-2 py-0.5 text-[11px] leading-4",
                          STATUS_CLASS[step.status],
                        )}
                      >
                        {statusLabel}
                        {STATUS_TEXT_SUFFIX[step.status]}
                      </span>
                    </div>

                    <p className="text-muted-foreground truncate font-mono text-[11px]">
                      {step.toolName || t.analytics.common.unknownEvent}
                    </p>

                    {step.unparsed && (
                      <p
                        role="status"
                        className="text-muted-foreground text-[11px]"
                      >
                        {t.analytics.trace.unparsed}
                      </p>
                    )}

                    {step.reviewerStatus !== null && (
                      <p
                        role="status"
                        data-testid="analytics-reviewer-status"
                        data-reviewer-status={step.reviewerStatus}
                        className="text-muted-foreground text-[11px]"
                      >
                        {t.analytics.trace.reviewer}:{" "}
                        {
                          t.analytics.trace[
                            REVIEWER_STATUS_LABEL[step.reviewerStatus]
                          ]
                        }
                        {step.reviewerReasonCode !== null && (
                          <>
                            {" "}
                            ·{" "}
                            {
                              t.analytics.trace[
                                REVIEWER_REASON_LABEL[step.reviewerReasonCode]
                              ]
                            }
                          </>
                        )}
                      </p>
                    )}

                    {step.todoCount !== null && (
                      <p className="text-muted-foreground text-[11px]">
                        {step.todoCount}
                      </p>
                    )}

                    {step.facts && (
                      <dl className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-[11px]">
                        <Fact
                          label={t.analytics.trace.rows}
                          value={step.facts.row_count}
                        />
                        <Fact
                          label={t.analytics.trace.bytes}
                          value={step.facts.byte_count}
                        />
                        <Fact
                          label={t.analytics.trace.estimatedRows}
                          value={step.facts.estimated_rows}
                        />
                        <Fact
                          label={t.analytics.trace.engineCost}
                          value={formatEngineCost(step.facts.engine_cost)}
                        />
                        <Fact
                          label={t.analytics.trace.truncated}
                          value={
                            step.facts.truncated === null
                              ? null
                              : step.facts.truncated
                                ? t.analytics.trace.truncatedYes
                                : t.analytics.trace.truncatedNo
                          }
                        />
                        <Fact
                          label={t.analytics.trace.risk}
                          value={step.facts.risk}
                        />
                        <Fact
                          label={t.analytics.trace.schemaVersion}
                          value={step.facts.schema_version}
                        />
                        <Fact
                          label={t.analytics.trace.policyVersion}
                          value={step.facts.policy_version}
                        />
                      </dl>
                    )}

                    {step.facts?.evidence_id && (
                      <div className="flex min-w-0 items-center gap-1">
                        <span className="text-muted-foreground shrink-0 text-[11px]">
                          {t.analytics.trace.evidenceId}
                        </span>
                        <code className="min-w-0 flex-1 truncate font-mono text-[11px]">
                          {abbreviateDigest(step.facts.evidence_id)}
                        </code>
                        <CopyButton
                          clipboardData={step.facts.evidence_id}
                          aria-label={t.analytics.trace.copyEvidence}
                        />
                      </div>
                    )}

                    {step.facts?.result_digest && (
                      <div className="flex min-w-0 items-center gap-1">
                        <span className="text-muted-foreground shrink-0 text-[11px]">
                          {t.analytics.trace.resultDigest}
                        </span>
                        <code className="min-w-0 flex-1 truncate font-mono text-[11px]">
                          {abbreviateDigest(step.facts.result_digest)}
                        </code>
                      </div>
                    )}

                    {step.artifactPaths.length > 0 && (
                      <ul className="text-muted-foreground flex flex-col gap-0.5 text-[11px]">
                        {step.artifactPaths.map((path) => (
                          <li key={path} className="truncate font-mono">
                            {path}
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </aside>
    </>
  );
}

function Fact({
  label,
  value,
}: {
  label: string;
  value: string | number | null;
}) {
  if (value === null) return null;
  return (
    <div className="flex min-w-0 gap-1">
      <dt className="text-muted-foreground shrink-0">{label}</dt>
      <dd className="min-w-0 truncate font-mono">{value}</dd>
    </div>
  );
}
