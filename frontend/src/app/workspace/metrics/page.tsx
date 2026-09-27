"use client";

/**
 * `/workspace/metrics` —— 指标目录与管理（Phase 4 §6）。
 *
 * 目录对所有人生效；创建／修改／下线只对管理员渲染。`expression` 始终是**定义字符串**：
 * 这里只把它当纯文本展示与提交，从不求值，也从不包装成可执行 SQL。
 */

import { useEffect } from "react";

import { MetricAdminSection } from "@/components/analytics/analytics-admin-panels";
import {
  AnalyticsPage,
  isCatalogEmpty,
  MetricCatalogTable,
} from "@/components/analytics/analytics-catalog-views";
import {
  useAdminMetrics,
  useAnalyticsIsAdmin,
  useAnalyticsMetrics,
} from "@/core/analytics/hooks";
import { useI18n } from "@/core/i18n/hooks";

export default function MetricsPage() {
  const { t } = useI18n();
  const m = t.analytics.metric;
  const isAdmin = useAnalyticsIsAdmin();
  const catalogue = useAnalyticsMetrics();
  const adminList = useAdminMetrics(isAdmin);
  const adminSection = isAdmin ? (
    <MetricAdminSection
      metrics={adminList.metrics}
      isError={adminList.isError}
    />
  ) : null;

  useEffect(() => {
    document.title = `${m.title} - ${t.pages.appName}`;
  }, [m.title, t.pages.appName]);

  return (
    <AnalyticsPage
      title={m.title}
      description={m.description}
      isLoading={catalogue.isLoading}
      isError={catalogue.isError}
      // 管理员列表的 403 也要成为页面级禁止态：客户端的管理员标记只是入口门禁，
      // 服务端拒绝读取时页面必须如实显示"禁止访问"，而不是一张空表或通用失败。
      error={catalogue.error ?? (isAdmin ? adminList.error : undefined)}
      onRetry={() => {
        void catalogue.refetch();
      }}
      isEmpty={isCatalogEmpty({
        isLoading: catalogue.isLoading,
        isError: catalogue.isError,
        count: catalogue.metrics.length,
      })}
      emptyMessage={isAdmin ? m.adminEmpty : m.empty}
      emptySupplement={adminSection}
    >
      <MetricCatalogTable metrics={catalogue.metrics} />
      {adminSection}
    </AnalyticsPage>
  );
}
