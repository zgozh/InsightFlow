"use client";

/**
 * `/workspace/reports` —— 已发布报告（Phase 4 §6）。
 *
 * 报告只登记索引：标题、状态、产物路径、证据编号与创建时间。**打开产物必须走会话路由**，
 * 因此这里唯一的动作是"打开对应分析"，链接到 `/workspace/analysis/{thread_id}`，
 * 由既有的分析会话与产物面板负责文件访问与授权。前端不构造产物直链、不请求产物字节——
 * 自己拼一个"公开"产物 URL 等于把授权边界搬到客户端。
 */

import { useEffect } from "react";

import {
  AnalyticsPage,
  isCatalogEmpty,
  ReportCatalogList,
} from "@/components/analytics/analytics-catalog-views";
import { Button } from "@/components/ui/button";
import { useAnalysisReports } from "@/core/analytics/hooks";
import { useI18n } from "@/core/i18n/hooks";

export default function ReportsPage() {
  const { t } = useI18n();
  const r = t.analytics.report;
  const reports = useAnalysisReports();

  useEffect(() => {
    document.title = `${r.title} - ${t.pages.appName}`;
  }, [r.title, t.pages.appName]);

  return (
    <AnalyticsPage
      title={r.title}
      description={r.description}
      isLoading={reports.isLoading}
      isError={reports.isError}
      error={reports.error}
      onRetry={() => {
        void reports.refresh();
      }}
      isEmpty={isCatalogEmpty({
        isLoading: reports.isLoading,
        isError: reports.isError,
        count: reports.reports.length,
      })}
      emptyMessage={r.empty}
    >
      <ReportCatalogList reports={reports.reports} />
      {/* 报告索引同样是 keyset 分页：只有明确还有下一页时才给出按钮。 */}
      {reports.hasMore && (
        <div className="flex justify-center">
          <Button
            type="button"
            variant="outline"
            className="min-h-11 min-w-11"
            disabled={reports.isFetching}
            onClick={() => {
              void reports.loadMore();
            }}
            data-testid="report-load-more"
          >
            {reports.isFetching
              ? t.analytics.common.loading
              : t.analytics.common.loadMore}
          </Button>
        </div>
      )}
    </AnalyticsPage>
  );
}
