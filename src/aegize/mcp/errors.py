"""Typed error categories for the MCP policy gateway.

The gateway distinguishes *why* a call did not run instead of collapsing every
failure into a policy denial. Each error carries a stable ``category`` string
that is written to the audit log and included in the MCP error result returned
to the host.
"""

from __future__ import annotations

from ..exceptions import AegizeError

# Stable category identifiers (audit + host-facing).
CATEGORY_POLICY_DENIED = "policy_denied"
CATEGORY_APPROVAL_REQUIRED = "approval_required"
CATEGORY_MALFORMED_REQUEST = "malformed_request"
CATEGORY_POLICY_UNAVAILABLE = "policy_unavailable"
CATEGORY_UPSTREAM_UNAVAILABLE = "upstream_unavailable"
CATEGORY_UPSTREAM_TOOL_ERROR = "upstream_tool_error"
CATEGORY_TIMEOUT = "timeout"
CATEGORY_INTERNAL = "internal_gateway_error"


class GatewayError(AegizeError):
    """Base class for gateway-originated failures."""

    category = CATEGORY_INTERNAL


class GatewayConfigError(GatewayError):
    """Raised when the gateway configuration is missing, unreadable, or invalid."""


class MalformedRequestError(GatewayError):
    """The host sent a tool call the gateway cannot interpret safely."""

    category = CATEGORY_MALFORMED_REQUEST


class PolicyUnavailableError(GatewayError):
    """Policy evaluation itself failed at runtime. The call is denied (fail closed)."""

    category = CATEGORY_POLICY_UNAVAILABLE


class UpstreamUnavailableError(GatewayError):
    """The upstream server or session is unreachable or has terminated."""

    category = CATEGORY_UPSTREAM_UNAVAILABLE


class UpstreamToolError(GatewayError):
    """The upstream server answered the call with a protocol-level error."""

    category = CATEGORY_UPSTREAM_TOOL_ERROR


class UpstreamTimeoutError(GatewayError):
    """The upstream call exceeded the configured timeout."""

    category = CATEGORY_TIMEOUT
