"use client";

import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

function EvidenceMark() {
  return (
    <svg
      aria-hidden="true"
      className="text-primary size-7 shrink-0"
      fill="none"
      viewBox="0 0 32 32"
    >
      <path
        d="M7 23 15 9l11 8"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeOpacity=".55"
        strokeWidth="1.5"
      />
      <circle cx="7" cy="23" r="2.4" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="15" cy="9" r="2.4" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="26" cy="17" r="2.4" fill="currentColor" />
    </svg>
  );
}

function WelcomeDescription({ children }: { children: string }) {
  return (
    <p className="max-w-full text-wrap break-words whitespace-pre-line">
      {children}
    </p>
  );
}

export function Welcome({ className }: { className?: string }) {
  const { t } = useI18n();
  return (
    <div
      className={cn(
        "mx-auto flex w-full max-w-full flex-col items-center justify-center gap-2 px-4 py-4 text-center sm:px-8",
        className,
      )}
    >
      <div className="max-w-full text-2xl font-bold">
        <div className="flex max-w-full flex-wrap items-center justify-center gap-2">
          <EvidenceMark />
          <span>{t.welcome.greeting}</span>
        </div>
      </div>
      <div className="text-muted-foreground max-w-full text-sm">
        <WelcomeDescription>{t.welcome.description}</WelcomeDescription>
      </div>
    </div>
  );
}
