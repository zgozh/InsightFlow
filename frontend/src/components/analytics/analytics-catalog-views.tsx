"use client";

/**
 * 分析工作台的共享页面框架与只读目录视图（Phase 4 §6）。
 *
 * 为什么把框架收在一个导出组件里，而不是每个页面各写一遍：
 *
 * 1. 五个页面都必须显式处理同样的五种状态（加载／错误＋重试／403／空／内容）。分散实现时
 *    最容易漏掉的正是 403——页面看起来"我没渲染管理员入口所以安全"，但服务端仍然可能拒绝
 *    这次读取，界面不能退化成静默空白。
 * 2. `403` 判定必须以**服务端结论**为准：客户端的管理员标记只决定隐藏入口，不构成授权。
 * 3. 只读视图（数据源目录／指标目录／审计记录／报告列表）与管理员面板分文件，让"普通用户
 *    到底能看到什么"可以被单独审阅——这是本阶段最需要被审阅的一条边界。
 *
 * 安全约定：本文件只渲染 `core/analytics/types` 里真实存在的字段。审计读取的解析类型本身
 * 不含 SQL、结果行、凭据、DSN 与异常文本，所以这里不存在"记得别渲染"的路径——字段不存在，
 * 就没有到达 DOM 的入口。
 *
 * 状态展示：所有状态标签都同时给出**本地化文字**与图标，绝不只用颜色区分（色觉障碍与
 * 高对比模式下颜色都可能失效）。
 */

import {
  CircleCheckIcon,
  CircleMinusIcon,
  CircleXIcon,
  DownloadIcon,
  TriangleAlertIcon,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useRef, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { CopyButton } from "@/components/workspace/copy-button";
import {
  WorkspaceBody,
  WorkspaceContainer,
  WorkspaceHeader,
} from "@/components/workspace/workspace-container";
import { newAnalysisPrefillHref } from "@/core/analytics/analysis-prefill";
import { AnalyticsRequestError } from "@/core/analytics/api";
import { abbreviateDigest, formatEngineCost } from "@/core/analytics/trace";
import type {
  AnalysisReportView,
  DatasourceStatus,
  DatasourceView,
  MetricStatus,
  MetricView,
  QueryAuditStatus,
  QueryAuditView,
  QueryRisk,
  ReportStatus,
} from "@/core/analytics/types";
import { urlOfArtifact } from "@/core/artifacts/utils";
import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

// --- 403 判定 ---------------------------------------------------------------

/**
 * 读取错误上的 HTTP 状态；拿不到就返回 null。
 *
 * 优先走 `instanceof`，同时接受结构等价的错误对象：跨包实例（测试替身、被复制的模块实例）
 * 会让 `instanceof` 失效，而这里要判断的是一条稳定契约——`status`。
 */
export function analyticsErrorStatus(error: unknown): number | null {
  if (error instanceof AnalyticsRequestError) {
    return error.status;
  }
  if (typeof error !== "object" || error === null) {
    return null;
  }
  const status = (error as { status?: unknown }).status;
  return typeof status === "number" ? status : null;
}

/** 服务端是否明确拒绝了这次操作（403）。 */
export function isAnalyticsForbidden(error: unknown): boolean {
  return analyticsErrorStatus(error) === 403;
}

// --- 状态标签 ---------------------------------------------------------------

export type AnalyticsStatusTone =
  | "positive"
  | "warning"
  | "negative"
  | "neutral";

/**
 * 复用 `analytics-trace-panel.tsx` 已经建立的语义色板，不新造颜色 token。
 * 颜色只是辅助：每个标签都必须带文字。
 */
const TONE_CLASS: Record<AnalyticsStatusTone, string> = {
  positive:
    "border-transparent bg-emerald-600/10 text-emerald-700 dark:text-emerald-400",
  warning:
    "border-transparent bg-amber-600/10 text-amber-700 dark:text-amber-500",
  negative: "border-transparent bg-destructive/10 text-destructive",
  neutral: "bg-muted text-muted-foreground",
};

const TONE_ICON: Record<AnalyticsStatusTone, typeof CircleCheckIcon> = {
  positive: CircleCheckIcon,
  warning: TriangleAlertIcon,
  negative: CircleXIcon,
  neutral: CircleMinusIcon,
};

export function AnalyticsStatusPill({
  tone,
  label,
  testId,
}: {
  tone: AnalyticsStatusTone;
  label: string;
  testId?: string;
}) {
  const Icon = TONE_ICON[tone];
  return (
    <span
      data-testid={testId}
      data-tone={tone}
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[11px] leading-4 whitespace-nowrap",
        TONE_CLASS[tone],
      )}
    >
      <Icon aria-hidden="true" className="size-3 shrink-0" />
      <span>{label}</span>
    </span>
  );
}

