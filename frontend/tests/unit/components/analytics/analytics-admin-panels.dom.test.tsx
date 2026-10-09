import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import type { ReactNode } from "react";

import {
  AuditPrincipalLookup,
  DatasourceAdminSection,
  DatasourcePolicyEditor,
  DatasourceSchemaEditor,
  MetricAdminSection,
  nextAnalyticsVersion,
  nextMetricVersion,
  parseSchemaImport,
} from "@/components/analytics/analytics-admin-panels";
import { AnalyticsRequestError } from "@/core/analytics/api";
import type { AdminDatasourceView, MetricView } from "@/core/analytics/types";
import { DEFAULT_LOCALE } from "@/core/i18n";
import { I18nProvider } from "@/core/i18n/context";

/**
 * 管理员面板测试：只钉三件事——引擎不可改、提交恰好一次、服务端 403/409 被如实呈现。
 */
rs.mock("@/components/workspace/workspace-container", () => ({
  WorkspaceContainer: ({ children }: { children?: ReactNode }) => children,
  WorkspaceHeader: () => null,
  WorkspaceBody: ({ children }: { children?: ReactNode }) => children,
}));

type MutationDouble = {
  mutate: ReturnType<typeof rs.fn>;
  isPending: boolean;
  error: unknown;
  isSuccess: boolean;
};

const mocks = rs.hoisted(() => ({
  createDatasource: {
    mutate: rs.fn(),
    isPending: false,
    error: null,
    isSuccess: false,
  } as MutationDouble,
  updateDatasource: {
    mutate: rs.fn(),
    isPending: false,
    error: null,
    isSuccess: false,
  } as MutationDouble,
  replaceSchema: {
    mutate: rs.fn(),
    isPending: false,
    error: null,
    isSuccess: false,
  } as MutationDouble,
  replacePolicy: {
    mutate: rs.fn(),
    isPending: false,
    error: null,
    isSuccess: false,
  } as MutationDouble,
  removePolicy: {
    mutate: rs.fn(),
    isPending: false,
    error: null,
    isSuccess: false,
  } as MutationDouble,
  createMetric: {
    mutate: rs.fn(),
    isPending: false,
    error: null,
    isSuccess: false,
  } as MutationDouble,
  updateMetric: {
    mutate: rs.fn(),
    isPending: false,
    error: null,
    isSuccess: false,
  } as MutationDouble,
  retireMetric: {
    mutate: rs.fn(),
    isPending: false,
    error: null,
    isSuccess: false,
  } as MutationDouble,
  grantMetric: {
    mutate: rs.fn(),
    isPending: false,
    error: null,
    isSuccess: false,
  } as MutationDouble,
  revokeMetric: {
    mutate: rs.fn(),
    isPending: false,
    error: null,
    isSuccess: false,
  } as MutationDouble,
  adminMetricGrants: {
    principalIds: [] as string[],
    isLoading: false,
    isFetching: false,
    isError: false,
    error: null as unknown,
    refetch: rs.fn(),
  },
  metricGrantCalls: [] as unknown[][],
  adminSchema: {
    schema: null as unknown,
    isLoading: false,
    isError: false,
    refetch: rs.fn(),
  },
  adminPolicy: {
    policy: null as unknown,
    isLoading: false,
    isError: false,
    refetch: rs.fn(),
  },
  adminAuditLookup: {
    audits: [] as unknown[],
    isLoading: false,
    isError: false,
  },
  policyCalls: [] as unknown[][],
}));

rs.mock("@/core/analytics/hooks", () => ({
  useCreateDatasource: () => mocks.createDatasource,
  useUpdateDatasource: () => mocks.updateDatasource,
  useReplaceSchema: () => mocks.replaceSchema,
  useReplacePolicy: () => mocks.replacePolicy,
  useRemovePolicy: () => mocks.removePolicy,
  useCreateMetric: () => mocks.createMetric,
  useUpdateMetric: () => mocks.updateMetric,
  useRetireMetric: () => mocks.retireMetric,
  useGrantMetric: () => mocks.grantMetric,
  useRevokeMetric: () => mocks.revokeMetric,
  useAdminMetricGrants: (metricKey: string, enabled: boolean) => {
    mocks.metricGrantCalls.push([metricKey, enabled]);
    return mocks.adminMetricGrants;
  },
  useAdminSchema: () => mocks.adminSchema,
  useAdminPolicy: (
    datasourceId: string,
    principalId: string | null,
    enabled: boolean,
  ) => {
    mocks.policyCalls.push([datasourceId, principalId, enabled]);
    return mocks.adminPolicy;
  },
  useAdminAuditLookup: () => mocks.adminAuditLookup,
}));

