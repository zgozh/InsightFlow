import {
  ArrowRightIcon,
  BotIcon,
  ClipboardListIcon,
  DatabaseIcon,
  FileOutputIcon,
  ScrollTextIcon,
  SearchIcon,
  SendIcon,
  ShieldCheckIcon,
  TableIcon,
} from "lucide-react";

import { Footer } from "@/components/landing/footer";
import { Header } from "@/components/landing/header";
import { Hero } from "@/components/landing/hero";
import { Section } from "@/components/landing/section";
import { DEFAULT_LOCALE } from "@/core/i18n/locale";
import { getI18n } from "@/core/i18n/server";

/**
 * 落地页保留四件事：价值主张、治理能力、工作流、进入工作台。
 *
 * 两个产品段落的文案刻意复用产品模块自己的词条（数据源／数据模型／访问策略／审计历史，
 * 以及分析轨迹的六个阶段），而不是另写一套营销文案：落地页描述的必须是产品真的做的事，
 * 两处文案一旦分开维护就会立刻漂移。展示的是结构化事件投影，不是模型的思维过程。
 *
 * 词条在服务端解析：客户端组件（Hero）只能接收纯字符串，遇到函数的词条无法跨 RSC 边界。
 * 这里显式传入 DEFAULT_LOCALE，避免读 cookie 把首页从静态渲染拖成动态渲染。
 */
export default async function LandingPage() {
  const { t } = await getI18n(DEFAULT_LOCALE);
  const governanceLayers = [
    { icon: DatabaseIcon, label: t.analytics.datasource.title },
    { icon: TableIcon, label: t.analytics.schema.title },
    { icon: ShieldCheckIcon, label: t.analytics.policy.title },
    { icon: ScrollTextIcon, label: t.analytics.history.title },
  ];
  const workflowSteps = [
    { icon: ClipboardListIcon, label: t.analytics.trace.stepPlan },
    { icon: SearchIcon, label: t.analytics.trace.stepCatalog },
    { icon: TableIcon, label: t.analytics.trace.stepQuery },
    { icon: BotIcon, label: t.analytics.trace.stepDelegate },
    { icon: FileOutputIcon, label: t.analytics.trace.stepArtifact },
    { icon: SendIcon, label: t.analytics.trace.stepPublish },
  ];

  return (
    <div className="min-h-screen w-full overflow-x-clip bg-[#0a0a0a]">
      <Header locale={DEFAULT_LOCALE} />
      <main className="flex w-full flex-col">
        <Hero
          productName={t.branding.productName}
          headline={t.branding.landingHeadline}
          description={t.branding.landingDescription}
          enterLabel={t.branding.landingEnter}
        />
        <Section
          title={t.branding.landingSecurityTitle}
          subtitle={t.branding.landingSecurityBody}
        >
          <ul className="container-md mx-auto mt-10 grid max-w-4xl grid-cols-2 gap-3 sm:grid-cols-4">
            {governanceLayers.map((layer) => (
              <li
                key={layer.label}
                className="flex flex-col items-center gap-3 rounded-lg border border-white/10 bg-white/2 px-4 py-6"
              >
                <layer.icon aria-hidden className="size-5 text-zinc-300" />
                <span className="text-center text-sm text-zinc-300">
                  {layer.label}
                </span>
              </li>
            ))}
          </ul>
        </Section>
        <Section
          title={t.branding.landingWorkflowTitle}
          subtitle={t.branding.landingWorkflowBody}
        >
          <ol className="container-md mx-auto mt-10 flex max-w-5xl flex-wrap items-center justify-center gap-x-3 gap-y-4">
            {workflowSteps.map((step, index) => (
              <li key={step.label} className="flex items-center gap-3">
                <div className="flex min-w-32 flex-col items-center gap-2 rounded-lg border border-white/10 bg-white/2 px-4 py-4">
                  <step.icon aria-hidden className="size-5 text-zinc-300" />
                  <span className="text-center text-sm text-zinc-300">
                    {step.label}
                  </span>
                </div>
                {index < workflowSteps.length - 1 && (
                  <ArrowRightIcon
                    aria-hidden
                    className="size-4 text-zinc-600"
                  />
                )}
              </li>
            ))}
          </ol>
        </Section>
      </main>
      <Footer />
    </div>
  );
}
