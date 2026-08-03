"""Tests for tool mirroring, name mapping, summaries, redaction, and hashing."""

from __future__ import annotations

import json

from mcp.types import Tool

from aegize.mcp.tool_mapping import (
    ToolMapping,
    argument_hash,
    redact_arguments,
    summarize_arguments,
)


def _tool(name: str, **kwargs) -> Tool:
    return Tool(
        name=name,
        description=kwargs.get("description", f"{name} description"),
        inputSchema=kwargs.get(
            "input_schema",
            {"type": "object", "properties": {"q": {"type": "string"}}},
        ),
    )


# -- mapping ---------------------------------------------------------------


def test_mapping_without_prefix_preserves_names():
    mapping = ToolMapping([_tool("searchDocs"), _tool("validateSpec")])
    assert mapping.exposed_names() == ["searchDocs", "validateSpec"]
    assert mapping.upstream_name("searchDocs") == "searchDocs"
    assert mapping.upstream_name("unknown") is None


def test_mapping_with_prefix():
    mapping = ToolMapping([_tool("searchDocs")], tool_prefix="ext_")
    assert mapping.exposed_names() == ["ext_searchDocs"]
    assert mapping.upstream_name("ext_searchDocs") == "searchDocs"
    # The bare upstream name is not exposed.
    assert mapping.upstream_name("searchDocs") is None


def test_mirrored_tools_preserve_schema_and_description():
    schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }
    tool = _tool("readFile", description="Reads a file", input_schema=schema)
    mapping = ToolMapping([tool], tool_prefix="g_")
    (mirrored,) = mapping.mirrored_tools()
    assert mirrored.name == "g_readFile"
    assert mirrored.description == "Reads a file"
    assert mirrored.input_schema == schema


def test_mapping_is_deterministic():
    tools = [_tool("b"), _tool("a")]
    m1 = ToolMapping(tools)
    m2 = ToolMapping(list(tools))
    assert m1.exposed_names() == m2.exposed_names()


# -- summaries and redaction ----------------------------------------------


def test_summarize_is_deterministic_and_sorted():
    args = {"b": 2, "a": 1}
    assert summarize_arguments(args) == summarize_arguments({"a": 1, "b": 2})
    assert summarize_arguments(args).index("a=") < summarize_arguments(args).index("b=")


def test_summarize_is_bounded():
    args = {"text": "x" * 10_000}
    assert len(summarize_arguments(args)) <= 200


def test_sensitive_keys_redacted_in_summary():
    args = {"query": "hello", "api_key": "sk-super-secret", "PASSWORD": "hunter2"}
    summary = summarize_arguments(args)
    assert "hello" in summary
    assert "sk-super-secret" not in summary
    assert "hunter2" not in summary
    assert "[redacted]" in summary


def test_redact_arguments_recurses():
    args = {"outer": {"token": "abc123", "safe": "ok"}, "auth": "basic xyz"}
    redacted = redact_arguments(args)
    assert redacted["outer"]["token"] == "[redacted]"
    assert redacted["outer"]["safe"] == "ok"
    assert redacted["auth"] == "[redacted]"
    # Original is untouched.
    assert args["outer"]["token"] == "abc123"


def test_argument_hash_is_stable_and_order_independent():
    h1 = argument_hash({"a": 1, "b": [1, 2]})
    h2 = argument_hash({"b": [1, 2], "a": 1})
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex
    assert argument_hash({"a": 2}) != h1


def test_argument_hash_survives_non_json_values():
    # Non-JSON-serializable values must not crash hashing.
    h = argument_hash({"when": object()})
    assert isinstance(h, str) and len(h) == 64


def test_summary_never_renders_raw_json_of_sensitive_nested_values():
    args = {"config": {"password": "deep-secret"}}
    summary = summarize_arguments(args)
    assert "deep-secret" not in summary
    assert json.dumps(args) != summary
