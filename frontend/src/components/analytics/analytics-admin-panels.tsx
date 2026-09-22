"use client";

/**
 * 分析工作台的管理员面板（Phase 4 §6）。
 *
 * 为什么单独一个文件：本阶段最容易出错的地方是"管理员能改什么、普通用户能看到什么"。
 * 把**所有写操作**收在一个文件里，审阅时只需要看这一处，而 `analytics-catalog-views.tsx`
 * 里没有任何 mutation。
 *
 * 贯穿全文件的三条规则：
 *
 * 1. **服务端才是授权边界**。客户端的管理员标记只决定隐藏入口；每个面板都把 403 渲染成
 *    禁止态，而不是假设"我没渲染按钮所以不会被拒"。
 * 2. **`expected_version` 永远来自最近一次成功读取**，只作为只读文本展示，不进任何输入框。
 *    用户能编辑的只有"新版本号"——服务端要求新版本必须与当前版本不同，协议里没有自动递增。
 * 3. **提交中不允许第二次请求**。`disabled` 只防"看得见的第二次点击"，同一 tick 内的两次点击
 *    仍会穿透，因此每次提交都额外过一次同步的单飞闸门（`useSingleFlightSubmit`）。
 *
 * 关于 `secret_ref`：它是服务端密钥存储里的**不透明引用**。这里只把它当中文本来显示与编辑——
 * 不解析、不探测、不做"看起来像已解析"的掩码。
 */

import { PlusIcon, Trash2Icon } from "lucide-react";
import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ComponentProps,
  type FormEvent,
  type ReactNode,
} from "react";

import {
  AnalyticsConfirmDialog,
  AnalyticsInlineAlert,
  AnalyticsStaleBanner,
  AnalyticsTableScroll,
  analyticsErrorStatus,
  AuditRecordCard,
  isAnalyticsForbidden,
  MetricCatalogTable,
} from "@/components/analytics/analytics-catalog-views";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { AnalyticsRequestError } from "@/core/analytics/api";
import {
  useAdminAuditLookup,
  useAdminPolicy,
  useAdminSchema,
  useCreateDatasource,
  useCreateMetric,
  useRemovePolicy,
  useReplacePolicy,
  useReplaceSchema,
  useRetireMetric,
  useUpdateDatasource,
  useUpdateMetric,
} from "@/core/analytics/hooks";
import {
  COLUMN_SENSITIVITIES,
  DATASOURCE_ENGINES,
  type AdminDatasourceView,
  type ColumnSchemaView,
  type ColumnSensitivity,
  type DatasourceEngine,
  type DatasourceStatus,
  type MetricStatus,
  type MetricView,
  type QueryAuditView,
  type RelationAccessRuleView,
  type RelationSchemaView,
} from "@/core/analytics/types";
import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

// --- 单飞提交闸门 -----------------------------------------------------------

/**
 * 同步的单飞闸门。
 *
 * 为什么不能只靠 `mutation.isPending`：TanStack 的 `isPending` 是异步置位的，同一 tick 里
 * 连点两次时两次回调都能读到 `false`，于是发出两个请求。`useRef` 的赋值是同步的，
 * 因此第二次点击一定被挡住。
 */
export function useSingleFlightSubmit() {
  const locked = useRef(false);
  const [busy, setBusy] = useState(false);

  const run = useCallback((start: (release: () => void) => void) => {
    if (locked.current) {
      return;
    }
    locked.current = true;
    setBusy(true);
    start(() => {
      locked.current = false;
      setBusy(false);
    });
  }, []);

  return { busy, run };
}

// --- 版本推进 ---------------------------------------------------------------

/**
 * 由服务端当前版本推导出一个**必定不同**的新版本号。
 *
 * 服务端契约（`catalogs.py::replace`）：内容不同但版本相同 → `version_drift`；
 * 当前版本不等于 `expected_version` → `stale_expected_version`。因此客户端必须给出一个
 * 新版本；协议里没有"自动递增"，所以这里做纯函数推导，并把它填进**可编辑**的版本输入框，
 * 让管理员能改成自己的版本策略。
 */
export function nextAnalyticsVersion(current: string | null): string {
  if (current === null || current.length === 0) {
    return "1";
  }
  if (/^\d{1,18}$/.test(current)) {
    return String(Number(current) + 1);
  }
  const suffixed = /^(.*)-(\d{1,9})$/.exec(current);
  if (suffixed?.[1] !== undefined && suffixed[2] !== undefined) {
    return `${suffixed[1]}-${Number(suffixed[2]) + 1}`;
  }
  // 版本串上限 64：截断到 55 再加后缀，保证结果不超过上限，且推导是确定性的。
  return `${current.slice(0, 55)}-1`;
}

/** 指标版本是正整数，更新时必须严格前进。 */
export function nextMetricVersion(current: number): number {
  return Number.isSafeInteger(current) && current > 0 ? current + 1 : 1;
}

// --- 表单原语 ---------------------------------------------------------------

function FormField({
  id,
  label,
  hint,
  children,
  className,
}: {
  id: string;
  label: string;
  hint?: string;
  children: ReactNode;
  className?: string;
}) {
  const hintId = `${id}-hint`;
  return (
    <div className={cn("flex min-w-0 flex-col gap-1", className)}>
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      {children}
      {hint !== undefined && (
        <p id={hintId} className="text-muted-foreground text-xs">
          {hint}
        </p>
      )}
    </div>
  );
}

function PanelHeading({
  title,
  adminBadge,
  children,
}: {
  title: string;
  adminBadge?: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      <h2 className="min-w-0 text-lg font-semibold break-words">{title}</h2>
      {adminBadge !== undefined && (
        <Badge variant="secondary">{adminBadge}</Badge>
      )}
      {children}
    </div>
  );
}

function FormPanel({ children }: { children: ReactNode }) {
  return (
    <div className="border-border flex min-w-0 flex-col gap-3 rounded-md border p-3">
      {children}
    </div>
  );
}

/**
 * 所有文本类控件统一到 44×44 的最小命中区。
 *
 * `Input` 的基础高度只有 36px，逐处补 `min-h-11` 容易漏（尤其是动态增删的列/维度行），
 * 因此在这里统一包一层；调用点已有的宽度约束由 `cn` 合并保留（它们都不小于 44px）。
 */
function FieldInput({ className, ...props }: ComponentProps<typeof Input>) {
  return <Input {...props} className={cn("min-h-11 min-w-11", className)} />;
}

function FieldTextarea({
  className,
  ...props
}: ComponentProps<typeof Textarea>) {
  return <Textarea {...props} className={cn("min-h-11 min-w-11", className)} />;
}

/** 把服务端的稳定错误码翻译成本地化文案；只用于展示，不参与任何授权判断。 */
function useMutationErrorText() {
  const { t } = useI18n();
  return useCallback(
    (error: unknown): string | null => {
      if (error === null || error === undefined) {
        return null;
      }
      if (isAnalyticsForbidden(error)) {
        return t.analytics.common.forbidden;
      }
      const code = error instanceof AnalyticsRequestError ? error.code : null;
      if (code === "invalid_analytics_request") {
        return t.analytics.errors.invalidRequest;
      }
      if (code === "analytics_not_found") {
        return t.analytics.errors.notFound;
      }
      if (code === "analytics_version_conflict") {
        return t.analytics.errors.versionConflict;
      }
      if (code === "analytics_unavailable") {
        return t.analytics.errors.unavailable;
      }
      if (code === "analytics_storage_unavailable") {
        return t.analytics.errors.storageUnavailable;
      }
      const status = analyticsErrorStatus(error);
      if (status === 400 || status === 422) {
        return t.analytics.errors.invalidRequest;
      }
      if (status === 404) {
        return t.analytics.errors.notFound;
      }
      if (status === 503) {
        return t.analytics.errors.storageUnavailable;
      }
      return t.analytics.errors.unavailable;
    },
    [t],
  );
}

function isConflict(error: unknown): boolean {
  return analyticsErrorStatus(error) === 409;
}

// --- JSON 导入的严格本地校验 ------------------------------------------------

export type SchemaImportResult =
  | { ok: true; relations: RelationSchemaView[]; defaultSchema: string | null }
  | { ok: false };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** 严格：出现未声明的键就判失败，绝不"忽略未知字段"再提交。 */
