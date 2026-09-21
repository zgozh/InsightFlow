"""显式、版本化的 JSON codec（Phase 2C1）。

设计取舍：

- **不用 pickle、不用动态 import、不用 `dataclasses.asdict()` 直落**：这些做法会把
  "未知类型就 `str()`" 变成隐式协议，且无法在不改变数据库内容的前提下演进。
- 每个 codec 都手写字段集合，并用**精确 key 集合比较**校验：多一个字段、少一个字段都拒绝。
- 数值与时间有唯一规范形式：`Decimal` 用非指数 canonical 字符串，`datetime` 用带时区
  ISO 8601 并在解码后统一为 UTC，`tuple` 编码为 list、解码后恢复 tuple。
- 解码**必须重新构造 domain dataclass**，让既有 `__post_init__` 不变量再执行一遍；
  损坏 payload 只会得到 `PersistenceDataError`，绝不返回部分值，也绝不回显 payload。

这里保存的 plan payload 是 Phase 2A 重新序列化后的 canonical SQL 加上当次授权快照，
最多存活 300 秒并在 claim 时立即删除——它不得被复制进日志、异常、receipt 或审计。
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from app.analytics.application import PersistenceDataError, StoredExecutionPlan
from app.analytics.domain import (
    AuthorizedQuerySpec,
    ColumnAccess,
    ColumnAccessRule,
    ColumnSchema,
    ColumnSensitivity,
    DatasourceDefinition,
    DatasourceEngine,
    DatasourceStatus,
    ExecutionLimits,
    PreparedQuery,
    PrincipalAccessPolicy,
    QueryCostEstimate,
    QueryRisk,
    RelationAccessRule,
    RelationSchema,
    SchemaSnapshot,
)

PLAN_PAYLOAD_VERSION = 1
MAX_PLAN_PAYLOAD_BYTES = 1024 * 1024

# canonical decimal：可选负号 + 非指数十进制。`1E+2` / `NaN` / `Infinity` 都不是规范形式。
_CANONICAL_DECIMAL = re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$")

_SNAPSHOT_KEYS = ("datasource_id", "engine", "version", "default_schema", "relations")
_RELATION_KEYS = ("catalog", "schema", "name", "columns")
_COLUMN_KEYS = ("name", "data_type", "sensitivity")
_POLICY_KEYS = ("datasource_id", "principal_id", "version", "relations", "allowed_functions")
_POLICY_RELATION_KEYS = ("catalog", "schema", "name", "columns")
_POLICY_COLUMN_KEYS = ("name", "access")
_PLAN_KEYS = ("token_digest", "principal_id", "datasource", "authorized", "estimate", "limits", "issued_at", "expires_at")
_DATASOURCE_KEYS = ("id", "owner_id", "name", "engine", "secret_ref", "default_schema", "status")
_AUTHORIZED_KEYS = ("prepared", "datasource_id", "principal_id", "schema_version", "policy_version", "relations", "columns", "functions", "risk")
_PREPARED_KEYS = ("sql", "engine", "relations", "row_limit", "query_hash")
_ESTIMATE_KEYS = ("engine", "estimated_rows", "engine_cost", "plan_digest")
_LIMITS_KEYS = (
    "connect_timeout_ms",
    "statement_timeout_ms",
    "cancellation_grace_ms",
    "max_estimated_rows",
    "max_engine_cost",
    "max_explain_bytes",
    "max_result_columns",
    "max_result_rows",
    "max_result_bytes",
    "plan_ttl_seconds",
)


def _fail(reason: str) -> PersistenceDataError:
    """稳定 reason 一律是单 token：它会被写进日志字段，不能含空白或 payload 片段。"""

    return PersistenceDataError(reason)


def _dump(value: object) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)
    if len(text.encode("utf-8")) > MAX_PLAN_PAYLOAD_BYTES:
        raise _fail("payload_too_large")
    return text


def _load(payload: object) -> object:
    if not isinstance(payload, str):
        raise _fail("payload_not_a_string")
    if len(payload.encode("utf-8")) > MAX_PLAN_PAYLOAD_BYTES:
        raise _fail("payload_too_large")
    try:
        return json.loads(payload)
    except ValueError as error:
        raise _fail("payload_not_valid_json") from error


def _mapping(value: object, keys: tuple[str, ...]) -> dict:
    if not isinstance(value, dict):
        raise _fail("payload_not_an_object")
    if set(value) != set(keys):
        raise _fail("payload_unexpected_keys")
    return value


def _sequence(value: object) -> list:
    if not isinstance(value, list):
        raise _fail("payload_not_a_list")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise _fail("payload_invalid_text")
    return value


def _integer(value: object) -> int:
    # bool 是 int 的子类；放行它会让 `true` 变成一个合法的计数。
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail("payload_invalid_integer")
    return value


def _boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise _fail("payload_invalid_bool")
    return value


def _enum(enum_type, value: object):
    if not isinstance(value, str):
        raise _fail("payload_invalid_enum")
    try:
        return enum_type(value)
    except ValueError as error:
        raise _fail("payload_invalid_enum") from error


def _temporal(value: object) -> datetime:
    if not isinstance(value, str):
        raise _fail("payload_invalid_datetime")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise _fail("payload_invalid_datetime") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        # naive 时间无法判断真实时刻，必须拒绝而不是假定本地时区。
        raise _fail("payload_invalid_datetime")
    return parsed.astimezone(UTC)


def _render_temporal(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _decimal(value: object) -> Decimal:
    if not isinstance(value, str) or _CANONICAL_DECIMAL.fullmatch(value) is None:
        raise _fail("payload_invalid_decimal")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise _fail("payload_invalid_decimal") from error
    if not parsed.is_finite() or format(parsed, "f") != value:
        raise _fail("payload_invalid_decimal")
    return parsed


def _render_decimal(value: Decimal) -> str:
    return format(value, "f")


def _relation_key(catalog: str | None, schema: str, name: str) -> str:
    return ".".join(part for part in (catalog, schema, name) if part)


def _reconstruct(factory, **values: object):
    """重建 domain dataclass，让既有 `__post_init__` 不变量再跑一遍。"""

    try:
        return factory(**values)
    except (ValueError, TypeError) as error:
        raise _fail("payload_domain_invariant") from error


# --- schema snapshot --------------------------------------------------------


def _render_column(column: ColumnSchema) -> dict:
    return {"name": column.name, "data_type": column.data_type, "sensitivity": column.sensitivity.value}


def _parse_column(value: object) -> ColumnSchema:
    item = _mapping(value, _COLUMN_KEYS)
    return _reconstruct(
        ColumnSchema,
        name=_text(item["name"]),
        data_type=_text(item["data_type"]),
        sensitivity=_enum(ColumnSensitivity, item["sensitivity"]),
    )


def _render_relation(relation: RelationSchema) -> dict:
    return {
        "catalog": relation.catalog,
        "schema": relation.schema,
        "name": relation.name,
        "columns": [_render_column(column) for column in relation.columns],
    }


def _parse_relations(value: object, *, keys: tuple[str, ...], parse_column) -> tuple:
    entries = _sequence(value)
    seen: set[str] = set()
    relations = []
    for entry in entries:
        item = _mapping(entry, keys)
        catalog = item["catalog"]
        if catalog is not None:
            catalog = _text(catalog)
        schema = _text(item["schema"])
        name = _text(item["name"])
        key = _relation_key(catalog, schema, name)
        if key in seen:
            raise _fail("payload_duplicate_relation")
        seen.add(key)
        columns_raw = _sequence(item["columns"])
        column_names: set[str] = set()
        columns = []
        for column_raw in columns_raw:
            column = parse_column(column_raw)
            if column.name in column_names:
                raise _fail("payload_duplicate_column")
            column_names.add(column.name)
            columns.append(column)
        relations.append((catalog, schema, name, tuple(columns)))
    return tuple(relations)


def encode_schema_snapshot(value: SchemaSnapshot) -> str:
    return _dump(
        {
            "datasource_id": value.datasource_id,
            "engine": value.engine.value,
            "version": value.version,
            "default_schema": value.default_schema,
            "relations": [_render_relation(relation) for relation in value.relations],
        }
    )


def decode_schema_snapshot(payload: str) -> SchemaSnapshot:
    item = _mapping(_load(payload), _SNAPSHOT_KEYS)
    relations = _parse_relations(item["relations"], keys=_RELATION_KEYS, parse_column=_parse_column)
    return _reconstruct(
        SchemaSnapshot,
        datasource_id=_text(item["datasource_id"]),
        engine=_enum(DatasourceEngine, item["engine"]),
        version=_text(item["version"]),
        default_schema=_text(item["default_schema"]),
        relations=tuple(_reconstruct(RelationSchema, catalog=catalog, schema=schema, name=name, columns=columns) for catalog, schema, name, columns in relations),
    )


# --- access policy ----------------------------------------------------------


def _render_access_column(rule: ColumnAccessRule) -> dict:
    return {"name": rule.name, "access": rule.access.value}


def _parse_access_column(value: object) -> ColumnAccessRule:
    item = _mapping(value, _POLICY_COLUMN_KEYS)
    return _reconstruct(ColumnAccessRule, name=_text(item["name"]), access=_enum(ColumnAccess, item["access"]))


def encode_access_policy(value: PrincipalAccessPolicy) -> str:
    return _dump(
        {
            "datasource_id": value.datasource_id,
            "principal_id": value.principal_id,
            "version": value.version,
            "relations": [
                {
                    "catalog": relation.catalog,
                    "schema": relation.schema,
                    "name": relation.name,
                    "columns": [_render_access_column(column) for column in relation.columns],
                }
                for relation in value.relations
            ],
            "allowed_functions": list(value.allowed_functions),
        }
    )


def decode_access_policy(payload: str) -> PrincipalAccessPolicy:
    item = _mapping(_load(payload), _POLICY_KEYS)
    relations = _parse_relations(item["relations"], keys=_POLICY_RELATION_KEYS, parse_column=_parse_access_column)
    functions = [_text(entry) for entry in _sequence(item["allowed_functions"])]
    return _reconstruct(
        PrincipalAccessPolicy,
        datasource_id=_text(item["datasource_id"]),
        principal_id=_text(item["principal_id"]),
        version=_text(item["version"]),
        relations=tuple(_reconstruct(RelationAccessRule, catalog=catalog, schema=schema, name=name, columns=columns) for catalog, schema, name, columns in relations),
        allowed_functions=tuple(functions),
    )


# --- metric dimensions ------------------------------------------------------


def encode_dimensions(value: tuple[str, ...]) -> str:
    return _dump(list(value))


def decode_dimensions(payload: str) -> tuple[str, ...]:
    entries = [_text(entry) for entry in _sequence(_load(payload))]
    if len(set(entries)) != len(entries):
        raise _fail("payload_duplicate_dimension")
    return tuple(entries)


# --- stored execution plan --------------------------------------------------


def _render_datasource(value: DatasourceDefinition) -> dict:
    return {
        "id": value.id,
        "owner_id": value.owner_id,
        "name": value.name,
        "engine": value.engine.value,
        # 只保存 opaque reference；解析后的用户名、口令与 DSN 绝不入 payload。
        "secret_ref": value.secret_ref,
        "default_schema": value.default_schema,
        "status": value.status.value,
    }


def _parse_datasource(value: object) -> DatasourceDefinition:
    item = _mapping(value, _DATASOURCE_KEYS)
    default_schema = item["default_schema"]
    if default_schema is not None:
        default_schema = _text(default_schema)
    return _reconstruct(
        DatasourceDefinition,
        id=_text(item["id"]),
        owner_id=_text(item["owner_id"]),
        name=_text(item["name"]),
        engine=_enum(DatasourceEngine, item["engine"]),
        secret_ref=_text(item["secret_ref"]),
        default_schema=default_schema,
        status=_enum(DatasourceStatus, item["status"]),
    )


def _render_limits(value: ExecutionLimits) -> dict:
    return {
        "connect_timeout_ms": value.connect_timeout_ms,
        "statement_timeout_ms": value.statement_timeout_ms,
        "cancellation_grace_ms": value.cancellation_grace_ms,
        "max_estimated_rows": value.max_estimated_rows,
        "max_engine_cost": _render_decimal(value.max_engine_cost),
        "max_explain_bytes": value.max_explain_bytes,
        "max_result_columns": value.max_result_columns,
        "max_result_rows": value.max_result_rows,
        "max_result_bytes": value.max_result_bytes,
        "plan_ttl_seconds": value.plan_ttl_seconds,
    }


def _parse_limits(value: object) -> ExecutionLimits:
    item = _mapping(value, _LIMITS_KEYS)
    return _reconstruct(
        ExecutionLimits,
        connect_timeout_ms=_integer(item["connect_timeout_ms"]),
        statement_timeout_ms=_integer(item["statement_timeout_ms"]),
        cancellation_grace_ms=_integer(item["cancellation_grace_ms"]),
        max_estimated_rows=_integer(item["max_estimated_rows"]),
        max_engine_cost=_decimal(item["max_engine_cost"]),
        max_explain_bytes=_integer(item["max_explain_bytes"]),
        max_result_columns=_integer(item["max_result_columns"]),
        max_result_rows=_integer(item["max_result_rows"]),
        max_result_bytes=_integer(item["max_result_bytes"]),
        plan_ttl_seconds=_integer(item["plan_ttl_seconds"]),
    )


def _render_estimate(value: QueryCostEstimate) -> dict:
    return {
        "engine": value.engine.value,
        "estimated_rows": value.estimated_rows,
        "engine_cost": _render_decimal(value.engine_cost),
        "plan_digest": value.plan_digest,
    }


def _parse_estimate(value: object) -> QueryCostEstimate:
    item = _mapping(value, _ESTIMATE_KEYS)
    return _reconstruct(
        QueryCostEstimate,
        engine=_enum(DatasourceEngine, item["engine"]),
        estimated_rows=_integer(item["estimated_rows"]),
        engine_cost=_decimal(item["engine_cost"]),
        plan_digest=_text(item["plan_digest"]),
    )


def _render_prepared(value: PreparedQuery) -> dict:
    return {
        "sql": value.sql,
        "engine": value.engine.value,
        "relations": list(value.relations),
        "row_limit": value.row_limit,
        "query_hash": value.query_hash,
    }


def _parse_prepared(value: object) -> PreparedQuery:
    item = _mapping(value, _PREPARED_KEYS)
    return _reconstruct(
        PreparedQuery,
        sql=_text(item["sql"]),
        engine=_enum(DatasourceEngine, item["engine"]),
        relations=tuple(_text(entry) for entry in _sequence(item["relations"])),
        row_limit=_integer(item["row_limit"]),
        query_hash=_text(item["query_hash"]),
    )


def _render_authorized(value: AuthorizedQuerySpec) -> dict:
    return {
        "prepared": _render_prepared(value.prepared),
        "datasource_id": value.datasource_id,
        "principal_id": value.principal_id,
        "schema_version": value.schema_version,
        "policy_version": value.policy_version,
        "relations": list(value.relations),
        "columns": list(value.columns),
        "functions": list(value.functions),
        "risk": value.risk.value,
    }


def _parse_authorized(value: object) -> AuthorizedQuerySpec:
    item = _mapping(value, _AUTHORIZED_KEYS)
    return _reconstruct(
        AuthorizedQuerySpec,
        prepared=_parse_prepared(item["prepared"]),
        datasource_id=_text(item["datasource_id"]),
        principal_id=_text(item["principal_id"]),
        schema_version=_text(item["schema_version"]),
        policy_version=_text(item["policy_version"]),
        relations=tuple(_text(entry) for entry in _sequence(item["relations"])),
        columns=tuple(_text(entry) for entry in _sequence(item["columns"])),
        functions=tuple(_text(entry) for entry in _sequence(item["functions"])),
        risk=_enum(QueryRisk, item["risk"]),
    )


def encode_stored_plan(value: StoredExecutionPlan) -> str:
    return _dump(
        {
            "token_digest": value.token_digest,
            "principal_id": value.principal_id,
            "datasource": _render_datasource(value.datasource),
            "authorized": _render_authorized(value.authorized),
            "estimate": _render_estimate(value.estimate),
            "limits": _render_limits(value.limits),
            "issued_at": _render_temporal(value.issued_at),
            "expires_at": _render_temporal(value.expires_at),
        }
    )


def decode_stored_plan(payload: str, *, payload_version: int) -> StoredExecutionPlan:
    if payload_version != PLAN_PAYLOAD_VERSION:
        # 未知版本必须 fail closed：它可能是更新版本写的、语义不同的 payload。
        raise _fail("unknown_payload_version")
    item = _mapping(_load(payload), _PLAN_KEYS)
    return _reconstruct(
        StoredExecutionPlan,
        token_digest=_text(item["token_digest"]),
        principal_id=_text(item["principal_id"]),
        datasource=_parse_datasource(item["datasource"]),
        authorized=_parse_authorized(item["authorized"]),
        estimate=_parse_estimate(item["estimate"]),
        limits=_parse_limits(item["limits"]),
        issued_at=_temporal(item["issued_at"]),
        expires_at=_temporal(item["expires_at"]),
    )
