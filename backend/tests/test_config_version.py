"""Tests for config version check and upgrade logic."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from pydantic import ValidationError
from support.shell import find_script_bash

from deerflow.config.app_config import AppConfig

# Only the upgrade-script test shells out; it needs Git Bash on Windows (the
# WSL launcher and Store alias stubs cannot run the repo scripts).
SCRIPT_BASH = find_script_bash()


def _make_config_files(tmpdir: Path, user_config: dict, example_config: dict) -> Path:
    """Write user config.yaml and config.example.yaml to a temp dir, return config path."""
    config_path = tmpdir / "config.yaml"
    example_path = tmpdir / "config.example.yaml"

    # Minimal valid config needs sandbox
    defaults = {
        "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
    }
    for cfg in (user_config, example_config):
        for k, v in defaults.items():
            cfg.setdefault(k, v)

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(user_config, f)
    with open(example_path, "w", encoding="utf-8") as f:
        yaml.dump(example_config, f)

    return config_path


def test_missing_version_treated_as_zero(caplog):
    """Config without config_version should be treated as version 0."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = _make_config_files(
            Path(tmpdir),
            user_config={},  # no config_version
            example_config={"config_version": 1},
        )
        with caplog.at_level(logging.WARNING, logger="deerflow.config.app_config"):
            AppConfig._check_config_version(
                {"sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"}},
                config_path,
            )
        assert "outdated" in caplog.text
        assert "version 0" in caplog.text
        assert "version is 1" in caplog.text


def test_matching_version_no_warning(caplog):
    """Config with matching version should not emit a warning."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = _make_config_files(
            Path(tmpdir),
            user_config={"config_version": 1},
            example_config={"config_version": 1},
        )
        with caplog.at_level(logging.WARNING, logger="deerflow.config.app_config"):
            AppConfig._check_config_version(
                {"config_version": 1},
                config_path,
            )
        assert "outdated" not in caplog.text


def test_outdated_version_emits_warning(caplog):
    """Config with lower version should emit a warning."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = _make_config_files(
            Path(tmpdir),
            user_config={"config_version": 1},
            example_config={"config_version": 2},
        )
        with caplog.at_level(logging.WARNING, logger="deerflow.config.app_config"):
            AppConfig._check_config_version(
                {"config_version": 1},
                config_path,
            )
        assert "outdated" in caplog.text
        assert "version 1" in caplog.text
        assert "version is 2" in caplog.text


def test_no_example_file_no_warning(caplog):
    """If config.example.yaml doesn't exist, no warning should be emitted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump({"sandbox": {"use": "test"}}, f)
        # No config.example.yaml created

        with caplog.at_level(logging.WARNING, logger="deerflow.config.app_config"):
            AppConfig._check_config_version({}, config_path)
        assert "outdated" not in caplog.text


def test_string_config_version_does_not_raise_type_error(caplog):
    """config_version stored as a YAML string should not raise TypeError on comparison."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = _make_config_files(
            Path(tmpdir),
            user_config={"config_version": "1"},  # string, as YAML can produce
            example_config={"config_version": 2},
        )
        # Must not raise TypeError: '<' not supported between instances of 'str' and 'int'
        AppConfig._check_config_version({"config_version": "1"}, config_path)


