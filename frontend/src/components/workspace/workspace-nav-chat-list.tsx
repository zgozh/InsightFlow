"use client";

import {
  BlocksIcon,
  BotIcon,
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
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useSettingsDialog } from "@/components/workspace/settings";
import { useAgentsApiEnabled } from "@/core/agents";
import { useI18n } from "@/core/i18n/hooks";

/**
 * 侧边栏主导航 = InsightFlow 的分析工作流入口，顺序固定。
 *
 * 继承自 DeerFlow 的智能体与能力中心仍然可用，但退到第二个「更多」分组：兼容期不删除任何
 * 既有能力，只是不再占据主导航位置。
 *
 * 旧的「对话」入口**不再重复列出**：它指向的 `/workspace/chats` 已经由主导航的「经营分析」
 * 承担，同一路由放两个条目会让两行同时高亮，用户与测试都无法区分它们。路由本身完全保留。
 */
export function WorkspaceNavChatList() {
  const { t } = useI18n();
  const pathname = usePathname();
  const { openSettings } = useSettingsDialog();
  const { enabled: agentsEnabled } = useAgentsApiEnabled();

  // 分析会话与审计链路同属分析工作台：/workspace/chats 是会话列表，
  // /workspace/analysis 是新的分析路由前缀。新建分析页单独高亮，避免两个条目同时点亮。
  const isAnalysisRoute =
    pathname.startsWith("/workspace/chats") ||
    (pathname.startsWith("/workspace/analysis") &&
      pathname !== "/workspace/analysis/new");

  return (
    <>
      <SidebarGroup className="pt-1">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              isActive={pathname === "/workspace/analysis/new"}
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
              isActive={isAnalysisRoute}
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
      <SidebarGroup className="pt-1">
        <SidebarGroupLabel>{t.analytics.nav.more}</SidebarGroupLabel>
        <SidebarMenu>
          <SidebarMenuItem>
            {agentsEnabled ? (
              <SidebarMenuButton
                isActive={pathname.startsWith("/workspace/agents")}
                tooltip={t.sidebar.agents}
                asChild
              >
                <Link
                  className="text-muted-foreground"
                  href="/workspace/agents"
                >
                  <BotIcon />
                  <span>{t.sidebar.agents}</span>
                </Link>
              </SidebarMenuButton>
            ) : (
              // Disabled: aria-disabled drives the sidebar CVA to suppress
              // pointer events on the button, so wrap it in a hoverable span
              // that still surfaces the "feature not enabled" tooltip for mouse
              // users. The button stays in the tab order (no tabIndex={-1}) and
              // is wired via aria-describedby to a visually-hidden reason, so
              // keyboard and screen-reader users also learn why it is disabled.
              <Tooltip>
                <TooltipTrigger asChild>
                  {/* cursor-not-allowed lives on the span (the element that
                      still receives pointer events), not the inert button. */}
                  <span className="block w-full cursor-not-allowed">
                    <SidebarMenuButton
                      className="text-muted-foreground/50"
                      aria-disabled
                      aria-describedby="agents-disabled-reason"
                    >
                      <BotIcon />
                      <span>{t.sidebar.agents}</span>
                    </SidebarMenuButton>
                    <span id="agents-disabled-reason" className="sr-only">
                      {t.sidebar.agentsDisabledTooltip}
                    </span>
                  </span>
                </TooltipTrigger>
                <TooltipContent side="right">
                  {t.sidebar.agentsDisabledTooltip}
                </TooltipContent>
              </Tooltip>
            )}
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton
              isActive={pathname.startsWith("/workspace/capabilities")}
              tooltip={t.capabilities.title}
              asChild
            >
              <Link
                className="text-muted-foreground"
                href="/workspace/capabilities"
              >
                <BlocksIcon />
                <span>{t.capabilities.title}</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarGroup>
    </>
  );
}
