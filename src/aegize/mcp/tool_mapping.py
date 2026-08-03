"""Tool mirroring, name mapping, argument summaries, redaction, and hashing.

This module is deliberately free of ``mcp`` imports: it operates on the SDK's
pydantic ``Tool`` models duck-typed via ``model_copy``, so the pure logic is
importable and testable anywhere.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

SUMMARY_LIMIT = 200
REDACTED = "[redacted]"

# Keys whose values are never written to summaries or the audit log.
_SENSITIVE_KEY_RE = re.compile(
    r"(?i)(pass(word)?|secret|token|api[_-]?key|auth|credential|private[_-]?key|session)"
)

_MAX_REDACT_DEPTH = 8


def is_sensitive_name(name: str) -> bool:
    """True if a key or tool name looks credential-bearing (password/token/…)."""
    return bool(_SENSITIVE_KEY_RE.search(name))


_is_sensitive = is_sensitive_name


def redact_arguments(arguments: dict[str, Any], _depth: int = 0) -> dict[str, Any]:
    """Return a copy of ``arguments`` with sensitive-looking values replaced.

    Redaction is by key name (password/secret/token/key/auth/credential/...),
    applied recursively through nested mappings. The input is never mutated.
    """
    if _depth >= _MAX_REDACT_DEPTH:
        return {k: REDACTED for k in arguments}
    redacted: dict[str, Any] = {}
    for key, value in arguments.items():
        if _is_sensitive(str(key)):
            redacted[key] = REDACTED
        elif isinstance(value, dict):
            redacted[key] = redact_arguments(value, _depth + 1)
        else:
            redacted[key] = value
    return redacted


def _truncate(text: str, limit: int = SUMMARY_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def summarize_arguments(
    arguments: dict[str, Any], limit: int = SUMMARY_LIMIT, *, redact_all: bool = False
) -> str:
    """A deterministic, bounded, redacted rendering of a call's arguments.

    Keys are sorted, sensitive values are redacted, and the result is truncated
    to ``limit`` characters. With ``redact_all`` (used when the *tool name*
    itself looks credential-bearing, e.g. ``setCredential``) every value is
    redacted regardless of key name. Full argument values are never emitted for
    sensitive keys; correlation is possible via :func:`argument_hash`.
    """
    if redact_all:
        redacted: dict[str, Any] = {key: REDACTED for key in arguments}
    else:
        redacted = redact_arguments(arguments)
    parts = [f"{key}={redacted[key]!r}" for key in sorted(redacted)]
    return _truncate(", ".join(parts), limit)


def argument_hash(arguments: dict[str, Any]) -> str:
    """SHA-256 hex digest of the canonical JSON encoding of the arguments.

    The hash covers the *unredacted* arguments so identical calls correlate in
    the audit log without storing their values. Non-JSON values are rendered
    via ``str`` so hashing never fails.
    """
    canonical = json.dumps(
        arguments, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ToolMapping:
    """Deterministic mapping between exposed and upstream tool names.

    Exposed name = ``tool_prefix + upstream name``. Tools are kept in sorted
    upstream-name order so the mapping (and ``tools/list`` output) is
    deterministic regardless of upstream ordering.
    """

    def __init__(self, tools: list[Any], tool_prefix: str = "") -> None:
        self._prefix = tool_prefix
        self._tools = sorted(tools, key=lambda t: t.name)
        self._by_exposed = {tool_prefix + tool.name: tool for tool in self._tools}

    def exposed_names(self) -> list[str]:
        return [self._prefix + tool.name for tool in self._tools]

    def upstream_name(self, exposed_name: str) -> str | None:
        """The upstream name behind an exposed name, or None if unknown."""
        tool = self._by_exposed.get(exposed_name)
        return tool.name if tool is not None else None

    def mirrored_tools(self) -> list[Any]:
        """Upstream tools re-published under their exposed names.

        Everything except the name — description, input/output schema,
        annotations, metadata — is preserved verbatim via ``model_copy``.
        """
        return [
            tool.model_copy(update={"name": self._prefix + tool.name})
            for tool in self._tools
        ]
