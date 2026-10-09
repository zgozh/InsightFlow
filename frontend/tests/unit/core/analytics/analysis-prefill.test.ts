import { describe, expect, it, rs } from "@rstest/core";

import {
  newAnalysisPrefillHref,
  readAnalysisPrefill,
} from "@/core/analytics/analysis-prefill";

describe("analysis prompt prefill", () => {
  it("builds an encoded link to a new analysis with a bounded prompt", () => {
    const href = newAnalysisPrefillHref("  Analyze “Orders”  ");
    const url = new URL(href, "https://example.test");

    expect(url.pathname).toBe("/workspace/analysis/new");
    expect(url.searchParams.get("prompt")).toBe("Analyze “Orders”");
    expect(
      new URL(
        newAnalysisPrefillHref("a".repeat(600)),
        "https://example.test",
      ).searchParams.get("prompt"),
    ).toHaveLength(512);
  });

  it("reads the prompt only for a new analysis and rejects empty or overlong values", () => {
    const get = rs.fn((key: string) =>
      key === "prompt" ? "  question  " : null,
    );
    const searchParams = { get };

    expect(readAnalysisPrefill(searchParams, false)).toBeUndefined();
    expect(get).not.toHaveBeenCalled();
    expect(readAnalysisPrefill(searchParams, true)).toBe("question");
    expect(get).toHaveBeenCalledWith("prompt");
    expect(readAnalysisPrefill({ get: () => "   " }, true)).toBeUndefined();
    expect(readAnalysisPrefill({ get: () => "x".repeat(513) }, true)).toBe(
      undefined,
    );
    expect(
      readAnalysisPrefill({ get: () => `${" ".repeat(513)}x` }, true),
    ).toBe(undefined);
  });
});
