# RFC 0009: MCP Policy Gateway (local stdio)

- Status: Implemented
- Author(s): Aegize maintainers
- Created: 2026-08-03
- Related: [roadmap v0.3 "MCP adapter"](../docs/roadmap.md),
  [RFC 0001](./0001-agent-identity.md), [RFC 0003](./0003-audit-format.md),
  [RFC 0004](./0004-approval-workflow.md), [RFC 0005](./0005-runtime-governance.md),
  [principles: Protocols over proprietary APIs](../docs/principles.md)

## Summary

Add an optional, generic **local stdio MCP policy gateway**: a process that an
MCP host (Claude Code, Claude Desktop, Cursor, …) connects to *instead of* a
tool server. The gateway launches the real upstream MCP server as a subprocess,
discovers its tools, exposes mirrored copies of them, and routes every tool call
through the existing Aegize runtime — identity, policy, approval gate, audit —
forwarding only allowed calls upstream. It ships as an optional extra
(`pip install "aegize[mcp]"`) with a new `aegize-mcp` console script; the core
SDK remains dependency-light and MCP-free.

```
MCP Host  ──stdio──►  Aegize MCP Gateway  ──stdio──►  Upstream MCP server
(client)              (identity · policy ·            (any local stdio server)
                       approval · audit)
```

## Motivation

Aegize's thesis is that every meaningful AI action should pass through trusted
runtime infrastructure. Today that requires the tool author to wrap callables
with `GuardedTool` / `@guarded_tool` in-process. MCP is where agents
increasingly meet tools, and most MCP servers are third-party code the operator
cannot modify. A protocol-level gateway lets an operator put Aegize in front of
*any* existing local MCP server — no upstream changes — which is exactly the
"meet agents and tools where they already are" principle (*Protocols over
proprietary APIs*). It is also the v0.3 "MCP adapter" roadmap item.

RFC 0005 considered a sidecar/proxy and noted it "does not replace the
in-process SDK and raises its own trust and coverage questions." This RFC keeps
that framing: the gateway is a **deployment shape** of the same runtime, not a
replacement enforcement point. The trust boundaries below are explicit about
what it does and does not cover.

## Guide-level explanation

The operator writes a normal Aegize policy keyed on MCP tool names, with
`operation: "call"`:

```yaml
agents:
  claude-code:
    allow:
      - tool: searchDocs
        operations: ["call"]
    require_approval:
      - tool: createSimulatorSession
        operations: ["call"]
    deny:
      - tool: deployProduction
        operations: ["call"]
```

Then points the host at the gateway instead of the server:

```bash
aegize-mcp proxy \
  --policy ./aegize.yaml \
  --agent-id claude-code \
  --owner geoff \
  --environment development \
  --audit-log ./aegize-mcp-audit.jsonl \
  -- \
  npx -y @extentos/mcp-server@latest
```

Everything after `--` is the upstream server's argv. A YAML config file
(`aegize-mcp proxy --config aegize-mcp.yaml`) covers the same settings;
command-line flags override config values. An `aegize-mcp inspect -- <argv>`
helper launches an upstream server, lists its tools (names, descriptions,
schemas), and exits — for writing the policy in the first place.

Behavior per call:

- **allow** → decision audited first, arguments forwarded unchanged, upstream
  result returned unchanged (text and structured content preserved), outcome
  audited after.
- **deny** → upstream is never contacted; denial audited; the host receives a
  valid MCP error result naming the tool, a safe reason, and the `action_id`
  for audit correlation.
- **require_approval** → upstream is never contacted; gate audited; the host
  receives a valid MCP error result saying approval is required, with the
  `action_id`. This is a **hard gate** — consistent with the SDK's
  `ApprovalRequired` semantics, there is no durable approval queue yet
  (RFC 0004 is still the plan of record for that).
- **unknown tool** (not discovered at startup) → denied without upstream
  contact.

## Reference-level explanation

### Placement and packaging

- New subpackage `src/aegize/mcp/` (`config`, `errors`, `tool_mapping`,
  `upstream`, `gateway`, `cli`). The core `aegize` package does not import it.
- Optional extra: `mcp = ["mcp>=2.0,<3; python_version >= '3.10'"]`. The
  official MCP Python SDK requires Python ≥ 3.10; the base package stays ≥ 3.9.
  On < 3.10 the extra installs nothing and `aegize-mcp` exits with a clear
  message.
- Console script `aegize-mcp = aegize.mcp.cli:main`. Importing `aegize.mcp`
  without the extra installed raises a helpful error; `import aegize` is
  unaffected.
- Built on the official SDK primitives: `mcp.client.stdio.stdio_client` +
  `ClientSession` upstream; `mcp.server.lowlevel.Server` +
  `mcp.server.stdio.stdio_server` downstream. No hand-rolled JSON-RPC.

### Identity

Per RFC 0001, identity is declared, not verified: the operator asserts which
agent is on the other end of the host connection (`--agent-id`, `--owner`,
`--environment`). The gateway constructs one `AgentIdentity` for the process
lifetime and attributes every call to it. It does **not** add a verification
layer, and one gateway process serves one agent identity. Environment aliases
`development` → `dev` and `production` → `prod` are normalized in gateway
config only; the core `AgentIdentity` contract is unchanged.