// --- 危险操作确认对话框 -----------------------------------------------------

/**
 * 危险操作的确认对话框。
 *
 * 仓库里没有 `alert-dialog` / `ConfirmDialog` 原语，因此这里用真实的
 * `role="alertdialog"` 元素实现，并满足四条可验收行为：
 *
 * - 打开时焦点移到"取消"（`Cancel` 永远是默认安全动作）；
 * - `Escape` 只在非提交中生效，提交中不允许关闭（避免用户在请求飞行时误判"已取消"）；
 * - 提交中"取消"与"确认"同时禁用，第二次点击不会发出第二个请求；
 * - 两个按钮都是原生 `button`，键盘可聚焦、可用 Enter/Space 触发。
 */
export function AnalyticsConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  pending = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  pending?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { t } = useI18n();
  const titleId = useId();
  const descriptionId = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (open) {
      cancelRef.current?.focus();
    }
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") {
        return;
      }
      if (pending) {
        // 提交中不允许关闭：请求已经发出，关闭界面只会让结果无人看见。
        event.preventDefault();
        return;
      }
      event.preventDefault();
      onCancel();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onCancel, pending]);

  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        className="bg-background border-border flex w-full max-w-md min-w-0 flex-col gap-3 rounded-lg border p-4 shadow-lg"
      >
        <h2 id={titleId} className="text-base font-semibold">
          {title}
        </h2>
        <p id={descriptionId} className="text-muted-foreground text-sm">
          {description}
        </p>
        <div className="flex flex-wrap justify-end gap-2">
          <Button
            ref={cancelRef}
            type="button"
            variant="outline"
            className="min-h-11 min-w-11"
            disabled={pending}
            onClick={onCancel}
          >
            {t.analytics.common.cancel}
          </Button>
          <Button
            type="button"
            variant="destructive"
            className="min-h-11 min-w-11"
            disabled={pending}
            onClick={onConfirm}
          >
            {pending ? t.analytics.common.saving : confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}

// --- 页面框架 ---------------------------------------------------------------

export interface AnalyticsPageProps {
  title: string;
  description: string;
  isLoading?: boolean;
  isError?: boolean;
  /** 查询错误；`status === 403` 时框架渲染禁止态，优先于其他状态。 */
  error?: unknown;
  /** 调用方已经判定为禁止（例如管理员面板被服务端拒绝）。 */
  isForbidden?: boolean;
  onRetry?: () => void;
  isEmpty?: boolean;
  emptyMessage?: string;
  emptySupplement?: ReactNode;
  children?: ReactNode;
}

/**
 * 五个分析页面共用的外壳：标题＋说明，然后**恰好**渲染一种状态。
 *
 * 状态优先级：禁止 > 加载 > 错误 > 空 > 内容。把禁止放在最前，是因为"没有权限"比
 * "正在加载"更接近事实——服务端已经给出结论，不该继续显示骨架。
 */
