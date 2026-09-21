"""Phase 2B2 真实数据库门禁：启动一次性 Docker 栈、注入测试凭证、跑集成测试、无论成败都销毁栈。

为什么这样编排：

- 真实数据库行为（只读事务、服务端超时、取消后无残留查询、流式配额）无法用 mock 证明，所以这条门禁
  必须跑真容器；但它又绝不能变成普通单元测试的前提，因此只由本脚本显式启动。
- 凭证只以环境变量注入子进程：不写凭证文件、不进命令行参数（命令行会出现在进程列表里），
  被测连接使用 compose 里创建的普通用户与只读业务用户，不是超级用户。
- 数据目录是 tmpfs，`compose down --volumes` 之后既没有容器也没有需要清理的具名卷。
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
COMPOSE_FILE = REPO_ROOT / "docker" / "docker-compose.analytics-test.yml"

DEFAULT_POSTGRESQL_PORT = 55432
DEFAULT_MYSQL_PORT = 53306
_LOG_TAIL_LINES = 200
_HEALTH_TIMEOUT_SECONDS = 300

# 每个引擎对应的服务名、测试文件、门禁环境变量与两个账号。
# postgresql 额外跑 Phase 2C1 的持久化控制面测试：它在独立临时 schema 里运行，schema 生命周期
# 由初始化超级用户完成，被测连接仍是普通用户 analytics_tester。
ENGINES = {
    "postgresql": {
        "service": "postgresql",
        "test_files": (
            "tests/test_analytics_postgresql_integration.py",
            "tests/test_analytics_persistence_postgresql.py",
        ),
        "gate_env": "ANALYTICS_TEST_POSTGRESQL",
        "port_env": "ANALYTICS_PG_PORT",
        "port_default": DEFAULT_POSTGRESQL_PORT,
        "database": "analytics_test",
        "credential_env": "ANALYTICS_TEST_PG_CREDENTIAL",
        "readonly_env": "ANALYTICS_TEST_PG_READONLY_CREDENTIAL",
        "admin_credential_env": "ANALYTICS_TEST_PG_ADMIN_CREDENTIAL",
        "tester": ("analytics_tester", "analytics_tester_pw"),
        "reader": ("analytics_reader", "analytics_reader_pw"),
        "admin": ("analytics_admin", "analytics_admin_pw"),
    },
    "mysql": {
        "service": "mysql",
        "test_files": ("tests/test_analytics_mysql_integration.py",),
        "gate_env": "ANALYTICS_TEST_MYSQL",
        "port_env": "ANALYTICS_MYSQL_PORT",
        "port_default": DEFAULT_MYSQL_PORT,
        "database": "analytics_test",
        "credential_env": "ANALYTICS_TEST_MYSQL_CREDENTIAL",
        "readonly_env": "ANALYTICS_TEST_MYSQL_READONLY_CREDENTIAL",
        "tester": ("analytics_tester", "analytics_tester_pw"),
        "reader": ("analytics_reader", "analytics_reader_pw"),
    },
}


def _run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=False, **kwargs)


def _capture(command: list[str]) -> subprocess.CompletedProcess:
    """捕获输出时固定 UTF-8：Windows 默认用本地代码页，容器日志里的多字节字符会让读取线程直接崩掉。"""

    return _run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")


def _compose(*arguments: str, **kwargs) -> subprocess.CompletedProcess:
    return _run(["docker", "compose", "-f", str(COMPOSE_FILE), *arguments], **kwargs)


def _compose_capture(*arguments: str) -> subprocess.CompletedProcess:
    return _capture(["docker", "compose", "-f", str(COMPOSE_FILE), *arguments])


def _require_docker() -> None:
    """先确认 Docker 与 Compose 真的可用：不可用时明确失败，而不是让集成测试静默跳过。"""

    if not COMPOSE_FILE.exists():
        raise SystemExit(f"compose file not found: {COMPOSE_FILE}")
    probe = _capture(["docker", "version", "--format", "{{.Server.Version}}"])
    if probe.returncode != 0:
        raise SystemExit(f"docker engine unavailable (exit {probe.returncode}): {(probe.stderr or '').strip()}")
    compose = _capture(["docker", "compose", "version"])
    if compose.returncode != 0:
        raise SystemExit(f"docker compose unavailable (exit {compose.returncode}): {(compose.stderr or '').strip()}")
    print(f"[gate] docker engine {(probe.stdout or '').strip()} / {(compose.stdout or '').strip()}")


def _credential_payload(engine: str, port: int, database: str, account: tuple[str, str]) -> str:
    """构造 resolver 需要的受限 JSON；host 固定 loopback，因此允许 tls_mode=disable。"""

    username, password = account
    return json.dumps(
        {
            "engine": engine,
            "host": "127.0.0.1",
            "port": port,
            "database": database,
            "username": username,
            "password": password,
            "tls_mode": "disable",
        }
    )


def _test_environment(engines: list[str]) -> dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = "."
    environment["UV_DEFAULT_INDEX"] = "https://pypi.org/simple"
    for name in engines:
        configuration = ENGINES[name]
        port = int(environment.get(configuration["port_env"], configuration["port_default"]))
        environment[configuration["gate_env"]] = "1"
        environment[configuration["credential_env"]] = _credential_payload(name, port, configuration["database"], configuration["tester"])
        environment[configuration["readonly_env"]] = _credential_payload(name, port, configuration["database"], configuration["reader"])
        # 持久化控制面测试需要建/删自己的临时 schema；管理员凭证只用于 schema 生命周期，
        # 被测连接仍然只用上面那两个非管理员账号。
        if "admin_credential_env" in configuration:
            environment[configuration["admin_credential_env"]] = _credential_payload(name, port, configuration["database"], configuration["admin"])
    return environment


def _report_failure(engines: list[str]) -> None:
    """失败时输出 compose ps 与有限尾部日志：完整日志可能包含整库输出，不能无界打印。"""

    print("\n[gate] docker compose ps", file=sys.stderr)
    status = _compose_capture("ps")
    print(status.stdout or "", file=sys.stderr)

    for name in engines:
        service = ENGINES[name]["service"]
        print(f"\n[gate] last {_LOG_TAIL_LINES} log lines of {service}", file=sys.stderr)
        logs = _compose_capture("logs", "--no-color", "--tail", str(_LOG_TAIL_LINES), service)
        print(logs.stdout or "", file=sys.stderr)
        print(logs.stderr or "", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="InsightFlow Phase 2B2 real-database gate")
    parser.add_argument("--engine", choices=["postgresql", "mysql", "all"], default="all")
    options = parser.parse_args(argv)
    engines = ["postgresql", "mysql"] if options.engine == "all" else [options.engine]

    _require_docker()

    services = [ENGINES[name]["service"] for name in engines]
    print(f"[gate] starting services: {' '.join(services)}")
    try:
        started = _compose("up", "-d", "--wait", "--wait-timeout", str(_HEALTH_TIMEOUT_SECONDS), *services)
        if started.returncode != 0:
            print(f"[gate] compose up failed with exit {started.returncode}", file=sys.stderr)
            _report_failure(engines)
            return started.returncode

        status = _compose_capture("ps", "--format", "json")
        print(f"[gate] health:\n{(status.stdout or '').strip()}")

        test_files = [path for name in engines for path in ENGINES[name]["test_files"]]
        command = ["uv", "run", "--locked", "pytest", *test_files, "-q"]
        print(f"[gate] running: {' '.join(command)} (cwd={BACKEND_DIR})")
        result = _run(command, cwd=str(BACKEND_DIR), env=_test_environment(engines))
        if result.returncode != 0:
            print(f"[gate] integration tests failed with exit {result.returncode}", file=sys.stderr)
            _report_failure(engines)
        else:
            print("[gate] integration tests passed")
        return result.returncode
    finally:
        # 无论成功、失败还是异常都必须销毁栈：容器与 tmpfs 数据都不能留在机器上。
        print("[gate] tearing down the disposable stack")
        _compose("down", "--volumes", "--remove-orphans", "--timeout", "20")


if __name__ == "__main__":
    raise SystemExit(main())
