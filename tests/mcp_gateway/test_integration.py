"""End-to-end tests: host ⇄ aegize-mcp gateway subprocess ⇄ fixture upstream.

The test acts as the MCP host and connects (over real stdio) to a gateway
subprocess launched with ``python -m aegize.mcp.cli proxy``; the gateway in
turn launches ``fixture_server.py`` as its upstream. No network, Node, or
external servers involved.
"""

from __future__ import annotations

import json
import os
import signal
import textwrap
import time
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from mcp.client.stdio import stdio_client
from mcp.types import TextContent

from aegize import AuditLog
from mcp import ClientSession, StdioServerParameters

pytestmark = pytest.mark.anyio

FIXTURE_SERVER = str(Path(__file__).with_name("fixture_server.py"))

POLICY_YAML = textwrap.dedent(
    """
    agents:
      test-agent:
        allow:
          - tool: echo
            operations: ["call"]
          - tool: structured_tool
            operations: ["call"]
          - tool: slow_tool
            operations: ["call"]
          - tool: fail_tool
            operations: ["call"]
        require_approval:
          - tool: send_email
            operations: ["call"]
        deny:
          - tool: destructive_shell
            operations: ["call"]
    """
)


@asynccontextmanager
async def gateway_session(tmp_path, *, call_timeout: float = 30.0, extra_flags=()):
    """Connect to a real gateway subprocess; yield (session, paths)."""
    import sys

    policy = tmp_path / "policy.yaml"
    policy.write_text(POLICY_YAML, encoding="utf-8")
    audit = tmp_path / "audit.jsonl"
    call_log = tmp_path / "calls.jsonl"
    stderr_log = tmp_path / "gateway-stderr.log"

    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m", "aegize.mcp.cli", "proxy",
            "--policy", str(policy),
            "--agent-id", "test-agent",
            "--owner", "tester",
            "--environment", "development",
            "--audit-log", str(audit),
            "--call-timeout", str(call_timeout),
            *extra_flags,
            "--",
            sys.executable, FIXTURE_SERVER, str(call_log),
        ],
    )
    with open(stderr_log, "w", encoding="utf-8") as errlog:
        async with stdio_client(params, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session, {
                    "audit": AuditLog(audit),
                    "call_log": call_log,
                    "stderr_log": stderr_log,
                }


def _upstream_calls(paths) -> list[dict]:
    if not paths["call_log"].exists():
        return []
    lines = paths["call_log"].read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line and "started" not in line]


def _fixture_pid(paths) -> int:
    for line in paths["call_log"].read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        if "started" in entry:
            return entry["started"]
    raise AssertionError("fixture server never started")


def _text(result) -> str:
    return " ".join(c.text for c in result.content if isinstance(c, TextContent))


async def test_discovery_and_mirrored_tool_list(tmp_path):
    async with gateway_session(tmp_path) as (session, _paths):
        listed = await session.list_tools()
        names = [t.name for t in listed.tools]
        assert names == sorted(
            ["echo", "send_email", "destructive_shell", "fail_tool", "slow_tool",
             "structured_tool"]
        )
        echo = next(t for t in listed.tools if t.name == "echo")
        assert echo.description == "Echo the arguments back"
        assert echo.input_schema["type"] == "object"


async def test_allowed_call_forwards_args_unchanged_exactly_once(tmp_path):
    args = {"nested": {"a": [1, 2, 3]}, "text": "héllo"}
    async with gateway_session(tmp_path) as (session, paths):
        result = await session.call_tool("echo", args)
        assert not result.is_error
        assert _text(result) == "echo:" + json.dumps(args, sort_keys=True)
        calls = _upstream_calls(paths)
        assert calls == [{"tool": "echo", "arguments": args}]
        events = [r["event"] for r in paths["audit"].read_all()]
        assert events == ["allowed", "execution_succeeded"]


async def test_denied_call_never_reaches_upstream(tmp_path):
    async with gateway_session(tmp_path) as (session, paths):
        result = await session.call_tool("destructive_shell", {"cmd": "rm -rf /"})
        assert result.is_error
        assert "denied" in _text(result).lower()
        assert _upstream_calls(paths) == []
        records = paths["audit"].read_all()
        assert [r["event"] for r in records] == ["denied"]
        assert records[0]["category"] == "policy_denied"
        assert records[0]["action_id"] in _text(result)


async def test_approval_required_never_reaches_upstream(tmp_path):
    async with gateway_session(tmp_path) as (session, paths):
        result = await session.call_tool("send_email", {"to": "x@y.z"})
        assert result.is_error
        assert "approval" in _text(result).lower()
        assert _upstream_calls(paths) == []
        records = paths["audit"].read_all()
        assert [r["event"] for r in records] == ["approval_required"]


async def test_upstream_tool_error_forwarded_verbatim(tmp_path):
    async with gateway_session(tmp_path) as (session, paths):
        result = await session.call_tool("fail_tool", {})
        assert result.is_error
        assert _text(result) == "fixture tool failure"
        records = paths["audit"].read_all()
        assert [r["event"] for r in records] == ["allowed", "execution_failed"]
        assert records[1]["category"] == "upstream_tool_error"


async def test_structured_output_preserved(tmp_path):
    async with gateway_session(tmp_path) as (session, _paths):
        result = await session.call_tool("structured_tool", {})
        assert not result.is_error
        assert result.structured_content == {"answer": 42}


async def test_slow_tool_times_out_with_category(tmp_path):
    async with gateway_session(tmp_path, call_timeout=1.0) as (session, paths):
        result = await session.call_tool("slow_tool", {"seconds": 20})
        assert result.is_error
        assert "timeout" in _text(result)
        records = paths["audit"].read_all()
        assert [r["event"] for r in records] == ["allowed", "execution_failed"]
        assert records[1]["category"] == "timeout"


async def test_stdout_is_protocol_only_and_diagnostics_on_stderr(tmp_path):
    async with gateway_session(tmp_path) as (session, paths):
        await session.call_tool("echo", {"x": 1})
    # If the gateway wrote any human-readable output to stdout, the JSON-RPC
    # session above would have failed. Its diagnostics went to stderr:
    stderr = paths["stderr_log"].read_text(encoding="utf-8")
    assert "aegize-mcp" in stderr
    assert "discovered 6 upstream tool(s)" in stderr


async def test_upstream_subprocess_cleaned_up_on_shutdown(tmp_path):
    async with gateway_session(tmp_path) as (session, paths):
        await session.call_tool("echo", {})
        pid = _fixture_pid(paths)
    # Session and gateway have exited; the fixture upstream must be gone too.
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return  # cleaned up
        try:
            # Reap in case it is a zombie child of a dead gateway.
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            pass
        time.sleep(0.2)
    os.kill(pid, signal.SIGKILL)  # do not leak it beyond the test
    raise AssertionError(f"fixture upstream (pid {pid}) was not cleaned up")


async def test_tool_prefix_applied_end_to_end(tmp_path):
    async with gateway_session(tmp_path, extra_flags=("--tool-prefix", "g_")) as (
        session,
        paths,
    ):
        listed = await session.list_tools()
        assert all(t.name.startswith("g_") for t in listed.tools)
        # Policy names the bare tools, so the prefixed name is default-denied —
        # proving policy matches on the *exposed* name.
        result = await session.call_tool("g_echo", {})
        assert result.is_error
        assert _upstream_calls(paths) == []
