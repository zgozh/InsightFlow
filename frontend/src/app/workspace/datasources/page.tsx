"use client";

/**
 * `/workspace/datasources` —— 数据源目录与管理（Phase 4 §6）。
 *
 * 页面的分工刻意简单：目录表格（所有人可见）＋管理员面板（仅管理员渲染）。管理员面板里
 * 才有 `secret_ref` / `owner_id`，而且那两个字段只存在于管理员的解析类型里。
 *
 * 403 由带 `error` 的目录查询负责判定：客户端的管理员标记只决定入口是否渲染，
 * 服务端拒绝读取时页面渲染禁止态，而不是显示一张空表。
 */

import { useEffect } from "react";

import { DatasourceAdminSection } from "@/components/analytics/analytics-admin-panels";
import {
  AnalyticsPage,
  DatasourceCatalogTable,
  isCatalogEmpty,
} from "@/components/analytics/analytics-catalog-views";
import {
  useAdminDatasources,
  useAnalyticsDatasources,
  useAnalyticsIsAdmin,
} from "@/core/analytics/hooks";
import { useI18n } from "@/core/i18n/hooks";

export default function DatasourcesPage() {
  const { t } = useI18n();
  const d = t.analytics.datasource;
  const isAdmin = useAnalyticsIsAdmin();
  const catalogue = useAnalyticsDatasources();
  // enabled=false 时普通用户不会发起管理员查询，也就不会顺带拿到管理员字段。
  const adminList = useAdminDatasources(isAdmin);

  useEffect(() => {
    document.title = `${d.title} - ${t.pages.appName}`;
  }, [d.title, t.pages.appName]);

  return (
    <AnalyticsPage
      title={d.title}
      description={d.description}
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
        count: catalogue.datasources.length,
      })}
      emptyMessage={t.analytics.common.empty}
    >
      <DatasourceCatalogTable datasources={catalogue.datasources} />
      {isAdmin && (
        <DatasourceAdminSection
          datasources={adminList.datasources}
          isLoading={adminList.isLoading}
          isError={adminList.isError}
        />
      )}
    </AnalyticsPage>
  );
}
