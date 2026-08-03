"""Tests for policy coverage assessment (drift detection)."""

from __future__ import annotations

from aegize import PermissionPolicy
from aegize.mcp.coverage import assess_coverage

POLICY = PermissionPolicy.from_dict(
    {
        "agents": {
            "test-agent": {
                "allow": [{"tool": "echo", "operations": ["call"]}],
                "require_approval": [{"tool": "send_email", "operations": ["call"]}],
                "deny": [
                    {"tool": "destructive_shell", "operations": ["call"]},
                    {"tool": "removed_tool", "operations": ["call"]},
                ],
            }
        }
    }
)

DISCOVERED = ["echo", "send_email", "destructive_shell", "new_tool", "other_new"]


def test_listed_tools_report_their_decision():
    report = assess_coverage(POLICY, "test-agent", DISCOVERED)
    by_tool = {item.tool: item for item in report.items}
    assert by_tool["echo"].decision == "allow" and by_tool["echo"].listed
    assert by_tool["send_email"].decision == "require_approval"
    assert by_tool["destructive_shell"].decision == "deny"
    assert by_tool["destructive_shell"].listed


def test_unlisted_tools_are_flagged():
    report = assess_coverage(POLICY, "test-agent", DISCOVERED)
    assert report.unlisted == ["new_tool", "other_new"]
    by_tool = {item.tool: item for item in report.items}
    assert by_tool["new_tool"].decision == "deny"
    assert not by_tool["new_tool"].listed


def test_stale_rules_are_flagged():
    # "removed_tool" has a deny rule but was not discovered upstream.
    report = assess_coverage(POLICY, "test-agent", DISCOVERED)
    assert report.stale_rule_tools == ["removed_tool"]


def test_unknown_agent_reported():
    report = assess_coverage(POLICY, "stranger", DISCOVERED)
    assert not report.agent_known
    assert report.unlisted == sorted(DISCOVERED)


def test_no_drift_is_clean():
    report = assess_coverage(
        POLICY, "test-agent", ["echo", "send_email", "destructive_shell", "removed_tool"]
    )
    assert report.unlisted == []
    assert report.stale_rule_tools == []
    assert not report.has_drift


def test_drift_property():
    assert assess_coverage(POLICY, "test-agent", DISCOVERED).has_drift
    assert assess_coverage(POLICY, "stranger", ["echo"]).has_drift
