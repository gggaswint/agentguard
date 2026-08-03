"""Tests for the aegize-mcp CLI: argv splitting, config building, overrides."""

from __future__ import annotations

import textwrap

import pytest

from aegize.mcp.cli import build_config, main, split_upstream_argv
from aegize.mcp.errors import GatewayConfigError

CONFIG_YAML = textwrap.dedent(
    """
    agent:
      id: config-agent
      owner: config-owner
      environment: staging
    policy: ./from-config.yaml
    audit_log: ./from-config.jsonl
    upstream:
      command: config-server
      args: ["--flag"]
    gateway:
      call_timeout_seconds: 30
    """
)


# -- argv splitting --------------------------------------------------------


def test_split_upstream_argv():
    argv, upstream = split_upstream_argv(
        ["proxy", "--policy", "p.yaml", "--", "npx", "-y", "server", "--", "srv-arg"]
    )
    assert argv == ["proxy", "--policy", "p.yaml"]
    # Only the FIRST "--" splits; later ones belong to the upstream command.
    assert upstream == ["npx", "-y", "server", "--", "srv-arg"]


def test_split_without_separator():
    argv, upstream = split_upstream_argv(["proxy", "--config", "c.yaml"])
    assert argv == ["proxy", "--config", "c.yaml"]
    assert upstream == []


# -- config building -------------------------------------------------------


def test_build_config_from_flags_only():
    cfg = build_config(
        config=None,
        policy="./policy.yaml",
        agent_id="claude-code",
        agent_name=None,
        owner="geoff",
        environment="development",
        audit_log="./audit.jsonl",
        tool_prefix=None,
        startup_timeout=None,
        call_timeout=None,
        upstream_argv=["npx", "-y", "@extentos/mcp-server@latest"],
    )
    assert cfg.agent_id == "claude-code"
    assert cfg.environment == "dev"
    assert cfg.upstream.command == "npx"
    assert cfg.upstream.args == ["-y", "@extentos/mcp-server@latest"]


def test_flags_override_config_file(tmp_path):
    config_path = tmp_path / "aegize-mcp.yaml"
    config_path.write_text(CONFIG_YAML, encoding="utf-8")
    cfg = build_config(
        config=str(config_path),
        policy="./cli-policy.yaml",
        agent_id=None,
        agent_name=None,
        owner=None,
        environment=None,
        audit_log=None,
        tool_prefix=None,
        startup_timeout=None,
        call_timeout=5,
        upstream_argv=["cli-server"],
    )
    # CLI values win…
    assert cfg.policy_file == "./cli-policy.yaml"
    assert cfg.gateway.call_timeout_seconds == 5
    assert cfg.upstream.command == "cli-server"
    # …config-file values fill the gaps.
    assert cfg.agent_id == "config-agent"
    assert cfg.owner == "config-owner"
    assert cfg.environment == "staging"
    assert cfg.audit_log == "./from-config.jsonl"


def test_build_config_requires_upstream():
    with pytest.raises(GatewayConfigError, match="upstream"):
        build_config(
            config=None,
            policy="./policy.yaml",
            agent_id="a",
            agent_name=None,
            owner="o",
            environment=None,
            audit_log="./audit.jsonl",
            tool_prefix=None,
            startup_timeout=None,
            call_timeout=None,
            upstream_argv=[],
        )


# -- main ------------------------------------------------------------------


def test_main_without_command_shows_help(capsys):
    assert main([]) == 2
    assert "aegize-mcp" in capsys.readouterr().err


def test_main_proxy_with_bad_config_exits_2(capsys, tmp_path):
    code = main(
        [
            "proxy",
            "--config",
            str(tmp_path / "missing.yaml"),
            "--",
            "some-server",
        ]
    )
    assert code == 2
    assert "error" in capsys.readouterr().err.lower()


def test_main_proxy_without_upstream_exits_2(capsys):
    code = main(["proxy", "--policy", "p.yaml", "--agent-id", "a", "--owner", "o",
                 "--audit-log", "a.jsonl"])
    assert code == 2
    assert "upstream" in capsys.readouterr().err.lower()


def test_main_rejects_recursive_upstream(capsys):
    code = main(
        [
            "proxy",
            "--policy", "p.yaml",
            "--agent-id", "a",
            "--owner", "o",
            "--audit-log", "a.jsonl",
            "--",
            "aegize-mcp", "proxy",
        ]
    )
    assert code == 2
    assert "itself" in capsys.readouterr().err.lower()
