"""The ``aegize-mcp`` command-line interface.

Commands:

    aegize-mcp proxy [flags] [--config FILE] -- <upstream command> [args...]
    aegize-mcp inspect -- <upstream command> [args...]

Everything after the first ``--`` is the upstream MCP server's argv (never
interpreted by a shell). ``proxy`` serves MCP on stdout, so all diagnostics go
to stderr. Flags override config-file values.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import logging
import signal
import sys

from ..exceptions import PolicyLoadError
from ..policy import PermissionPolicy
from .config import MCPGatewayConfig, UpstreamConfig
from .coverage import assess_coverage
from .errors import GatewayConfigError, GatewayError


def _require_mcp_sdk() -> bool:
    """True if the optional MCP SDK is importable; otherwise explain on stderr."""
    if importlib.util.find_spec("mcp") is not None:
        return True
    print(
        "aegize-mcp error: the MCP gateway requires the optional 'mcp' extra "
        "(Python 3.10+).\n"
        "  In a 3.10+ environment:  pip install \"aegize[mcp]\"\n"
        "  On any machine (isolated, fetches its own interpreter):\n"
        "    uv tool install --python 3.12 \"aegize[mcp]\"\n"
        "    # or: pipx install --python 3.12 \"aegize[mcp]\"\n"
        "  Your project's own Python version does not matter — the gateway "
        "runs as a separate process.",
        file=sys.stderr,
    )
    return False


def split_upstream_argv(argv: list[str]) -> tuple[list[str], list[str]]:
    """Split ``argv`` at the first ``--`` into (own args, upstream argv)."""
    if "--" in argv:
        index = argv.index("--")
        return argv[:index], argv[index + 1 :]
    return list(argv), []


def build_config(
    *,
    config: str | None,
    policy: str | None,
    agent_id: str | None,
    agent_name: str | None,
    owner: str | None,
    environment: str | None,
    audit_log: str | None,
    tool_prefix: str | None,
    startup_timeout: float | None,
    call_timeout: float | None,
    upstream_argv: list[str],
) -> MCPGatewayConfig:
    """Combine a config file (if any) with CLI flags; flags win."""
    if config is not None:
        base = MCPGatewayConfig.from_yaml(config)
        return base.with_overrides(
            agent_id=agent_id,
            agent_name=agent_name,
            owner=owner,
            environment=environment,
            policy_file=policy,
            audit_log=audit_log,
            tool_prefix=tool_prefix,
            startup_timeout_seconds=startup_timeout,
            call_timeout_seconds=call_timeout,
            upstream_argv=upstream_argv or None,
        )

    if not upstream_argv:
        raise GatewayConfigError(
            "no upstream server configured: pass it after '--' or use --config"
        )
    data: dict = {
        "agent": {
            "id": agent_id,
            "name": agent_name,
            "owner": owner,
            "environment": environment or "dev",
        },
        "policy": policy,
        "audit_log": audit_log,
        "upstream": {"command": upstream_argv[0], "args": upstream_argv[1:]},
        "gateway": {
            "tool_prefix": tool_prefix,
            "startup_timeout_seconds": startup_timeout,
            "call_timeout_seconds": call_timeout,
        },
    }
    # Drop unset values so config defaults apply.
    data["agent"] = {k: v for k, v in data["agent"].items() if v is not None}
    data["gateway"] = {k: v for k, v in data["gateway"].items() if v is not None}
    data = {k: v for k, v in data.items() if v is not None}
    return MCPGatewayConfig.from_dict(data)


def _add_proxy_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help="path to an aegize-mcp YAML config file")
    parser.add_argument("--policy", help="path to the Aegize policy YAML file")
    parser.add_argument("--agent-id", help="agent identity the host connection acts as")
    parser.add_argument("--agent-name", help="human-readable agent name")
    parser.add_argument("--owner", help="owner of the agent identity")
    parser.add_argument(
        "--environment",
        help="dev | staging | prod (aliases: development, production)",
    )
    parser.add_argument("--audit-log", help="path to the JSONL audit log")
    parser.add_argument("--tool-prefix", help="prefix added to exposed tool names")
    parser.add_argument("--startup-timeout", type=float, metavar="SECONDS",
                        help="upstream startup/discovery timeout")
    parser.add_argument("--call-timeout", type=float, metavar="SECONDS",
                        help="per-tool-call timeout")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aegize-mcp",
        description=(
            "Aegize MCP policy gateway: put identity, policy, approvals, and "
            "audit in front of any local stdio MCP server."
        ),
        epilog="Everything after '--' is the upstream MCP server command and its arguments.",
    )
    sub = parser.add_subparsers(dest="command")

    proxy = sub.add_parser(
        "proxy", help="serve the host over stdio, guarding the upstream server"
    )
    _add_proxy_flags(proxy)

    inspect = sub.add_parser(
        "inspect", help="launch the upstream server, list its tools, and exit"
    )
    inspect.add_argument("--startup-timeout", type=float, metavar="SECONDS", default=20.0)
    inspect.add_argument(
        "--emit-policy",
        action="store_true",
        help="print a full-coverage policy skeleton (all tools under "
        "require_approval) instead of the human-readable report",
    )
    inspect.add_argument(
        "--agent-id", default="claude-code",
        help="agent id used in the emitted policy skeleton",
    )
    inspect.add_argument(
        "--tool-prefix", default="",
        help="tool prefix the gateway will apply (emitted names must match it)",
    )

    check = sub.add_parser(
        "check",
        help="compare a policy against the upstream tool list and report drift",
    )
    check.add_argument("--policy", required=True, help="path to the Aegize policy YAML")
    check.add_argument("--agent-id", required=True, help="agent id to check coverage for")
    check.add_argument("--tool-prefix", default="",
                       help="tool prefix the gateway will apply")
    check.add_argument("--startup-timeout", type=float, metavar="SECONDS", default=20.0)

    return parser


async def _run_proxy(config: MCPGatewayConfig) -> None:
    from .gateway import MCPGateway

    gateway = MCPGateway(config)
    task = asyncio.current_task()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, task.cancel)
        except (NotImplementedError, RuntimeError):  # pragma: no cover - platform
            pass
    try:
        await gateway.run_stdio()
    except asyncio.CancelledError:  # clean shutdown on signal
        logging.getLogger("aegize.mcp").info("shutting down on signal")


async def _discover_tools(upstream_argv: list[str], startup_timeout: float) -> list:
    from .upstream import UpstreamClient

    upstream = UpstreamConfig(command=upstream_argv[0], args=upstream_argv[1:])
    async with UpstreamClient(
        upstream,
        startup_timeout_seconds=startup_timeout,
        call_timeout_seconds=startup_timeout,
    ) as client:
        return await client.list_tools()


def _emit_policy_skeleton(agent_id: str, exposed_names: list[str]) -> str:
    """A full-coverage policy skeleton: every tool gated behind approval.

    Nothing runs silently and nothing is silently blocked; the operator moves
    tools into allow/deny as they review them.
    """
    lines = [
        "# Aegize policy skeleton generated by `aegize-mcp inspect --emit-policy`.",
        "# Every discovered tool starts under require_approval: nothing runs",
        "# silently and nothing is silently blocked. Move tools into allow/deny",
        "# as you review them; anything removed is denied (default deny).",
        "agents:",
        f"  {agent_id}:",
        "    allow: []",
        "    require_approval:",
    ]
    for name in sorted(exposed_names):
        lines.append(f"      - tool: {name}")
        lines.append('        operations: ["call"]')
    lines.append("    deny: []")
    return "\n".join(lines) + "\n"


async def _run_inspect(
    upstream_argv: list[str],
    startup_timeout: float,
    *,
    emit_policy: bool = False,
    agent_id: str = "claude-code",
    tool_prefix: str = "",
) -> None:
    tools = await _discover_tools(upstream_argv, startup_timeout)

    if emit_policy:
        names = [tool_prefix + tool.name for tool in tools]
        print(_emit_policy_skeleton(agent_id, names), end="")
        return

    print(f"# {len(tools)} tool(s) discovered from: {' '.join(upstream_argv)}\n")
    for tool in tools:
        print(f"## {tool.name}")
        if tool.description:
            print(tool.description.strip())
        print("input schema:")
        print(json.dumps(tool.input_schema, indent=2, ensure_ascii=False))
        if tool.output_schema is not None:
            print("output schema:")
            print(json.dumps(tool.output_schema, indent=2, ensure_ascii=False))
        print()


async def _run_check(
    policy_file: str,
    agent_id: str,
    tool_prefix: str,
    upstream_argv: list[str],
    startup_timeout: float,
) -> int:
    policy = PermissionPolicy.from_yaml(policy_file)
    tools = await _discover_tools(upstream_argv, startup_timeout)
    names = [tool_prefix + tool.name for tool in tools]
    report = assess_coverage(policy, agent_id, names)

    print(f"# policy: {policy_file} | agent: {agent_id} | upstream tools: {len(names)}")
    if not report.agent_known:
        print(f"agent '{agent_id}' not found in policy — every tool is default-denied")
    counts = {"allow": 0, "require_approval": 0, "deny": 0, "unlisted": 0}
    for item in report.items:
        if not item.listed:
            counts["unlisted"] += 1
            print(f"UNLISTED          {item.tool}  (no rule -> default deny)")
        else:
            counts[item.decision] += 1
            print(f"{item.decision:<17} {item.tool}")
    if report.stale_rule_tools:
        print(
            "stale rules (tool not found upstream): "
            + ", ".join(report.stale_rule_tools)
        )
    print(
        f"summary: {counts['allow']} allow, {counts['require_approval']} approval, "
        f"{counts['deny']} deny, {counts['unlisted']} unlisted, "
        f"{len(report.stale_rule_tools)} stale"
    )
    return 1 if report.has_drift else 0


def main(argv: list[str] | None = None) -> int:
    if argv is None:  # pragma: no cover - passthrough
        argv = sys.argv[1:]
    own_argv, upstream_argv = split_upstream_argv(argv)

    parser = _build_parser()
    args = parser.parse_args(own_argv)

    # Diagnostics must never touch stdout (the MCP protocol channel).
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="aegize-mcp %(levelname)s %(message)s",
    )

    if args.command == "proxy":
        if not _require_mcp_sdk():
            return 2
        try:
            config = build_config(
                config=args.config,
                policy=args.policy,
                agent_id=args.agent_id,
                agent_name=args.agent_name,
                owner=args.owner,
                environment=args.environment,
                audit_log=args.audit_log,
                tool_prefix=args.tool_prefix,
                startup_timeout=args.startup_timeout,
                call_timeout=args.call_timeout,
                upstream_argv=upstream_argv,
            )
        except GatewayConfigError as exc:
            print(f"aegize-mcp error: {exc}", file=sys.stderr)
            return 2
        try:
            asyncio.run(_run_proxy(config))
        except GatewayError as exc:
            print(f"aegize-mcp error: {exc}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:  # pragma: no cover - interactive
            return 0
        return 0

    if args.command == "inspect":
        if not _require_mcp_sdk():
            return 2
        if not upstream_argv:
            print(
                "aegize-mcp error: pass the upstream command after '--'",
                file=sys.stderr,
            )
            return 2
        try:
            UpstreamConfig(command=upstream_argv[0], args=upstream_argv[1:])
        except GatewayConfigError as exc:
            print(f"aegize-mcp error: {exc}", file=sys.stderr)
            return 2
        try:
            asyncio.run(
                _run_inspect(
                    upstream_argv,
                    args.startup_timeout,
                    emit_policy=args.emit_policy,
                    agent_id=args.agent_id,
                    tool_prefix=args.tool_prefix,
                )
            )
        except GatewayError as exc:
            print(f"aegize-mcp error: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.command == "check":
        if not _require_mcp_sdk():
            return 2
        if not upstream_argv:
            print(
                "aegize-mcp error: pass the upstream command after '--'",
                file=sys.stderr,
            )
            return 2
        try:
            UpstreamConfig(command=upstream_argv[0], args=upstream_argv[1:])
        except GatewayConfigError as exc:
            print(f"aegize-mcp error: {exc}", file=sys.stderr)
            return 2
        try:
            return asyncio.run(
                _run_check(
                    args.policy,
                    args.agent_id,
                    args.tool_prefix,
                    upstream_argv,
                    args.startup_timeout,
                )
            )
        except (PolicyLoadError, GatewayConfigError) as exc:
            print(f"aegize-mcp error: {exc}", file=sys.stderr)
            return 2
        except GatewayError as exc:
            print(f"aegize-mcp error: {exc}", file=sys.stderr)
            return 1

    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
