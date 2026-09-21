import ast
from pathlib import Path

from app.analytics.application import AccessPolicyCatalog, QueryPolicy, SchemaCatalog, SemanticQueryAuthorizer
from app.analytics.application.execution_ports import (
    Clock,
    DatasourceQueryGateway,
    ExecutionPlanStore,
    PlanTokenIssuer,
)
from app.analytics.application.ports import DatasourceCatalog, MetricCatalog

ANALYTICS_ROOT = Path(__file__).parent.parent / "app" / "analytics"
DOMAIN_ALLOWED_ROOTS = {"__future__", "dataclasses", "datetime", "decimal", "enum", "math", "re"}
APPLICATION_BANNED_PREFIXES = (
    "app.gateway",
    "deerflow",
    "fastapi",
    "langchain",
    "sqlalchemy",
    "asyncpg",
    "asyncmy",
    "sqlglot",
)
DATABASE_DRIVER_NAMES = ("sqlalchemy", "asyncpg", "asyncmy")


def _imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append((node.lineno, node.module))
    return imports


def test_analytics_domain_uses_only_the_standard_library():
    violations: list[str] = []
    for path in sorted((ANALYTICS_ROOT / "domain").rglob("*.py")):
        for line, module in _imports(path):
            if module.startswith("app.analytics.domain"):
                continue
            if module.split(".", 1)[0] not in DOMAIN_ALLOWED_ROOTS:
                violations.append(f"{path.relative_to(ANALYTICS_ROOT)}:{line} imports {module}")
    assert not violations, "Analytics domain dependency violations:\n" + "\n".join(violations)


def test_analytics_application_does_not_depend_on_delivery_or_runtime_layers():
    violations: list[str] = []
    for path in sorted((ANALYTICS_ROOT / "application").rglob("*.py")):
        for line, module in _imports(path):
            if any(module == prefix or module.startswith(f"{prefix}.") for prefix in APPLICATION_BANNED_PREFIXES):
                violations.append(f"{path.relative_to(ANALYTICS_ROOT)}:{line} imports {module}")
    assert not violations, "Analytics application dependency violations:\n" + "\n".join(violations)


def test_catalog_ports_are_runtime_checkable_protocols():
    assert getattr(DatasourceCatalog, "_is_runtime_protocol", False)
    assert getattr(MetricCatalog, "_is_runtime_protocol", False)


def test_query_policy_port_is_a_runtime_checkable_protocol():
    assert getattr(QueryPolicy, "_is_runtime_protocol", False)


def test_authorization_ports_are_runtime_checkable_protocols():
    assert getattr(SchemaCatalog, "_is_runtime_protocol", False)
    assert getattr(AccessPolicyCatalog, "_is_runtime_protocol", False)
    assert getattr(SemanticQueryAuthorizer, "_is_runtime_protocol", False)


def test_execution_ports_are_runtime_checkable_protocols():
    assert getattr(DatasourceQueryGateway, "_is_runtime_protocol", False)
    assert getattr(ExecutionPlanStore, "_is_runtime_protocol", False)
    assert getattr(Clock, "_is_runtime_protocol", False)
    assert getattr(PlanTokenIssuer, "_is_runtime_protocol", False)


def test_database_drivers_never_appear_in_domain_or_application_sources():
    # 原始文本扫描：AST 检查只能发现静态 import，字符串扫描还能拦住动态导入与手写方言分支。
    violations: list[str] = []
    for layer in ("domain", "application"):
        for path in sorted((ANALYTICS_ROOT / layer).rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for name in DATABASE_DRIVER_NAMES:
                if name in text:
                    violations.append(f"{path.relative_to(ANALYTICS_ROOT)} mentions {name}")
    assert not violations, "Database driver leakage outside infrastructure:\n" + "\n".join(violations)


def test_infrastructure_actually_imports_the_database_drivers():
    # 反向断言：避免上面的禁令因为路径写错而变成永远通过的空测试。
    gateway = (ANALYTICS_ROOT / "infrastructure" / "database_runtime.py").read_text(encoding="utf-8")
    assert "sqlalchemy" in gateway


def test_analytics_infrastructure_does_not_depend_on_delivery_or_harness():
    banned = ("app.gateway", "deerflow", "fastapi", "langchain")
    violations: list[str] = []
    infrastructure = ANALYTICS_ROOT / "infrastructure"
    if infrastructure.exists():
        for path in sorted(infrastructure.rglob("*.py")):
            for line, module in _imports(path):
                if any(module == prefix or module.startswith(f"{prefix}.") for prefix in banned):
                    violations.append(f"{path.relative_to(ANALYTICS_ROOT)}:{line} imports {module}")
    assert not violations, "Analytics infrastructure dependency violations:\n" + "\n".join(violations)
