"""Policy coverage assessment: which discovered tools does the policy cover?

Default deny means a tool with no rule is silently blocked — safe, but easy to
mistake for a bug when an upstream server ships new tools. This module makes
the drift visible: for a set of discovered (exposed) tool names, report the
decision each would get, which tools are unlisted (default-denied), and which
rules reference tools that no longer exist upstream.

Deliberately free of ``mcp`` imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..action import ToolAction
from ..policy import PermissionPolicy


@dataclass(frozen=True)
class CoverageItem:
    tool: str
    decision: str  # "allow" | "require_approval" | "deny"
    listed: bool  # False -> no rule matched (default deny)


@dataclass(frozen=True)
class CoverageReport:
    agent_id: str
    agent_known: bool
    items: list[CoverageItem] = field(default_factory=list)
    stale_rule_tools: list[str] = field(default_factory=list)

    @property
    def unlisted(self) -> list[str]:
        """Discovered tools with no matching rule — default-denied."""
        return [item.tool for item in self.items if not item.listed]

    @property
    def has_drift(self) -> bool:
        return bool(self.unlisted) or bool(self.stale_rule_tools) or not self.agent_known


def _rule_tools(agent_rules: dict[str, Any]) -> set[str]:
    tools: set[str] = set()
    for section in ("allow", "require_approval", "deny"):
        for rule in agent_rules.get(section, []) or []:
            tool = rule.get("tool")
            if isinstance(tool, str):
                tools.add(tool)
    return tools


def assess_coverage(
    policy: PermissionPolicy, agent_id: str, exposed_names: list[str]
) -> CoverageReport:
    """Evaluate each discovered tool name against the policy for ``agent_id``.

    Names should be the *exposed* names (tool prefix applied), since that is
    what the policy matches at runtime.
    """
    # Internal access within the package: the coverage report needs the raw
    # rule list to detect stale rules, which evaluation alone cannot reveal.
    agent_rules = policy._agents.get(agent_id)
    agent_known = agent_rules is not None

    items: list[CoverageItem] = []
    for name in sorted(exposed_names):
        action = ToolAction(agent_id=agent_id, tool_name=name, operation="call")
        result = policy.evaluate(action)
        items.append(
            CoverageItem(
                tool=name,
                decision=result.decision.value,
                listed=result.matched_rule is not None,
            )
        )

    stale: list[str] = []
    if agent_known:
        discovered = set(exposed_names)
        stale = sorted(_rule_tools(agent_rules) - discovered)

    return CoverageReport(
        agent_id=agent_id, agent_known=agent_known, items=items, stale_rule_tools=stale
    )