export function AnalyticsPage({
  title,
  description,
  isLoading = false,
  isError = false,
  error,
  isForbidden = false,
  onRetry,
  isEmpty = false,
  emptyMessage,
  emptySupplement,
  children,
}: AnalyticsPageProps) {
  const { t } = useI18n();
  const forbidden = isForbidden || isAnalyticsForbidden(error);

  let body: ReactNode;
  if (forbidden) {
    body = (
      <p role="alert" className="text-muted-foreground text-sm">
        {t.analytics.common.forbidden}
      </p>
    );
  } else if (isLoading) {
    body = (
      <p role="status" className="text-muted-foreground text-sm">
        {t.analytics.common.loading}
      </p>
    );
  } else if (isError) {
    body = (
      <div role="alert" className="flex flex-col items-start gap-3">
        <p className="text-sm">{t.analytics.common.loadFailed}</p>
        {onRetry && (
          <Button
            type="button"
            variant="outline"
            className="min-h-11 min-w-11"
            onClick={onRetry}
          >
            {t.analytics.common.retry}
          </Button>
        )}
      </div>
    );
  } else if (isEmpty) {
    body = (
      <>
        <p role="status" className="text-muted-foreground text-sm">
          {emptyMessage ?? t.analytics.common.empty}
        </p>
        {emptySupplement}
      </>
    );
  } else {
    body = children;
  }

  return (
    <WorkspaceContainer>
      <WorkspaceHeader />
      <WorkspaceBody>
        {/* 每一层都带 min-w-0：宽表格只能在自己的滚动容器里滚，不能把页面撑宽。 */}
        <div className="mx-auto flex w-full max-w-5xl min-w-0 flex-col gap-5 p-4 sm:p-6">
          <header className="flex min-w-0 flex-col gap-1">
            <h1 className="text-2xl font-semibold break-words">{title}</h1>
            <p className="text-muted-foreground text-sm">{description}</p>
          </header>
          <section className="flex min-w-0 flex-col gap-4">{body}</section>
        </div>
      </WorkspaceBody>
    </WorkspaceContainer>
  );
}

/**
 * 宽表格的显式内部滚动容器。
 *
 * `tabIndex={0}` 让键盘用户可以在这个区域里横向滚动（否则只能用鼠标滚轮/触控板），
 * 因此它同时是 `role="region"` 并需要一个可访问名称。
 */
