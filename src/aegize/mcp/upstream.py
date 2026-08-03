"""Client side of the gateway: the upstream stdio MCP server.

Launches the configured upstream server as a subprocess (always an argv list —
no shell), completes the MCP initialization lifecycle, and exposes
``list_tools`` / ``call_tool`` with timeouts and typed error classification.
Subprocess teardown (terminate → wait → force-kill) is handled by the official
SDK's stdio transport when the context exits.
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any

import anyio
from mcp.client.stdio import stdio_client
from mcp.types import (
    CONNECTION_CLOSED,
    REQUEST_TIMEOUT,
    CallToolResult,
    PaginatedRequestParams,
    Tool,
)

from mcp import ClientSession, MCPError, StdioServerParameters

from .config import UpstreamConfig
from .errors import UpstreamTimeoutError, UpstreamToolError, UpstreamUnavailableError

_ERROR_LIMIT = 200


def _bounded(text: str, limit: int = _ERROR_LIMIT) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def classify_mcp_error(exc: MCPError, *, context: str) -> Exception:
    """Map an SDK ``MCPError`` to the gateway's typed error taxonomy."""
    message = _bounded(f"{context}: {exc.message}")
    if exc.code == REQUEST_TIMEOUT:
        return UpstreamTimeoutError(message)
    if exc.code == CONNECTION_CLOSED:
        return UpstreamUnavailableError(message)
    return UpstreamToolError(message)


class UpstreamClient:
    """Async context manager owning the upstream subprocess and session."""

    def __init__(
        self,
        config: UpstreamConfig,
        *,
        startup_timeout_seconds: float,
        call_timeout_seconds: float,
    ) -> None:
        self._config = config
        self._startup_timeout = startup_timeout_seconds
        self._call_timeout = call_timeout_seconds
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> UpstreamClient:
        params = StdioServerParameters(
            command=self._config.command,
            args=list(self._config.args),
            # The SDK merges this with its default inherited environment; the
            # values are passed to the subprocess but never logged by Aegize.
            env=dict(self._config.env) or None,
            cwd=self._config.cwd,
        )
        self._stack = AsyncExitStack()
        try:
            read, write = await self._stack.enter_async_context(stdio_client(params))
            session = await self._stack.enter_async_context(ClientSession(read, write))
            with anyio.fail_after(self._startup_timeout):
                await session.initialize()
        except TimeoutError:
            await self.__aexit__(None, None, None)
            raise UpstreamUnavailableError(
                f"upstream server did not initialize within {self._startup_timeout}s"
            ) from None
        except (MCPError, OSError, anyio.BrokenResourceError, anyio.ClosedResourceError) as exc:
            await self.__aexit__(None, None, None)
            raise UpstreamUnavailableError(
                _bounded(f"could not start upstream server: {exc}")
            ) from exc
        self._session = session
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        self._session = None
        if self._stack is not None:
            stack, self._stack = self._stack, None
            await stack.aclose()

    def _require_session(self) -> ClientSession:
        if self._session is None:
            raise UpstreamUnavailableError("upstream session is not connected")
        return self._session

    async def list_tools(self) -> list[Tool]:
        """The upstream tool list (all pages), within the startup timeout."""
        session = self._require_session()
        tools: list[Tool] = []
        cursor: str | None = None
        try:
            with anyio.fail_after(self._startup_timeout):
                while True:
                    params = (
                        PaginatedRequestParams(cursor=cursor) if cursor is not None else None
                    )
                    result = await session.list_tools(params=params)
                    tools.extend(result.tools)
                    cursor = result.next_cursor
                    if cursor is None:
                        return tools
        except TimeoutError:
            raise UpstreamTimeoutError(
                f"upstream tool discovery timed out after {self._startup_timeout}s"
            ) from None
        except MCPError as exc:
            raise classify_mcp_error(exc, context="tool discovery failed") from exc

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        """Forward one tool call upstream, bounded by the call timeout."""
        session = self._require_session()
        try:
            result = await session.call_tool(
                name, arguments, read_timeout_seconds=self._call_timeout
            )
        except MCPError as exc:
            raise classify_mcp_error(exc, context=f"tool '{name}'") from exc
        except (anyio.BrokenResourceError, anyio.ClosedResourceError) as exc:
            raise UpstreamUnavailableError(
                _bounded(f"upstream connection lost during tool '{name}': {exc}")
            ) from exc
        if not isinstance(result, CallToolResult):  # pragma: no cover - defensive
            raise UpstreamToolError(
                f"upstream returned an unexpected result type for tool '{name}'"
            )
        return result
