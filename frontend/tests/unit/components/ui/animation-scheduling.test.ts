import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "@rstest/core";

const frontendRoot = join(import.meta.dirname, "../../../..");

describe("decorative animation scheduling", () => {
  it("suspends the Galaxy render loop when its container is inactive", () => {
    const source = readFileSync(
      join(frontendRoot, "src/components/landing/hero.tsx"),
      "utf8",
    );

    expect(source).toContain("useRenderActivity");
    expect(source).toContain("renderGalaxy && (");
    expect(source).toContain(
      'dynamic(() => import("@/components/ui/galaxy"), { ssr: false })',
    );
  });
});
