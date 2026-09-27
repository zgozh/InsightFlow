"use client";

import { ChevronRightIcon } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { PixelBlackHole } from "./pixel-black-hole";

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
      <div className="container-md mx-auto grid min-h-[92svh] w-full grid-cols-1 items-center gap-3 px-4 pt-20 pb-4 md:grid-cols-2 md:gap-8 md:py-16">
        <div
          data-testid="hero-copy"
          className="relative z-10 flex flex-col items-center text-center md:items-start md:text-left"
        >
          <h1 className="text-5xl leading-tight font-bold break-words md:text-6xl">
            {productName}
          </h1>
          <p className="mt-4 max-w-4xl text-2xl leading-snug font-semibold text-balance md:text-4xl">
            {headline}
          </p>
          <p
            className="mt-4 max-w-3xl text-base leading-7 text-zinc-100 sm:text-lg"
            style={{ textShadow: "0 1px 8px rgba(0, 0, 0, .95)" }}
          >
            {description}
          </p>
          <Link href="/workspace">
            <Button className="mt-5 h-11 px-5" size="lg">
              <span className="text-md">{enterLabel}</span>
              <ChevronRightIcon className="size-4" />
            </Button>
          </Link>
        </div>
        <div
          data-testid="hero-art"
          className="relative mx-auto h-60 w-full max-w-[32rem] overflow-hidden md:h-[min(64svh,36rem)] md:max-w-none"
        >
          <PixelBlackHole />
          <div
            className="pointer-events-none absolute inset-0"
            aria-hidden="true"
            style={{
              background:
                "radial-gradient(ellipse at center, rgba(8, 8, 10, 0.1) 0%, rgba(8, 8, 10, 0.02) 62%, rgba(8, 8, 10, 0.3) 100%)",
            }}
          />
        </div>
      </div>
    </div>
  );
}