function hasOnlyKeys(
  record: Record<string, unknown>,
  allowed: readonly string[],
): boolean {
  return Object.keys(record).every((key) => allowed.includes(key));
}

function parseImportedColumn(value: unknown): ColumnSchemaView | null {
  if (
    !isRecord(value) ||
    !hasOnlyKeys(value, ["name", "data_type", "sensitivity"])
  ) {
    return null;
  }
  const { name, data_type: dataType, sensitivity } = value;
  if (typeof name !== "string" || name.length === 0) {
    return null;
  }
  if (typeof dataType !== "string" || dataType.length === 0) {
    return null;
  }
  if (
    typeof sensitivity !== "string" ||
    !(COLUMN_SENSITIVITIES as readonly string[]).includes(sensitivity)
  ) {
    return null;
  }
  return {
    name,
    data_type: dataType,
    sensitivity: sensitivity as ColumnSensitivity,
  };
}

function parseImportedRelation(value: unknown): RelationSchemaView | null {
  if (
    !isRecord(value) ||
    !hasOnlyKeys(value, ["name", "schema", "catalog", "columns"])
  ) {
    return null;
  }
  const { name, schema, catalog, columns } = value;
  if (typeof name !== "string" || name.length === 0) {
    return null;
  }
  if (typeof schema !== "string" || schema.length === 0) {
    return null;
  }
  if (
    catalog !== undefined &&
    catalog !== null &&
    typeof catalog !== "string"
  ) {
    return null;
  }
  if (catalog === "") {
    return null;
  }
  if (!Array.isArray(columns)) {
    return null;
  }
  const parsedColumns: ColumnSchemaView[] = [];
  for (const column of columns) {
    const parsed = parseImportedColumn(column);
    if (parsed === null) {
      return null;
    }
    parsedColumns.push(parsed);
  }
  return {
    name,
    schema,
    catalog: catalog ?? null,
    columns: parsedColumns,
  };
}

/**
 * 严格解析可选的 JSON 导入内容。
 *
 * 只接受 `{ default_schema?, relations }`：未知键、类型不符、`relations` 不是数组、
 * 列级字段不符都直接判失败。失败时**不返回任何半成品**——调用方拿不到就什么都不会提交。
 */
export function parseSchemaImport(text: string): SchemaImportResult {
  let payload: unknown;
  try {
    payload = JSON.parse(text);
  } catch {
    return { ok: false };
  }
  if (!isRecord(payload)) {
    return { ok: false };
  }
  if (!hasOnlyKeys(payload, ["default_schema", "relations"])) {
    return { ok: false };
  }
  if (!Array.isArray(payload.relations)) {
    return { ok: false };
  }
  const relations: RelationSchemaView[] = [];
  for (const relation of payload.relations) {
    const parsed = parseImportedRelation(relation);
    if (parsed === null) {
      return { ok: false };
    }
    relations.push(parsed);
  }
  const rawDefaultSchema = payload.default_schema;
  let defaultSchema: string | null = null;
  if (rawDefaultSchema !== undefined && rawDefaultSchema !== null) {
    if (typeof rawDefaultSchema !== "string" || rawDefaultSchema.length === 0) {
      return { ok: false };
    }
    defaultSchema = rawDefaultSchema;
  }
  return { ok: true, relations, defaultSchema };
}

// --- 管理员：数据源列表＋创建/编辑 ------------------------------------------

const DATASOURCE_STATUS_KEYS = {
  active: "statusActive",
  disabled: "statusDisabled",
  unhealthy: "statusUnhealthy",
} as const;

