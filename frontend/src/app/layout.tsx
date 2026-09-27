import "@/styles/globals.css";

import { type Metadata } from "next";

import { ThemeProvider } from "@/components/theme-provider";
import { DEFAULT_LOCALE } from "@/core/i18n/locale";
import { analyticsEnUS } from "@/core/i18n/locales/analytics.en-US";

// 根元数据在构建期确定：这里直接取品牌词条，而不是调用 `getI18n()`。
// 根布局一旦读 cookie（locale 就存在 cookie 里）就会把整站、包括纯静态的营销首页
// 一起拖成动态渲染；默认语言的英文词条在构建期就是常量，代价只是根标题不随语言切换。
const { branding } = analyticsEnUS;

export const metadata: Metadata = {
  title: branding.productName,
  description: branding.tagline,
  applicationName: branding.productName,
  icons: {
    icon: [{ url: "/favicon.svg", type: "image/svg+xml", sizes: "any" }],
  },
  openGraph: {
    title: branding.productName,
    description: branding.tagline,
    siteName: branding.productName,
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang={DEFAULT_LOCALE}
      suppressContentEditableWarning
      suppressHydrationWarning
    >
      <body>
        <ThemeProvider attribute="class" enableSystem disableTransitionOnChange>
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
