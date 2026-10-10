"""首屏配置说明与推荐模型示例的回归检查。"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from langchain_openai import ChatOpenAI

from deerflow.config.app_config import AppConfig
from deerflow.config.model_config import ModelConfig
from deerflow.config.sandbox_config import SandboxConfig
from deerflow.models.factory import create_chat_model

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_EXAMPLE = REPO_ROOT / "config.example.yaml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
INSTALL_GUIDE = REPO_ROOT / "Install.md"
SAMPLE_START = "# BEGIN DEEPSEEK FLASH QUICKSTART"
SAMPLE_END = "# END DEEPSEEK FLASH QUICKSTART"


def _deepseek_flash_sample() -> dict:
    lines = CONFIG_EXAMPLE.read_text(encoding="utf-8").splitlines()
    marker = next((index for index, line in enumerate(lines) if line.strip() == SAMPLE_START), None)
    assert marker is not None, "config.example.yaml 缺少 DeepSeek Flash 快速配置样例"
    end = next(index for index in range(marker + 1, len(lines)) if lines[index].strip() == SAMPLE_END)
    start = next(index for index in range(marker + 1, end) if lines[index].lstrip().startswith("#   - name: deepseek-flash"))
    model = "\n".join(line.lstrip().removeprefix("# ") for line in lines[start:end])
    snippet = f"models:\n{model}"
    return yaml.safe_load(snippet)


def test_quickstart_model_example_constructs_with_the_real_model_factory():
    data = _deepseek_flash_sample()
    assert data["models"]
    config = ModelConfig.model_validate(data["models"][0])
    config.api_key = "sk-test-placeholder"
    app_config = AppConfig(
        models=[config],
        sandbox=SandboxConfig(use="deerflow.sandbox.local:LocalSandboxProvider"),
    )

    model = create_chat_model(config.name, app_config=app_config, attach_tracing=False)

    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "deepseek-flash"
    assert str(model.openai_api_base).rstrip("/") in {
        "https://api.deepseek.com",
        "https://api.deepseek.com/v1",
    }
    assert model.extra_body == {"thinking": {"type": "disabled"}}


def test_env_example_covers_setup_wizard_model_credentials_without_real_values():
    providers = (REPO_ROOT / "scripts" / "wizard" / "providers.py").read_text(encoding="utf-8")
    env_names = set(re.findall(r'env_var="([A-Z][A-Z0-9_]+)"', providers))
    template = ENV_EXAMPLE.read_text(encoding="utf-8")

    missing = sorted(name for name in env_names if not re.search(rf"(?m)^\s*#?\s*{re.escape(name)}=", template))
    assert not missing, f".env.example 缺少向导支持的模型凭据占位项：{missing}"
    assert all(re.search(rf"(?m)^\s*#\s*{re.escape(name)}=", template) for name in env_names)


def test_install_guide_explains_the_configuration_layers_in_chinese():
    guide = INSTALL_GUIDE.read_text(encoding="utf-8")

    for filename in (".env", ".env.example", "config.yaml", "extensions_config.json", "Compose", "BIND_HOST", "PORT", "secret_ref"):
        assert filename in guide
    for term in ("经营分析", "PostgreSQL", "MySQL"):
        assert term in guide