export function DatasourceAdminSection({
  datasources,
  isLoading,
  isError = false,
}: {
  datasources: AdminDatasourceView[];
  isLoading: boolean;
  isError?: boolean;
}) {
  const { t } = useI18n();
  const d = t.analytics.datasource;
  const create = useCreateDatasource();
  const update = useUpdateDatasource();
  const createGuard = useSingleFlightSubmit();
  const updateGuard = useSingleFlightSubmit();
  const errorText = useMutationErrorText();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [createName, setCreateName] = useState("");
  const [createEngine, setCreateEngine] =
    useState<DatasourceEngine>("postgresql");
  const [createSecretRef, setCreateSecretRef] = useState("");
  const [createDefaultSchema, setCreateDefaultSchema] = useState("");
  const [editName, setEditName] = useState("");
  const [editSecretRef, setEditSecretRef] = useState("");
  const [editDefaultSchema, setEditDefaultSchema] = useState("");
  const [editStatus, setEditStatus] = useState<DatasourceStatus>("active");

  const selected = datasources.find((item) => item.id === selectedId) ?? null;
  const createNameId = useId();
  const createEngineId = useId();
  const createSecretRefId = useId();
  const createDefaultSchemaId = useId();
  const editNameId = useId();
  const editSecretRefId = useId();
  const editDefaultSchemaId = useId();
  const editStatusId = useId();

  // 只在选中项变化时把服务端值填进编辑表单：后台 refetch 返回新对象时不能覆盖正在编辑的内容。
  useEffect(() => {
    const current = datasources.find((item) => item.id === selectedId);
    if (current === undefined) {
      return;
    }
    setEditName(current.name);
    setEditSecretRef(current.secret_ref);
    setEditDefaultSchema(current.default_schema ?? "");
    setEditStatus(current.status);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const submitCreate = (event: FormEvent) => {
    event.preventDefault();
    const name = createName.trim();
    const secretRef = createSecretRef.trim();
    if (name.length === 0 || secretRef.length === 0) {
      return;
    }
    createGuard.run((release) => {
      create.mutate(
        {
          name,
          engine: createEngine,
          secret_ref: secretRef,
          default_schema:
            createDefaultSchema.trim().length === 0
              ? null
              : createDefaultSchema.trim(),
        },
        {
          onSuccess: () => {
            setCreateName("");
            setCreateSecretRef("");
            setCreateDefaultSchema("");
          },
          onSettled: release,
        },
      );
    });
  };

  const submitUpdate = (event: FormEvent) => {
    event.preventDefault();
    if (selected === null) {
      return;
    }
    const datasourceId = selected.id;
    updateGuard.run((release) => {
      update.mutate(
        {
          datasourceId,
          request: {
            name: editName.trim(),
            secret_ref: editSecretRef.trim(),
            default_schema:
              editDefaultSchema.trim().length === 0
                ? null
                : editDefaultSchema.trim(),
            status: editStatus,
          },
        },
        { onSettled: release },
      );
    });
  };

  const createError = errorText(create.error);
  const updateError = errorText(update.error);

  return (
    <section
      aria-label={t.analytics.common.adminOnly}
      className="flex min-w-0 flex-col gap-4"
    >
      <PanelHeading title={d.title} adminBadge={t.analytics.common.adminOnly} />

      {/* 管理员列表读取失败只给出通用错误：该 hook 不暴露 error，因此无法区分 403 与 500。
          页面级的 403 判定由带 error 的目录查询负责。 */}
      {isError && (
        <AnalyticsInlineAlert>
          {t.analytics.common.loadFailed}
        </AnalyticsInlineAlert>
      )}

      <AnalyticsTableScroll label={d.title}>
        <table className="w-full min-w-[52rem] border-collapse text-sm">
          <caption className="sr-only">{d.title}</caption>
          <thead>
            <tr className="border-border border-b text-left">
              <th scope="col" className="p-2 font-medium">
                {d.name}
              </th>
              <th scope="col" className="p-2 font-medium">
                {d.engine}
              </th>
              <th scope="col" className="p-2 font-medium">
                {d.defaultSchema}
              </th>
              <th scope="col" className="p-2 font-medium">
                {d.status}
              </th>
              <th scope="col" className="p-2 font-medium">
                {d.secretRef}
              </th>
              <th scope="col" className="p-2 font-medium">
                {t.analytics.history.principalId}
              </th>
              <th scope="col" className="p-2 font-medium">
                {t.analytics.common.edit}
              </th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={7} className="p-2">
                  <span role="status" className="text-muted-foreground text-sm">
                    {t.analytics.common.loading}
                  </span>
                </td>
              </tr>
            )}
            {datasources.map((datasource) => (
              <tr
                key={datasource.id}
                className="border-border border-b last:border-b-0"
                data-testid={`admin-datasource-${datasource.id}`}
              >
                <td className="p-2 font-medium break-words">
                  {datasource.name}
                </td>
                <td className="p-2">
                  <code className="font-mono text-xs">{datasource.engine}</code>
                </td>
                <td className="p-2 break-words">
                  {datasource.default_schema ?? t.analytics.common.notAvailable}
                </td>
                <td className="p-2">
                  <code className="font-mono text-xs">
                    {d[DATASOURCE_STATUS_KEYS[datasource.status]]}
                  </code>
                </td>
                {/* secret_ref 是不透明引用：原样展示，不掩码、不解析。 */}
                <td className="p-2">
                  <code
                    className="block max-w-[20rem] font-mono text-xs break-all"
                    data-testid={`admin-datasource-secret-${datasource.id}`}
                  >
                    {datasource.secret_ref}
                  </code>
                </td>
                <td className="p-2">
                  <code className="font-mono text-xs break-all">
                    {datasource.owner_id}
                  </code>
                </td>
                <td className="p-2">
                  <Button
                    type="button"
                    variant="outline"
                    className="min-h-11 min-w-11"
                    aria-label={`${t.analytics.common.edit} ${datasource.name}`}
                    onClick={() => setSelectedId(datasource.id)}
                  >
                    {t.analytics.common.edit}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </AnalyticsTableScroll>

      <FormPanel>
        <h3 className="text-base font-semibold">{d.createTitle}</h3>
        <form
          className="flex min-w-0 flex-col gap-3"
          data-testid="datasource-create-form"
          onSubmit={submitCreate}
          noValidate
        >
          <FormField id={createNameId} label={d.name}>
            <FieldInput
              id={createNameId}
              value={createName}
              onChange={(event) => setCreateName(event.target.value)}
            />
          </FormField>
          <FormField id={createEngineId} label={d.engine}>
            {/* 引擎只在创建时可选：创建后不可更改，因此编辑表单里没有这个控件。 */}
            <select
              id={createEngineId}
              data-testid="datasource-engine-select"
              className="border-input focus-visible:ring-ring/50 h-11 min-h-11 min-w-11 rounded-md border bg-transparent px-3 text-sm outline-none focus-visible:ring-[3px]"
              value={createEngine}
              onChange={(event) =>
                setCreateEngine(event.target.value as DatasourceEngine)
              }
            >
              {DATASOURCE_ENGINES.map((engine) => (
                <option key={engine} value={engine}>
                  {engine}
                </option>
              ))}
            </select>
          </FormField>
          <FormField
            id={createSecretRefId}
            label={d.secretRef}
            hint={d.secretRefHint}
          >
            <FieldInput
              id={createSecretRefId}
              value={createSecretRef}
              onChange={(event) => setCreateSecretRef(event.target.value)}
            />
          </FormField>
          <FormField id={createDefaultSchemaId} label={d.defaultSchema}>
            <FieldInput
              id={createDefaultSchemaId}
              value={createDefaultSchema}
              onChange={(event) => setCreateDefaultSchema(event.target.value)}
            />
          </FormField>
          {createError !== null && (
            <AnalyticsInlineAlert>{createError}</AnalyticsInlineAlert>
          )}
          <Button
            type="submit"
            className="min-h-11 min-w-11 self-start"
            disabled={
              createGuard.busy ||
              create.isPending ||
              createName.trim().length === 0 ||
              createSecretRef.trim().length === 0
            }
          >
            {create.isPending
              ? t.analytics.common.saving
              : t.analytics.common.create}
          </Button>
        </form>
      </FormPanel>

      {selected !== null && (
        <FormPanel>
          <h3 className="text-base font-semibold">{d.editTitle}</h3>
          <form
            className="flex min-w-0 flex-col gap-3"
            data-testid="datasource-edit-form"
            onSubmit={submitUpdate}
            noValidate
          >
            {/* engine 只读展示：服务端的更新 DTO 里根本没有这个字段位。 */}
            <div className="flex min-w-0 flex-col gap-1">
              <span className="text-sm font-medium">{d.engine}</span>
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <Badge variant="outline">{selected.engine}</Badge>
                <span className="text-muted-foreground text-xs">
                  {d.engineImmutable}
                </span>
              </div>
            </div>
            <div className="flex min-w-0 flex-col gap-1">
              <span className="text-sm font-medium">
                {t.analytics.history.principalId}
              </span>
              <code className="font-mono text-xs break-all">
                {selected.owner_id}
              </code>
            </div>
            <FormField id={editNameId} label={d.name}>
              <FieldInput
                id={editNameId}
                value={editName}
                onChange={(event) => setEditName(event.target.value)}
              />
            </FormField>
            <FormField
              id={editSecretRefId}
              label={d.secretRef}
              hint={d.secretRefHint}
            >
              <FieldInput
                id={editSecretRefId}
                value={editSecretRef}
                onChange={(event) => setEditSecretRef(event.target.value)}
              />
            </FormField>
            <FormField id={editDefaultSchemaId} label={d.defaultSchema}>
              <FieldInput
                id={editDefaultSchemaId}
                value={editDefaultSchema}
                onChange={(event) => setEditDefaultSchema(event.target.value)}
              />
            </FormField>
            <FormField id={editStatusId} label={d.status}>
              <select
                id={editStatusId}
                className="border-input focus-visible:ring-ring/50 h-11 min-h-11 min-w-11 rounded-md border bg-transparent px-3 text-sm outline-none focus-visible:ring-[3px]"
                value={editStatus}
                onChange={(event) =>
                  setEditStatus(event.target.value as DatasourceStatus)
                }
              >
                {(["active", "disabled", "unhealthy"] as const).map(
                  (status) => (
                    <option key={status} value={status}>
                      {d[DATASOURCE_STATUS_KEYS[status]]}
                    </option>
                  ),
                )}
              </select>
            </FormField>
            {updateError !== null && (
              <AnalyticsInlineAlert>{updateError}</AnalyticsInlineAlert>
            )}
            <Button
              type="submit"
              className="min-h-11 min-w-11 self-start"
              disabled={updateGuard.busy || update.isPending}
            >
              {update.isPending
                ? t.analytics.common.saving
                : t.analytics.common.save}
            </Button>
          </form>

          <DatasourceSchemaEditor datasourceId={selected.id} />
          <DatasourcePolicyEditor datasourceId={selected.id} />
        </FormPanel>
      )}
    </section>
  );
}

// --- 管理员：数据模型（schema）编辑器 ---------------------------------------

export function DatasourceSchemaEditor({
  datasourceId,
}: {
  datasourceId: string;
}) {
  const { t } = useI18n();
  const s = t.analytics.schema;
  const query = useAdminSchema(datasourceId, true);
  const replace = useReplaceSchema();
  const guard = useSingleFlightSubmit();
  const errorText = useMutationErrorText();
  const importErrorId = useId();
  const importId = useId();
  const versionId = useId();
  const defaultSchemaId = useId();

  const [relations, setRelations] = useState<RelationSchemaView[]>([]);
  const [defaultSchema, setDefaultSchema] = useState("");
  const [version, setVersion] = useState("1");
  // expected_version 只来自最近一次成功读取；它不在任何输入元素里，因此无法被改写。
  const [expectedVersion, setExpectedVersion] = useState<string | null>(null);
  const [importText, setImportText] = useState("");
  const [importFailed, setImportFailed] = useState(false);
  const [saved, setSaved] = useState(false);

  const snapshotVersion = query.schema?.version;
  useEffect(() => {
    const snapshot = query.schema;
    if (snapshot === undefined || snapshot === null) {
      return;
    }
    setRelations(
      snapshot.relations.map((relation) => ({
        ...relation,
        columns: relation.columns.map((column) => ({ ...column })),
      })),
    );
    setDefaultSchema(snapshot.default_schema);
    setVersion(nextAnalyticsVersion(snapshot.version));
    setExpectedVersion(snapshot.version);
    setSaved(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snapshotVersion]);

  const updateRelation = (
    relationIndex: number,
    patch: Partial<RelationSchemaView>,
  ) => {
    setRelations((current) =>
      current.map((relation, index) =>
        index === relationIndex ? { ...relation, ...patch } : relation,
      ),
    );
  };

  const updateColumn = (
    relationIndex: number,
    columnIndex: number,
    patch: Partial<ColumnSchemaView>,
  ) => {
    setRelations((current) =>
      current.map((relation, index) => {
        if (index !== relationIndex) {
          return relation;
        }
        return {
          ...relation,
          columns: relation.columns.map((column, innerIndex) =>
            innerIndex === columnIndex ? { ...column, ...patch } : column,
          ),
        };
      }),
    );
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    // 单飞：pending 期间的第二、第三次点击不会发出请求。
    guard.run((release) => {
      let nextRelations = relations;
      let nextDefaultSchema = defaultSchema;
      const trimmedImport = importText.trim();
      if (trimmedImport.length > 0) {
        // 本地先解析并严格校验；失败就带着内联错误停下，绝不提交。
        const parsed = parseSchemaImport(trimmedImport);
        if (!parsed.ok) {
          setImportFailed(true);
          release();
          return;
        }
        setImportFailed(false);
        nextRelations = parsed.relations;
        if (parsed.defaultSchema !== null) {
          nextDefaultSchema = parsed.defaultSchema;
        }
        setRelations(parsed.relations);
      }
      setSaved(false);
      replace.mutate(
        {
          datasourceId,
          request: {
            version: version.trim().length === 0 ? "1" : version.trim(),
            expected_version: expectedVersion,
            default_schema:
              nextDefaultSchema.trim().length === 0
                ? (query.schema?.default_schema ?? "")
                : nextDefaultSchema.trim(),
            relations: nextRelations,
          },
        },
        {
          onSuccess: () => {
            setSaved(true);
            setImportText("");
            setImportFailed(false);
          },
          onSettled: release,
        },
      );
    });
  };

  const conflict = isConflict(replace.error);
  const forbidden = isAnalyticsForbidden(replace.error);
  const replaceError = errorText(replace.error);

  return (
    <div className="border-border flex min-w-0 flex-col gap-3 rounded-md border p-3">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <h4 className="text-sm font-semibold">{s.title}</h4>
        <Badge variant="secondary">
          {s.version} {query.schema?.version ?? t.analytics.common.notAvailable}
        </Badge>
        {saved && (
          <span role="status" className="text-muted-foreground text-xs">
            {s.saved}
          </span>
        )}
      </div>
      <p className="text-muted-foreground text-xs">{s.description}</p>

      {query.isLoading && (
        <p role="status" className="text-muted-foreground text-sm">
          {t.analytics.common.loading}
        </p>
      )}

      {/*
        读取失败时仍然允许编辑：服务端的 replace 只在"确实没有当前快照"时接受
        expected_version = null，已有快照时一律 409 stale_expected_version。
        因此这里放开编辑不会覆盖别人的修改——真正的守卫在服务端。
      */}
      {query.isError && (
        <div className="flex min-w-0 flex-col items-start gap-2">
          <p role="alert" className="text-destructive text-sm">
            {t.analytics.common.loadFailed}
          </p>
          <Button
            type="button"
            variant="outline"
            className="min-h-11 min-w-11"
            onClick={() => void query.refetch()}
          >
            {t.analytics.common.retry}
          </Button>
        </div>
      )}

      {/* 409：给出显式的"刷新后重试"入口，绝不自动重放这次写入。 */}
      {conflict && (
        <AnalyticsStaleBanner
          onRefresh={() => {
            void query.refetch();
          }}
          refreshing={query.isLoading}
        />
      )}

      <form
        className="flex min-w-0 flex-col gap-3"
        onSubmit={submit}
        noValidate
      >
        <div className="flex min-w-0 flex-wrap items-end gap-3">
          <FormField
            id={defaultSchemaId}
            label={s.defaultSchema}
            className="min-w-[12rem] flex-1"
          >
            <FieldInput
              id={defaultSchemaId}
              value={defaultSchema}
              onChange={(event) => setDefaultSchema(event.target.value)}
            />
          </FormField>
          <FormField id={versionId} label={s.version} className="min-w-[8rem]">
            <FieldInput
              id={versionId}
              value={version}
              onChange={(event) => setVersion(event.target.value)}
            />
          </FormField>
          <div className="flex min-w-0 flex-col gap-1">
            <span className="text-sm font-medium">{s.version}</span>
            {/* expected_version 是服务端结论：只读展示，没有输入元素。 */}
            <code
              data-testid="schema-expected-version"
              className="font-mono text-xs"
            >
              {expectedVersion ?? t.analytics.common.notAvailable}
            </code>
          </div>
        </div>

        <ul className="flex min-w-0 flex-col gap-3">
          {relations.map((relation, relationIndex) => (
            <li
              key={relationIndex}
              className="border-border flex min-w-0 flex-col gap-2 rounded-md border p-2"
              data-testid={`schema-relation-${relationIndex}`}
            >
              <div className="flex min-w-0 flex-wrap items-end gap-2">
                <FormField
                  id={`${importId}-relation-name-${relationIndex}`}
                  label={s.relationName}
                  className="min-w-[10rem] flex-1"
                >
                  <FieldInput
                    id={`${importId}-relation-name-${relationIndex}`}
                    value={relation.name}
                    onChange={(event) =>
                      updateRelation(relationIndex, {
                        name: event.target.value,
                      })
                    }
                  />
                </FormField>
                <FormField
                  id={`${importId}-relation-schema-${relationIndex}`}
                  label={s.relationSchema}
                  className="min-w-[10rem] flex-1"
                >
                  <FieldInput
                    id={`${importId}-relation-schema-${relationIndex}`}
                    value={relation.schema}
                    onChange={(event) =>
                      updateRelation(relationIndex, {
                        schema: event.target.value,
                      })
                    }
                  />
                </FormField>
                <Button
                  type="button"
                  variant="outline"
                  className="min-h-11 min-w-11"
                  aria-label={`${s.removeRelation} ${relation.name}`}
                  onClick={() =>
                    setRelations((current) =>
                      current.filter((_, index) => index !== relationIndex),
                    )
                  }
                >
                  <Trash2Icon aria-hidden="true" className="size-4" />
                  {s.removeRelation}
                </Button>
              </div>

              <ul className="flex min-w-0 flex-col gap-2">
                {relation.columns.map((column, columnIndex) => (
                  <li
                    key={columnIndex}
                    className="flex min-w-0 flex-wrap items-end gap-2"
                  >
                    <FormField
                      id={`${importId}-column-name-${relationIndex}-${columnIndex}`}
                      label={s.columnName}
                      className="min-w-[8rem] flex-1"
                    >
                      <FieldInput
                        id={`${importId}-column-name-${relationIndex}-${columnIndex}`}
                        value={column.name}
                        onChange={(event) =>
                          updateColumn(relationIndex, columnIndex, {
                            name: event.target.value,
                          })
                        }
                      />
                    </FormField>
                    <FormField
                      id={`${importId}-column-type-${relationIndex}-${columnIndex}`}
                      label={s.columnType}
                      className="min-w-[8rem] flex-1"
                    >
                      <FieldInput
                        id={`${importId}-column-type-${relationIndex}-${columnIndex}`}
                        value={column.data_type}
                        onChange={(event) =>
                          updateColumn(relationIndex, columnIndex, {
                            data_type: event.target.value,
                          })
                        }
                      />
                    </FormField>
                    <FormField
                      id={`${importId}-column-sensitivity-${relationIndex}-${columnIndex}`}
                      label={s.columnSensitivity}
                      className="min-w-[8rem]"
                    >
                      {/* sensitivity 是协议值（standard/sensitive/pii），按约定保留英文。 */}
                      <select
                        id={`${importId}-column-sensitivity-${relationIndex}-${columnIndex}`}
                        className="border-input focus-visible:ring-ring/50 h-11 min-h-11 min-w-11 rounded-md border bg-transparent px-3 text-sm outline-none focus-visible:ring-[3px]"
                        value={column.sensitivity}
                        onChange={(event) =>
                          updateColumn(relationIndex, columnIndex, {
                            sensitivity: event.target
                              .value as ColumnSensitivity,
                          })
                        }
                      >
                        {COLUMN_SENSITIVITIES.map((sensitivity) => (
                          <option key={sensitivity} value={sensitivity}>
                            {sensitivity}
                          </option>
                        ))}
                      </select>
                    </FormField>
                    <Button
                      type="button"
                      variant="outline"
                      className="min-h-11 min-w-11"
                      aria-label={`${s.removeColumn} ${column.name}`}
                      onClick={() =>
                        updateRelation(relationIndex, {
                          columns: relation.columns.filter(
                            (_, index) => index !== columnIndex,
                          ),
                        })
                      }
                    >
                      <Trash2Icon aria-hidden="true" className="size-4" />
                      {s.removeColumn}
                    </Button>
                  </li>
                ))}
              </ul>

              <Button
                type="button"
                variant="outline"
                className="min-h-11 min-w-11 self-start"
                onClick={() =>
                  updateRelation(relationIndex, {
                    columns: [
                      ...relation.columns,
                      {
                        name: "",
                        data_type: "",
                        sensitivity: "standard",
                      },
                    ],
                  })
                }
              >
                <PlusIcon aria-hidden="true" className="size-4" />
                {s.addColumn}
              </Button>
            </li>
          ))}
        </ul>

        <Button
          type="button"
          variant="outline"
          className="min-h-11 min-w-11 self-start"
          onClick={() =>
            setRelations((current) => [
              ...current,
              { name: "", schema: "", catalog: null, columns: [] },
            ])
          }
        >
          <PlusIcon aria-hidden="true" className="size-4" />
          {s.addRelation}
        </Button>

        {/* 可选的 JSON 导入：内容非空时在提交前严格本地校验。 */}
        <div className="flex min-w-0 flex-col gap-1">
          <FieldTextarea
            aria-label={s.importLabel}
            aria-invalid={importFailed}
            aria-describedby={importFailed ? importErrorId : undefined}
            data-testid="schema-import"
            rows={4}
            value={importText}
            onChange={(event) => {
              setImportText(event.target.value);
              setImportFailed(false);
            }}
            className="font-mono text-xs"
          />
          <p className="text-muted-foreground text-xs">{s.description}</p>
        </div>
        {importFailed && (
          <AnalyticsInlineAlert id={importErrorId}>
            {s.importInvalidJson}
          </AnalyticsInlineAlert>
        )}

        {forbidden && (
          <AnalyticsInlineAlert>
            {t.analytics.common.forbidden}
          </AnalyticsInlineAlert>
        )}
        {!forbidden && !conflict && replaceError !== null && (
          <AnalyticsInlineAlert>{replaceError}</AnalyticsInlineAlert>
        )}

        <Button
          type="submit"
          className="min-h-11 min-w-11 self-start"
          disabled={guard.busy || replace.isPending}
        >
          {replace.isPending
            ? t.analytics.common.saving
            : t.analytics.common.save}
        </Button>
      </form>
    </div>
  );
}

// --- 管理员：访问策略编辑器 -------------------------------------------------

export function DatasourcePolicyEditor({
  datasourceId,
}: {
  datasourceId: string;
}) {
  const { t } = useI18n();
  const s = t.analytics.schema;
  const p = t.analytics.policy;
  const [principalInput, setPrincipalInput] = useState("");
  // 默认 null：没有显式提交主体时 query 是 disabled 的，绝不会发起跨主体查询。
  const [appliedPrincipal, setAppliedPrincipal] = useState<string | null>(null);
  const query = useAdminPolicy(datasourceId, appliedPrincipal, true);
  const replace = useReplacePolicy();
  const remove = useRemovePolicy();
  const saveGuard = useSingleFlightSubmit();
  const removeGuard = useSingleFlightSubmit();
  const errorText = useMutationErrorText();

  const [relations, setRelations] = useState<RelationAccessRuleView[]>([]);
  const [allowedFunctions, setAllowedFunctions] = useState<string[]>([]);
  const [version, setVersion] = useState("1");
  const [expectedVersion, setExpectedVersion] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const principalFieldId = useId();
  const versionId = useId();

  const policyVersion = query.policy?.version;
  useEffect(() => {
    const policy = query.policy;
    if (policy === undefined || policy === null) {
      return;
    }
    setRelations(
      policy.relations.map((relation) => ({
        ...relation,
        columns: relation.columns.map((column) => ({ ...column })),
      })),
    );
    setAllowedFunctions([...policy.allowed_functions]);
    setVersion(nextAnalyticsVersion(policy.version));
    setExpectedVersion(policy.version);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [policyVersion]);

  const applyPrincipal = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = principalInput.trim();
    setAppliedPrincipal(trimmed.length === 0 ? null : trimmed);
    // 主体切换后旧的 expected_version 不再适用；等新一次读取成功再填。
    setExpectedVersion(null);
    setRelations([]);
    setAllowedFunctions([]);
    setVersion("1");
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (appliedPrincipal === null) {
      return;
    }
    const principalId = appliedPrincipal;
    saveGuard.run((release) => {
      replace.mutate(
        {
          datasourceId,
          principalId,
          request: {
            version: version.trim().length === 0 ? "1" : version.trim(),
            expected_version: expectedVersion,
            relations,
            allowed_functions: allowedFunctions
              .map((name) => name.trim())
              .filter((name) => name.length > 0),
          },
        },
        { onSettled: release },
      );
    });
  };

  const confirmRemove = () => {
    if (appliedPrincipal === null) {
      return;
    }
    const principalId = appliedPrincipal;
    removeGuard.run((release) => {
      remove.mutate(
        { datasourceId, principalId },
        {
          onSuccess: () => {
            setConfirmOpen(false);
            setExpectedVersion(null);
            setRelations([]);
            setAllowedFunctions([]);
          },
          onSettled: release,
        },
      );
    });
  };

  const conflict = isConflict(replace.error);
  const saveError = errorText(replace.error);
  const removeError = errorText(remove.error);

  return (
    <div className="border-border flex min-w-0 flex-col gap-3 rounded-md border p-3">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <h4 className="text-sm font-semibold">{p.title}</h4>
        {query.policy !== null && (
          <Badge variant="secondary">
            {s.version} {query.policy.version}
          </Badge>
        )}
        {remove.isSuccess && (
          <span role="status" className="text-muted-foreground text-xs">
            {p.removed}
          </span>
        )}
      </div>
      <p className="text-muted-foreground text-xs">{p.description}</p>

      <form
        className="flex min-w-0 flex-wrap items-end gap-2"
        onSubmit={applyPrincipal}
        noValidate
      >
        <FormField
          id={principalFieldId}
          label={p.principalId}
          className="min-w-[12rem] flex-1"
        >
          <FieldInput
            id={principalFieldId}
            data-testid="policy-principal"
            value={principalInput}
            onChange={(event) => setPrincipalInput(event.target.value)}
          />
        </FormField>
        <Button type="submit" variant="outline" className="min-h-11 min-w-11">
          {t.common.search}
        </Button>
      </form>

      {appliedPrincipal === null ? null : (
        <>
          {query.isLoading && (
            <p role="status" className="text-muted-foreground text-sm">
              {t.analytics.common.loading}
            </p>
          )}

          {query.isError && (
            <div className="flex min-w-0 flex-col items-start gap-2">
              <p role="alert" className="text-destructive text-sm">
                {t.analytics.common.loadFailed}
              </p>
              <Button
                type="button"
                variant="outline"
                className="min-h-11 min-w-11"
                onClick={() => void query.refetch()}
              >
                {t.analytics.common.retry}
              </Button>
            </div>
          )}

          {conflict && (
            <AnalyticsStaleBanner
              onRefresh={() => {
                void query.refetch();
              }}
              refreshing={query.isLoading}
            />
          )}

          <form
            className="flex min-w-0 flex-col gap-3"
            onSubmit={submit}
            noValidate
          >
            <div className="flex min-w-0 flex-wrap items-end gap-3">
              <FormField
                id={versionId}
                label={s.version}
                className="min-w-[8rem]"
              >
                <FieldInput
                  id={versionId}
                  value={version}
                  onChange={(event) => setVersion(event.target.value)}
                />
              </FormField>
              <div className="flex min-w-0 flex-col gap-1">
                <span className="text-sm font-medium">{s.version}</span>
                <code className="font-mono text-xs">
                  {expectedVersion ?? t.analytics.common.notAvailable}
                </code>
              </div>
            </div>

            <h5 className="text-sm font-medium">{p.relations}</h5>
            <ul className="flex min-w-0 flex-col gap-3">
              {relations.map((relation, relationIndex) => (
                <li
                  key={relationIndex}
                  className="border-border flex min-w-0 flex-col gap-2 rounded-md border p-2"
                  data-testid={`policy-relation-${relationIndex}`}
                >
                  <div className="flex min-w-0 flex-wrap items-end gap-2">
                    <FormField
                      id={`${principalFieldId}-relation-name-${relationIndex}`}
                      label={s.relationName}
                      className="min-w-[10rem] flex-1"
                    >
                      <FieldInput
                        id={`${principalFieldId}-relation-name-${relationIndex}`}
                        value={relation.name}
                        onChange={(event) =>
                          setRelations((current) =>
                            current.map((item, index) =>
                              index === relationIndex
                                ? { ...item, name: event.target.value }
                                : item,
                            ),
                          )
                        }
                      />
                    </FormField>
                    <FormField
                      id={`${principalFieldId}-relation-schema-${relationIndex}`}
                      label={s.defaultSchema}
                      className="min-w-[10rem] flex-1"
                    >
                      <FieldInput
                        id={`${principalFieldId}-relation-schema-${relationIndex}`}
                        value={relation.schema}
                        onChange={(event) =>
                          setRelations((current) =>
                            current.map((item, index) =>
                              index === relationIndex
                                ? { ...item, schema: event.target.value }
                                : item,
                            ),
                          )
                        }
                      />
                    </FormField>
                    <Button
                      type="button"
                      variant="outline"
                      className="min-h-11 min-w-11"
                      aria-label={`${s.removeRelation} ${relation.name}`}
                      onClick={() =>
                        setRelations((current) =>
                          current.filter((_, index) => index !== relationIndex),
                        )
                      }
                    >
                      <Trash2Icon aria-hidden="true" className="size-4" />
                      {s.removeRelation}
                    </Button>
                  </div>

                  <ul className="flex min-w-0 flex-col gap-2">
                    {relation.columns.map((column, columnIndex) => (
                      <li
                        key={columnIndex}
                        className="flex min-w-0 flex-wrap items-end gap-2"
                      >
                        <FormField
                          id={`${principalFieldId}-column-${relationIndex}-${columnIndex}`}
                          label={s.columnName}
                          className="min-w-[8rem] flex-1"
                        >
                          <FieldInput
                            id={`${principalFieldId}-column-${relationIndex}-${columnIndex}`}
                            value={column.name}
                            onChange={(event) =>
                              setRelations((current) =>
                                current.map((item, index) =>
                                  index === relationIndex
                                    ? {
                                        ...item,
                                        columns: item.columns.map(
                                          (inner, innerIndex) =>
                                            innerIndex === columnIndex
                                              ? {
                                                  ...inner,
                                                  name: event.target.value,
                                                }
                                              : inner,
                                        ),
                                      }
                                    : item,
                                ),
                              )
                            }
                          />
                        </FormField>
                        {/* 允许/拒绝用一对切换按钮：可见文字就是本地化文案，不依赖颜色或颜色语义。 */}
                        <div
                          role="group"
                          aria-label={`${s.columnName} ${column.name}`}
                          className="flex min-w-0 gap-1"
                        >
                          {(["allow", "deny"] as const).map((access) => (
                            <Button
                              key={access}
                              type="button"
                              variant={
                                column.access === access ? "default" : "outline"
                              }
                              aria-pressed={column.access === access}
                              className="min-h-11 min-w-11"
                              onClick={() =>
                                setRelations((current) =>
                                  current.map((item, index) =>
                                    index === relationIndex
                                      ? {
                                          ...item,
                                          columns: item.columns.map(
                                            (inner, innerIndex) =>
                                              innerIndex === columnIndex
                                                ? { ...inner, access }
                                                : inner,
                                          ),
                                        }
                                      : item,
                                  ),
                                )
                              }
                            >
                              {access === "allow"
                                ? p.accessAllowed
                                : p.accessDenied}
                            </Button>
                          ))}
                        </div>
                        <Button
                          type="button"
                          variant="outline"
                          className="min-h-11 min-w-11"
                          aria-label={`${s.removeColumn} ${column.name}`}
                          onClick={() =>
                            setRelations((current) =>
                              current.map((item, index) =>
                                index === relationIndex
                                  ? {
                                      ...item,
                                      columns: item.columns.filter(
                                        (_, innerIndex) =>
                                          innerIndex !== columnIndex,
                                      ),
                                    }
                                  : item,
                              ),
                            )
                          }
                        >
                          <Trash2Icon aria-hidden="true" className="size-4" />
                          {s.removeColumn}
                        </Button>
                      </li>
                    ))}
                  </ul>

                  <Button
                    type="button"
                    variant="outline"
                    className="min-h-11 min-w-11 self-start"
                    onClick={() =>
                      setRelations((current) =>
                        current.map((item, index) =>
                          index === relationIndex
                            ? {
                                ...item,
                                columns: [
                                  ...item.columns,
                                  { name: "", access: "deny" },
                                ],
                              }
                            : item,
                        ),
                      )
                    }
                  >
                    <PlusIcon aria-hidden="true" className="size-4" />
                    {s.addColumn}
                  </Button>
                </li>
              ))}
            </ul>

            <Button
              type="button"
              variant="outline"
              className="min-h-11 min-w-11 self-start"
              onClick={() =>
                setRelations((current) => [
                  ...current,
                  { name: "", schema: "", catalog: null, columns: [] },
                ])
              }
            >
              <PlusIcon aria-hidden="true" className="size-4" />
              {s.addRelation}
            </Button>

            <h5 className="text-sm font-medium">{p.allowedFunctions}</h5>
            <ul className="flex min-w-0 flex-col gap-2">
              {allowedFunctions.map((allowed, functionIndex) => (
                <li
                  key={functionIndex}
                  className="flex min-w-0 items-end gap-2"
                >
                  <FieldInput
                    aria-label={`${p.allowedFunctions} ${functionIndex + 1}`}
                    className="min-w-[10rem] flex-1"
                    value={allowed}
                    onChange={(event) =>
                      setAllowedFunctions((current) =>
                        current.map((item, index) =>
                          index === functionIndex ? event.target.value : item,
                        ),
                      )
                    }
                  />
                  <Button
                    type="button"
                    variant="outline"
                    className="min-h-11 min-w-11"
                    aria-label={`${t.common.delete} ${p.allowedFunctions}`}
                    onClick={() =>
                      setAllowedFunctions((current) =>
                        current.filter((_, index) => index !== functionIndex),
                      )
                    }
                  >
                    <Trash2Icon aria-hidden="true" className="size-4" />
                    {t.common.delete}
                  </Button>
                </li>
              ))}
            </ul>
            <Button
              type="button"
              variant="outline"
              className="min-h-11 min-w-11 self-start"
              aria-label={`${t.common.create} ${p.allowedFunctions}`}
              onClick={() => setAllowedFunctions((current) => [...current, ""])}
            >
              <PlusIcon aria-hidden="true" className="size-4" />
              {t.common.create}
            </Button>

            <p className="text-muted-foreground text-xs">{p.saveHint}</p>

            {saveError !== null && !conflict && (
              <AnalyticsInlineAlert>{saveError}</AnalyticsInlineAlert>
            )}
            {removeError !== null && (
              <AnalyticsInlineAlert>{removeError}</AnalyticsInlineAlert>
            )}

            <div className="flex min-w-0 flex-wrap gap-2">
              <Button
                type="submit"
                className="min-h-11 min-w-11"
                disabled={saveGuard.busy || replace.isPending}
              >
                {replace.isPending
                  ? t.analytics.common.saving
                  : t.analytics.common.save}
              </Button>
              <Button
                type="button"
                variant="destructive"
                className="min-h-11 min-w-11"
                disabled={removeGuard.busy || remove.isPending}
                onClick={() => setConfirmOpen(true)}
              >
                {p.remove}
              </Button>
            </div>
          </form>
        </>
      )}

      <AnalyticsConfirmDialog
        open={confirmOpen}
        title={p.confirmRemoveTitle}
        description={p.confirmRemoveBody}
        confirmLabel={p.remove}
        pending={removeGuard.busy || remove.isPending}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={confirmRemove}
      />
    </div>
  );
}

// --- 管理员：指标 -----------------------------------------------------------

const METRIC_STATUS_KEYS = {
  draft: "statusDraft",
  active: "statusActive",
  retired: "statusRetired",
} as const;

export function MetricAdminSection({
  metrics,
  isError = false,
}: {
  metrics: MetricView[];
  isError?: boolean;
}) {
  const { t } = useI18n();
  const m = t.analytics.metric;
  const create = useCreateMetric();
  const update = useUpdateMetric();
  const retire = useRetireMetric();
  const createGuard = useSingleFlightSubmit();
  const updateGuard = useSingleFlightSubmit();
  const retireGuard = useSingleFlightSubmit();
  const errorText = useMutationErrorText();

  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [retireKey, setRetireKey] = useState<string | null>(null);
  const [createKey, setCreateKey] = useState("");
  const [createName, setCreateName] = useState("");
  const [createDescription, setCreateDescription] = useState("");
  const [createExpression, setCreateExpression] = useState("");
  const [createDimensions, setCreateDimensions] = useState<string[]>([]);
  const [createStatus, setCreateStatus] = useState<MetricStatus>("draft");
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editExpression, setEditExpression] = useState("");
  const [editDimensions, setEditDimensions] = useState<string[]>([]);
  const [editVersion, setEditVersion] = useState(1);
  const [editStatus, setEditStatus] = useState<MetricStatus>("draft");
  const createKeyId = useId();
  const createNameId = useId();
  const createDescriptionId = useId();
  const createExpressionId = useId();
  const createStatusId = useId();
  const editNameId = useId();
  const editDescriptionId = useId();
  const editExpressionId = useId();
  const editVersionId = useId();
  const editStatusId = useId();

  const selected = metrics.find((metric) => metric.key === selectedKey) ?? null;

  // 只在切换指标时同步表单：后台 refetch 不能覆盖正在编辑的内容。
  useEffect(() => {
    const metric = metrics.find((item) => item.key === selectedKey);
    if (metric === undefined) {
      return;
    }
    setEditName(metric.name);
    setEditDescription(metric.description);
    setEditExpression(metric.expression);
    setEditDimensions([...metric.dimensions]);
    // 版本必须显式前进：预填成一个必定大于当前值的版本，管理员仍可改成自己的策略。
    setEditVersion(nextMetricVersion(metric.version));
    setEditStatus(metric.status);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedKey]);

  const submitCreate = (event: FormEvent) => {
    event.preventDefault();
    const key = createKey.trim();
    if (key.length === 0 || createName.trim().length === 0) {
      return;
    }
    createGuard.run((release) => {
      create.mutate(
        {
          key,
          name: createName.trim(),
          description: createDescription,
          // expression 是定义字符串：原样提交，绝不求值、绝不改写。
          expression: createExpression,
          dimensions: createDimensions
            .map((dimension) => dimension.trim())
            .filter((dimension) => dimension.length > 0),
          version: 1,
          status: createStatus,
        },
        {
          onSuccess: () => {
            setCreateKey("");
            setCreateName("");
            setCreateDescription("");
            setCreateExpression("");
            setCreateDimensions([]);
            setCreateStatus("draft");
          },
          onSettled: release,
        },
      );
    });
  };

  const submitUpdate = (event: FormEvent) => {
    event.preventDefault();
    if (selected === null) {
      return;
    }
    const metricKey = selected.key;
    updateGuard.run((release) => {
      update.mutate(
        {
          metricKey,
          request: {
            name: editName.trim(),
            description: editDescription,
            expression: editExpression,
            dimensions: editDimensions
              .map((dimension) => dimension.trim())
              .filter((dimension) => dimension.length > 0),
            version: editVersion,
            status: editStatus,
          },
        },
        { onSettled: release },
      );
    });
  };

  const confirmRetire = () => {
    if (retireKey === null) {
      return;
    }
    const metricKey = retireKey;
    retireGuard.run((release) => {
      retire.mutate(metricKey, {
        onSuccess: () => setRetireKey(null),
        onSettled: release,
      });
    });
  };

  const createError = errorText(create.error);
  const updateError = errorText(update.error);
  const retireError = errorText(retire.error);
  // 服务端以 409 表达"版本没有前进"，这里给出对应的本地化提示。
  const updateNeedsVersionBump = isConflict(update.error);

  return (
    <section
      aria-label={t.analytics.common.adminOnly}
      className="flex min-w-0 flex-col gap-4"
    >
      <PanelHeading title={m.title} adminBadge={t.analytics.common.adminOnly} />

      {isError && (
        <AnalyticsInlineAlert>
          {t.analytics.common.loadFailed}
        </AnalyticsInlineAlert>
      )}

      <MetricCatalogTable
        metrics={metrics}
        renderActions={(metric) => (
          <div className="flex min-w-0 flex-wrap gap-1">
            <Button
              type="button"
              variant="outline"
              className="min-h-11 min-w-11"
              aria-label={`${t.analytics.common.edit} ${metric.name}`}
              onClick={() => setSelectedKey(metric.key)}
            >
              {t.analytics.common.edit}
            </Button>
            {/* 这是"下线状态"，不是物理删除；文案也来自 metric.retire。 */}
            <Button
              type="button"
              variant="destructive"
              className="min-h-11 min-w-11"
              aria-label={`${m.retire} ${metric.name}`}
              disabled={metric.status === "retired"}
              onClick={() => setRetireKey(metric.key)}
            >
              {m.retire}
            </Button>
          </div>
        )}
      />

      <FormPanel>
        <h3 className="text-base font-semibold">{m.createTitle}</h3>
        <form
          className="flex min-w-0 flex-col gap-3"
          data-testid="metric-create-form"
          onSubmit={submitCreate}
          noValidate
        >
          <FormField id={createKeyId} label={m.key}>
            <FieldInput
              id={createKeyId}
              value={createKey}
              onChange={(event) => setCreateKey(event.target.value)}
            />
          </FormField>
          <FormField id={createNameId} label={m.name}>
            <FieldInput
              id={createNameId}
              value={createName}
              onChange={(event) => setCreateName(event.target.value)}
            />
          </FormField>
          <FormField id={createDescriptionId} label={m.description}>
            <FieldTextarea
              id={createDescriptionId}
              rows={2}
              value={createDescription}
              onChange={(event) => setCreateDescription(event.target.value)}
            />
          </FormField>
          <FormField
            id={createExpressionId}
            label={m.expression}
            hint={m.expressionHint}
          >
            {/* 纯文本定义：不做任何求值，也不包装成可执行 SQL。 */}
            <FieldTextarea
              id={createExpressionId}
              rows={3}
              className="font-mono text-xs"
              value={createExpression}
              onChange={(event) => setCreateExpression(event.target.value)}
            />
          </FormField>
          <h4 className="text-sm font-medium">{m.dimensions}</h4>
          <ul className="flex min-w-0 flex-col gap-2">
            {createDimensions.map((dimension, index) => (
              <li key={index} className="flex min-w-0 items-end gap-2">
                <FieldInput
                  aria-label={`${m.dimensions} ${index + 1}`}
                  className="min-w-[10rem] flex-1"
                  value={dimension}
                  onChange={(event) =>
                    setCreateDimensions((current) =>
                      current.map((item, innerIndex) =>
                        innerIndex === index ? event.target.value : item,
                      ),
                    )
                  }
                />
                <Button
                  type="button"
                  variant="outline"
                  className="min-h-11 min-w-11"
                  aria-label={`${t.common.delete} ${m.dimensions}`}
                  onClick={() =>
                    setCreateDimensions((current) =>
                      current.filter((_, innerIndex) => innerIndex !== index),
                    )
                  }
                >
                  <Trash2Icon aria-hidden="true" className="size-4" />
                  {t.common.delete}
                </Button>
              </li>
            ))}
          </ul>
          <Button
            type="button"
            variant="outline"
            className="min-h-11 min-w-11 self-start"
            aria-label={`${t.common.create} ${m.dimensions}`}
            onClick={() => setCreateDimensions((current) => [...current, ""])}
          >
            <PlusIcon aria-hidden="true" className="size-4" />
            {t.common.create}
          </Button>
          <FormField id={createStatusId} label={m.status}>
            <select
              id={createStatusId}
              className="border-input focus-visible:ring-ring/50 h-11 min-h-11 min-w-11 rounded-md border bg-transparent px-3 text-sm outline-none focus-visible:ring-[3px]"
              value={createStatus}
              onChange={(event) =>
                setCreateStatus(event.target.value as MetricStatus)
              }
            >
              {(["draft", "active", "retired"] as const).map((status) => (
                <option key={status} value={status}>
                  {m[METRIC_STATUS_KEYS[status]]}
                </option>
              ))}
            </select>
          </FormField>
          {createError !== null && (
            <AnalyticsInlineAlert>{createError}</AnalyticsInlineAlert>
          )}
          <Button
            type="submit"
            className="min-h-11 min-w-11 self-start"
            disabled={
              createGuard.busy ||
              create.isPending ||
              createKey.trim().length === 0 ||
              createName.trim().length === 0
            }
          >
            {create.isPending
              ? t.analytics.common.saving
              : t.analytics.common.create}
          </Button>
        </form>
      </FormPanel>

      {selected !== null && (
        <FormPanel>
          <h3 className="text-base font-semibold">{m.editTitle}</h3>
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span className="text-sm font-medium">{m.key}</span>
            <Badge variant="outline">{selected.key}</Badge>
          </div>
          <form
            className="flex min-w-0 flex-col gap-3"
            data-testid="metric-edit-form"
            onSubmit={submitUpdate}
            noValidate
          >
            <FormField id={editNameId} label={m.name}>
              <FieldInput
                id={editNameId}
                value={editName}
                onChange={(event) => setEditName(event.target.value)}
              />
            </FormField>
            <FormField id={editDescriptionId} label={m.description}>
              <FieldTextarea
                id={editDescriptionId}
                rows={2}
                value={editDescription}
                onChange={(event) => setEditDescription(event.target.value)}
              />
            </FormField>
            <FormField
              id={editExpressionId}
              label={m.expression}
              hint={m.expressionHint}
            >
              <FieldTextarea
                id={editExpressionId}
                rows={3}
                className="font-mono text-xs"
                value={editExpression}
                onChange={(event) => setEditExpression(event.target.value)}
              />
            </FormField>
            <h4 className="text-sm font-medium">{m.dimensions}</h4>
            <ul className="flex min-w-0 flex-col gap-2">
              {editDimensions.map((dimension, index) => (
                <li key={index} className="flex min-w-0 items-end gap-2">
                  <FieldInput
                    aria-label={`${m.dimensions} ${index + 1}`}
                    className="min-w-[10rem] flex-1"
                    value={dimension}
                    onChange={(event) =>
                      setEditDimensions((current) =>
                        current.map((item, innerIndex) =>
                          innerIndex === index ? event.target.value : item,
                        ),
                      )
                    }
                  />
                  <Button
                    type="button"
                    variant="outline"
                    className="min-h-11 min-w-11"
                    aria-label={`${t.common.delete} ${m.dimensions}`}
                    onClick={() =>
                      setEditDimensions((current) =>
                        current.filter((_, innerIndex) => innerIndex !== index),
                      )
                    }
                  >
                    <Trash2Icon aria-hidden="true" className="size-4" />
                    {t.common.delete}
                  </Button>
                </li>
              ))}
            </ul>
            <Button
              type="button"
              variant="outline"
              className="min-h-11 min-w-11 self-start"
              aria-label={`${t.common.create} ${m.dimensions}`}
              onClick={() => setEditDimensions((current) => [...current, ""])}
            >
              <PlusIcon aria-hidden="true" className="size-4" />
              {t.common.create}
            </Button>
            <FormField id={editVersionId} label={m.version}>
              <FieldInput
                id={editVersionId}
                type="number"
                min={1}
                className="min-w-[8rem]"
                value={String(editVersion)}
                onChange={(event) =>
                  setEditVersion(Number(event.target.value) || 1)
                }
              />
            </FormField>
            <FormField id={editStatusId} label={m.status}>
              <select
                id={editStatusId}
                className="border-input focus-visible:ring-ring/50 h-11 min-h-11 min-w-11 rounded-md border bg-transparent px-3 text-sm outline-none focus-visible:ring-[3px]"
                value={editStatus}
                onChange={(event) =>
                  setEditStatus(event.target.value as MetricStatus)
                }
              >
                {(["draft", "active", "retired"] as const).map((status) => (
                  <option key={status} value={status}>
                    {m[METRIC_STATUS_KEYS[status]]}
                  </option>
                ))}
              </select>
            </FormField>
            {updateNeedsVersionBump && (
              <AnalyticsInlineAlert>
                {m.versionMustAdvance}
              </AnalyticsInlineAlert>
            )}
            {!updateNeedsVersionBump && updateError !== null && (
              <AnalyticsInlineAlert>{updateError}</AnalyticsInlineAlert>
            )}
            <Button
              type="submit"
              className="min-h-11 min-w-11 self-start"
              disabled={updateGuard.busy || update.isPending}
            >
              {update.isPending
                ? t.analytics.common.saving
                : t.analytics.common.save}
            </Button>
          </form>
        </FormPanel>
      )}

      {retireError !== null && (
        <AnalyticsInlineAlert>{retireError}</AnalyticsInlineAlert>
      )}

      <AnalyticsConfirmDialog
        open={retireKey !== null}
        title={m.confirmRetireTitle}
        description={m.confirmRetireBody}
        confirmLabel={m.retire}
        pending={retireGuard.busy || retire.isPending}
        onCancel={() => setRetireKey(null)}
        onConfirm={confirmRetire}
      />
    </section>
  );
}

// --- 管理员：按主体查询审计 -------------------------------------------------

/**
 * 跨主体审计查询。
 *
 * 只有在管理员**显式提交**一个主体 ID 之后才会发起查询；默认 `null` 让 query 保持 disabled，
 * 因此打开页面永远不会顺带读取别人的审计。结果只渲染 `QueryAuditView` 里的安全字段。
 */
export function AuditPrincipalLookup() {
  const { t } = useI18n();
  const [principalInput, setPrincipalInput] = useState("");
  const [appliedPrincipal, setAppliedPrincipal] = useState<string | null>(null);
  const lookup = useAdminAuditLookup(appliedPrincipal);
  const fieldId = useId();
  const audits: QueryAuditView[] = lookup.audits;

  return (
    <section
      aria-label={t.analytics.history.principalId}
      className="border-border flex min-w-0 flex-col gap-3 rounded-md border p-3"
    >
      <h2 className="text-base font-semibold">
        {t.analytics.history.principalId}
      </h2>
      <p className="text-muted-foreground text-xs">
        {t.analytics.history.adminHint}
      </p>
      <form
        className="flex min-w-0 flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          const trimmed = principalInput.trim();
          setAppliedPrincipal(trimmed.length === 0 ? null : trimmed);
        }}
        noValidate
      >
        <FormField
          id={fieldId}
          label={t.analytics.history.principalId}
          className="min-w-[12rem] flex-1"
        >
          <FieldInput
            id={fieldId}
            data-testid="audit-principal"
            value={principalInput}
            onChange={(event) => setPrincipalInput(event.target.value)}
          />
        </FormField>
        <Button type="submit" variant="outline" className="min-h-11 min-w-11">
          {t.common.search}
        </Button>
      </form>

      {appliedPrincipal !== null && (
        <div
          className="flex min-w-0 flex-col gap-2"
          data-testid="audit-lookup-result"
        >
          {lookup.isLoading && (
            <p role="status" className="text-muted-foreground text-sm">
              {t.analytics.common.loading}
            </p>
          )}
          {lookup.isError && (
            <p role="alert" className="text-destructive text-sm">
              {t.analytics.common.loadFailed}
            </p>
          )}
          {!lookup.isLoading && !lookup.isError && audits.length === 0 && (
            <p role="status" className="text-muted-foreground text-sm">
              {t.analytics.common.empty}
            </p>
          )}
          <ul className="flex min-w-0 flex-col gap-3">
            {audits.map((audit) => (
              <AuditRecordCard key={audit.id} audit={audit} />
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
