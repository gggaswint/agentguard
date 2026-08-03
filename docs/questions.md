# Open Questions

A living list of unresolved product and architecture questions. The goal is to
make our uncertainty explicit so it can be discussed, prototyped, and eventually
resolved — ideally through an [RFC](../rfcs/README.md) and recorded in
[decisions.md](./decisions.md).

These are open on purpose. Where we have a leaning, it is noted as *current
thinking*, not a commitment. Nothing here is settled until it moves to a decision.

---

## Identity

### What is an AI identity?

What, precisely, does an `AgentIdentity` represent? A process? A deployed agent
config? A (model, system-prompt, toolset) tuple? An instance vs. a class of
agents? The answer shapes how policy is written, how audit attributes actions,
and how identity composes in multi-agent systems.

*Current thinking:* today identity is a declared `agent_id` plus owner,
environment, and metadata — a stable, human-assigned handle. The open question is
how much of an agent's actual configuration should be bound into its identity.

### Should identity be cryptographic?

Should an agent's identity be a verifiable, signed credential rather than a
self-declared string? Cryptographic identity would let a policy or audit consumer
*verify* who acted, not just trust the claim. What is the key model, who issues
credentials, and what is the rotation/revocation story?

*Current thinking:* signed identity is on the long-term roadmap; the open
questions are issuance, trust roots, and whether to adopt an existing standard
rather than invent one.

### How should agents authenticate?

When an agent presents an identity to Aegize (or to a future remote policy
service), how is that claim authenticated? In-process trust is sufficient today,
but a networked deployment needs an answer: tokens, mTLS, signed assertions,
workload identity?

---

## Permissions & policy

### How do agents inherit permissions?

When an agent spawns or delegates to a sub-agent, or acts on behalf of a user,
how do permissions flow? Is it strict attenuation (a child can never exceed its
parent)? Role-based? Does the acting-on-behalf-of principal's scope bound the
agent's? Inheritance is central to multi-agent governance and is currently
undefined. A related concern raised by the community: a policy written for
`research_agent` should **not** silently apply to a delegated sub-agent unless the
delegation is explicit.

### What is a capability?

Is the right unit of permission a (tool, operation) pair (today's model), or a
finer-grained, composable *capability* (e.g. "read files under ./data",
"send email to internal domains")? A capability model could be more expressive
and more portable, but also more complex. What is the smallest model that is
expressive enough?

### Should policies remain YAML?

YAML is readable, diff-able, and lives in version control — good properties for
policy. But it lacks types, composition, and validation guarantees, and it can
get unwieldy at scale. Do we keep YAML as the authoring format and add schema +
validation, introduce a typed policy language, or support a programmatic API?

*Current thinking:* keep YAML as the default authoring format and invest in a
schema validator / linter before considering anything heavier. The operational
lifecycle (tests, versioning, staged rollout, rollback) is explored in
[RFC 0008](../rfcs/0008-policy-as-code-lifecycle.md).

### How fine-grained should permissions be?

Tool names are coarse: "can call `send_email`" is not the same as "to whom, with
what attachment, using which account, in which workspace?" — and likewise for
shell, databases, cloud, and payments. Should permissions be scoped to normalized
arguments and resources, not just `(tool, operation)`? Explored in
[RFC 0006](../rfcs/0006-resource-scoped-permissions.md). *This sharpens "What is a
capability?" above.*

### How should the decision result model represent failures?

Today the model is `allow` / `deny` / `require_approval`. Agents likely need to
react differently to *why* an action didn't run: a policy **deny**, an
**approval_required** gate, **policy_unavailable**, **tool_unavailable**, and a
**malformed_request** are distinct conditions. What is the right taxonomy, and how
much of it belongs in the public decision type vs. error handling? (See
[RFC 0005](../rfcs/0005-runtime-governance.md).)

### How should policies be tested and rolled out safely?

Once teams depend on policy, untested drift is its own risk. How do we let
operators assert invariants ("agent A can read but not write this table") and ship
policy changes with review, staging, and rollback? Explored in
[RFC 0008](../rfcs/0008-policy-as-code-lifecycle.md).

---

## MCP gateway

### How should the gateway track upstream tool-list changes?

The MCP gateway ([RFC 0009](../rfcs/0009-mcp-policy-gateway.md)) snapshots the
upstream tool list at startup; tools added later are denied as unknown until
restart. MCP supports `tools/list_changed` notifications — should the gateway
re-discover live (and re-emit the notification downstream), or is a
restart-to-refresh model safer for a policy boundary? A changing tool surface
is also a changing *policy* surface.

### What risk level should an MCP tool call carry?

MCP tools carry no risk metadata, so gateway actions default to `low`, which
makes `risk_level_max` rules inert at this boundary. Should risk come from a
config-side map (tool → risk), from tool annotations (e.g. MCP's
`destructiveHint`), or stay out of the gateway until RFC 0007's effect
classification lands?

---

## Approval

### How should approval delegation work?

`require_approval` is a decision today, but a real approval *workflow* raises
questions: who can approve what, how is approval authority delegated, how is an
approved action re-issued safely, how do approvals expire, and how do we prevent
an agent from approving its own actions? What is the trust model for the approver?

---

## Audit

### How should audit logs become tamper-evident?

The audit log is append-only JSONL with host-level integrity today. To be
trustworthy as evidence it should be tamper-evident: hash-chaining, signing, or
an external anchor. What scheme balances integrity, performance, and the
local-first, dependency-light principle? How is the chain verified, and by whom?

### What must a decision record contain to be trustworthy?

For audits to hold up later, each allow/deny/approval decision likely needs:
policy version, agent identity, tool + operation, **normalized arguments**, the
reason, a timestamp, and possibly an **argument hash**. Which fields are required,
and how are arguments normalized without coupling to each tool? (See
[RFC 0003](../rfcs/0003-audit-format.md) and
[RFC 0008](../rfcs/0008-policy-as-code-lifecycle.md).)

---

## Mutating actions

### Whose responsibility is mutating-action safety?

Write actions (delete a table, charge a card, restart a service) carry far more
risk than reads. Should Aegize understand effect / blast-radius and be able to
require dry-run or approval for destructive writes — and where is the line between
Aegize (govern + record) and the tool (implement idempotency, dry-run, rollback)?
Explored in [RFC 0007](../rfcs/0007-mutating-action-safety.md).

---

## Protocol & ecosystem

### What should be standardized as protocol?

If "every meaningful AI action passes through trusted runtime infrastructure" is
to become a norm, parts of it likely need to be an open protocol rather than one
implementation. What is the right surface to standardize — the action/decision
schema, the audit record format, the identity credential, the policy interface —
and what should stay implementation detail?

### How should multi-agent governance work?

When agents act on behalf of other agents, coordinate, or form chains, how is the
whole interaction governed and audited? How do we attribute an action to the
right principal, bound the authority of a chain, and reconstruct "who caused
what" across agents? This is the hardest open area and the most important for the
long-term thesis.

---

## How to use this document

- Add a question when you hit a real fork that we cannot yet answer.
- When a question gets serious enough to act on, open an [RFC](../rfcs/README.md).
- When it is resolved, record it in [decisions.md](./decisions.md) and remove it
  here (or link the decision).
