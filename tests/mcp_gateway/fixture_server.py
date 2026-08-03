"""A tiny stdio MCP server used by the gateway integration tests.

Not a pytest module — launched as a subprocess by the gateway under test:

    python tests/mcp_gateway/fixture_server.py <call_log_path>

Every tool invocation appends a JSON line to ``call_log_path`` so tests can
prove exactly how many calls reached upstream (and with which arguments). On
startup the server writes a ``{"started": <pid>}`` line so tests can verify
the subprocess is cleaned up afterwards.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

import anyio
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

CALL_LOG = sys.argv[1] if len(sys.argv) > 1 else None

OBJECT_SCHEMA = {"type": "object", "additionalProperties": True}

TOOLS = [
    Tool(name="echo", description="Echo the arguments back", input_schema=OBJECT_SCHEMA),
    Tool(name="send_email", description="Pretend to send an email", input_schema=OBJECT_SCHEMA),
    Tool(
        name="destructive_shell",
        description="Pretend to run a destructive shell command",
        input_schema=OBJECT_SCHEMA,
    ),
    Tool(name="fail_tool", description="Always fails", input_schema=OBJECT_SCHEMA),
    Tool(name="slow_tool", description="Sleeps before answering", input_schema=OBJECT_SCHEMA),
    Tool(
        name="structured_tool",
        description="Returns structured output",
        input_schema=OBJECT_SCHEMA,
        output_schema={
            "type": "object",
            "properties": {"answer": {"type": "integer"}},
            "required": ["answer"],
        },
    ),
]


def _log(entry: dict[str, Any]) -> None:
    if CALL_LOG:
        with open(CALL_LOG, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")


def _text_result(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)])


async def on_list_tools(_ctx: Any, _params: Any) -> ListToolsResult:
    return ListToolsResult(tools=TOOLS)


async def on_call_tool(_ctx: Any, params: Any) -> CallToolResult:
    name = params.name
    arguments = params.arguments or {}
    _log({"tool": name, "arguments": arguments})

    if name == "echo":
        return _text_result("echo:" + json.dumps(arguments, sort_keys=True))
    if name == "send_email":
        return _text_result("email sent")
    if name == "destructive_shell":
        return _text_result("shell executed")
    if name == "fail_tool":
        return CallToolResult(
            content=[TextContent(type="text", text="fixture tool failure")],
            is_error=True,
        )
    if name == "slow_tool":
        await asyncio.sleep(float(arguments.get("seconds", 10)))
        return _text_result("finally done")
    if name == "structured_tool":
        return CallToolResult(
            content=[TextContent(type="text", text='{"answer": 42}')],
            structured_content={"answer": 42},
        )
    return CallToolResult(
        content=[TextContent(type="text", text=f"unknown tool {name}")], is_error=True
    )


async def main() -> None:
    _log({"started": os.getpid()})
    server = Server("fixture-server", version="0.0.1",
                    on_list_tools=on_list_tools, on_call_tool=on_call_tool)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    anyio.run(main)
