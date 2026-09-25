"use client";

import Link from "next/link";

import { Button } from "@/components/ui/button";
import { useI18n } from "@/core/i18n/hooks";

/**
 * 受控分析后端及工具隔离尚未通过复验前，分析入口明确保持不可用；不能复用普通聊天运行链。
 */
export default function AnalysisThreadPage() {
  const { t } = useI18n();

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-4 p-6">
      <section
        aria-labelledby="analysis-unavailable-title"
        className="bg-card space-y-4 rounded-xl border p-6 shadow-sm"
      >
        <div className="space-y-2">
          <h1
            className="text-2xl font-semibold tracking-tight"
            id="analysis-unavailable-title"
          >
            {t.analysisUnavailable.title}
          </h1>
          <p className="text-muted-foreground">
            {t.analysisUnavailable.description}
          </p>
        </div>
        <Button asChild>
          <Link href="/workspace/chats/new">
            {t.analysisUnavailable.goToChat}
          </Link>
        </Button>
      </section>
    </main>
  );
}
