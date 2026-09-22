"""Analytics Agent 的 startup-only 服务绑定（Phase 3 任务 2）。

Gateway 在 Analytics composition 成功后把**不可变**的 `AnalyticsServices` 绑定到这里，
shutdown 清除。这里刻意只保存一个引用：

- 不创建 engine/session/repository，不 dispose 共享资源（生命周期仍归 Harness）；
- 不缓存 principal——每次工具调用都从可信运行上下文重新取；
- 重复绑定不同对象是配置错误，必须稳定失败而不是静默替换掉另一个控制面。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - 仅类型检查；运行时不 import composition（避免拉入 infrastructure）
    from app.analytics.composition import AnalyticsServices

#: 未认证/遗留单用户模式的用户桶。它不是一个可信 principal。
UNTRUSTED_DEFAULT_USER_ID = "default"

_services: AnalyticsServices | None = None


class AnalyticsAgentBindingError(RuntimeError):
    """绑定状态非法。只携带稳定 reason。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def bind_analytics_services(services: AnalyticsServices | None) -> None:
    """绑定控制面。`None` 等价于"本进程不提供 Analytics"（不报错）。"""

    global _services
    if services is None:
        clear_analytics_services()
        return
    if _services is not None and _services is not services:
        raise AnalyticsAgentBindingError("analytics_agent_already_bound")
    _services = services


def clear_analytics_services() -> None:
    global _services
    _services = None


def get_bound_analytics_services() -> AnalyticsServices | None:
    return _services


def trusted_principal(runtime: object | None) -> str | None:
    """从可信运行上下文取 principal；取不到就返回 None（调用方必须 fail closed）。

    只接受 Gateway 的 `inject_authenticated_user_context` 写入的
    `runtime.context["user_id"]`（来源是认证过的 `request.state.user`）。刻意**不**回退到
    ambient ContextVar 或 `DEFAULT_USER_ID`：后者是未认证桶，把它当 principal 会让任何
    未认证路径落到一个字面量为 `default` 的账号上。
    """

    context = getattr(runtime, "context", None)
    if not isinstance(context, Mapping):
        return None
    value = context.get("user_id")
    if not isinstance(value, str):
        return None
    if not value or value != value.strip() or value == UNTRUSTED_DEFAULT_USER_ID:
        return None
    return value
