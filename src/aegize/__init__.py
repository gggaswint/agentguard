"""Aegize: infrastructure for autonomous AI agents.

Aegize provides the runtime governance layer between an agent and its tools:
identity, policy, permissions, approval workflows, and audit. Every tool call
carries an identity, is evaluated against policy, and is written to an
append-only audit log before it is allowed to run.
"""

from __future__ import annotations

from .action import RISK_LEVELS, ToolAction
from .audit import AuditLog
from .context import (
    GuardContext,
    clear_default_context,
    get_default_context,
    set_default_context,
)
from .decorators import GuardedFunction, GuardSpec, guard, guarded_tool
from .exceptions import (
    AegizeError,
    ApprovalRequired,
    PolicyDenied,
    PolicyLoadError,
)
from .guarded_tool import GuardedTool
from .identity import AgentIdentity
from .policy import Decision, PermissionPolicy, PolicyResult

__version__ = "0.4.2"

__all__ = [
    "__version__",
    # primitives
    "AgentIdentity",
    "ToolAction",
    "RISK_LEVELS",
    # policy
    "PermissionPolicy",
    "PolicyResult",
    "Decision",
    # enforcement + audit
    "GuardedTool",
    "AuditLog",
    # ergonomics (v0.2)
    "guarded_tool",
    "guard",
    "GuardedFunction",
    "GuardSpec",
    "GuardContext",
    "set_default_context",
    "get_default_context",
    "clear_default_context",
    # exceptions
    "AegizeError",
    "PolicyDenied",
    "ApprovalRequired",
    "PolicyLoadError",
]
