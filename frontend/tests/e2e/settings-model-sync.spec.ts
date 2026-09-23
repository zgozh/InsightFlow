import { expect, test } from "@playwright/test";

import { mockLangGraphAPI, MOCK_THREAD_ID } from "./utils/mock-api";

for (const field of ["effort", "mode"] as const) {
    test(`chat thread ${field} selection preserves the account model`, async ({
      page,
    }) => {
      mockLangGraphAPI(page, {
        threads: [
          {
            thread_id: MOCK_THREAD_ID,
          },
        ],
      });
      await page.addInitScript(
        ({ threadId }) => {
          localStorage.setItem(
            `deerflow.thread-model.${threadId}`,
            "thread-model",
          );
        },
        { threadId: MOCK_THREAD_ID },
      );
      await page.route("**/api/models", (route) =>
        route.fulfill({
          json: {
            models: [
              {
                name: "account-model",
                display_name: "Account Model",
                supports_thinking: true,
                supports_reasoning_effort: true,
              },
              {
                name: "thread-model",
                display_name: "Thread Model",
                supports_thinking: true,
                supports_reasoning_effort: true,
              },
            ],
          },
        }),
      );
      await page.route("**/api/v1/auth/me", (route) =>
        route.fulfill({
          json: {
            id: "00000000-0000-0000-0000-000000000028",
            email: "thread@example.com",
            system_role: "admin",
            needs_setup: false,
          },
        }),
      );
      const patches: unknown[] = [];
      let reads = 0;
      let server = {
        model_name: "account-model",
        mode: "pro",
        reasoning_effort: "medium",
        notification_enabled: true,
      };
      await page.route("**/api/v1/auth/preferences", async (route) => {
        if (route.request().method() === "PATCH") {
          const patch = route.request().postDataJSON() as Partial<
            typeof server
          >;
          patches.push(patch);
          server = { ...server, ...patch };
          await route.fulfill({ status: 204 });
        } else {
          reads++;
          await route.fulfill({ json: server });
        }
      });
      await page.goto(`/workspace/chats/${MOCK_THREAD_ID}`);
      await page
        .locator("[data-sidebar='sidebar']")
        .getByRole("button", { name: /Settings and more/ })
        .click();
      await page.keyboard.press("Escape");
      await page.evaluate(() =>
        document.dispatchEvent(new Event("visibilitychange")),
      );
      await expect.poll(() => reads).toBe(1);
      await expect(
        page.getByRole("button", { name: "Thread Model", exact: true }),
      ).toBeVisible();
      await expect(
        page.getByRole("button", {
          name: "Reasoning Effort: Medium",
          exact: true,
        }),
      ).toBeVisible();
      if (field === "effort") {
        await page
          .getByRole("button", {
            name: "Reasoning Effort: Medium",
            exact: true,
          })
          .click();
        await page.getByRole("menuitem").filter({ hasText: /^High/ }).click();
      } else {
        await page.getByRole("button", { name: "Pro", exact: true }).click();
        await page
          .getByRole("menuitem")
          .filter({ hasText: /^Ultra/ })
          .click();
      }
      await expect
        .poll(() => patches)
        .toEqual([
          field === "effort"
            ? { reasoning_effort: "high" }
            : { mode: "ultra", reasoning_effort: "high" },
        ]);
      expect(server.model_name).toBe("account-model");
      await page.keyboard.press("Escape");
      await expect(
        page.getByRole("button", { name: "Thread Model", exact: true }),
      ).toBeVisible();
    });
}
