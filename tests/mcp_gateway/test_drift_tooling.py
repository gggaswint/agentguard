"""Tests for the drift tooling: inspect --emit-policy and the check command."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import yaml

from aegize import PermissionPolicy
from aegize.mcp.cli import main

FIXTURE_SERVER = str(Path(__file__).with_name("fixture_server.py"))

ALL_TOOLS = sorted(
    ["echo", "send_email", "destructive_shell", "fail_tool", "slow_tool", "structured_tool"]
)


def _upstream_argv():
    return ["--", sys.executable, FIXTURE_SERVER]


# -- inspect --emit-policy -------------------------------------------------


def test_emit_policy_outputs_loadable_full_coverage_skeleton(capsys, tmp_path):
    code = main(["inspect", "--emit-policy", "--agent-id", "my-agent", *_upstream_argv()])
    assert code == 0
    out = capsys.readouterr().out
    data = yaml.safe_load(out)
    rules = data["agents"]["my-agent"]
    # Every discovered tool starts under require_approval: nothing runs
    # silently, nothing is silently blocked.
    gated = [rule["tool"] for rule in rules["require_approval"]]
    assert gated == ALL_TOOLS
    assert rules["allow"] == []
    assert rules["deny"] == []
    # And the skeleton is a valid policy with zero drift.
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text(out, encoding="utf-8")
    PermissionPolicy.from_yaml(policy_file)


def test_emit_policy_applies_tool_prefix(capsys):
    code = main(
        ["inspect", "--emit-policy", "--agent-id", "a", "--tool-prefix", "g_",
         *_upstream_argv()]
    )
    assert code == 0
    data = yaml.safe_load(capsys.readouterr().out)
    gated = [rule["tool"] for rule in data["agents"]["a"]["require_approval"]]
    assert all(name.startswith("g_") for name in gated)


# -- inspect --json --------------------------------------------------------


def test_inspect_json_emits_deterministic_tool_surface(capsys):
    import json

    code = main(["inspect", "--json", *_upstream_argv()])
    assert code == 0
    first = capsys.readouterr().out
    tools = json.loads(first)
    assert [t["name"] for t in tools] == ALL_TOOLS  # sorted -> diffable
    echo = next(t for t in tools if t["name"] == "echo")
    assert echo["description"] == "Echo the arguments back"
    assert echo["input_schema"]["type"] == "object"
    structured = next(t for t in tools if t["name"] == "structured_tool")
    assert structured["output_schema"]["required"] == ["answer"]
    # Byte-for-byte stable across runs — the property CI diffing depends on.
    assert main(["inspect", "--json", *_upstream_argv()]) == 0
    assert capsys.readouterr().out == first


def test_inspect_json_and_emit_policy_are_exclusive(capsys):
    code = main(["inspect", "--json", "--emit-policy", *_upstream_argv()])
    assert code == 2
    assert "not allowed" in capsys.readouterr().err.lower()


# -- check -----------------------------------------------------------------


def _write_policy(tmp_path, body: str) -> str:
    path = tmp_path / "policy.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return str(path)


def test_check_reports_drift_and_exits_nonzero(capsys, tmp_path):
    policy = _write_policy(
        tmp_path,
        """
        agents:
          test-agent:
            allow:
              - tool: echo
                operations: ["call"]
            deny:
              - tool: removed_tool
                operations: ["call"]
        """,
    )
    code = main(
        ["check", "--policy", policy, "--agent-id", "test-agent", *_upstream_argv()]
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "UNLISTED" in out
    assert "send_email" in out  # one of the uncovered tools
    assert "removed_tool" in out  # the stale rule
    assert "allow" in out and "echo" in out


def test_check_clean_policy_exits_zero(capsys, tmp_path):
    body = "agents:\n  test-agent:\n    require_approval:\n" + "".join(
        f'      - tool: {name}\n        operations: ["call"]\n' for name in ALL_TOOLS
    )
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(body, encoding="utf-8")
    policy = str(policy_path)
    code = main(
        ["check", "--policy", policy, "--agent-id", "test-agent", *_upstream_argv()]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "UNLISTED" not in out
    assert "0 unlisted" in out


def test_check_unknown_agent_exits_nonzero(capsys, tmp_path):
    policy = _write_policy(tmp_path, "agents: {}\n")
    code = main(
        ["check", "--policy", policy, "--agent-id", "ghost", *_upstream_argv()]
    )
    assert code == 1
    assert "ghost" in capsys.readouterr().out


def test_check_missing_policy_exits_2(capsys, tmp_path):
    code = main(
        ["check", "--policy", str(tmp_path / "nope.yaml"), "--agent-id", "a",
         *_upstream_argv()]
    )
    assert code == 2
    assert "error" in capsys.readouterr().err.lower()
