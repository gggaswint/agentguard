"""Shared fixtures for the Aegize test suite."""

from __future__ import annotations

import pytest

from aegize import AgentIdentity, AuditLog, PermissionPolicy

POLICY_DICT = {
    "agents": {
        "research_bot": {
            "allow": [
                {"tool": "web_search", "operations": ["search"], "risk_level_max": "medium"},
                {"tool": "file_reader", "operations": ["read"], "paths": ["./safe_data/**"]},
            ],
            "require_approval": [
                {"tool": "email", "operations": ["send"]},
                {"tool": "shell", "operations": ["execute"]},
            ],
            "deny": [
                {"tool": "payments", "operations": ["charge"]},
                {"tool": "shell", "operations": ["rm", "delete"]},
            ],
        }
    }
}

POLICY_YAML = """
agents:
  research_bot:
    allow:
      - tool: web_search
        operations: ["search"]
        risk_level_max: medium
      - tool: file_reader
        operations: ["read"]
        paths:
          - "./safe_data/**"
    require_approval:
      - tool: email
        operations: ["send"]
      - tool: shell
        operations: ["execute"]
    deny:
      - tool: payments
        operations: ["charge"]
      - tool: shell
        operations: ["rm", "delete"]
"""


@pytest.fixture
def agent() -> AgentIdentity:
    return AgentIdentity(
        agent_id="research_bot",
        name="Research Bot",
        owner="Geoffrey",
        environment="dev",
    )


@pytest.fixture
def policy() -> PermissionPolicy:
    return PermissionPolicy.from_dict(POLICY_DICT)


@pytest.fixture
def audit(tmp_path) -> AuditLog:
    return AuditLog(tmp_path / "audit.jsonl")


# The tests/mcp_gateway suite requires the optional ``aegize[mcp]`` extra (Python
# 3.10+). When the ``mcp`` SDK is not importable — e.g. the base package on
# Python 3.9 — the directory is excluded from collection so the core suite
# stays green without it.
import importlib.util  # noqa: E402

collect_ignore = []
if importlib.util.find_spec("mcp") is None:
    collect_ignore.append("mcp_gateway")
