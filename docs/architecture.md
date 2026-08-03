# Architecture

This document explains how Aegize is built today and where the architecture is
headed. It favors precision over ambition: the "current" sections describe code
that exists; the "future" sections describe direction.

## Conceptual stack

Aegize sits between the agent layer and the tools an agent acts through. It does
not replace either; it governs the boundary between them.

```
┌──────────────────────────────────────────────┐
│  AI frameworks / agents                        │  LangChain, MCP, custom
└──────────────────────────────────────────────┘
                      │  attempts a tool call
                      ▼
┌──────────────────────────────────────────────┐
│  Aegize runtime                                │
│  identity · policy · permissions · approval ·  │
│  execution boundary · audit · observability    │
└──────────────────────────────────────────────┘
                      │  allowed (and recorded)
                      ▼
┌──────────────────────────────────────────────┐
│  Tools / the outside world                     │  shell, email, DB, APIs, FS
└──────────────────────────────────────────────┘
```

## Runtime flow

Every governed action follows the same path. This is the conceptual model:

```
AI Agent
  → Identity            who is acting (agent, owner, environment)
  → Policy Evaluation   what the policy says about this action
  → Permission Check    is this tool/operation/scope allowed
  → Approval Workflow   if high-impact, hold for a human
  → Execution           run the underlying tool (only if allowed)
  → Audit               record the attempt and its outcome
  → Observability       surface what happened, across environments
  → Tools               the action reaches the outside world
```

