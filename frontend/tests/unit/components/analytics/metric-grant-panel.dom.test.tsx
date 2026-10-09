import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { PropsWithChildren } from "react";

rs.mock("@/core/analytics/api", () => ({
  AnalyticsRequestError: class extends Error {
    readonly status: number;
    readonly code: string | null;

    constructor(status: number, code: string | null) {
      super(code ?? "analytics_http_" + status);
      this.name = "AnalyticsRequestError";
      this.status = status;
      this.code = code;
    }
  },
  adminListMetricGrants: rs.fn(),
  adminGrantMetric: rs.fn(),
  adminRevokeMetric: rs.fn(),
}));

import { MetricGrantPanel } from "@/components/analytics/metric-grant-panel";
import {
  adminGrantMetric,
  adminListMetricGrants,
  adminRevokeMetric,
} from "@/core/analytics/api";
import { DEFAULT_LOCALE } from "@/core/i18n";
import { I18nProvider } from "@/core/i18n/context";

const mockedList = rs.mocked(adminListMetricGrants);
const mockedGrant = rs.mocked(adminGrantMetric);
const mockedRevoke = rs.mocked(adminRevokeMetric);

function renderPanel(metricKey = "revenue", metricName = "Revenue") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>
      <I18nProvider initialLocale={DEFAULT_LOCALE}>{children}</I18nProvider>
    </QueryClientProvider>
  );
  return render(
    <MetricGrantPanel
      metricKey={metricKey}
      metricName={metricName}
      onClose={rs.fn()}
    />,
    { wrapper: Wrapper },
  );
}

beforeEach(() => {
  mockedList.mockReset();
  mockedList.mockResolvedValue({ principal_ids: ["user-1"] });
  mockedGrant.mockReset();
  mockedRevoke.mockReset();
});

afterEach(() => {
  cleanup();
  rs.restoreAllMocks();
});

describe("metric grant panel", () => {
  it("shows the current metric and grants, then grants and revokes the exact principal", async () => {
    mockedGrant.mockResolvedValue({ principal_id: "user-2", granted: true });
    mockedRevoke.mockResolvedValue({ removed: true });
    renderPanel();

    expect(await screen.findByText("user-1")).toBeTruthy();
    expect(screen.getByText("Revenue")).toBeTruthy();
    expect(screen.getByText("revenue")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("User principal ID"), {
      target: { value: "user-2" },
    });
    fireEvent.submit(screen.getByTestId("metric-grant-form"));

    await waitFor(() =>
      expect(mockedGrant).toHaveBeenCalledWith("revenue", "user-2"),
    );
    expect(await screen.findByText("Access granted.")).toBeTruthy();
    expect(screen.getByLabelText("User principal ID")).toHaveProperty(
      "value",
      "",
    );

    fireEvent.click(screen.getByRole("button", { name: "Revoke user-1" }));
    await waitFor(() =>
      expect(mockedRevoke).toHaveBeenCalledWith("revenue", "user-1"),
    );
    expect(await screen.findByText("Access revoked.")).toBeTruthy();
  });

  it("retries a failed grant-list read and renders a server 403 distinctly", async () => {
    mockedList
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce({ principal_ids: [] });
    renderPanel();

    expect(await screen.findByRole("alert")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No users have access yet.")).toBeTruthy();
    expect(mockedList).toHaveBeenCalledTimes(2);

    mockedGrant.mockRejectedValueOnce(
      Object.assign(new Error("forbidden"), { status: 403 }),
    );
    fireEvent.change(screen.getByLabelText("User principal ID"), {
      target: { value: "user-3" },
    });
    fireEvent.submit(screen.getByTestId("metric-grant-form"));

    expect(
      await screen.findByText("The server refused this action (403)"),
    ).toBeTruthy();
    expect(screen.getByLabelText("User principal ID")).toHaveProperty(
      "value",
      "user-3",
    );
    expect(screen.queryByText("Access granted.")).toBeNull();
  });

  it("blocks duplicate submissions in the same turn", async () => {
    let resolveGrant:
      | ((value: { principal_id: string; granted: true }) => void)
      | undefined;
    mockedGrant.mockImplementation(
      () =>
        new Promise<{ principal_id: string; granted: true }>((resolve) => {
          resolveGrant = resolve;
        }),
    );
    renderPanel();
    await screen.findByText("user-1");
    const principalField = screen.getByLabelText("User principal ID");
    fireEvent.change(principalField, {
      target: { value: "user-2" },
    });
    expect(principalField).toHaveProperty("value", "user-2");
    expect(screen.getByRole("button", { name: "Grant access" })).toHaveProperty(
      "disabled",
      false,
    );
    const submitButton = screen.getByRole("button", { name: "Grant access" });
    act(() => {
      fireEvent.click(submitButton);
      fireEvent.click(submitButton);
    });
    expect(submitButton).toHaveProperty("disabled", true);
    expect(screen.getByRole("button", { name: "Granting…" })).toBeTruthy();
    await waitFor(() => expect(mockedGrant).toHaveBeenCalledTimes(1));

    await act(async () => {
      resolveGrant?.({ principal_id: "user-2", granted: true });
    });
    expect(await screen.findByText("Access granted.")).toBeTruthy();
  });
});