function wrap(node: ReactNode) {
  return <I18nProvider initialLocale={DEFAULT_LOCALE}>{node}</I18nProvider>;
}

/**
 * 用 `instanceof` 收窄而不是类型断言：仓库的 ESLint 会自动"修复"多余的断言，
 * 断言一旦被自动移除，`value` 就不再存在于 `HTMLElement` 上。
 */
function inputValue(element: HTMLElement): string {
  return element instanceof HTMLInputElement ? element.value : "";
}

function isDisabled(element: HTMLElement): boolean {
  return element instanceof HTMLButtonElement && element.disabled;
}

function adminDatasourceView(): AdminDatasourceView {
  return {
    id: "ds-1",
    name: "Orders warehouse",
    engine: "postgresql",
    default_schema: "public",
    status: "active",
    owner_id: "user-7",
    secret_ref: "prod-secret-ref",
  };
}

function schemaSnapshot() {
  return {
    datasource_id: "ds-1",
    engine: "postgresql" as const,
    version: "3",
    default_schema: "public",
    relations: [
      {
        name: "orders",
        schema: "public",
        catalog: null,
        columns: [
          { name: "id", data_type: "int", sensitivity: "standard" as const },
        ],
      },
    ],
  };
}

function metricView(): MetricView {
  return {
    key: "revenue",
    name: "Revenue",
    description: "Net revenue",
    expression: "SUM(orders.amount)",
    dimensions: ["country"],
    version: 3,
    status: "active",
  };
}

function resetMutations() {
  for (const key of [
    "createDatasource",
    "updateDatasource",
    "replaceSchema",
    "replacePolicy",
    "removePolicy",
    "createMetric",
    "updateMetric",
    "retireMetric",
    "grantMetric",
    "revokeMetric",
  ] as const) {
    Object.assign(mocks[key], {
      mutate: rs.fn(),
      isPending: false,
      error: null,
      isSuccess: false,
    });
  }
}

beforeEach(() => {
  resetMutations();
  Object.assign(mocks.adminSchema, {
    schema: null,
    isLoading: false,
    isError: false,
    refetch: rs.fn(),
  });
  Object.assign(mocks.adminPolicy, {
    policy: null,
    isLoading: false,
    isError: false,
    refetch: rs.fn(),
  });
  Object.assign(mocks.adminAuditLookup, {
    audits: [],
    isLoading: false,
    isError: false,
  });
  Object.assign(mocks.adminMetricGrants, {
    principalIds: [],
    isLoading: false,
    isFetching: false,
    isError: false,
    error: null,
    refetch: rs.fn(),
  });
  mocks.metricGrantCalls = [];
  mocks.policyCalls = [];
});

afterEach(() => {
  cleanup();
  rs.restoreAllMocks();
});

describe("版本推进是纯函数推导", () => {
  it("数字版本 +1，非数字版本确定性追加后缀", () => {
    expect(nextAnalyticsVersion(null)).toBe("1");
    expect(nextAnalyticsVersion("3")).toBe("4");
    expect(nextAnalyticsVersion("v1")).toBe("v1-1");
    expect(nextAnalyticsVersion("v1-9")).toBe("v1-10");
    // 版本串上限 64，推导结果必须留在上限内。
    expect(nextAnalyticsVersion("x".repeat(64)).length).toBeLessThanOrEqual(64);
  });

  it("指标版本严格前进", () => {
    expect(nextMetricVersion(3)).toBe(4);
    expect(nextMetricVersion(0)).toBe(1);
  });
});

describe("JSON 导入的严格本地校验", () => {
  it("接受合法结构", () => {
    const result = parseSchemaImport(
      JSON.stringify({
        default_schema: "public",
        relations: [
          {
            name: "orders",
            schema: "public",
            catalog: null,
            columns: [
              { name: "id", data_type: "int", sensitivity: "standard" },
            ],
          },
        ],
      }),
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.defaultSchema).toBe("public");
      expect(result.relations).toHaveLength(1);
    }
  });

  it("拒绝非法 JSON、未知键、错误类型与非数组 relations", () => {
    expect(parseSchemaImport("{ not json").ok).toBe(false);
    expect(parseSchemaImport("[]").ok).toBe(false);
    expect(
      parseSchemaImport(JSON.stringify({ relations: [], extra: 1 })).ok,
    ).toBe(false);
    expect(parseSchemaImport(JSON.stringify({ relations: {} })).ok).toBe(false);
    expect(
      parseSchemaImport(
        JSON.stringify({
          relations: [
            {
              name: "orders",
              schema: "public",
              catalog: null,
              columns: [],
              sql: "SELECT 1",
            },
          ],
        }),
      ).ok,
    ).toBe(false);
    expect(
      parseSchemaImport(
        JSON.stringify({
          relations: [
            {
              name: "orders",
              schema: "public",
              columns: [
                { name: "id", data_type: "int", sensitivity: "top-secret" },
              ],
            },
          ],
        }),
      ).ok,
    ).toBe(false);
  });
});

