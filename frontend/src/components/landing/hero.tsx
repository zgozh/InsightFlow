"use client";

import { ChevronRightIcon } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { BlackHole } from "./black-hole";

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
  return (
    <div
      className={cn("relative w-full overflow-hidden bg-[#0a0a0a]", className)}
    >
      <BlackHole />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[linear-gradient(90deg,rgba(5,6,10,.85)_0%,rgba(5,6,10,.5)_36%,transparent_70%)] max-md:bg-[linear-gradient(180deg,rgba(5,6,10,.4),rgba(5,6,10,.62)_45%,transparent_85%)]"
      />
      <div className="container-md relative mx-auto flex min-h-[92svh] w-full items-center px-6 pt-20 pb-12 md:px-10 md:py-16">
        <div
          data-testid="hero-copy"
          className="relative z-10 flex max-w-[35rem] flex-col items-start text-left max-md:pb-32"
        >
          <h1 className="text-5xl leading-tight font-bold tracking-tight break-words text-[#fff6e7] md:text-6xl">
            {productName}
          </h1>
          <p className="mt-5 max-w-4xl text-2xl leading-snug font-semibold text-balance text-[#fff0dc] md:text-4xl">
            {headline}
          </p>
          <p
            className="mt-4 max-w-3xl text-base leading-7 text-zinc-100 sm:text-lg"
            style={{ textShadow: "0 1px 8px rgba(0, 0, 0, .95)" }}
          >
            {description}
          </p>
          <Link href="/workspace">
            <Button
              className="mt-7 h-12 border border-[#ffd9a0]/30 bg-[#ffc078] px-6 text-[#241207] shadow-[0_0_35px_#e68b3825] hover:bg-[#ffcf98]"
              size="lg"
            >
              <span className="text-md">{enterLabel}</span>
              <ChevronRightIcon className="size-4" />
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
