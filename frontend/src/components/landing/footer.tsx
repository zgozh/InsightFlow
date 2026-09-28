import type { BrandingTranslations } from "@/core/i18n/locales/analytics";
import { cn } from "@/lib/utils";

export type FooterProps = {
  className?: string;
  branding: Pick<
    BrandingTranslations,
    "productName" | "aboutSlogan" | "aboutDerivation" | "aboutLicense"
  >;
};

export function Footer({ branding, className }: FooterProps) {
  const year = new Date().getFullYear();
  const { productName, aboutSlogan, aboutDerivation, aboutLicense } = branding;
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
          {aboutSlogan}
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