describe("数据源创建/编辑表单", () => {
  it("创建表单有引擎选择器，编辑表单没有，且引擎只读并附不可更改说明", () => {
    render(
      wrap(
        <DatasourceAdminSection
          datasources={[adminDatasourceView()]}
          isLoading={false}
        />,
      ),
    );

    const createForm = screen.getByTestId("datasource-create-form");
    expect(
      within(createForm).getByTestId("datasource-engine-select"),
    ).toBeTruthy();

    fireEvent.click(
      screen.getByRole("button", { name: "Edit Orders warehouse" }),
    );
    const editForm = screen.getByTestId("datasource-edit-form");
    expect(
      within(editForm).queryByTestId("datasource-engine-select"),
    ).toBeNull();
    expect(within(editForm).queryByLabelText("Engine")).toBeNull();
    expect(editForm.textContent).toContain("postgresql");
    expect(editForm.textContent).toContain(
      "The engine cannot be changed after creation.",
    );
  });

  it("secret_ref 作为不透明文本展示，不做掩码", () => {
    render(
      wrap(
        <DatasourceAdminSection
          datasources={[adminDatasourceView()]}
          isLoading={false}
        />,
      ),
    );
    const secret = screen.getByTestId("admin-datasource-secret-ds-1");
    expect(secret.textContent).toBe("prod-secret-ref");
    expect(secret.textContent).not.toContain("•");
  });

  it("提交中禁用提交按钮，且同一 tick 的第二次提交不会发出第二个请求", () => {
    render(wrap(<DatasourceAdminSection datasources={[]} isLoading={false} />));
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "warehouse" },
    });
    fireEvent.change(screen.getByLabelText("Secret reference"), {
      target: { value: "ref-1" },
    });
    const form = screen.getByTestId("datasource-create-form");
    const submit = screen.getByRole("button", { name: "Create" });

    fireEvent.submit(form);
    expect(mocks.createDatasource.mutate).toHaveBeenCalledTimes(1);
    expect(isDisabled(submit)).toBe(true);

    fireEvent.click(submit);
    expect(mocks.createDatasource.mutate).toHaveBeenCalledTimes(1);
  });

  it("同一 tick 内连续两次提交只发出一次请求（单飞闸门）", () => {
    render(wrap(<DatasourceAdminSection datasources={[]} isLoading={false} />));
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "warehouse" },
    });
    fireEvent.change(screen.getByLabelText("Secret reference"), {
      target: { value: "ref-1" },
    });
    const form = screen.getByTestId("datasource-create-form");
    act(() => {
      fireEvent.submit(form);
      fireEvent.submit(form);
    });
    expect(mocks.createDatasource.mutate).toHaveBeenCalledTimes(1);
  });

  it("服务端 403 在管理员面板里渲染禁止态", () => {
    mocks.createDatasource.error = new AnalyticsRequestError(403, null);
    render(wrap(<DatasourceAdminSection datasources={[]} isLoading={false} />));
    expect(document.body.textContent).toContain(
      "The server refused this action (403)",
    );
  });
});