### Policy mapping

- `tool_name` = the exposed MCP tool name (upstream name plus optional
  configured prefix), `operation` = `"call"`.
- String argument values are surfaced as path candidates so existing `paths`
  allowlists work; `risk_level` is `"low"` by default (MCP tools carry no risk
  metadata; per-tool risk mapping is future work).
- Default deny and deny-wins are inherited unchanged from `PermissionPolicy`.
  If the policy cannot be loaded the gateway refuses to start; if evaluation
  itself fails at runtime the call is denied (fail closed) and audited with a
  `policy_unavailable` category.

### Audit

Records use the existing `AuditLog` JSONL schema and the five canonical events,
in the same audit-first order as `GuardedTool`. Call metadata adds:
`upstream_tool_name`, `mcp_transport: "stdio"`, sorted `argument_keys`, a
SHA-256 `argument_hash` of the canonical JSON encoding (a hash only — this does
not pre-empt RFC 0003's normalized-arguments question), `gateway_version`, and
the upstream command name (argv[0] only; never args or env). `input_summary` is
a deterministic, length-bounded rendering of the arguments with values of
sensitive-looking keys (password/secret/token/key/auth/credential…) redacted;
when the *tool name itself* looks credential-bearing (e.g. `setCredential`),
every argument value is redacted regardless of key name. Full argument values
are never written to the log by default.

### Error semantics

Failures are classified, not collapsed into `PolicyDenied`:

| Category | Meaning | Upstream contacted? |
| --- | --- | --- |
| `policy_denied` | explicit or default deny | no |
| `approval_required` | approval gate | no |
| `malformed_request` | arguments not a JSON object, unknown tool shape | no |
| `policy_unavailable` | policy evaluation failed at runtime → deny | no |
| `upstream_unavailable` | subprocess/session dead or unreachable | attempted |
| `upstream_tool_error` | upstream returned an error result | yes |
| `timeout` | upstream call exceeded `call_timeout_seconds` | yes |
| `internal_gateway_error` | unexpected gateway bug → error result, audited | no |

Upstream tool errors (`is_error: true` results) are forwarded to the host
unchanged and audited as `execution_failed`. Gateway-originated errors are
returned as MCP error results containing the category, tool name, safe reason,
and `action_id` — never policy internals, upstream env values, or full
arguments.

### Lifecycle

Startup: load config → load policy → build identity → open audit sink → spawn
upstream via `StdioServerParameters` (argv list, `shell=False` by
construction) → initialize session and list tools within
`startup_timeout_seconds` → register mirrored tools → serve the host on stdio.
stdout is the protocol channel; all diagnostics go to stderr. Shutdown (host
disconnect, SIGINT, SIGTERM): stop serving, close the upstream session, let the
SDK terminate the subprocess (terminate → brief wait → kill), flush audit
records. The tool list is a **startup snapshot**; upstream `list_changed`
notifications are not yet propagated (documented limitation).

### Security posture

- Upstream command is always an argv list; no shell interpretation anywhere.
- Recursive configuration (`aegize-mcp` proxying itself) is rejected at config
  validation.
- Upstream `env` values pass through to the subprocess but are never logged or
  summarized.
- Summaries and error messages are length-bounded.
- Fail closed: unknown tool → deny; policy evaluation failure → deny; audit
  write failure → the call is not forwarded (the error surfaces as an internal
  gateway error), consistent with "audit is part of the control loop".

## Alternatives considered

- **In-process only (status quo).** Keeps the trust story simplest but cannot
  govern third-party MCP servers without forking them. Fails the roadmap item.
- **Wrap upstream tools with `GuardedTool` directly.** `GuardedTool` is
  synchronous and execution-oriented; MCP calls are async and remote. The
  gateway replicates the same decision/audit sequence explicitly rather than
  contorting the primitive. The invariants, not the class, are the contract.
- **Remote (Streamable HTTP) proxying now.** Pulls in auth/OAuth and network
  trust questions RFC 0005 defers. stdio-only keeps v1 local-first.
- **Hand-rolled JSON-RPC.** Rejected; the official SDK covers the full
  lifecycle and stays protocol-current.

## Drawbacks and risks

- A second enforcement surface to keep consistent with the SDK (mitigated by
  reusing `PermissionPolicy`/`AuditLog` and asserting the same invariants in
  tests).
- The MCP SDK is a heavyweight dependency (pydantic, starlette, httpx…) —
  acceptable only because it is an optional extra; the core stays
  PyYAML-only.
- The gateway trusts its own host: like the SDK, it does not defend against an
  operator bypassing it (connecting the host directly upstream).
- MCP SDK 2.x is young; the pin (`>=2.0,<3`) may need maintenance.

## Unresolved questions

- Propagating upstream `tools/list_changed` notifications (re-snapshot vs.
  live re-mirror).
- Per-tool risk levels for MCP tools (candidate: config-side risk map).
- Resources/prompts proxying (explicitly out of scope here).
- Remote transports and how identity is asserted across a network boundary
  (RFC 0001 / RFC 0005 territory).
