"use client";

/**
 * `/workspace/history` —— 审计历史（Phase 4 §6）。
 *
 * 两条不可让步的规则：
 *
 * 1. 分页只有服务端的 keyset 游标（`hasMore` + `loadMore`）；这里不引入任何 offset，
 *    因为 offset 会在持续追加的审计流上产生重复与跳漏。
 * 2. 只渲染 `QueryAuditView` 里的安全字段。SQL、结果行、凭据与异常文本根本不在解析类型里，
 *    因此没有任何"记得别渲染"的路径。
 *
 * 管理员可以按主体查询，但必须显式提交主体 ID；默认不提交，也就不会发起跨主体读取。
 */

import { useEffect } from "react";

import { AuditPrincipalLookup } from "@/components/analytics/analytics-admin-panels";
import {
  AnalyticsPage,
  AuditHistoryList,
} from "@/components/analytics/analytics-catalog-views";
import { useAnalyticsIsAdmin, useAuditHistory } from "@/core/analytics/hooks";
import { useI18n } from "@/core/i18n/hooks";

export default function HistoryPage() {
  const { t } = useI18n();
  const h = t.analytics.history;
  const isAdmin = useAnalyticsIsAdmin();
  const history = useAuditHistory();

  useEffect(() => {
    document.title = `${h.title} - ${t.pages.appName}`;
  }, [h.title, t.pages.appName]);

  return (
    <AnalyticsPage
      title={h.title}
      description={h.description}
      isLoading={history.isLoading}
      isError={history.isError}
      error={history.error}
      onRetry={() => {
        void history.refresh();
      }}
      isEmpty={
        !history.isLoading && !history.isError && history.audits.length === 0
      }
      emptyMessage={h.empty}
    >
      <AuditHistoryList
        audits={history.audits}
        hasMore={history.hasMore}
        isFetching={history.isFetching}
        onLoadMore={() => {
          void history.loadMore();
        }}
      />
      {isAdmin && <AuditPrincipalLookup />}
    </AnalyticsPage>
  );
}
