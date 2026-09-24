"""本机配置模板的端到端回归测试。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_windows_make_config_runs_from_a_powershell_invocation(tmp_path: Path) -> None:
    """Windows GNU Make 必须用能执行目标的 shell，而不能误启动交互 CMD。"""
    if os.name != "nt":
        pytest.skip("Windows Make shell integration")
    make = shutil.which("make")
    if make is None:
        pytest.skip("GNU Make is not installed")

    repository = Path(__file__).resolve().parents[2]
    project = tmp_path
    (project / "scripts").mkdir()
    (project / "frontend").mkdir()
    for relative_path in (
        "Makefile",
        "scripts/configure.py",
        "config.example.yaml",
        "extensions_config.example.json",
        ".env.example",
        "frontend/.env.example",
    ):
        source = repository / relative_path
        target = project / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    environment = os.environ.copy()
    environment["OS"] = "Windows_NT"
    result = subprocess.run(
        [make, "config"],
        cwd=project,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (project / "config.yaml").exists()
    assert (project / "extensions_config.json").exists()
    assert (project / ".env").exists()
    assert (project / "frontend/.env").exists()


def test_msys_make_runs_repository_shell_scripts_in_msys_bash(tmp_path: Path) -> None:
    """PowerShell-launched MSYS Make must not resolve `bash` to WSL."""
    if os.name != "nt":
        pytest.skip("MSYS Make shell integration")
    make = shutil.which("make")
    posix_shell = shutil.which("sh")
    if make is None or posix_shell is None:
        pytest.skip("GNU Make and a POSIX shell are required")

    host_shell = subprocess.run(
        [posix_shell, "-lc", "uname -s"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    if not host_shell.stdout.strip().startswith("MSYS_NT"):
        pytest.skip("MSYS GNU Make is not the active Windows Make implementation")

    repository = Path(__file__).resolve().parents[2]
    project = tmp_path
    scripts_dir = project / "scripts"
    scripts_dir.mkdir()
    shutil.copyfile(repository / "Makefile", project / "Makefile")
    (scripts_dir / "probe-shell.sh").write_text("printf '%s\\n' \"$(uname -s)\"\n", encoding="utf-8")
    with (project / "Makefile").open("a", encoding="utf-8") as makefile:
        makefile.write("\nprobe-shell:\n\t@$(RUN_SHELL_SCRIPT) ./scripts/probe-shell.sh\n")

    environment = os.environ.copy()
    environment["OS"] = "Windows_NT"
    result = subprocess.run(
        [make, "probe-shell"],
        cwd=project,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "MSYS_NT" in result.stdout


def test_make_config_copies_current_templates_without_removed_capabilities(tmp_path: Path) -> None:
    """make config 生成完整本地模板，且不携带已删除能力或伪密钥。"""
    repository = Path(__file__).resolve().parents[2]
    project = tmp_path
    scripts_dir = project / "scripts"
    frontend_dir = project / "frontend"
    scripts_dir.mkdir()
    frontend_dir.mkdir()

    for relative_path in (
        "scripts/configure.py",
        "config.example.yaml",
        "extensions_config.example.json",
        ".env.example",
        "frontend/.env.example",
    ):
        source = repository / relative_path
        target = project / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    result = subprocess.run(
        [sys.executable, str(scripts_dir / "configure.py")],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    generated_env = (project / ".env").read_text(encoding="utf-8")
    assert "# JINA_API_KEY=your-jina-api-key" in generated_env
    active_placeholders = [line for line in generated_env.splitlines() if line.strip() and not line.lstrip().startswith("#") and "=" in line and line.split("=", 1)[1].startswith("your-")]
    assert active_placeholders == []
    removed_options = (
        "SERPER_API_KEY",
        "SERPLY_API_KEY",
        "TAVILY_API_KEY",
        "INFOQUEST_API_KEY",
        "SOFYA_API_KEY",
        "FIRECRAWL_API_KEY",
        "OPENVIKING_API_KEY",
        "STEPFUN_API_KEY",
        "VLLM_API_KEY",
        "IMAGE_GENERATION_PROVIDER",
        "IMAGE_GENERATION_API_KEY",
        "IMAGE_GENERATION_BASE_URL",
        "IMAGE_GENERATION_MODEL",
        "IMAGE_GENERATION_SIZE",
        "E2B_API_KEY",
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "SLACK_BOT_TOKEN",
        "SLACK_APP_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "DISCORD_BOT_TOKEN",
        "WECOM_BOT_ID",
        "WECOM_BOT_SECRET",
        "DINGTALK_CLIENT_ID",
        "DINGTALK_CLIENT_SECRET",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "ANTHROPIC_AUTH_TOKEN",
        "CLAUDE_CODE_CREDENTIALS_PATH",
        "CODEX_AUTH_PATH",
    )
    assert all(option not in generated_env for option in removed_options)
    assert "OPENAI_API_KEY" in generated_env
    assert "DATABASE_URL" in generated_env
    assert (project / "extensions_config.json").read_bytes() == (project / "extensions_config.example.json").read_bytes()


def test_make_config_preserves_an_existing_env_file(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    project = tmp_path
    scripts_dir = project / "scripts"
    frontend_dir = project / "frontend"
    scripts_dir.mkdir()
    frontend_dir.mkdir()

    for relative_path in (
        "scripts/configure.py",
        "config.example.yaml",
        "extensions_config.example.json",
        ".env.example",
        "frontend/.env.example",
    ):
        source = repository / relative_path
        target = project / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    local_env = "LOCAL_SETTING=keep-this-value\n"
    (project / ".env").write_text(local_env, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(scripts_dir / "configure.py")],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (project / ".env").read_text(encoding="utf-8") == local_env
    assert (project / "config.yaml").exists()


def test_make_config_aborts_without_overwriting_existing_config_or_env(tmp_path: Path) -> None:
    project = tmp_path
    scripts_dir = project / "scripts"
    scripts_dir.mkdir()
    repository = Path(__file__).resolve().parents[2]
    shutil.copyfile(repository / "scripts" / "configure.py", scripts_dir / "configure.py")
    config = "config_version: 5\nlocal_setting: preserve\n"
    local_env = "LOCAL_SETTING=keep-this-value\n"
    (project / "config.yaml").write_text(config, encoding="utf-8")
    (project / ".env").write_text(local_env, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(scripts_dir / "configure.py")],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 1
    assert "configuration file already exists" in result.stdout
    assert (project / "config.yaml").read_text(encoding="utf-8") == config
    assert (project / ".env").read_text(encoding="utf-8") == local_env
