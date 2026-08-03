"""Tests for MCP gateway configuration loading and merging."""

from __future__ import annotations

import textwrap

import pytest

from aegize.mcp.config import MCPGatewayConfig
from aegize.mcp.errors import GatewayConfigError

CONFIG_YAML = """
agent:
  id: claude-code
  name: Claude Code
  owner: geoff
  environment: development

policy: ./aegize.yaml
audit_log: ./aegize-mcp-audit.jsonl

upstream:
  command: npx
  args:
    - -y
    - "@extentos/mcp-server@latest"
  env:
    EXAMPLE_ENV_VAR: optional-value

gateway:
  tool_prefix: ""
  startup_timeout_seconds: 20
  call_timeout_seconds: 120
"""


def _write_config(tmp_path, body: str = CONFIG_YAML):
    path = tmp_path / "aegize-mcp.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def test_from_yaml_parses_all_sections(tmp_path):
    cfg = MCPGatewayConfig.from_yaml(_write_config(tmp_path))
    assert cfg.agent_id == "claude-code"
    assert cfg.agent_name == "Claude Code"
    assert cfg.owner == "geoff"
    # "development" is normalized to the core identity vocabulary.
    assert cfg.environment == "dev"
    assert cfg.policy_file.endswith("aegize.yaml")
    assert cfg.audit_log.endswith("aegize-mcp-audit.jsonl")
    assert cfg.upstream.command == "npx"
    assert cfg.upstream.args == ["-y", "@extentos/mcp-server@latest"]
    assert cfg.upstream.env == {"EXAMPLE_ENV_VAR": "optional-value"}
    assert cfg.gateway.tool_prefix == ""
    assert cfg.gateway.startup_timeout_seconds == 20
    assert cfg.gateway.call_timeout_seconds == 120


def test_environment_aliases_normalized(tmp_path):
    for raw, expected in [
        ("development", "dev"),
        ("dev", "dev"),
        ("production", "prod"),
        ("prod", "prod"),
        ("staging", "staging"),
    ]:
        cfg = MCPGatewayConfig.from_yaml(
            _write_config(tmp_path, CONFIG_YAML.replace("development", raw))
        )
        assert cfg.environment == expected


def test_invalid_environment_rejected(tmp_path):
    with pytest.raises(GatewayConfigError, match="environment"):
        MCPGatewayConfig.from_yaml(
            _write_config(tmp_path, CONFIG_YAML.replace("development", "space"))
        )


def test_missing_upstream_command_rejected(tmp_path):
    body = CONFIG_YAML.replace("command: npx", "command: ''")
    with pytest.raises(GatewayConfigError, match="command"):
        MCPGatewayConfig.from_yaml(_write_config(tmp_path, body))


def test_missing_policy_rejected(tmp_path):
    body = CONFIG_YAML.replace("policy: ./aegize.yaml", "")
    with pytest.raises(GatewayConfigError, match="policy"):
        MCPGatewayConfig.from_yaml(_write_config(tmp_path, body))


def test_recursive_gateway_rejected(tmp_path):
    body = CONFIG_YAML.replace("command: npx", "command: aegize-mcp")
    with pytest.raises(GatewayConfigError, match="itself"):
        MCPGatewayConfig.from_yaml(_write_config(tmp_path, body))


def test_recursive_gateway_rejected_in_args(tmp_path):
    body = CONFIG_YAML.replace('- "@extentos/mcp-server@latest"', "- aegize-mcp")
    with pytest.raises(GatewayConfigError, match="itself"):
        MCPGatewayConfig.from_yaml(_write_config(tmp_path, body))


def test_unreadable_config_errors(tmp_path):
    with pytest.raises(GatewayConfigError, match="read"):
        MCPGatewayConfig.from_yaml(tmp_path / "nope.yaml")


def test_invalid_yaml_errors(tmp_path):
    with pytest.raises(GatewayConfigError, match="parse"):
        MCPGatewayConfig.from_yaml(_write_config(tmp_path, "a: [unclosed"))


def test_overrides_replace_config_values(tmp_path):
    base = MCPGatewayConfig.from_yaml(_write_config(tmp_path))
    merged = base.with_overrides(
        agent_id="other-agent",
        environment="prod",
        call_timeout_seconds=5,
        upstream_argv=["python", "-m", "fixture"],
    )
    assert merged.agent_id == "other-agent"
    assert merged.environment == "prod"
    assert merged.gateway.call_timeout_seconds == 5
    assert merged.upstream.command == "python"
    assert merged.upstream.args == ["-m", "fixture"]
    # Untouched values survive the merge.
    assert merged.owner == "geoff"
    assert merged.policy_file == base.policy_file
    # The original is not mutated.
    assert base.agent_id == "claude-code"
    assert base.upstream.command == "npx"


def test_overrides_reject_recursive_upstream(tmp_path):
    base = MCPGatewayConfig.from_yaml(_write_config(tmp_path))
    with pytest.raises(GatewayConfigError, match="itself"):
        base.with_overrides(upstream_argv=["aegize-mcp", "proxy"])


def test_agent_name_defaults_to_agent_id(tmp_path):
    body = CONFIG_YAML.replace("  name: Claude Code\n", "")
    cfg = MCPGatewayConfig.from_yaml(_write_config(tmp_path, body))
    assert cfg.agent_name == "claude-code"
