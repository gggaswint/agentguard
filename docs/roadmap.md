# Roadmap

This is a practical roadmap from the current open-source SDK toward a runtime
governance platform. It is intentionally honest about where the project is: an
early-stage SDK with a clear thesis, not a finished product. Versions describe
intent and sequence, not committed dates.

## Current status

Aegize is an open-source Python SDK at **v0.3**. It is local, dependency-light
(PyYAML only), typed, and tested. It implements the core loop — identity,
policy, permission decisions, approval gating, and audit — for tool calls.

Shipped capabilities:

- **Agent identity** (`AgentIdentity`) — owner, environment, metadata.
- **YAML policy engine** (`PermissionPolicy`) — declarative, versionable.
- **GuardedTool** — wrap any callable as a permissioned, audited tool.
- **`@guarded_tool` decorator** — declare a tool's policy coordinates inline.
- **GuardContext** — bundle agent, policy, and audit log; bind once.
- **`guard()` adapter** — signature-preserving callable for tool registries / MCP.
- **Permission decisions** — `allow` / `deny` / `require_approval`.
- **JSONL audit logs** — append-only, one record per attempt and outcome.
- **`aegize policy test` CLI** — assert policy decisions from a YAML test file.
- **`aegize-mcp` policy gateway** — guard any local stdio MCP server
  (optional `aegize[mcp]` extra, Python 3.10+).
- **Runnable examples**, a **pytest** suite, and **Ruff** linting.

## Launch foundation

The work to make the project legible and adoptable in public. Most of this is
complete; the rest is near-term.

- [x] Rename from AgentGuard to Aegize (package, repo, identifiers, docs)
- [x] Website at aegize.com (static, developer-first)
- [x] README polish and positioning
- [x] Demo GIF and animated runtime visualization
- [x] Architecture and runtime diagrams
- [ ] GitHub profile / org presentation
- [ ] Launch post

## v0.1 — SDK foundation (done)

The core primitives and security posture:

- `AgentIdentity`, `ToolAction`, `PermissionPolicy`, `GuardedTool`, `AuditLog`.
- Default-deny evaluation: deny → require_approval → allow → default-deny.
- Gated and denied actions never execute the wrapped function.
- Audit-first: the decision is recorded before execution is attempted; the
  result is recorded after.

## v0.2 — Developer ergonomics (done)

Make adoption frictionless:

- `@guarded_tool` decorator, `GuardContext`, and the `guard()` adapter.
- Per-call metadata (e.g. paths for allowlists).
- Both explicit (`GuardedTool(...)`) and decorator-based usage on one code path.

## v0.3 — Integrations

Meet agents where they already are:

- [x] **Policy tests** — `aegize policy test <policy> <tests>` asserts
  "agent + action → decision" from a YAML test file and exits non-zero on drift;
  the first step of the policy-as-code lifecycle
  ([RFC 0008](../rfcs/0008-policy-as-code-lifecycle.md)).
- [x] **MCP policy gateway** — `aegize-mcp proxy` puts the runtime in front of
  any local stdio MCP server: mirrored tools, per-call policy evaluation,
  approval hard-gate, full audit; optional `aegize[mcp]` extra
  ([RFC 0009](../rfcs/0009-mcp-policy-gateway.md)). Remote (HTTP) transports and
  tool-list change notifications are future work.
- First-class helpers for common agent frameworks via the `guard()` callable.
- **CLI policy validator** — lint and validate policy files (`aegize` CLI).
- Policy schema validation with helpful errors.

## v0.4 — Observability

Make agent behavior visible:

- Pluggable audit sinks beyond local JSONL (stdout, syslog, object storage, SIEM).
- Structured, queryable event stream.
- Per-environment policy overlays (`dev` / `staging` / `prod`).
- Local inspection tooling for reading and filtering audit logs.
- **Richer decision records** — policy version, normalized arguments, and an
  optional argument hash, for audits that hold up later (exploring,
  [RFC 0003](../rfcs/0003-audit-format.md) / [0008](../rfcs/0008-policy-as-code-lifecycle.md)).

## v1.0 — Runtime governance

The point at which Aegize is a dependable control surface, not just an SDK:

- **Tamper-evident audit logs** (hash-chained / signed records).
- **Approval workflow** beyond the exception (pluggable backends: webhook,
  queue, chat) — a real human-in-the-loop path for `require_approval`. Explore
  approval as a **scoped capability grant**: single-use, time-limited, bound to
  specific arguments/resources, fully audited (exploring,
  [RFC 0004](../rfcs/0004-approval-workflow.md)).
- Rate limits and budget/quota controls per agent and per tool.
- Stable, documented extension points for policy, approval, and audit.

## Future platform

Direction, not commitment. These are platform-shaped and come after the SDK is
trusted:

- Signed agent identity and verifiable provenance.
- Remote / centralized policy service.
- Organization-level policy and approval queues.
- Multi-agent governance (agents acting on behalf of other agents).
- Distributed audit sinks.
- **Resource-scoped capability model** — permissions scoped to arguments and
  resources, not just `(tool, operation)` (exploring, [RFC 0006](../rfcs/0006-resource-scoped-permissions.md)).
- **Policy-as-code lifecycle** — review, staged rollout, and rollback for policy
  changes (exploring, [RFC 0008](../rfcs/0008-policy-as-code-lifecycle.md)).
- **Mutating-action safety** — effect / blast-radius classification and dry-run
  gates for destructive writes (exploring, [RFC 0007](../rfcs/0007-mutating-action-safety.md)).
- **Richer failure taxonomy** — distinguish policy/tool-unavailable and malformed
  requests from deny/approval (exploring, [RFC 0005](../rfcs/0005-runtime-governance.md)).
- A hosted dashboard — **later, not now.**

## Non-goals

What we are deliberately not building, at least for the foreseeable future:

- A model, a guardrail prompt, or a content/safety filter.
- A hosted dashboard or SaaS control plane in the early phases.
- Framework or vendor lock-in of any kind.
- Heavy runtime dependencies in the core SDK.
- Claims about model alignment or existential risk.
- Anything that requires trusting Aegize more than the policy you give it.
