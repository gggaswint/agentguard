# RFCs

RFCs (Requests for Comments) are how Aegize makes and records significant
decisions in the open. They are the bridge between an [open
question](../docs/questions.md) and a recorded [decision](../docs/decisions.md):
a place to think a change through in writing before building it, and a durable
record of *why* once it ships.

## Index

| RFC | Title | Status |
| --- | ----- | ------ |
| [0001](./0001-agent-identity.md) | Agent Identity | Draft |
| [0002](./0002-policy-engine.md) | Policy Engine | Draft |
| [0003](./0003-audit-format.md) | Audit Format | Draft |
| [0004](./0004-approval-workflow.md) | Approval Workflow | Draft |
| [0005](./0005-runtime-governance.md) | Runtime Governance | Draft |
| [0006](./0006-resource-scoped-permissions.md) | Resource-Scoped Permissions (Capability Model) | Draft |
| [0007](./0007-mutating-action-safety.md) | Mutating-Action Safety | Draft |
| [0008](./0008-policy-as-code-lifecycle.md) | Policy-as-Code Lifecycle | Draft |
| [0009](./0009-mcp-policy-gateway.md) | MCP Policy Gateway (local stdio) | Implemented |

## What RFCs are for

An RFC captures a proposed change, the reasoning behind it, the alternatives
considered, and the consequences — at enough depth that a future contributor can
understand the decision without having been in the room. They exist so we do not
lose context, and so substantial changes get scrutiny before they are
implemented.

RFCs are for **direction**, not routine work. They should be grounded in the
[vision](../docs/vision.md) and [principles](../docs/principles.md); if a proposal
conflicts with those, the RFC must say so explicitly and argue the case.

## When to create one

Write an RFC when a change is hard to reverse, affects the public API, or sets a
direction others will build on. Concretely:

- A change to a core primitive or the public API surface.
- The policy model, the audit format, or the identity model.
- A new protocol, standard, or integration surface (e.g. MCP, a remote service).
- Anything that resolves an entry in [questions.md](../docs/questions.md).
- A decision that should end up in [decisions.md](../docs/decisions.md).

You do **not** need an RFC for bug fixes, docs, refactors that preserve behavior,
small ergonomic additions, or anything easily reversed. When in doubt, open an
issue first; if the discussion gets deep, promote it to an RFC.

## Naming convention

One Markdown file per RFC, zero-padded and slugged:

```
rfcs/NNNN-short-title.md
```

- `NNNN` — a four-digit number, allocated in order (`0001`, `0002`, …).
- `short-title` — a few kebab-case words.

Examples: `rfcs/0001-agent-identity.md`, `rfcs/0007-tamper-evident-audit.md`.

Numbers are permanent. A rejected or superseded RFC keeps its number.

## Lifecycle

Every RFC has a `Status` in its header. The states:

- **Draft** — under discussion; the proposal may change substantially.
- **Accepted** — agreed as the direction; ready to be implemented.
- **Rejected** — considered and declined. Kept for the record, with the reason.
- **Implemented** — accepted and shipped; the code now reflects it.
- **Superseded** — replaced by a later RFC (link it).

Typical flow: `Draft → Accepted → Implemented`. Some end at `Rejected`. When an
RFC reaches `Accepted` or `Rejected`, record the outcome in
[decisions.md](../docs/decisions.md) so the decision log stays the single index of
"what we decided."

## Template

Copy this into a new `rfcs/NNNN-short-title.md`:

```markdown
# RFC NNNN: <Title>

- Status: Draft
- Author(s): <name/handle>
- Created: YYYY-MM-DD
- Related: <links to questions.md entries, decisions, prior RFCs>

## Summary

One paragraph: what is being proposed, and what changes if it is accepted.

## Motivation

The problem this solves and why it matters now. Tie it to the vision and
principles. If it resolves an open question, link it.

## Guide-level explanation

How the change works, explained for someone using or integrating Aegize.
Examples, API sketches, and policy/audit samples where relevant.

## Reference-level explanation

The details: data shapes, edge cases, migration/compatibility, and how it fits
the existing primitives (identity, policy, permissions, approval, audit).

## Alternatives considered

Other approaches and why they were not chosen. "Do nothing" is a valid option to
weigh.

## Drawbacks and risks

What this costs us — complexity, dependencies, lock-in, surface area — and how it
interacts with the [anti-goals](../docs/anti-goals.md).

## Unresolved questions

What is intentionally left open, to be settled during implementation or in a
follow-up RFC.
```