Two of these stages — a distinct approval *workflow* and a distinct
*observability* surface — are partially or not-yet implemented (see
[Approval model](#approval-model) and [Future architecture](#future-architecture)).
The SDK today implements identity, policy+permission evaluation, an approval
*decision*, the execution boundary, and audit.

## Current SDK architecture

The SDK is a small set of primitives connected by one enforcement point. A tool
call is modeled as a `ToolAction`, evaluated by a `PermissionPolicy`, recorded by
an `AuditLog`, and gated by a `GuardedTool`. A `GuardContext` bundles the agent,
policy, and audit log so they do not have to be threaded through every call.

```
        GuardContext (agent + policy + audit_log)
                       │
   @guarded_tool  ─►  guard()  ─►  GuardedTool.__call__
                                        │
                  1. build ToolAction (identity + inputs)
                  2. policy.evaluate(action) -> allow | deny | require_approval
                  3. audit the decision         (before execution)
                  4a. deny           -> raise PolicyDenied
                  4b. require_approval-> raise ApprovalRequired
                  4c. allow          -> run func, then audit success/failure
```

## Core primitives

| Primitive          | Responsibility                                                        |
| ------------------ | --------------------------------------------------------------------- |
| `AgentIdentity`    | Who is acting: `agent_id`, owner, environment, metadata.              |
| `ToolAction`       | A single attempted call: tool, operation, inputs, risk, metadata.     |
| `PermissionPolicy` | Evaluates an action against per-agent YAML rules; returns a decision. |
| `GuardedTool`      | The enforcement point. Wraps a callable; builds, evaluates, audits.   |
| `GuardContext`     | Bundles agent + policy + audit log; supports decorator-based use.     |
| `AuditLog`         | Append-only JSONL record of every attempt and outcome.               |
| `ApprovalRequired` | Raised when an action needs a human; the function does not run.       |
| `PolicyDenied`     | Raised when an action is denied; the function does not run.           |

Ergonomic surface: the `@guarded_tool` decorator tags a function with its policy
coordinates, and `guard()` binds it to a context, returning a signature-preserving
callable suitable for tool registries (including MCP).

## Policy evaluation model

Policy is per-agent YAML, kept in version control. Each agent has `allow`,
`require_approval`, and `deny` rule lists. Evaluation is deterministic and ordered:

1. **deny** — if any deny rule matches, the result is `deny`.
2. **require_approval** — else if an approval rule matches, the result is
   `require_approval`.
3. **allow** — else if an allow rule matches (subject to risk and path
   constraints), the result is `allow`.
4. **default-deny** — otherwise, `deny`.

Guarantees that follow from this model:

- **Default deny.** No matching allow rule means the action is denied.
- **Deny wins.** An explicit deny overrides any approval or allow rule.
- **Unknown agent / unknown tool defaults to deny.** Absence is denial.
- Allow rules may constrain `risk_level_max` and `paths` (glob allowlists); a
  call that exceeds the risk ceiling or falls outside the allowlist is denied.

## Audit model

Audit is part of the control loop, not a side effect.

- **Audit-first.** The decision (`allowed`, `denied`, `approval_required`) is
  written *before* execution is attempted.
- **Outcome appended.** After an allowed action runs, its result
  (`execution_succeeded` or `execution_failed`) is appended.
- **Append-only JSONL.** One self-contained JSON object per line — trivial to
  tail, grep, or ship to a downstream sink.
- Each record carries the action's identity, tool, operation, risk level, input
  summary, the decision reason, and call-time metadata.

The result: "what did this agent attempt, and what happened?" always has a
precise answer, including the attempts that were blocked or gated.

## Approval model

`require_approval` is a first-class policy decision today. When an action
resolves to `require_approval`, Aegize records it and raises `ApprovalRequired`;
the wrapped function **does not execute**. This makes the human-in-the-loop gate
real at the boundary: high-impact actions cannot run automatically.

What does *not* yet exist is an approval *workflow* — a durable queue, a way to
grant approval out of band, and a path to re-issue the approved action. That is a
v1.0 target (see [Future architecture](#future-architecture)). Today the
integration point is the exception: callers route `ApprovalRequired` to whatever
human process they already have.

## MCP gateway (deployment shape)

The SDK's enforcement point is in-process. The **MCP policy gateway**
(`aegize-mcp`, optional `aegize[mcp]` extra, [RFC 0009](../rfcs/0009-mcp-policy-gateway.md))
applies the same runtime at a process boundary: an MCP host connects to the
gateway over stdio; the gateway launches the real upstream MCP server as a
subprocess, mirrors its tools, and runs every `tools/call` through the same
sequence — build `ToolAction` → evaluate `PermissionPolicy` → audit the
decision → forward only if allowed → audit the outcome.

```
MCP Host ──stdio──► aegize-mcp proxy ──stdio──► Upstream MCP server
                    (same policy, same audit
                     schema, same invariants)
```

This is a *deployment shape* of the runtime, not a second enforcement model:
policies are ordinary Aegize YAML (tool = MCP tool name, operation = `"call"`),
audit records use the same JSONL schema (plus MCP metadata and a failure
`category`), and default-deny / deny-wins / gated-never-executes hold
unchanged. Scope today: local stdio servers only; the tool list is a startup
snapshot; approval is a hard gate. The gateway trusts its operator the same way
the SDK trusts its host process — it governs the calls that pass through it.

## Threat model / trust assumptions

Aegize is honest about what it does and does not defend.

What Aegize enforces:

- A denied or approval-gated action will not execute the underlying function.
- Every attempted action is recorded before execution.
- Policy is evaluated deterministically; the model cannot talk its way past it,
  because enforcement is in code that runs regardless of the model's output.

Trust assumptions (what Aegize relies on):

- **The policy is correct.** Aegize enforces the policy you give it; it cannot
  make an intentionally permissive policy safe.
- **The host process is trusted.** Aegize runs in-process with the agent. It does
  not defend against a compromised host, a malicious operator, or code that
  bypasses the guarded tool entirely.
- **Tools are invoked through Aegize.** A tool called directly, outside a
  `GuardedTool`, is not governed. Aegize governs the calls that pass through it.
- **The audit log integrity is host-level today.** Tamper-evidence
  (hash-chaining / signing) is a v1.0 target, not a current guarantee.

Out of scope (now): model alignment, content filtering, sandboxing of tool
implementations, and anything requiring trust in Aegize beyond the policy and the
host.

## Future architecture

Direction, sequenced roughly by the [roadmap](./roadmap.md):

- **MCP support** — shipped as the stdio policy gateway (above); remote
  transports and tool-list change propagation are future work.
- **Signed agent identity** — verifiable provenance for `AgentIdentity`.
- **Tamper-evident logs** — hash-chained / signed audit records.
- **Remote policy service** — centralized, versioned policy distribution.
- **Hosted dashboard** — observability and audit review (later, not now).
- **Multi-agent governance** — agents acting on behalf of other agents.
- **Organization-level policy** — shared policy and inheritance across teams.
- **Approval queues** — durable, out-of-band approval workflows.
- **Distributed audit sinks** — stream audit to object storage, SIEM, etc.

These are layers on top of the local-first core, never replacements for it.

## Integration points

The places Aegize is designed to plug into other systems:

- **Tool registries / MCP** — via the signature-preserving `guard()` callable,
  or protocol-level via the `aegize-mcp` stdio gateway.
- **Agent frameworks** — wrap framework tools with `GuardedTool` / `@guarded_tool`.
- **Approval systems** — by handling `ApprovalRequired` (chat, webhook, queue).
- **Audit sinks** — by extending the audit writer (stdout, syslog, storage, SIEM).
- **Policy sources** — YAML files today; a remote policy service in the future.
