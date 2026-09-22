import Link from "next/link";

import { DEFAULT_LOCALE, type Locale } from "@/core/i18n/locale";
import { getI18n } from "@/core/i18n/server";
import { cn } from "@/lib/utils";

import { MobileNav } from "./mobile-nav";

export type HeaderProps = {
  className?: string;
  homeURL?: string;
  locale?: Locale;
};

export async function Header({ className, homeURL, locale }: HeaderProps) {
  const { locale: resolvedLocale, t } = await getI18n(locale ?? DEFAULT_LOCALE);
  const lang = resolvedLocale.substring(0, 2);
  // 缺省入口回到站内首页：产品品牌不应再把上游 GitHub 仓库当作自己的主页。
  // 只有显式给出 http(s) 地址时才作为外部链接，否则一律站内跳转。
  const isExternalHome = homeURL?.startsWith("http") ?? false;
  return (
    <header
      className={cn(
        "container-md fixed top-0 right-0 left-0 z-20 mx-auto flex h-16 items-center justify-between gap-3 px-4 backdrop-blur-xs",
        className,
      )}
    >
      <div className="flex min-w-0 items-center gap-6">
        <a
          href={homeURL ?? "/"}
          target={isExternalHome ? "_blank" : "_self"}
          rel={isExternalHome ? "noopener noreferrer" : undefined}
          className="font-serif text-xl whitespace-nowrap"
        >
          {t.branding.productName}
        </a>
      </div>
      <nav className="ml-auto hidden items-center gap-5 text-sm font-medium sm:flex md:mr-8 md:gap-8">
        <Link
          href={`/${lang}/docs`}
          className="text-secondary-foreground hover:text-foreground transition-colors"
        >
          {t.home.docs}
        </Link>
        <Link
          href="/blog/posts"
          className="text-secondary-foreground hover:text-foreground transition-colors"
        >
          {t.home.blog}
        </Link>
      </nav>
      <MobileNav
        title={t.branding.productName}
        links={[
          { href: `/${lang}/docs`, label: t.home.docs },
          { href: "/blog/posts", label: t.home.blog },
        ]}
      />
      <hr className="from-border/0 via-border/70 to-border/0 absolute top-16 right-0 left-0 z-10 m-0 h-px w-full border-none bg-linear-to-r" />
    </header>
  );
}
