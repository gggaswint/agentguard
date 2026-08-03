"""Aegize MCP policy gateway (optional; requires ``pip install "aegize[mcp]"``).

A local stdio proxy that sits between an MCP host and an upstream MCP server,
routing every tool call through the Aegize runtime — identity, policy,
approval gate, audit — and forwarding only allowed calls. See RFC 0009.

The ``mcp`` SDK requires Python 3.10+; the core ``aegize`` package does not
import this subpackage.
"""

from __future__ import annotations

from .config import GatewaySettings, MCPGatewayConfig, UpstreamConfig
from .errors import (
    GatewayConfigError,
    GatewayError,
    MalformedRequestError,
    PolicyUnavailableError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)

__all__ = [
    "MCPGateway",
    "MCPGatewayConfig",
    "UpstreamConfig",
    "GatewaySettings",
    "GatewayError",
    "GatewayConfigError",
    "MalformedRequestError",
    "PolicyUnavailableError",
    "UpstreamTimeoutError",
    "UpstreamUnavailableError",
]


def __getattr__(name: str):
    # MCPGateway pulls in the mcp SDK; import it lazily so config/errors stay
    # importable (with a helpful message) when the extra is not installed.
    if name == "MCPGateway":
        try:
            from .gateway import MCPGateway
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise ImportError(
                "the Aegize MCP gateway requires the optional 'mcp' extra on "
                "Python 3.10+: pip install \"aegize[mcp]\""
            ) from exc
        return MCPGateway
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
