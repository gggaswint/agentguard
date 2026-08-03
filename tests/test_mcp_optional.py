"""The MCP gateway is optional: without the extra, aegize-mcp must fail helpfully.

These tests only run when the ``mcp`` SDK is *not* installed (e.g. the base
package on Python 3.9) — the inverse of ``tests/mcp_gateway/``.
"""

from __future__ import annotations

import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("mcp") is not None,
    reason="only meaningful without the aegize[mcp] extra",
)


def test_proxy_without_extra_fails_helpfully(capsys):
    from aegize.mcp.cli import main

    code = main(
        ["proxy", "--policy", "p.yaml", "--agent-id", "a", "--owner", "o",
         "--audit-log", "a.jsonl", "--", "some-server"]
    )
    assert code == 2
    err = capsys.readouterr().err
    assert 'aegize[mcp]' in err
    assert "3.10" in err


def test_inspect_without_extra_fails_helpfully(capsys):
    from aegize.mcp.cli import main

    code = main(["inspect", "--", "some-server"])
    assert code == 2
    assert 'aegize[mcp]' in capsys.readouterr().err


def test_core_package_imports_without_mcp():
    import aegize

    assert aegize.__version__
    # Config and error types are importable without the SDK…
    from aegize.mcp import MCPGatewayConfig  # noqa: F401

    # …but the gateway itself explains what is missing.
    with pytest.raises(ImportError, match=r"aegize\[mcp\]"):
        from aegize.mcp import MCPGateway  # noqa: F401
