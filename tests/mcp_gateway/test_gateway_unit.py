"""Unit tests for the gateway's call handling, with a fake upstream.

These prove the enforcement invariants at the handler level: audit-first
ordering, deny/approval never reaching upstream, error classification, and
redaction — without spawning any subprocess.
"""

from __future__ import annotations

import pytest
from mcp.types import CallToolResult, TextContent, Tool

from aegize import AuditLog, PermissionPolicy
from aegize.mcp.config import MCPGatewayConfig, UpstreamConfig
from aegize.mcp.errors import (
    CATEGORY_APPROVAL_REQUIRED,
    CATEGORY_INTERNAL,
    CATEGORY_MALFORMED_REQUEST,
    CATEGORY_POLICY_DENIED,
    CATEGORY_POLICY_UNAVAILABLE,
    CATEGORY_TIMEOUT,
    CATEGORY_UPSTREAM_TOOL_ERROR,
    CATEGORY_UPSTREAM_UNAVAILABLE,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from aegize.mcp.gateway import MCPGateway
from aegize.mcp.tool_mapping import ToolMapping

pytestmark = pytest.mark.anyio

POLICY = {
    "agents": {
        "test-agent": {
            "allow": [{"tool": "echo", "operations": ["call"]}],
            "require_approval": [{"tool": "send_email", "operations": ["call"]}],
            "deny": [{"tool": "destructive_shell", "operations": ["call"]}],
        }
    }
}


def _tool(name: str) -> Tool:
    return Tool(name=name, description=name, input_schema={"type": "object"})


class FakeUpstream:
    """Records calls; returns a canned result or raises a configured error."""

    def __init__(self, result: CallToolResult | None = None, error: Exception | None = None):
        self.calls: list[tuple[str, dict]] = []
        self.result = result or CallToolResult(
            content=[TextContent(type="text", text="ok")]
        )
        self.error = error
        self.on_call = None  # optional callback, invoked before returning

    async def call_tool(self, name: str, arguments: dict) -> CallToolResult:
        self.calls.append((name, arguments))
        if self.on_call is not None:
            self.on_call()
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def audit(tmp_path):
    return AuditLog(tmp_path / "audit.jsonl")


@pytest.fixture
def gateway(tmp_path, audit):
    config = MCPGatewayConfig(
        agent_id="test-agent",
        owner="tester",
        policy_file=str(tmp_path / "policy.yaml"),
        audit_log=str(audit.path),
        upstream=UpstreamConfig(command="fixture"),
    )
    gw = MCPGateway(config)
    tools = [_tool("echo"), _tool("send_email"), _tool("destructive_shell")]
    gw._bind(
        policy=PermissionPolicy.from_dict(POLICY),
        audit=audit,
        mapping=ToolMapping(tools),
        upstream=FakeUpstream(),
    )
    return gw


def _events(audit):
    return [(r["event"], r.get("category")) for r in audit.read_all()]


def _text(result: CallToolResult) -> str:
    return " ".join(c.text for c in result.content if isinstance(c, TextContent))


# -- allow ----------------------------------------------------------------


async def test_allowed_call_forwards_unchanged_and_audits(gateway, audit):
    args = {"text": "hello", "n": 3}
    result = await gateway.handle_call_tool("echo", dict(args))
    assert not result.is_error
    assert _text(result) == "ok"
    assert gateway._upstream.calls == [("echo", args)]
    assert _events(audit) == [("allowed", None), ("execution_succeeded", None)]


async def test_audit_first_allowed_is_recorded_before_upstream_call(gateway, audit):
    seen_at_call_time = {}

    def probe():
        seen_at_call_time["events"] = [r["event"] for r in audit.read_all()]

    gateway._upstream.on_call = probe
    await gateway.handle_call_tool("echo", {})
    assert seen_at_call_time["events"] == ["allowed"]


# -- deny / approval / unknown --------------------------------------------


async def test_denied_call_never_reaches_upstream(gateway, audit):
    result = await gateway.handle_call_tool("destructive_shell", {"cmd": "rm -rf /"})
    assert result.is_error
    text = _text(result)
    assert "denied" in text.lower()
    assert "destructive_shell" in text
    assert gateway._upstream.calls == []
    events = audit.read_all()
    assert [e["event"] for e in events] == ["denied"]
    assert events[0]["category"] == CATEGORY_POLICY_DENIED
    # The action id is surfaced for correlation.
    assert events[0]["action_id"] in text


async def test_approval_required_never_reaches_upstream(gateway, audit):
    result = await gateway.handle_call_tool("send_email", {"to": "a@b.c"})
    assert result.is_error
    text = _text(result)
    assert "approval" in text.lower()
    assert gateway._upstream.calls == []
    events = audit.read_all()
    assert [e["event"] for e in events] == ["approval_required"]
    assert events[0]["category"] == CATEGORY_APPROVAL_REQUIRED
    assert events[0]["action_id"] in text


async def test_unknown_tool_denied_without_upstream(gateway, audit):
    result = await gateway.handle_call_tool("not_a_tool", {})
    assert result.is_error
    assert "unknown" in _text(result).lower()
    assert gateway._upstream.calls == []
    events = audit.read_all()
    assert [e["event"] for e in events] == ["denied"]
    assert events[0]["category"] == CATEGORY_POLICY_DENIED


async def test_default_deny_for_unlisted_tool_in_mapping(gateway, audit):
    # Tool exists upstream but has no allow rule -> default deny.
    gateway._mapping = ToolMapping([_tool("echo"), _tool("mystery")])
    result = await gateway.handle_call_tool("mystery", {})
    assert result.is_error
    assert gateway._upstream.calls == []
    assert [e["event"] for e in audit.read_all()] == ["denied"]


# -- malformed ------------------------------------------------------------


async def test_malformed_arguments_rejected(gateway, audit):
    result = await gateway.handle_call_tool("echo", ["not", "a", "dict"])
    assert result.is_error
    assert gateway._upstream.calls == []
    events = audit.read_all()
    assert [e["event"] for e in events] == ["denied"]
    assert events[0]["category"] == CATEGORY_MALFORMED_REQUEST


# -- upstream failures ----------------------------------------------------


async def test_timeout_classified_and_audited(gateway, audit):
    gateway._upstream.error = UpstreamTimeoutError("upstream call timed out after 1s")
    result = await gateway.handle_call_tool("echo", {})
    assert result.is_error
    assert "timed out" in _text(result)
    events = audit.read_all()
    assert [e["event"] for e in events] == ["allowed", "execution_failed"]
    assert events[1]["category"] == CATEGORY_TIMEOUT


async def test_upstream_unavailable_classified(gateway, audit):
    gateway._upstream.error = UpstreamUnavailableError("upstream exited")
    result = await gateway.handle_call_tool("echo", {})
    assert result.is_error
    events = audit.read_all()
    assert events[1]["category"] == CATEGORY_UPSTREAM_UNAVAILABLE


async def test_upstream_error_result_forwarded_and_audited(gateway, audit):
    error_result = CallToolResult(
        content=[TextContent(type="text", text="tool blew up")], is_error=True
    )
    gateway._upstream.result = error_result
    result = await gateway.handle_call_tool("echo", {})
    # Forwarded unchanged — the host sees the upstream error verbatim.
    assert result is error_result
    events = audit.read_all()
    assert [e["event"] for e in events] == ["allowed", "execution_failed"]
    assert events[1]["category"] == CATEGORY_UPSTREAM_TOOL_ERROR


async def test_unexpected_exception_is_internal_error(gateway, audit):
    gateway._upstream.error = ValueError("bug")
    result = await gateway.handle_call_tool("echo", {})
    assert result.is_error
    events = audit.read_all()
    assert events[1]["category"] == CATEGORY_INTERNAL
    # The raw exception text is not leaked to the host.
    assert "bug" not in _text(result)


async def test_policy_evaluation_failure_fails_closed(gateway, audit):
    class BrokenPolicy:
        def evaluate(self, action):
            raise RuntimeError("policy backend exploded")

    gateway._policy = BrokenPolicy()
    result = await gateway.handle_call_tool("echo", {})
    assert result.is_error
    assert gateway._upstream.calls == []
    events = audit.read_all()
    assert [e["event"] for e in events] == ["denied"]
    assert events[0]["category"] == CATEGORY_POLICY_UNAVAILABLE


# -- redaction and metadata ------------------------------------------------


async def test_sensitive_arguments_redacted_in_audit(gateway, audit):
    await gateway.handle_call_tool("echo", {"query": "ok", "api_key": "sk-secret-123"})
    record = audit.read_all()[0]
    assert "sk-secret-123" not in str(record)
    assert "ok" in record["input_summary"]
    # But the untouched arguments still reached upstream.
    assert gateway._upstream.calls[0][1]["api_key"] == "sk-secret-123"


async def test_sensitive_tool_name_redacts_all_argument_values(gateway, audit):
    # A tool like setCredential signals sensitivity via its NAME; innocuous
    # key names ("value") must not leak the payload into the audit log.
    gateway._mapping = ToolMapping([_tool("echo"), _tool("setCredential")])
    await gateway.handle_call_tool("setCredential", {"kind": "api", "value": "sekret-123"})
    record = audit.read_all()[0]
    assert "sekret-123" not in str(record)
    assert "[redacted]" in record["input_summary"]


async def test_action_metadata_fields(gateway, audit):
    await gateway.handle_call_tool("echo", {"b": 1, "a": 2})
    meta = audit.read_all()[0]["metadata"]
    assert meta["upstream_tool_name"] == "echo"
    assert meta["mcp_transport"] == "stdio"
    assert meta["argument_keys"] == ["a", "b"]
    assert len(meta["argument_hash"]) == 64
    assert meta["gateway_version"]
    assert meta["upstream_command"] == "fixture"
    # Internal path-candidate bookkeeping is not echoed into the log.
    assert "candidate_paths" not in meta


# -- prefix + list --------------------------------------------------------


async def test_prefixed_tool_maps_to_upstream_name(gateway, audit):
    gateway._mapping = ToolMapping([_tool("echo")], tool_prefix="g_")
    result = await gateway.handle_call_tool("g_echo", {"x": 1})
    # Policy matches the exposed name; "g_echo" has no allow rule -> deny.
    assert result.is_error
    assert gateway._upstream.calls == []


async def test_prefixed_tool_allowed_calls_upstream_with_bare_name(gateway, audit, tmp_path):
    gateway._mapping = ToolMapping([_tool("echo")], tool_prefix="g_")
    gateway._policy = PermissionPolicy.from_dict(
        {"agents": {"test-agent": {"allow": [{"tool": "g_echo", "operations": ["call"]}]}}}
    )
    result = await gateway.handle_call_tool("g_echo", {"x": 1})
    assert not result.is_error
    assert gateway._upstream.calls == [("echo", {"x": 1})]


async def test_list_tools_returns_mirrored_tools(gateway):
    tools = await gateway.handle_list_tools()
    assert [t.name for t in tools] == ["destructive_shell", "echo", "send_email"]
    assert all(t.input_schema == {"type": "object"} for t in tools)