describe("数据模型（schema）编辑器", () => {
  it("期望版本只来自最近一次成功读取，不作为输入框暴露", () => {
    mocks.adminSchema.schema = schemaSnapshot();
    render(wrap(<DatasourceSchemaEditor datasourceId="ds-1" />));
    expect(screen.getByTestId("schema-expected-version").textContent).toBe("3");
    // 版本输入框里是"新版本"，不是 expected_version。
    expect(inputValue(screen.getByLabelText("Version"))).toBe("4");
  });

  it("非法 JSON 显示内联错误且不调用接口", () => {
    mocks.adminSchema.schema = schemaSnapshot();
    render(wrap(<DatasourceSchemaEditor datasourceId="ds-1" />));
    const textarea = screen.getByTestId("schema-import");
    fireEvent.change(textarea, { target: { value: "{ not json" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(mocks.replaceSchema.mutate).not.toHaveBeenCalled();
    // 文案来自 analytics 命名空间自己的词条，不再借用 MCP 设置的通用串。
    expect(screen.getByRole("alert").textContent).toContain("relations array");
    expect(textarea.getAttribute("aria-invalid")).toBe("true");
  });

  it("合法 JSON 在提交前被解析，并以解析结果与最近一次读取的版本提交", () => {
    mocks.adminSchema.schema = schemaSnapshot();
    render(wrap(<DatasourceSchemaEditor datasourceId="ds-1" />));
    fireEvent.change(screen.getByTestId("schema-import"), {
      target: {
        value: JSON.stringify({
          relations: [
            {
              name: "customers",
              schema: "crm",
              catalog: null,
              columns: [
                { name: "email", data_type: "text", sensitivity: "pii" },
              ],
            },
          ],
        }),
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(mocks.replaceSchema.mutate).toHaveBeenCalledWith(
      {
        datasourceId: "ds-1",
        request: {
          version: "4",
          expected_version: "3",
          default_schema: "public",
          relations: [
            {
              name: "customers",
              schema: "crm",
              catalog: null,
              columns: [
                { name: "email", data_type: "text", sensitivity: "pii" },
              ],
            },
          ],
        },
      },
      expect.any(Object),
    );
  });

  it("409 冲突给出刷新入口，且不会自动重放已失败的写入", () => {
    mocks.adminSchema.schema = schemaSnapshot();
    const view = render(wrap(<DatasourceSchemaEditor datasourceId="ds-1" />));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(mocks.replaceSchema.mutate).toHaveBeenCalledTimes(1);

    // 服务端返回稳定冲突码；重新渲染模拟 react-query 把错误交给组件。
    mocks.replaceSchema.error = new AnalyticsRequestError(
      409,
      "analytics_version_conflict",
    );
    view.rerender(wrap(<DatasourceSchemaEditor datasourceId="ds-1" />));

    expect(screen.getByTestId("analytics-stale-banner")).toBeTruthy();
    expect(document.body.textContent).toContain("This schema has changed");
    expect(document.body.textContent).toContain(
      "Saving now would overwrite someone else's change",
    );
    // 关键：没有自动重试写入。
    expect(mocks.replaceSchema.mutate).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(mocks.adminSchema.refetch).toHaveBeenCalledTimes(1);
    expect(mocks.replaceSchema.mutate).toHaveBeenCalledTimes(1);
  });
});

describe("访问策略编辑器", () => {
  it("默认空主体不发起跨主体查询，显式提交后才查询", () => {
    render(wrap(<DatasourcePolicyEditor datasourceId="ds-1" />));
    expect(mocks.policyCalls.at(-1)).toEqual(["ds-1", null, true]);
    expect(screen.queryByRole("button", { name: "Remove policy" })).toBeNull();

    fireEvent.change(screen.getByTestId("policy-principal"), {
      target: { value: "user-2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(mocks.policyCalls.at(-1)).toEqual(["ds-1", "user-2", true]);
    expect(screen.getByRole("button", { name: "Remove policy" })).toBeTruthy();
  });

  it("移除策略是危险操作：取消不调用接口，确认只调用一次", () => {
    render(wrap(<DatasourcePolicyEditor datasourceId="ds-1" />));
    fireEvent.change(screen.getByTestId("policy-principal"), {
      target: { value: "user-2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    const trigger = screen.getByRole("button", { name: "Remove policy" });
    fireEvent.click(trigger);
    const dialog = screen.getByRole("alertdialog");
    expect(within(dialog).getByText("Remove this policy?")).toBeTruthy();
    const cancel = within(dialog).getByRole("button", { name: "Cancel" });
    expect(cancel.tagName).toBe("BUTTON");
    expect(document.activeElement).toBe(cancel);

    fireEvent.click(cancel);
    expect(mocks.removePolicy.mutate).not.toHaveBeenCalled();
    expect(screen.queryByRole("alertdialog")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Remove policy" }));
    const reopened = screen.getByRole("alertdialog");
    fireEvent.click(
      within(reopened).getByRole("button", { name: "Remove policy" }),
    );
    expect(mocks.removePolicy.mutate).toHaveBeenCalledTimes(1);
    expect(mocks.removePolicy.mutate).toHaveBeenCalledWith(
      { datasourceId: "ds-1", principalId: "user-2" },
      expect.any(Object),
    );
  });
});

describe("指标管理面板", () => {
  it("按指标打开独立授权面板，关闭后切换指标不会保留旧输入", () => {
    const revenue = metricView();
    const margin = { ...metricView(), key: "margin", name: "Margin" };
    render(wrap(<MetricAdminSection metrics={[revenue, margin]} />));

    fireEvent.click(
      screen.getByRole("button", { name: "Grant access Revenue" }),
    );
    expect(mocks.metricGrantCalls.at(-1)).toEqual(["revenue", true]);
    fireEvent.change(screen.getByLabelText("User principal ID"), {
      target: { value: "old-user" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByTestId("metric-grant-panel")).toBeNull();

    fireEvent.click(
      screen.getByRole("button", { name: "Grant access Margin" }),
    );
    expect(mocks.metricGrantCalls.at(-1)).toEqual(["margin", true]);
    expect(inputValue(screen.getByLabelText("User principal ID"))).toBe("");
    expect(
      within(screen.getByTestId("metric-grant-panel")).getByText("margin"),
    ).toBeTruthy();
    expect(document.body.textContent).not.toContain("old-user");
  });

  it("下线是状态语义：确认取消不调用接口，确认只调用一次", () => {
    render(wrap(<MetricAdminSection metrics={[metricView()]} />));
    const trigger = screen.getByRole("button", {
      name: "Retire metric Revenue",
    });
    fireEvent.click(trigger);
    const dialog = screen.getByRole("alertdialog");
    expect(within(dialog).getByText("Retire this metric?")).toBeTruthy();
    expect(
      within(dialog).getByText(/New analyses can no longer reference it/),
    ).toBeTruthy();

    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(mocks.retireMetric.mutate).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole("button", { name: "Retire metric Revenue" }),
    );
    const reopened = screen.getByRole("alertdialog");
    fireEvent.click(
      within(reopened).getByRole("button", { name: "Retire metric" }),
    );
    expect(mocks.retireMetric.mutate).toHaveBeenCalledTimes(1);
    expect(mocks.retireMetric.mutate).toHaveBeenCalledWith(
      "revenue",
      expect.any(Object),
    );
  });

  it("更新时版本必须显式前进：服务端拒绝时给出对应提示", () => {
    const view = render(wrap(<MetricAdminSection metrics={[metricView()]} />));
    fireEvent.click(screen.getByRole("button", { name: "Edit Revenue" }));
    // 预填的版本已经严格大于当前版本。
    expect(inputValue(screen.getByLabelText("Version"))).toBe("4");

    fireEvent.submit(screen.getByTestId("metric-edit-form"));
    expect(mocks.updateMetric.mutate).toHaveBeenCalledTimes(1);

    mocks.updateMetric.error = new AnalyticsRequestError(
      409,
      "analytics_version_conflict",
    );
    view.rerender(wrap(<MetricAdminSection metrics={[metricView()]} />));

    expect(document.body.textContent).toContain(
      "Editing an active metric requires advancing its version.",
    );
    expect(mocks.updateMetric.mutate).toHaveBeenCalledTimes(1);
  });

  it("expression 以纯文本提交，不做任何求值或包装", () => {
    render(wrap(<MetricAdminSection metrics={[]} />));
    const form = screen.getByTestId("metric-create-form");
    fireEvent.change(within(form).getByLabelText("Metric key"), {
      target: { value: "margin" },
    });
    fireEvent.change(within(form).getByLabelText("Metric name"), {
      target: { value: "Margin" },
    });
    fireEvent.change(within(form).getByLabelText("Expression"), {
      target: { value: "SUM(orders.amount) - SUM(orders.cost)" },
    });
    fireEvent.submit(form);

    expect(mocks.createMetric.mutate).toHaveBeenCalledWith(
      {
        key: "margin",
        name: "Margin",
        description: "",
        expression: "SUM(orders.amount) - SUM(orders.cost)",
        dimensions: [],
        version: 1,
        status: "draft",
      },
      expect.any(Object),
    );
  });
});

describe("按主体查询审计", () => {
  it("默认不查询，提交主体后才查询", () => {
    render(wrap(<AuditPrincipalLookup />));
    expect(screen.queryByTestId("audit-lookup-result")).toBeNull();
    fireEvent.change(screen.getByTestId("audit-principal"), {
      target: { value: "user-9" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(screen.getByTestId("audit-lookup-result")).toBeTruthy();
  });
});