def test_newer_user_version_no_warning(caplog):
    """If user has a newer version than example (edge case), no warning."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = _make_config_files(
            Path(tmpdir),
            user_config={"config_version": 3},
            example_config={"config_version": 2},
        )
        with caplog.at_level(logging.WARNING, logger="deerflow.config.app_config"):
            AppConfig._check_config_version(
                {"config_version": 3},
                config_path,
            )
        assert "outdated" not in caplog.text


@pytest.mark.skipif(SCRIPT_BASH is None, reason="repo shell-script tests need Git Bash on Windows")
def test_version_26_config_upgrades_to_checkpoint_channel_mode(tmp_path, caplog):
    """A v26 user config must be flagged outdated and merge the new persisted field.

    `database.checkpoint_channel_mode` shipped with config_version 27; the
    upgrade path must add it with the safe default (``full``) without touching
    the user's existing database backend settings. Uses the repository's real
    config.example.yaml and the real config-upgrade script.
    """
    import subprocess

    repo_root = Path(__file__).resolve().parents[2]
    example_src = repo_root / "config.example.yaml"
    example_data = yaml.safe_load(example_src.read_text(encoding="utf-8"))
    expected_version = example_data["config_version"]
    assert expected_version > 26, "config.example.yaml must be bumped past 26 for checkpoint_channel_mode"

    config_path = tmp_path / "config.yaml"
    (tmp_path / "config.example.yaml").write_text(example_src.read_text(encoding="utf-8"), encoding="utf-8")
    user_config = {
        "config_version": 26,
        "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
        "database": {"backend": "sqlite", "sqlite_dir": "custom-data"},
    }
    config_path.write_text(yaml.dump(user_config), encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="deerflow.config.app_config"):
        AppConfig._check_config_version(dict(user_config), config_path)
    assert "outdated" in caplog.text
    assert "(version 26)" in caplog.text

    env = {**os.environ, "DEER_FLOW_CONFIG_PATH": str(config_path)}
    result = subprocess.run(
        [SCRIPT_BASH, str(repo_root / "scripts" / "config-upgrade.sh")],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr

    upgraded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert upgraded["config_version"] == expected_version
    assert upgraded["database"]["checkpoint_channel_mode"] == "full"
    assert upgraded["database"]["backend"] == "sqlite"
    assert upgraded["database"]["sqlite_dir"] == "custom-data"
    assert upgraded["verification"]["receipts_enabled"] is True
    assert upgraded["verification"]["receipts_render_mode"] == "delegation_only"
    assert upgraded["verification"]["judge_enabled"] is False
    assert upgraded["verification"]["judge_model_name"] is None


def _load_repo_example() -> dict:
    """Load the real repo config.example.yaml (first-run template)."""
    example_path = Path(__file__).resolve().parents[2] / "config.example.yaml"
    with open(example_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def test_example_uses_db_for_run_event_persistence_by_default():
    example = _load_repo_example()

    assert example["database"]["backend"] == "sqlite"
    assert example["run_events"]["backend"] == "db"


def _merge_missing(target: dict, source: dict) -> None:
    """Add-missing-keys-only recursive merge mirroring scripts/config-upgrade.sh."""
    for key, value in source.items():
        if key not in target:
            import copy

            target[key] = copy.deepcopy(value)
        elif isinstance(value, dict) and isinstance(target[key], dict):
            _merge_missing(target[key], value)


def test_skill_security_config_version_and_safe_defaults():
    """The example carries the split security policy with fail-closed defaults."""
    example = _load_repo_example()
    assert example["config_version"] == 49
    assert "skill_evolution" not in example
    assert example["skill_security"] == {"moderation_model_name": None, "security_fail_closed": True}


def test_version_26_config_reported_outdated_against_example(caplog):
    """A version-26 user config is flagged outdated against the real example version."""
    example = _load_repo_example()
    example_version = example["config_version"]
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = _make_config_files(
            Path(tmpdir),
            user_config={"config_version": 26},
            example_config=example,
        )
        with caplog.at_level(logging.WARNING, logger="deerflow.config.app_config"):
            AppConfig._check_config_version({"config_version": 26}, config_path)
        assert "outdated" in caplog.text
        assert "version 26" in caplog.text
        assert f"version is {example_version}" in caplog.text


def test_legacy_skill_evolution_migrates_security_and_discards_agent_toggle():
    config = AppConfig.model_validate(
        {
            "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
            "skill_evolution": {
                "enabled": True,
                "moderation_model_name": "legacy-moderation",
                "security_fail_closed": False,
            },
        }
    )

    assert config.skill_security.moderation_model_name == "legacy-moderation"
    assert config.skill_security.security_fail_closed is False
    assert not hasattr(config, "skill_evolution")
    assert "skill_evolution" not in config.model_dump()


def test_explicit_skill_security_values_override_legacy_fields():
    config = AppConfig.model_validate(
        {
            "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
            "skill_evolution": {
                "enabled": True,
                "moderation_model_name": "legacy-moderation",
                "security_fail_closed": False,
            },
            "skill_security": {"moderation_model_name": "explicit-moderation", "security_fail_closed": True},
        }
    )

    assert config.skill_security.moderation_model_name == "explicit-moderation"
    assert config.skill_security.security_fail_closed is True
    assert not hasattr(config, "skill_evolution")


def test_invalid_legacy_security_policy_fails_validation():
    with pytest.raises(ValidationError):
        AppConfig.model_validate(
            {
                "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
                "skill_evolution": {"enabled": True, "security_fail_closed": "allow"},
            }
        )


def test_from_file_applies_legacy_security_migration(tmp_path, monkeypatch):
    from deerflow.config.extensions_config import ExtensionsConfig

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
                "skill_evolution": {"enabled": True, "security_fail_closed": False},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(ExtensionsConfig, "from_file", classmethod(lambda cls, *args, **kwargs: cls()))

    config = AppConfig.from_file(str(config_path))

    assert config.skill_security.security_fail_closed is False
    assert not hasattr(config, "skill_evolution")


@pytest.mark.skipif(SCRIPT_BASH is None, reason="repo shell-script tests need Git Bash on Windows")
def test_config_upgrade_migrates_legacy_skill_security_and_keeps_backup(tmp_path):
    import subprocess

    repo_root = Path(__file__).resolve().parents[2]
    example_src = repo_root / "config.example.yaml"
    config_path = tmp_path / "config.yaml"
    (tmp_path / "config.example.yaml").write_text(example_src.read_text(encoding="utf-8"), encoding="utf-8")
    config_path.write_text(
        yaml.safe_dump(
            {
                "config_version": 48,
                "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
                "skill_evolution": {
                    "enabled": True,
                    "moderation_model_name": "legacy-moderation",
                    "security_fail_closed": False,
                },
                "skill_security": {"moderation_model_name": "explicit-moderation"},
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [SCRIPT_BASH, str(repo_root / "scripts" / "config-upgrade.sh")],
        env={**os.environ, "DEER_FLOW_CONFIG_PATH": str(config_path)},
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    upgraded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    backup = yaml.safe_load(config_path.with_suffix(".yaml.bak").read_text(encoding="utf-8"))
    assert upgraded["config_version"] == 49
    assert "skill_evolution" not in upgraded
    assert upgraded["skill_security"] == {"moderation_model_name": "explicit-moderation", "security_fail_closed": False}
    assert backup["skill_evolution"]["enabled"] is True


def test_the_example_analytics_block_parses_with_the_app_owned_parser():
    """模板里的 `analytics:` 必须能被 `app.analytics` 的严格解析器接受。

    模板与解析器是同一份契约的两端：任何一侧单独改动（新增字段却不更新解析器、或把
    float 成本写进模板）都会在这里失败。
    """

    from app.analytics.config import AnalyticsConfig

    example = _load_repo_example()
    assert example["config_version"] >= 46
    assert "analytics" in example

    config = AnalyticsConfig.from_app_config(SimpleNamespace(analytics=example["analytics"]))

    assert config.enabled is True
    assert config.execution_limits().max_result_rows == config.max_result_rows
