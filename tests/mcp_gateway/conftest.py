"""Fixtures for the MCP gateway tests.

This directory is only collected when the optional ``mcp`` SDK is installed —
see ``tests/conftest.py``. Async tests run on asyncio via anyio's pytest
plugin (anyio ships with the MCP SDK).
"""

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"
