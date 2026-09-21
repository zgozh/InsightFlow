import ast
from pathlib import Path

from app.analytics.application import AccessPolicyCatalog, QueryPolicy, SchemaCatalog, SemanticQueryAuthorizer
from app.analytics.application.ports import DatasourceCatalog, MetricCatalog

ANALYTICS_ROOT = Path(__file__).parent.parent / "app" / "analytics"
DOMAIN_ALLOWED_ROOTS = {"__future__", "dataclasses", "enum", "re"}
APPLICATION_BANNED_PREFIXES = (
    "app.gateway",
    "deerflow",
    "fastapi",
    "langchain",
    "sqlalchemy",
    "sqlglot",
)


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
