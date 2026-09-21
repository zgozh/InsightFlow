"""锁定 Phase 2B2 专用验收 Compose 的环境契约。

为什么需要这层契约测试：

- 真实数据库门禁的结论只在「确切的镜像版本」上成立。如果允许用环境变量切换 MySQL 版本，
  一次在 8.0 上的运行就会与 8.4 的验收证据无法区分，而 2B2 的验收基线明确是官方
  `mysql:8.4` Linux 镜像。所以镜像必须是字面量，且文件里不得存在版本开关。
- `--lower-case-table-names=0` 必须在服务器初始化时确定，与 Phase 2B1 的大小写敏感标识符
  语义配套；它一旦被删掉，应该在契约层立刻失败，而不是等真实数据库门禁给出错误结论。
- 端口绑定 `127.0.0.1` 与测试账号非管理员是这套栈只影响本机、且不会把权限问题掩盖成
  「通过」的前提。
- 端口覆盖 `ANALYTICS_MYSQL_PORT` 与镜像版本无关：它用来并行运行多套一次性栈，必须保留。

本测试只读文件，不启动 Docker、不拉取镜像、不访问网络。
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = REPO_ROOT / "docker" / "docker-compose.analytics-test.yml"

EXPECTED_MYSQL_IMAGE = "mysql:8.4"


def _compose() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def test_analytics_compose_is_readable_yaml():
    compose = _compose()

    assert isinstance(compose.get("services"), dict)
    assert "mysql" in compose["services"]
    assert "postgresql" in compose["services"]


def test_mysql_image_is_pinned_to_a_literal_version():
    """验收基线就是字面量 `mysql:8.4`：不接受 latest、8、8.0 或 digest 替代。"""

    assert _compose()["services"]["mysql"]["image"] == EXPECTED_MYSQL_IMAGE


def test_compose_text_does_not_allow_switching_the_mysql_version():
    """整个文件都不应出现版本切换开关，避免非默认取值产生无法区分的验收证据。"""

    text = COMPOSE_PATH.read_text(encoding="utf-8")

    assert "ANALYTICS_MYSQL_TAG" not in text


def test_mysql_port_is_published_on_loopback_only():
    ports = _compose()["services"]["mysql"]["ports"]

    assert ports
    published = [str(entry) for entry in ports]
    assert all(entry.startswith("127.0.0.1:") for entry in published), published


def test_mysql_port_remains_operator_overridable():
    """端口覆盖不是镜像版本漂移：它让多套一次性栈可以并行运行，必须保留。"""

    ports = [str(entry) for entry in _compose()["services"]["mysql"]["ports"]]

    assert any("ANALYTICS_MYSQL_PORT" in entry for entry in ports), ports


def test_mysql_is_initialized_case_sensitive():
    command = _compose()["services"]["mysql"]["command"]
    rendered = " ".join(str(part) for part in command) if isinstance(command, list) else str(command)

    assert "--lower-case-table-names=0" in rendered


def test_postgresql_port_is_published_on_loopback_only():
    ports = [str(entry) for entry in _compose()["services"]["postgresql"]["ports"]]

    assert ports
    assert all(entry.startswith("127.0.0.1:") for entry in ports), ports