export function AnalyticsTableScroll({
  label,
  className,
  children,
}: {
  label: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      role="region"
      aria-label={label}
      tabIndex={0}
      className={cn(
        "border-border focus-visible:ring-ring/50 w-full min-w-0 overflow-x-auto rounded-md border outline-none focus-visible:ring-[3px]",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** 过期版本的显式刷新入口：必须由用户主动点击，绝不自动重放。 */
export function AnalyticsStaleBanner({
  onRefresh,
  refreshing = false,
}: {
  onRefresh: () => void;
  refreshing?: boolean;
}) {
  const { t } = useI18n();
  return (
    <div
      role="alert"
      data-testid="analytics-stale-banner"
      className="border-destructive/40 bg-destructive/5 flex min-w-0 flex-col items-start gap-2 rounded-md border p-3"
    >
      <p className="text-sm font-medium">{t.analytics.schema.staleTitle}</p>
      <p className="text-muted-foreground text-sm">
        {t.analytics.schema.staleBody}
      </p>
      <Button
        type="button"
        variant="outline"
        className="min-h-11 min-w-11"
        disabled={refreshing}
        onClick={onRefresh}
      >
        {t.analytics.common.refresh}
      </Button>
    </div>
  );
}

/** 就地展示的变更/校验失败提示。 */
export function AnalyticsInlineAlert({
  id,
  children,
}: {
  id?: string;
  children: ReactNode;
}) {
  return (
    <p id={id} role="alert" className="text-destructive text-sm">
      {children}
    </p>
  );
}

// --- 只读：数据源目录 -------------------------------------------------------

const DATASOURCE_STATUS: Record<
  DatasourceStatus,
  {
    tone: AnalyticsStatusTone;
    key: "statusActive" | "statusDisabled" | "statusUnhealthy";
  }
> = {
  active: { tone: "positive", key: "statusActive" },
  disabled: { tone: "neutral", key: "statusDisabled" },
  unhealthy: { tone: "warning", key: "statusUnhealthy" },
};

export function AnalyticsDatasourceStatusPill({
  status,
}: {
  status: DatasourceStatus;
}) {
  const { t } = useI18n();
  const mapped = DATASOURCE_STATUS[status];
  return (
    <AnalyticsStatusPill
      tone={mapped.tone}
      label={t.analytics.datasource[mapped.key]}
      testId={`datasource-status-${status}`}
    />
  );
}

/**
 * 普通用户可读的数据源目录。
 *
 * 列里只有 `name / engine / default_schema / status`：`owner_id` 与 `secret_ref` 属于管理员视图，
 * 而且 `DatasourceView` 这个类型本身也没有它们——这一层不是"记得别渲染"，而是没有字段可渲染。
 */
export function DatasourceCatalogTable({
  datasources,
}: {
  datasources: DatasourceView[];
}) {
  const { t } = useI18n();
  const d = t.analytics.datasource;
  return (
    <AnalyticsTableScroll label={d.title}>
      <table className="w-full min-w-[44rem] border-collapse text-sm">
        <caption className="sr-only">{d.title}</caption>
        <thead>
          <tr className="border-border border-b text-left">
            <th scope="col" className="p-2 font-medium">
              {d.name}
            </th>
            <th scope="col" className="p-2 font-medium">
              {d.engine}
            </th>
            <th scope="col" className="p-2 font-medium">
              {d.defaultSchema}
            </th>
            <th scope="col" className="p-2 font-medium">
              {d.status}
            </th>
            <th scope="col" className="p-2 font-medium">
              {d.analyzeAction}
            </th>
          </tr>
        </thead>
        <tbody>
          {datasources.map((datasource) => (
            <tr
              key={datasource.id}
              className="border-border border-b last:border-b-0"
            >
              <td className="p-2 font-medium break-words">{datasource.name}</td>
              {/* engine 是协议值（mysql / postgresql）：保持英文原样，只做等宽展示。 */}
              <td className="p-2">
                <code className="font-mono text-xs">{datasource.engine}</code>
              </td>
              <td className="p-2 break-words">
                {datasource.default_schema ?? t.analytics.common.notAvailable}
              </td>
              <td className="p-2">
                <AnalyticsDatasourceStatusPill status={datasource.status} />
              </td>
              <td className="p-2">
                <Button asChild variant="outline" className="min-h-11 min-w-11">
                  <Link
                    href={newAnalysisPrefillHref(
                      d.analysisPrompt(datasource.name),
                    )}
                    aria-label={d.analyzeLabel(datasource.name)}
                  >
                    {d.analyzeAction}
                  </Link>
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </AnalyticsTableScroll>
  );
}

// --- 只读：指标目录 ---------------------------------------------------------

const METRIC_STATUS: Record<
  MetricStatus,
  {
    tone: AnalyticsStatusTone;
    key: "statusDraft" | "statusActive" | "statusRetired";
  }
> = {
  draft: { tone: "neutral", key: "statusDraft" },
  active: { tone: "positive", key: "statusActive" },
  // 已下线是需要被注意的终态，但不代表错误，因此用 warning 而不是 negative。
  retired: { tone: "warning", key: "statusRetired" },
};

export function AnalyticsMetricStatusPill({
  status,
}: {
  status: MetricStatus;
}) {
  const { t } = useI18n();
  const mapped = METRIC_STATUS[status];
  return (
    <AnalyticsStatusPill
      tone={mapped.tone}
      label={t.analytics.metric[mapped.key]}
      testId={`metric-status-${status}`}
    />
  );
}

/**
 * 所有人可读的指标目录。
 *
 * `expression` 是**定义字符串**：这里按纯文本渲染（`<code>`），绝不求值、绝不拼进 SQL、
 * 也绝不交给任何解析器。`renderActions` 只在管理员场景传入，非管理员拿到的表格里
 * 连操作列都不存在。
 */
export function MetricCatalogTable({
  metrics,
  renderActions,
}: {
  metrics: MetricView[];
  renderActions?: (metric: MetricView) => ReactNode;
}) {
  const { t } = useI18n();
  const m = t.analytics.metric;
  return (
    <AnalyticsTableScroll label={m.title}>
      <table className="w-full min-w-[60rem] border-collapse text-sm">
        <caption className="sr-only">{m.title}</caption>
        <thead>
          <tr className="border-border border-b text-left">
            <th scope="col" className="p-2 font-medium">
              {m.key}
            </th>
            <th scope="col" className="p-2 font-medium">
              {m.name}
            </th>
            <th scope="col" className="p-2 font-medium">
              {m.description}
            </th>
            <th scope="col" className="p-2 font-medium">
              {m.expression}
            </th>
            <th scope="col" className="p-2 font-medium">
              {m.dimensions}
            </th>
            <th scope="col" className="p-2 font-medium">
              {m.version}
            </th>
            <th scope="col" className="p-2 font-medium">
              {m.status}
            </th>
            <th scope="col" className="p-2 font-medium">
              {m.analyzeAction}
            </th>
            {renderActions && (
              <th scope="col" className="p-2 font-medium">
                {t.analytics.common.edit}
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {metrics.map((metric) => (
            <tr
              key={metric.key}
              className="border-border border-b last:border-b-0"
            >
              <td className="p-2">
                <code className="font-mono text-xs">{metric.key}</code>
              </td>
              <td className="p-2 font-medium break-words">{metric.name}</td>
              <td className="text-muted-foreground p-2 break-words">
                {metric.description}
              </td>
              <td className="p-2">
                {/* 纯文本展示：不做任何求值，也不包装成可执行 SQL。 */}
                <code
                  className="block max-w-[24rem] font-mono text-xs break-words"
                  data-testid={`metric-expression-${metric.key}`}
                >
                  {metric.expression}
                </code>
              </td>
              <td className="p-2">
                {metric.dimensions.length === 0 ? (
                  t.analytics.common.notAvailable
                ) : (
                  <span className="flex flex-wrap gap-1">
                    {metric.dimensions.map((dimension) => (
                      <code key={dimension} className="font-mono text-xs">
                        {dimension}
                      </code>
                    ))}
                  </span>
                )}
              </td>
              <td className="p-2 font-mono text-xs">{metric.version}</td>
              <td className="p-2">
                <AnalyticsMetricStatusPill status={metric.status} />
              </td>
              <td className="p-2">
                <Button asChild variant="outline" className="min-h-11 min-w-11">
                  <Link
                    href={newAnalysisPrefillHref(
                      m.analysisPrompt(metric.key, metric.name),
                    )}
                    aria-label={m.analyzeLabel(metric.key, metric.name)}
                  >
                    {m.analyzeAction}
                  </Link>
                </Button>
              </td>
              {renderActions && (
                <td className="p-2">{renderActions(metric)}</td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </AnalyticsTableScroll>
  );
}

// --- 只读：审计历史 ---------------------------------------------------------

const AUDIT_STATUS: Record<
  QueryAuditStatus,
  { tone: AnalyticsStatusTone; key: "statusRunning" | "statusCompleted" }
> = {
  started: { tone: "neutral", key: "statusRunning" },
  completed: { tone: "positive", key: "statusCompleted" },
};

/**
 * risk 的取值（low/medium/high/blocked）与 phase 一样是服务端协议值，
 * `analytics.*` 词典里没有对应的本地化条目，因此按仓库约定保留英文原样，
 * 并用图标＋文字（而不是颜色）表达程度。
 */
const RISK_TONE: Record<QueryRisk, AnalyticsStatusTone> = {
  low: "neutral",
  medium: "warning",
  high: "negative",
  blocked: "negative",
};

function formatTimestamp(value: string, locale: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function AuditFact({
  label,
  value,
}: {
  label: string;
  value: string | number | null;
}) {
  const { t } = useI18n();
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <dt className="text-muted-foreground text-[11px]">{label}</dt>
      <dd className="min-w-0 font-mono text-xs break-words">
        {value ?? t.analytics.common.notAvailable}
      </dd>
    </div>
  );
}

function DigestField({ label, value }: { label: string; value: string }) {
  const { t } = useI18n();
  return (
    <div className="flex min-w-0 items-center gap-1">
      <span className="text-muted-foreground shrink-0 text-[11px]">
        {label}
      </span>
      <code className="min-w-0 flex-1 truncate font-mono text-xs">
        {abbreviateDigest(value)}
      </code>
      <CopyButton
        clipboardData={value}
        className="min-h-11 min-w-11"
        aria-label={`${t.analytics.common.copy} ${label}`}
      />
    </div>
  );
}

/**
 * 一条审计记录。
 *
 * 渲染的字段是 `QueryAuditView` 的全部——而它按设计就不含 SQL、结果行、凭据、DSN 与异常文本。
 * 因此"不泄漏"不是靠这里克制，而是靠类型与解析层没有这些字段。
 */
export function AuditRecordCard({ audit }: { audit: QueryAuditView }) {
  const { t, locale } = useI18n();
  const h = t.analytics.history;
  const status = AUDIT_STATUS[audit.status];
  return (
    <li
      data-testid="audit-record"
      className="border-border flex min-w-0 flex-col gap-3 rounded-md border p-3"
    >
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        {/* phase 是协议值（policy/authorization/plan/execute），按仓库约定保持英文。 */}
        <code className="font-mono text-xs break-words">{audit.phase}</code>
        <AnalyticsStatusPill
          tone={status.tone}
          label={t.analytics.trace[status.key]}
          testId={`audit-status-${audit.status}`}
        />
        {audit.risk !== null && (
          <AnalyticsStatusPill
            tone={RISK_TONE[audit.risk]}
            label={audit.risk}
            testId={`audit-risk-${audit.risk}`}
          />
        )}
      </div>
      <dl className="grid min-w-0 grid-cols-2 gap-x-3 gap-y-2 sm:grid-cols-3 lg:grid-cols-4">
        <AuditFact label={h.code} value={audit.decision_code} />
        <AuditFact label={h.rows} value={audit.row_count} />
        <AuditFact label={h.bytes} value={audit.byte_count} />
        <AuditFact label={h.cost} value={formatEngineCost(audit.engine_cost)} />
        <AuditFact label={h.latency} value={audit.latency_ms} />
        <AuditFact
          label={h.startedAt}
          value={formatTimestamp(audit.started_at, locale)}
        />
        <AuditFact
          label={h.finishedAt}
          value={
            audit.finished_at === null
              ? null
              : formatTimestamp(audit.finished_at, locale)
          }
        />
      </dl>
      {(audit.query_hash !== null || audit.plan_digest !== null) && (
        <div className="flex min-w-0 flex-col gap-2">
          {audit.query_hash !== null && (
            <DigestField label={h.queryHash} value={audit.query_hash} />
          )}
          {audit.plan_digest !== null && (
            <DigestField label={h.planDigest} value={audit.plan_digest} />
          )}
        </div>
      )}
    </li>
  );
}

/**
 * 审计记录列表 ＋ keyset 分页。
 *
 * 分页只认服务端游标：`hasMore` 为真时给出"加载更多"，加载完显示"没有更多"。
 * 界面里没有任何 offset 概念，也不做页码跳转。
 */
export function AuditHistoryList({
  audits,
  hasMore,
  isFetching,
  onLoadMore,
}: {
  audits: QueryAuditView[];
  hasMore: boolean;
  isFetching: boolean;
  onLoadMore: () => void;
}) {
  const { t } = useI18n();
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <ul className="flex min-w-0 flex-col gap-3">
        {audits.map((audit) => (
          <AuditRecordCard key={audit.id} audit={audit} />
        ))}
      </ul>
      <div className="flex justify-center">
        {hasMore ? (
          <Button
            type="button"
            variant="outline"
            className="min-h-11 min-w-11"
            disabled={isFetching}
            onClick={onLoadMore}
            data-testid="audit-load-more"
          >
            {isFetching
              ? t.analytics.common.loading
              : t.analytics.common.loadMore}
          </Button>
        ) : (
          <p role="status" className="text-muted-foreground text-xs">
            {t.analytics.common.noMore}
          </p>
        )}
      </div>
    </div>
  );
}

// --- 只读：报告列表 ---------------------------------------------------------

const REPORT_STATUS_LABEL: Record<ReportStatus, "statusPublished"> = {
  published: "statusPublished",
};

/**
 * 报告列表。
 *
 * 下载动作只用共享工具构造同源 Gateway 产物 URL；URL 本身不是授权凭证，
 * 每次请求仍由 Gateway 的 `threads:read` owner check 决定能否读取。
 */
export function ReportCatalogList({
  reports,
}: {
  reports: AnalysisReportView[];
}) {
  const { t, locale } = useI18n();
  const r = t.analytics.report;
  return (
    <ul className="flex min-w-0 flex-col gap-3">
      {reports.map((report) => (
        <li
          key={report.id}
          data-testid="report-record"
          className="border-border flex min-w-0 flex-col gap-3 rounded-md border p-3"
        >
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span className="min-w-0 text-sm font-medium break-words">
              {report.title}
            </span>
            <AnalyticsStatusPill
              tone="positive"
              label={r[REPORT_STATUS_LABEL[report.status]]}
              testId={`report-status-${report.status}`}
            />
          </div>
          <dl className="grid min-w-0 grid-cols-1 gap-x-3 gap-y-2 sm:grid-cols-2">
            <AuditFact label={r.artifactPath} value={report.artifact_path} />
            <AuditFact
              label={r.createdAt}
              value={formatTimestamp(report.created_at, locale)}
            />
          </dl>
          <div className="flex min-w-0 flex-col gap-1">
            <span className="text-muted-foreground text-[11px]">
              {r.evidence}
            </span>
            <ul className="flex min-w-0 flex-col gap-1">
              {report.evidence_ids.map((evidenceId) => (
                <li
                  key={evidenceId}
                  className="flex min-w-0 items-center gap-1"
                >
                  <code className="min-w-0 flex-1 truncate font-mono text-xs">
                    {abbreviateDigest(evidenceId)}
                  </code>
                  <CopyButton
                    clipboardData={evidenceId}
                    className="min-h-11 min-w-11"
                    aria-label={`${t.analytics.common.copy} ${r.evidence}`}
                  />
                </li>
              ))}
            </ul>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline" className="min-h-11 min-w-11">
              <a
                href={urlOfArtifact({
                  filepath: report.artifact_path,
                  threadId: report.thread_id,
                  download: true,
                })}
                download
                data-testid="report-download"
              >
                <DownloadIcon className="size-4" aria-hidden="true" />
                {r.downloadReport}
              </a>
            </Button>
            <Button asChild variant="outline" className="min-h-11 min-w-11">
              <Link
                href={`/workspace/analysis/${encodeURIComponent(report.thread_id)}`}
                data-testid="report-open-analysis"
              >
                {r.openAnalysis}
              </Link>
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
}

// --- 空状态判定 -------------------------------------------------------------

/** 只有成功读取且结果为空时才算"空"：读取中或读取失败都不是空。 */
export function isCatalogEmpty(options: {
  isLoading: boolean;
  isError: boolean;
  count: number;
}): boolean {
  return !options.isLoading && !options.isError && options.count === 0;
}
