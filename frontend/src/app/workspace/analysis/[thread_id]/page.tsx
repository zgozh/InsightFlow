"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import ChatPage from "@/components/workspace/chats/chat-page";
import { useI18n } from "@/core/i18n/hooks";
import { useThreadMetadata } from "@/core/threads/hooks";

function AnalysisRouteState({ message }: { message: string }) {
  const { t } = useI18n();

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-4 p-6">
      <section
        aria-labelledby="analysis-state-title"
        aria-live="polite"
        className="bg-card space-y-4 rounded-xl border p-6 shadow-sm"
        role="status"
      >
        <div className="space-y-2">
          <h1
            className="text-2xl font-semibold tracking-tight"
            id="analysis-state-title"
          >
            {t.analysisUnavailable.title}
          </h1>
          <p className="text-muted-foreground">{message}</p>
        </div>
        <Button asChild>
          <Link href="/workspace/analysis/new">
            {t.analysisUnavailable.goToNewAnalysis}
          </Link>
        </Button>
      </section>
    </main>
  );
}

function ExistingAnalysisThread({ threadId }: { threadId: string }) {
  const { t } = useI18n();
  const metadata = useThreadMetadata(threadId);

  if (metadata.isLoading) {
    return <AnalysisRouteState message={t.analysisUnavailable.loading} />;
  }
  if (metadata.isError) {
    return <AnalysisRouteState message={t.analysisUnavailable.unavailable} />;
  }
  if (metadata.data === null || metadata.data === undefined) {
    return <AnalysisRouteState message={t.analysisUnavailable.missingThread} />;
  }
  if (metadata.data.metadata?.analysis_mode !== true) {
    return <AnalysisRouteState message={t.analysisUnavailable.wrongThread} />;
  }

  return <ChatPage mode="analysis" />;
}

export default function AnalysisThreadPage() {
  const params = useParams<{ thread_id: string }>();
  if (params.thread_id === "new") {
    return <ChatPage mode="analysis" />;
  }
  return <ExistingAnalysisThread threadId={params.thread_id} />;
}
