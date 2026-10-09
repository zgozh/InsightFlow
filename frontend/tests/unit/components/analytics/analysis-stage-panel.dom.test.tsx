import { afterEach, describe, expect, test } from "@rstest/core";
import { cleanup, render, screen, within } from "@testing-library/react";
import type { PropsWithChildren } from "react";

import { AnalysisStagePanel } from "@/components/analytics/analysis-stage-panel";
import type { AnalysisStageEvent } from "@/core/analytics/types";
import { clientTranslations } from "@/core/i18n/client-translations";
import { I18nContext } from "@/core/i18n/context";

function wrapper({ children }: PropsWithChildren) {
  return (
    <I18nContext.Provider
      value={{
        locale: "en-US",
        setLocale: () => undefined,
        t: clientTranslations["en-US"],
      }}
    >
      {children}
    </I18nContext.Provider>
  );
}

function event(
  overrides: Partial<AnalysisStageEvent> = {},
): AnalysisStageEvent {
  return {
    type: "analysis_stage",
    version: 1,
    run_id: "run-1",
    seq: 1,
    stage: "execution",
    status: "running",
    ...overrides,
  };
}

afterEach(cleanup);

describe("AnalysisStagePanel", () => {
  test("uses accessible labels and renders the latest status with known observations", () => {
    render(
      <AnalysisStagePanel
        events={[
          event({ seq: 1, stage: "sql", status: "running" }),
          event({
            seq: 2,
            stage: "sql",
            status: "blocked",
            row_count: 0,
            byte_count: 128,
            risk: "HIGH",
            cached: true,
            code: "policy_denied",
          }),
        ]}
        runStatus="interrupted"
      />,
      { wrapper },
    );

    const panel = screen.getByTestId("analysis-stage-panel");
    const item = within(panel).getByTestId("analysis-stage-item");
    expect(panel.getAttribute("aria-label")).toBe("Analysis stages");
    expect(item.getAttribute("data-status")).toBe("blocked");
    expect(within(item).getByText("SQL execution")).toBeTruthy();
    expect(within(item).getByText("Blocked")).toBeTruthy();
    expect(within(item).getByText("High")).toBeTruthy();
    expect(within(item).getByText("128")).toBeTruthy();
    expect(within(item).getByText("Reused")).toBeTruthy();
    expect(within(panel).getByText(/Run status: Interrupted/)).toBeTruthy();
    expect(within(item).queryByText("Input tokens")).toBeNull();
    expect(panel.textContent).not.toContain("SELECT");
  });

  test("localizes the empty state in Chinese", () => {
    render(
      <I18nContext.Provider
        value={{
          locale: "zh-CN",
          setLocale: () => undefined,
          t: clientTranslations["zh-CN"],
        }}
      >
        <AnalysisStagePanel events={[]} />
      </I18nContext.Provider>,
    );

    expect(screen.getByText("分析阶段")).toBeTruthy();
    expect(screen.getByText("本次运行尚无阶段记录。")).toBeTruthy();
  });
});
