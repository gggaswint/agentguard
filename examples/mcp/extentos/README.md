# Guarding the Extentos MCP server with Aegize

This example puts the Aegize MCP gateway in front of the
[Extentos](https://www.npmjs.com/package/@extentos/mcp-server) MCP server, so
every tool call from your MCP host (Claude Code, Claude Desktop, Cursor, …)
passes through identity, policy, approval, and audit before it reaches
Extentos:

```
MCP Host  ──stdio──►  aegize-mcp proxy  ──stdio──►  npx -y @extentos/mcp-server@latest
```

The gateway is generic — nothing here is Extentos-specific beyond the upstream
command. Aegize is an independent project; this example does not imply any
endorsement by Extentos.

## Prerequisites

- The gateway: `pip install "aegize[mcp]"` (Python 3.10+ environment), or on
  any machine `uv tool install --python 3.12 "aegize[mcp]"` — the gateway is a
  separate process, so your project's own Python version doesn't matter.
- Node.js with `npx` (to run the Extentos server)

## 1. Discover the tools

The policy is written against real tool names. List them first:

```bash
aegize-mcp inspect -- npx -y @extentos/mcp-server@latest
```

This launches the server, prints every tool's name, description, and schema,
and exits. It never proxies anything.

## 2. Write the policy

[`policy.yaml`](./policy.yaml) ships with the **38 tool names discovered from
`@extentos/mcp-server@0.11.43`** grouped into an opinionated starting point
(reads allowed, mutations gated, credential writes denied). Extentos may add or
rename tools — re-run `inspect` and compare; unlisted tools are denied, so a
stale policy fails closed. Rules of thumb:

- `allow` — read-only / low-impact tools.
- `require_approval` — anything you want a human to see first. This is a hard
  gate: the call is refused and recorded; there is no automatic approval
  workflow yet.
- `deny` — tools this agent must never call. Deny always wins.
- Everything unlisted is denied (default deny), so start narrow.

When Extentos ships new tools, updating the policy is one command each way:

```bash
# Regenerate a full-coverage skeleton (everything gated) and diff it:
aegize-mcp inspect --emit-policy --agent-id claude-code \
  -- npx -y @extentos/mcp-server@latest

# Or check the current policy against the live tool list (exits non-zero on
# drift — usable in CI):
aegize-mcp check --policy ./policy.yaml --agent-id claude-code \
  -- npx -y @extentos/mcp-server@latest
```

The gateway also warns on stderr at startup when discovered tools have no
policy rule, so drift shows up in the host's MCP logs rather than as
mysterious denials.

## 3. Run the gateway

With the config file (edit [`aegize-mcp.yaml`](./aegize-mcp.yaml) first):

```bash
aegize-mcp proxy --config ./aegize-mcp.yaml
```

Or fully flag-driven, no config file:

```bash
aegize-mcp proxy \
  --policy ./policy.yaml \
  --agent-id claude-code \
  --owner geoff \
  --environment development \
  --audit-log ./aegize-mcp-audit.jsonl \
  -- \
  npx -y @extentos/mcp-server@latest
```

Everything after `--` is the upstream command. Don't run this by hand for real
use — the host launches it for you (next step). If you do run it manually it
will sit waiting on stdin, which is correct: stdout/stdin are the MCP protocol
channel, and all diagnostics go to stderr.

## 4. Point your MCP host at the gateway

For Claude Code (syntax verified against `claude mcp add --help`; use absolute
paths — the host controls the working directory):

```bash
claude mcp add extentos-guarded -- \
  aegize-mcp proxy \
  --policy /absolute/path/to/policy.yaml \
  --agent-id claude-code \
  --owner geoff \
  --environment development \
  --audit-log /absolute/path/to/aegize-mcp-audit.jsonl \
  -- \
  npx -y @extentos/mcp-server@latest
```

For other hosts (Claude Desktop, Cursor, …), configure a stdio MCP server
whose command is `aegize-mcp` with the same arguments, adapting to that host's
JSON config format.

The host now sees the Extentos tools as usual — but calls are governed.

## Expected audit output

One JSONL record per decision, plus one per execution outcome
(`aegize-mcp-audit.jsonl`; timestamps/ids/hashes will differ):

```json
{"timestamp": "2026-08-03T21:52:10+00:00", "event": "allowed", "action_id": "a3adf125-…", "agent_id": "claude-code", "tool_name": "searchDocs", "operation": "call", "risk_level": "low", "input_summary": "query='governance'", "reason": "allowed by rule for tool 'searchDocs'", "metadata": {"upstream_tool_name": "searchDocs", "mcp_transport": "stdio", "argument_keys": ["query"], "argument_hash": "faf02374…", "gateway_version": "0.4.0", "upstream_command": "npx", "environment": "dev"}}
{"timestamp": "2026-08-03T21:52:10+00:00", "event": "execution_succeeded", "action_id": "a3adf125-…", "agent_id": "claude-code", "tool_name": "searchDocs", "operation": "call", "risk_level": "low", "input_summary": "query='governance'", "result_summary": "…", "metadata": {"…": "…"}}
{"timestamp": "2026-08-03T21:52:11+00:00", "event": "denied", "action_id": "5767b07b-…", "agent_id": "claude-code", "tool_name": "deployProduction", "operation": "call", "risk_level": "low", "input_summary": "target='prod'", "reason": "denied by rule for tool 'deployProduction'", "category": "policy_denied", "metadata": {"…": "…"}}
{"timestamp": "2026-08-03T21:52:12+00:00", "event": "approval_required", "action_id": "4c9c8311-…", "agent_id": "claude-code", "tool_name": "createSimulatorSession", "operation": "call", "risk_level": "low", "input_summary": "api_key='[redacted]', name='test'", "reason": "approval required for tool 'createSimulatorSession'", "category": "approval_required", "metadata": {"…": "…"}}
```

Note the redaction: values of sensitive-looking argument keys (password,
secret, token, key, auth, …) are never written to the log; the `argument_hash`
still lets you correlate identical calls.

## Troubleshooting

- **`aegize-mcp: command not found`** — install the extra:
  `pip install "aegize[mcp]"` (requires Python 3.10+), and make sure the
  Python bin directory is on the host's `PATH` (or use the absolute path to
  `aegize-mcp` in the host config).
- **Gateway exits immediately at startup** — check stderr in the host's MCP
  logs. Common causes: policy file path wrong (use absolute paths), invalid
  YAML, or the upstream command failed to start.
- **Startup timeout** — the first `npx -y` run downloads the package; raise
  `gateway.startup_timeout_seconds` (the config in this directory uses 60).
- **Every call is denied** — expected until the policy lists the real tool
  names (default deny). Re-run `aegize-mcp inspect` and compare names exactly;
  if you set `tool_prefix`, the policy must use the *prefixed* names.
- **A call reports `requires approval`** — working as intended: the gateway is
  a hard gate. Move the tool to `allow` if it should not be gated.
- **Where did my logs go?** — the gateway never prints to stdout (that's the
  protocol channel). Diagnostics: stderr. Decisions: the audit JSONL.
