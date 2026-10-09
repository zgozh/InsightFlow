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
DOMAIN_ALLOWED_ROOTS = {"__future__", "dataclasses", "datetime", "decimal", "enum", "hashlib", "json", "math", "re"}
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


# --- Phase 2C2：composition 与 API 的边界 -----------------------------------


def test_the_composition_root_does_not_import_gateway_or_harness():
    """composition 只接收注入的 engine/session factory，不认识 Gateway，也不 import Harness。"""

    banned = ("app.gateway", "deerflow", "fastapi", "langchain")
    violations: list[str] = []
    for path in sorted(ANALYTICS_ROOT.glob("*.py")):
        for line, module in _imports(path):
            if any(module == prefix or module.startswith(f"{prefix}.") for prefix in banned):
                violations.append(f"{path.relative_to(ANALYTICS_ROOT)}:{line} imports {module}")
    assert not violations, "Analytics composition dependency violations:\n" + "\n".join(violations)


def test_the_api_layer_never_reaches_sqlalchemy_or_the_business_gateway():
    """HTTP 层只能调用应用服务：不得直接持有 SQLAlchemy、repository 或业务数据库 gateway。"""

    banned = ("sqlalchemy", "asyncpg", "asyncmy", "sqlglot")
    violations: list[str] = []
    api = ANALYTICS_ROOT / "api"
    for path in sorted(api.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for name in banned:
            if name in text:
                violations.append(f"{path.relative_to(ANALYTICS_ROOT)} mentions {name}")
        for line, module in _imports(path):
            if module.startswith("app.analytics.infrastructure"):
                violations.append(f"{path.relative_to(ANALYTICS_ROOT)}:{line} imports {module}")
    assert not violations, "Analytics API dependency violations:\n" + "\n".join(violations)


def test_the_api_layer_uses_the_shared_gateway_auth_helpers():
    """认证主体必须来自现有 Gateway 认证上下文，不能另建身份来源。"""

    router = (ANALYTICS_ROOT / "api" / "router.py").read_text(encoding="utf-8")

    assert "get_current_user" in router
    assert "require_admin_user" in router
    # 应用服务只从 app.state 取，未装配时 503。
    assert '"analytics_services"' in router
    assert "503" in router


def test_the_harness_never_imports_the_analytics_package():
    harness_root = Path(__file__).parent.parent / "packages" / "harness" / "deerflow"
    violations: list[str] = []
    for path in sorted(harness_root.rglob("*.py")):
        for line, module in _imports(path):
            if module == "app" or module.startswith("app."):
                violations.append(f"{path.relative_to(harness_root)}:{line} imports {module}")
    assert not violations, "Harness must never import App code:\n" + "\n".join(violations)


def test_the_api_package_is_importable_without_the_gateway_app():
    """API 包只依赖 gateway 的认证助手，不依赖 `create_app()` 或 lifespan。"""

    api_init = (ANALYTICS_ROOT / "api" / "__init__.py").read_text(encoding="utf-8")

    assert "install_request_error_handler" in api_init
    assert "app.gateway.app" not in api_init
