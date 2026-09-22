"use client";

import { ChevronRightIcon } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRef } from "react";

import { Button } from "@/components/ui/button";
import { useRenderActivity } from "@/core/dom/render-activity";
import { cn } from "@/lib/utils";

const Galaxy = dynamic(() => import("@/components/ui/galaxy"), { ssr: false });

export type HeroProps = {
  className?: string;
  productName: string;
  headline: string;
  description: string;
  enterLabel: string;
};

/**
 * 落地页首屏只承担一件事：说清产品价值并把用户送进工作台。
 *
 * 文案由服务端从词条表解析后以纯字符串传入（客户端组件无法跨 RSC 边界接收函数），
 * 因此这里不出现任何硬编码的产品措辞。
 */
export function Hero({
  className,
  productName,
  headline,
  description,
  enterLabel,
}: HeroProps) {
  const galaxyContainerRef = useRef<HTMLDivElement>(null);
  const renderGalaxy = useRenderActivity(galaxyContainerRef);

  return (
    <div
      className={cn(
        "relative flex size-full flex-col items-center justify-center",
        className,
      )}
    >
      <div
        ref={galaxyContainerRef}
        className="absolute inset-0 z-0 bg-black/40"
      >
        {renderGalaxy && (
          <Galaxy
            mouseRepulsion={false}
            starSpeed={0.2}
            density={0.6}
            glowIntensity={0.35}
            twinkleIntensity={0.3}
            speed={0.5}
          />
        )}
      </div>
      <div className="container-md relative z-10 mx-auto flex min-h-[92svh] flex-col items-center justify-center px-4 pt-20 pb-14">
        <h1 className="text-center text-5xl leading-tight font-bold break-words md:text-6xl">
          {productName}
        </h1>
        <p className="mt-6 max-w-4xl text-center text-2xl leading-snug font-semibold text-balance md:text-4xl">
          {headline}
        </p>
        <p className="text-muted-foreground mt-6 max-w-3xl text-center text-base leading-7 sm:text-lg">
          {description}
        </p>
        <Link href="/workspace">
          <Button className="mt-8 h-11 px-5" size="lg">
            <span className="text-md">{enterLabel}</span>
            <ChevronRightIcon className="size-4" />
          </Button>
        </Link>
      </div>
    </div>
  );
}
