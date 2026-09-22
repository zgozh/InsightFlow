import { analyticsEnUS } from "@/core/i18n/locales/analytics.en-US";
import { cn } from "@/lib/utils";

export type FooterProps = {
  className?: string;
};

// 页脚始终以品牌词条为唯一来源。Phase 5 之后它只被产品首页复用，
// 该路由的布局是服务端组件，因此这里可以直接读词条常量，无须再走 provider。
const { productName, aboutDerivation, aboutLicense } = analyticsEnUS.branding;

export function Footer({ className }: FooterProps) {
  const year = new Date().getFullYear();
  return (
    <footer
      className={cn(
        "container-md mx-auto mt-32 flex flex-col items-center justify-center",
        className,
      )}
    >
      <hr className="from-border/0 to-border/0 m-0 h-px w-full border-none bg-linear-to-r via-white/20" />
      <div className="text-muted-foreground container flex max-w-3xl flex-col items-center justify-center gap-2 px-4 py-8 text-center text-xs">
        <p className="text-center font-serif text-lg md:text-xl">
          &quot;Originated from Open Source, give back to Open Source.&quot;
        </p>
        <p>{aboutDerivation}</p>
        <p>{aboutLicense}</p>
        <p>
          &copy; {year} {productName}
        </p>
      </div>
    </footer>
  );
}
