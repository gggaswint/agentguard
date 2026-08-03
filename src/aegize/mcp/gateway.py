"""The MCP policy gateway: an MCP server that guards an upstream MCP server.

The gateway serves the host over stdio, mirrors the upstream server's tools,
and routes every ``tools/call`` through the Aegize runtime. The order of
operations per call is identical to :class:`aegize.GuardedTool`:

1. Build a :class:`ToolAction` describing the attempt.
2. Evaluate it against the :class:`PermissionPolicy` (fail closed on error).
3. Audit the decision **before** any forwarding.
4. Deny / approval / malformed / unknown -> a valid MCP error result; the
   upstream server is never contacted.
   Allow -> forward the original arguments unchanged, return the upstream
   result unchanged, then audit success or failure.

stdout is the MCP protocol channel: nothing in this module prints to stdout.
Diagnostics go to stderr via ``logging``.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from .. import __version__
from ..action import ToolAction
from ..audit import (
    EVENT_ALLOWED,
    EVENT_APPROVAL_REQUIRED,
    EVENT_DENIED,
    EVENT_EXECUTION_FAILED,
    EVENT_EXECUTION_SUCCEEDED,
    AuditLog,
)
from ..identity import AgentIdentity
from ..policy import Decision, PermissionPolicy
from .config import MCPGatewayConfig
from .errors import (
    CATEGORY_INTERNAL,
    CATEGORY_MALFORMED_REQUEST,
    CATEGORY_POLICY_DENIED,
    CATEGORY_POLICY_UNAVAILABLE,
    CATEGORY_UPSTREAM_TOOL_ERROR,
    GatewayError,
)
from .tool_mapping import (
    ToolMapping,
    argument_hash,
    is_sensitive_name,
    summarize_arguments,
)
from .upstream import UpstreamClient

logger = logging.getLogger("aegize.mcp")

GATEWAY_NAME = "aegize-mcp-gateway"
_SUMMARY_LIMIT = 200


def _truncate(text: str, limit: int = _SUMMARY_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _result_summary(result: CallToolResult) -> str:
    texts = [c.text for c in result.content if isinstance(c, TextContent)]
    summary = " ".join(texts) if texts else f"{len(result.content)} content item(s)"
    if result.structured_content is not None:
        keys = sorted(result.structured_content) if isinstance(
            result.structured_content, dict
        ) else []
        summary += f" [structured: {keys}]"
    return _truncate(summary)


class MCPGateway:
    """Guards one upstream stdio MCP server behind Aegize policy and audit."""

    def __init__(self, config: MCPGatewayConfig) -> None:
        self.config = config
        self._policy: Any = None
        self._audit: AuditLog | None = None
        self._mapping: ToolMapping | None = None
        self._upstream: Any = None

    @classmethod
    def from_config(cls, path: str | Path) -> MCPGateway:
        return cls(MCPGatewayConfig.from_yaml(path))

    # -- wiring ----------------------------------------------------------

    def _bind(self, *, policy: Any, audit: AuditLog, mapping: ToolMapping, upstream: Any) -> None:
        """Attach the runtime collaborators (also used by unit tests)."""
        self._policy = policy
        self._audit = audit
        self._mapping = mapping
        self._upstream = upstream

    def build_identity(self) -> AgentIdentity:
        return AgentIdentity(
            agent_id=self.config.agent_id,
            name=self.config.agent_name,
            owner=self.config.owner,
            environment=self.config.environment,
        )

    # -- action construction --------------------------------------------

    def _build_action(
        self, exposed_name: str, upstream_name: str | None, arguments: dict[str, Any]
    ) -> ToolAction:
        metadata: dict[str, Any] = {
            "upstream_tool_name": upstream_name or exposed_name,
            "mcp_transport": "stdio",
            "argument_keys": sorted(str(k) for k in arguments),
            "argument_hash": argument_hash(arguments),
            "gateway_version": __version__,
            "upstream_command": os.path.basename(self.config.upstream.command),
            "environment": self.config.environment,
            # String argument values may represent paths; surface them so the
            # policy's `paths` allowlists apply. Stripped from the audit copy.
            "candidate_paths": [v for v in arguments.values() if isinstance(v, str)],
        }
        return ToolAction(
            agent_id=self.config.agent_id,
            tool_name=exposed_name,
            operation="call",
            # If the tool name itself looks credential-bearing (setCredential,
            # storeToken, …), redact every argument value, not just sensitive
            # keys — the argument hash still allows correlation.
            input_summary=summarize_arguments(
                arguments, redact_all=is_sensitive_name(exposed_name)
            ),
            metadata=metadata,
        )

    @staticmethod
    def _audit_extra(action: ToolAction, category: str | None = None) -> dict[str, Any]:
        metadata = {k: v for k, v in action.metadata.items() if k != "candidate_paths"}
        extra: dict[str, Any] = {"metadata": metadata}
        if category is not None:
            extra["category"] = category
        return extra

    def _error_result(
        self, message: str, *, category: str, action_id: str | None = None
    ) -> CallToolResult:
        correlation = f", action_id={action_id}" if action_id else ""
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=_truncate(f"{message} (category={category}{correlation})", 400),
                )
            ],
            is_error=True,
        )

    # -- handlers --------------------------------------------------------

    async def handle_list_tools(self) -> list[Tool]:
        assert self._mapping is not None
        return self._mapping.mirrored_tools()

    async def handle_call_tool(self, name: str, arguments: Any) -> CallToolResult:
        """Evaluate and (only if allowed) forward one tool call.

        Never raises: every failure mode maps to a valid MCP error result so
        the host session stays healthy.
        """
        try:
            return await self._guarded_call(name, arguments)
        except Exception:  # pragma: no cover - absolute backstop
            logger.exception("internal gateway error handling tool %r", name)
            return self._error_result(
                f"Aegize gateway internal error while handling tool '{name}'; "
                "the call was not completed",
                category=CATEGORY_INTERNAL,
            )

    async def _guarded_call(self, name: str, arguments: Any) -> CallToolResult:
        assert self._audit is not None and self._mapping is not None
        audit = self._audit

        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            action = self._build_action(name, self._mapping.upstream_name(name), {})
            reason = "malformed request: tool arguments must be a JSON object"
            audit.record(
                action,
                EVENT_DENIED,
                reason=reason,
                extra=self._audit_extra(action, CATEGORY_MALFORMED_REQUEST),
            )
            return self._error_result(
                f"Aegize rejected tool call '{name}': {reason}",
                category=CATEGORY_MALFORMED_REQUEST,
                action_id=action.action_id,
            )

        upstream_name = self._mapping.upstream_name(name)
        action = self._build_action(name, upstream_name, arguments)

        # Unknown tools are denied without ever contacting upstream.
        if upstream_name is None:
            reason = f"unknown tool '{name}' (not discovered at startup; default deny)"
            audit.record(
                action,
                EVENT_DENIED,
                reason=reason,
                extra=self._audit_extra(action, CATEGORY_POLICY_DENIED),
            )
            return self._error_result(
                f"Aegize denied tool call '{name}': {reason}",
                category=CATEGORY_POLICY_DENIED,
                action_id=action.action_id,
            )

        # Policy evaluation fails closed.
        try:
            result = self._policy.evaluate(action)
        except Exception as exc:
            logger.exception("policy evaluation failed for tool %r", name)
            reason = _truncate(f"policy evaluation failed: {exc}")
            audit.record(
                action,
                EVENT_DENIED,
                reason=reason,
                extra=self._audit_extra(action, CATEGORY_POLICY_UNAVAILABLE),
            )
            return self._error_result(
                f"Aegize denied tool call '{name}': policy is unavailable "
                "(fail closed)",
                category=CATEGORY_POLICY_UNAVAILABLE,
                action_id=action.action_id,
            )

        if result.decision is Decision.DENY:
            audit.record(
                action,
                EVENT_DENIED,
                reason=result.reason,
                extra=self._audit_extra(action, CATEGORY_POLICY_DENIED),
            )
            return self._error_result(
                f"Aegize denied tool call '{name}': {result.reason}",
                category=CATEGORY_POLICY_DENIED,
                action_id=action.action_id,
            )

        if result.decision is Decision.REQUIRE_APPROVAL:
            audit.record(
                action,
                EVENT_APPROVAL_REQUIRED,
                reason=result.reason,
                extra=self._audit_extra(action, "approval_required"),
            )
            return self._error_result(
                f"Aegize: tool call '{name}' requires approval and was not "
                f"executed ({result.reason}). Approval is a hard gate; there is "
                "no automatic approval workflow",
                category="approval_required",
                action_id=action.action_id,
            )

        # Allowed: audit the authorization *before* forwarding upstream.
        audit.record(
            action, EVENT_ALLOWED, reason=result.reason, extra=self._audit_extra(action)
        )
        try:
            upstream_result = await self._upstream.call_tool(upstream_name, arguments)
        except GatewayError as exc:
            audit.record(
                action,
                EVENT_EXECUTION_FAILED,
                error=_truncate(str(exc)),
                extra=self._audit_extra(action, exc.category),
            )
            return self._error_result(
                f"Aegize: tool call '{name}' failed upstream: {_truncate(str(exc))}",
                category=exc.category,
                action_id=action.action_id,
            )
        except Exception as exc:
            logger.exception("unexpected error forwarding tool %r", name)
            audit.record(
                action,
                EVENT_EXECUTION_FAILED,
                error=_truncate(repr(exc)),
                extra=self._audit_extra(action, CATEGORY_INTERNAL),
            )
            return self._error_result(
                f"Aegize gateway internal error while forwarding tool '{name}'",
                category=CATEGORY_INTERNAL,
                action_id=action.action_id,
            )

        if upstream_result.is_error:
            # The upstream tool reported failure. Forward its result unchanged
            # (the host should see exactly what the tool said) and record it.
            audit.record(
                action,
                EVENT_EXECUTION_FAILED,
                error=_result_summary(upstream_result),
                extra=self._audit_extra(action, CATEGORY_UPSTREAM_TOOL_ERROR),
            )
            return upstream_result

        audit.record(
            action,
            EVENT_EXECUTION_SUCCEEDED,
            result_summary=_result_summary(upstream_result),
            extra=self._audit_extra(action),
        )
        return upstream_result

    # -- serving ----------------------------------------------------------

    def _build_server(self) -> Server:
        async def on_list_tools(_ctx: Any, _params: Any) -> ListToolsResult:
            return ListToolsResult(tools=await self.handle_list_tools())

        async def on_call_tool(_ctx: Any, params: Any) -> CallToolResult:
            return await self.handle_call_tool(params.name, params.arguments)

        return Server(
            GATEWAY_NAME,
            version=__version__,
            instructions=(
                "Aegize MCP policy gateway. Tool calls are evaluated against an "
                "Aegize policy (default deny); denied and approval-gated calls "
                "never reach the upstream server, and every attempt is audited."
            ),
            on_list_tools=on_list_tools,
            on_call_tool=on_call_tool,
        )

    async def run_stdio(self) -> None:
        """Start the upstream server, mirror its tools, and serve the host."""
        config = self.config
        # Fail fast, before touching the upstream: policy, identity, audit.
        policy = PermissionPolicy.from_yaml(config.policy_file)
        self.build_identity()  # validates identity fields
        audit = AuditLog(config.audit_log)

        logger.info(
            "starting gateway: agent=%s upstream=%s", config.agent_id,
            os.path.basename(config.upstream.command),
        )
        async with UpstreamClient(
            config.upstream,
            startup_timeout_seconds=config.gateway.startup_timeout_seconds,
            call_timeout_seconds=config.gateway.call_timeout_seconds,
        ) as upstream:
            tools = await upstream.list_tools()
            mapping = ToolMapping(tools, tool_prefix=config.gateway.tool_prefix)
            logger.info("discovered %d upstream tool(s): %s",
                        len(tools), ", ".join(mapping.exposed_names()))
            self._bind(policy=policy, audit=audit, mapping=mapping, upstream=upstream)

            server = self._build_server()
            async with stdio_server() as (read_stream, write_stream):
                await server.run(
                    read_stream, write_stream, server.create_initialization_options()
                )
        logger.info("gateway stopped")
