"""Analytics Agent 服务绑定与可信 principal 测试（Phase 3 任务 2）。

绑定是 startup-only 的进程级状态：Gateway 装配成功后写入，shutdown 清除。这里固定三件事：

- 未绑定、disabled/memory（绑定为 `None`）、无可信 principal 都必须稳定失败；
- 重复绑定**不同**对象是配置错误，必须报错而不是静默替换；
- principal 只来自 Gateway 注入的可信运行上下文，`DEFAULT_USER_ID` 这个未认证桶永远不是 principal。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.analytics.agent.runtime import (
    UNTRUSTED_DEFAULT_USER_ID,
    AnalyticsAgentBindingError,
    bind_analytics_services,
    clear_analytics_services,
    get_bound_analytics_services,
    trusted_principal,
)


@pytest.fixture(autouse=True)
def _clean_binding():
    clear_analytics_services()
    yield
    clear_analytics_services()


def _services(name: str = "services"):
    return SimpleNamespace(name=name)


# --- 绑定 -------------------------------------------------------------------


def test_an_unbound_process_has_no_services():
    assert get_bound_analytics_services() is None


def test_binding_exposes_the_exact_object():
    services = _services()

    bind_analytics_services(services)

    assert get_bound_analytics_services() is services


def test_binding_the_same_object_twice_is_idempotent():
    services = _services()

    bind_analytics_services(services)
    bind_analytics_services(services)

    assert get_bound_analytics_services() is services


def test_binding_a_different_object_while_bound_is_a_stable_failure():
    bind_analytics_services(_services("first"))

    with pytest.raises(AnalyticsAgentBindingError) as error:
        bind_analytics_services(_services("second"))

    assert error.value.reason == "analytics_agent_already_bound"
    assert get_bound_analytics_services().name == "first"


def test_clearing_releases_the_binding_and_allows_a_fresh_bind():
    bind_analytics_services(_services("first"))

    clear_analytics_services()
    assert get_bound_analytics_services() is None

    bind_analytics_services(_services("second"))
    assert get_bound_analytics_services().name == "second"


def test_binding_none_means_the_capability_is_unavailable():
    bind_analytics_services(_services("first"))

    bind_analytics_services(None)

    assert get_bound_analytics_services() is None


def test_clearing_an_unbound_process_is_a_no_op():
    clear_analytics_services()
    clear_analytics_services()

    assert get_bound_analytics_services() is None


# --- 可信 principal ---------------------------------------------------------


def _runtime(**context):
    return SimpleNamespace(context=context)


def test_a_gateway_injected_user_id_is_the_principal():
    assert trusted_principal(_runtime(user_id="user-1")) == "user-1"


@pytest.mark.parametrize(
    "runtime",
    [
        None,
        SimpleNamespace(),
        SimpleNamespace(context=None),
        SimpleNamespace(context={}),
        SimpleNamespace(context={"user_id": None}),
        SimpleNamespace(context={"user_id": 7}),
        SimpleNamespace(context={"user_id": ""}),
        SimpleNamespace(context={"user_id": "  "}),
        SimpleNamespace(context={"user_id": " user-1"}),
        SimpleNamespace(context={"user_id": "user-1 "}),
    ],
)
def test_a_missing_or_malformed_identity_is_not_a_principal(runtime):
    assert trusted_principal(runtime) is None


def test_the_unauthenticated_default_bucket_is_never_a_principal():
    # `DEFAULT_USER_ID` 是遗留单用户桶；把它当 principal 会让未认证路径落到某个真实账号上。
    assert trusted_principal(_runtime(user_id=UNTRUSTED_DEFAULT_USER_ID)) is None
    assert UNTRUSTED_DEFAULT_USER_ID == "default"


def test_the_principal_is_never_cached_between_calls():
    first = _runtime(user_id="user-1")
    second = _runtime(user_id="user-2")

    assert trusted_principal(first) == "user-1"
    assert trusted_principal(second) == "user-2"
    assert trusted_principal(_runtime(user_id="user-1")) == "user-1"


def test_importing_the_agent_package_pulls_in_no_infrastructure_framework():
    """绑定/证据/工具模块的真实 import 面：不 import SQLAlchemy、驱动、SQLGlot 或基础设施。

    这里用子进程实际 import 后检查 `sys.modules`，而不是扫源码文本——`TYPE_CHECKING` 下的类型
    注解 import 在运行时不会执行，文本扫描会误报，而真实 import 面才是要证明的东西。
    """

    import os
    import subprocess
    import sys
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    # sqlalchemy 会经 LangGraph/LangChain 的传递依赖出现在 sys.modules 里，那不是本模块的
    # import；这里断言的是"App bridge 没有拉入基础设施层、驱动或 SQLGlot"。
    probe = (
        "import sys;"
        "import app.analytics.agent.tools;"
        "import app.analytics.agent.runtime;"
        "import app.analytics.agent.evidence;"
        "roots={'asyncpg','asyncmy','sqlglot'};"
        "print(sorted({m.split('.')[0] for m in sys.modules} & roots),"
        "any(m.startswith('app.analytics.infrastructure') for m in sys.modules))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(backend),
        env={**os.environ, "PYTHONPATH": "."},
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "[] False", f"agent modules pulled in infrastructure/driver/SQLGlot: {completed.stdout.strip()}"


def test_the_agent_modules_never_import_the_infrastructure_layer_in_source():
    import ast
    from pathlib import Path

    banned = {"sqlalchemy", "asyncpg", "asyncmy", "sqlglot"}
    violations: list[str] = []
    for path in sorted((Path(__file__).resolve().parents[1] / "app/analytics/agent").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            else:
                continue
            for module in modules:
                if module.split(".")[0] in banned or module.startswith("app.analytics.infrastructure"):
                    violations.append(f"{path.name}: {module}")

    assert not violations, violations


def test_the_runtime_module_keeps_composition_as_a_type_only_import():
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "app/analytics/agent/runtime.py").read_text(encoding="utf-8")
    text = source
    tree = ast.parse(source)

    # composition 只在 TYPE_CHECKING 分支里被 import：运行时不执行，也就不会拉入 infrastructure。
    guarded: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and getattr(node.test, "id", None) == "TYPE_CHECKING":
            for inner in ast.walk(node):
                if isinstance(inner, ast.ImportFrom) and inner.module:
                    guarded.append(inner.module)
    assert "app.analytics.composition" in guarded, "composition must be imported only under TYPE_CHECKING"
    assert "if TYPE_CHECKING" in text
