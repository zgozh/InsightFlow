"""Phase 2B2 真实数据库门禁：启动一次性 Docker 栈、注入测试凭证、跑集成测试、无论成败都销毁栈。

为什么这样编排：

- 真实数据库行为（只读事务、服务端超时、取消后无残留查询、流式配额）无法用 mock 证明，所以这条门禁
  必须跑真容器；但它又绝不能变成普通单元测试的前提，因此只由本脚本显式启动。
- 凭证只以环境变量注入子进程：不写凭证文件、不进命令行参数（命令行会出现在进程列表里），
  被测连接使用 compose 里创建的普通用户与只读业务用户，不是超级用户。
- 数据目录是 tmpfs，`compose down` 之后既没有容器也没有需要清理的具名卷。
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
COMPOSE_FILE = REPO_ROOT / "docker" / "docker-compose.analytics-test.yml"
COMPOSE_PROJECT = "insightflow-analytics-test"
_COMPOSE_ENV_FILE: Path | None = None

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
        "demo_readonly_env": "ANALYTICS_TEST_PG_DEMO_READONLY_CREDENTIAL",
        "observer_credential_env": "ANALYTICS_TEST_PG_OBSERVER_CREDENTIAL",
        "admin_credential_env": "ANALYTICS_TEST_PG_ADMIN_CREDENTIAL",
        "tester": ("analytics_tester", "analytics_tester_pw"),
        "reader": ("analytics_reader", "analytics_reader_pw"),
        "demo_reader": ("analytics_demo_reader", "analytics_demo_reader_pw"),
        "observer": ("analytics_demo_observer", "analytics_demo_observer_pw"),
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


def _compose_command(*arguments: str, env_file: Path) -> list[str]:
    return ["docker", "compose", "-p", COMPOSE_PROJECT, "--env-file", str(env_file), "-f", str(COMPOSE_FILE), *arguments]


def _compose(*arguments: str, **kwargs) -> subprocess.CompletedProcess:
    if _COMPOSE_ENV_FILE is None:
        raise RuntimeError("compose_env_file_not_initialized")
    return _run(_compose_command(*arguments, env_file=_COMPOSE_ENV_FILE), **kwargs)


def _compose_capture(*arguments: str) -> subprocess.CompletedProcess:
    if _COMPOSE_ENV_FILE is None:
        raise RuntimeError("compose_env_file_not_initialized")
    return _capture(_compose_command(*arguments, env_file=_COMPOSE_ENV_FILE))


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
        if "demo_readonly_env" in configuration:
            environment[configuration["demo_readonly_env"]] = _credential_payload(name, port, configuration["database"], configuration["demo_reader"])
        if "observer_credential_env" in configuration:
            environment[configuration["observer_credential_env"]] = _credential_payload(name, port, configuration["database"], configuration["observer"])
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


def _project_inventory() -> dict[str, list[str]]:
    label = f"label=com.docker.compose.project={COMPOSE_PROJECT}"
    commands = {
        "containers": ["docker", "ps", "-a", "--filter", label, "--format", "{{.Names}} {{.Ports}}"],
        "volumes": ["docker", "volume", "ls", "--filter", label, "--format", "{{.Name}}"],
        "networks": ["docker", "network", "ls", "--filter", label, "--format", "{{.Name}}"],
    }
    inventory: dict[str, list[str]] = {}
    for kind, command in commands.items():
        result = _capture(command)
        if result.returncode != 0:
            raise RuntimeError(f"docker_{kind}_inventory_failed:{result.returncode}")
        inventory[kind] = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    return inventory


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
        return True


def _preflight(engines: list[str]) -> bool:
    inventory = _project_inventory()
    ports = {int(os.environ.get(ENGINES[name]["port_env"], ENGINES[name]["port_default"])) for name in engines}
    busy_ports = sorted(port for port in ports if not _port_is_free(port))
    port_state = {str(port): "free" if port not in busy_ports else "busy" for port in sorted(ports)}
    print(f"[gate] preflight project={COMPOSE_PROJECT}: {json.dumps(inventory, ensure_ascii=False)}")
    print(f"[gate] preflight loopback ports: {json.dumps(port_state)}")
    if any(inventory.values()):
        print("[gate] refusing to reuse a non-empty project", file=sys.stderr)
        return False
    if busy_ports:
        print(f"[gate] refusing to bind occupied loopback ports: {busy_ports}", file=sys.stderr)
        return False
    return True


def _verify_clean(engines: list[str]) -> bool:
    inventory = _project_inventory()
    ports = {int(os.environ.get(ENGINES[name]["port_env"], ENGINES[name]["port_default"])) for name in engines}
    busy_ports = sorted(port for port in ports if not _port_is_free(port))
    port_state = {str(port): "free" if port not in busy_ports else "busy" for port in sorted(ports)}
    print(f"[gate] post-cleanup project={COMPOSE_PROJECT}: {json.dumps(inventory, ensure_ascii=False)}")
    print(f"[gate] post-cleanup loopback ports: {json.dumps(port_state)}")
    return not any(inventory.values()) and not busy_ports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="InsightFlow Phase 2B2 real-database gate")
    parser.add_argument("--engine", choices=["postgresql", "mysql", "all"], default="all")
    options = parser.parse_args(argv)
    engines = ["postgresql", "mysql"] if options.engine == "all" else [options.engine]

    global _COMPOSE_ENV_FILE
    with tempfile.TemporaryDirectory(prefix="insightflow-analytics-test-") as temp_dir:
        _COMPOSE_ENV_FILE = Path(temp_dir) / "compose.env"
        _COMPOSE_ENV_FILE.write_text("", encoding="utf-8")
        try:
            return _run_gate(engines)
        finally:
            _COMPOSE_ENV_FILE = None


def _run_gate(engines: list[str]) -> int:
    _require_docker()
    if not _preflight(engines):
        return 2

    services = [ENGINES[name]["service"] for name in engines]
    print(f"[gate] starting services in project {COMPOSE_PROJECT}: {' '.join(services)}")
    result_code = 0
    try:
        started = _compose("up", "-d", "--wait", "--wait-timeout", str(_HEALTH_TIMEOUT_SECONDS), *services)
        if started.returncode != 0:
            print(f"[gate] compose up failed with exit {started.returncode}", file=sys.stderr)
            _report_failure(engines)
            result_code = started.returncode
        else:
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
            result_code = result.returncode
    finally:
        print(f"[gate] stopping only project {COMPOSE_PROJECT}; volumes are preserved")
        stopped = _compose("down", "--timeout", "20")
        if stopped.returncode != 0:
            print(f"[gate] compose down failed with exit {stopped.returncode}", file=sys.stderr)
            result_code = result_code or stopped.returncode
        if not _verify_clean(engines):
            print("[gate] project cleanup left resources or occupied loopback ports; nothing was force-removed", file=sys.stderr)
            result_code = result_code or 1
    return result_code


if __name__ == "__main__":
    raise SystemExit(main())
