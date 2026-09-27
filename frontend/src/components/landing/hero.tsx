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
      className={cn(
        "relative flex size-full flex-col items-center justify-center",
        className,
      )}
    >
      <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden bg-black/40">
        <PixelBlackHole />
        <div
          className="absolute inset-0"
          aria-hidden="true"
          style={{
            background:
              "radial-gradient(ellipse at center, rgba(8, 8, 10, 0.66) 0%, rgba(8, 8, 10, 0.15) 42%, rgba(8, 8, 10, 0.04) 76%), linear-gradient(to bottom, rgba(5, 5, 7, 0.12), transparent 38%, rgba(5, 5, 7, 0.5))",
          }}
        />
      </div>
      <div className="container-md relative z-10 mx-auto flex min-h-[92svh] flex-col items-center justify-center px-4 pt-20 pb-14">
        <h1 className="text-center text-5xl leading-tight font-bold break-words md:text-6xl">
          {productName}
        </h1>
        <p className="mt-6 max-w-4xl text-center text-2xl leading-snug font-semibold text-balance md:text-4xl">
          {headline}
        </p>
        <p
          className="mt-6 max-w-3xl text-center text-base leading-7 text-zinc-100 sm:text-lg"
          style={{ textShadow: "0 1px 8px rgba(0, 0, 0, .95)" }}
        >
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
