"use client";

import {
  CalendarClock,
  ChartColumnIcon,
  DatabaseIcon,
  FileTextIcon,
  HistoryIcon,
  MessagesSquare,
  MessageSquarePlus,
  SettingsIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  SidebarGroup,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { useSettingsDialog } from "@/components/workspace/settings";
import { getWorkspaceNavigationActiveState } from "@/components/workspace/workspace-nav-state";
import { useI18n } from "@/core/i18n/hooks";

/**
 * 侧边栏主导航 = InsightFlow 的分析工作流入口，顺序固定。
 *
 * Phase 5 之后上游的智能体与能力中心入口已随其路由一起删除：这里只保留
 * 分析、数据源、指标、报告、定时任务、历史与设置。
 */
export function WorkspaceNavChatList() {
  const { t } = useI18n();
  const pathname = usePathname();
  const { openSettings } = useSettingsDialog();
  const activeNavigation = getWorkspaceNavigationActiveState(pathname);

  return (
    <>
      <SidebarGroup className="pt-1">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              isActive={activeNavigation.newAnalysis}
              tooltip={t.analytics.nav.newAnalysis}
              asChild
            >
              <Link
                className="text-muted-foreground"
                href="/workspace/analysis/new"
              >
                <MessageSquarePlus />
                <span>{t.analytics.nav.newAnalysis}</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton
              isActive={activeNavigation.analysis}
              tooltip={t.analytics.nav.analysis}
              asChild
            >
              <Link className="text-muted-foreground" href="/workspace/chats">
                <MessagesSquare />
                <span>{t.analytics.nav.analysis}</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton
              isActive={pathname.startsWith("/workspace/datasources")}
              tooltip={t.analytics.nav.datasources}
              asChild
            >
              <Link
                className="text-muted-foreground"
                href="/workspace/datasources"
              >
                <DatabaseIcon />
                <span>{t.analytics.nav.datasources}</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton
              isActive={pathname.startsWith("/workspace/metrics")}
              tooltip={t.analytics.nav.metrics}
              asChild
            >
              <Link className="text-muted-foreground" href="/workspace/metrics">
                <ChartColumnIcon />
                <span>{t.analytics.nav.metrics}</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton
              isActive={pathname.startsWith("/workspace/reports")}
              tooltip={t.analytics.nav.reports}
              asChild
            >
              <Link className="text-muted-foreground" href="/workspace/reports">
                <FileTextIcon />
                <span>{t.analytics.nav.reports}</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton
              isActive={pathname.startsWith("/workspace/scheduled-tasks")}
              tooltip={t.analytics.nav.scheduledTasks}
              asChild
            >
              <Link
                className="text-muted-foreground"
                href="/workspace/scheduled-tasks"
              >
                <CalendarClock />
                <span>{t.analytics.nav.scheduledTasks}</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton
              isActive={pathname.startsWith("/workspace/history")}
              tooltip={t.analytics.nav.history}
              asChild
            >
              <Link className="text-muted-foreground" href="/workspace/history">
                <HistoryIcon />
                <span>{t.analytics.nav.history}</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            {/* 设置没有独立路由，复用设置对话框入口，因此这里是按钮而不是链接。 */}
            <SidebarMenuButton
              onClick={() => openSettings("account")}
              tooltip={t.analytics.nav.settings}
            >
              <SettingsIcon />
              <span>{t.analytics.nav.settings}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarGroup>
    </>
  );
}
