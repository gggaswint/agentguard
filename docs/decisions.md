# Decisions

A running log of significant product, branding, and architecture decisions, so
the context behind them is not lost. Newest decisions are appended at the end.
Format is a lightweight ADR (Architecture Decision Record).

---

## Decision 001: Rename AgentGuard to Aegize

Status: Accepted

Date: 2026-06-27

Decision:
Rename the project, package, repository, and all public identifiers from
AgentGuard to Aegize. The Python package is `aegize`; the base error class is
`AegizeError`.

Rationale:
"AgentGuard" leads with "guard," which frames the project as a security/guardrail
tool. The product is broader: runtime infrastructure for AI actions, of which
security is one outcome. "Aegize" is short, ownable, vendor-neutral, and does not
pre-commit the brand to a single capability.

Consequences:
A one-time, breaking pre-launch rename. No backward-compatibility shims, since
there are no released users to support. All imports, metadata, examples, tests,
and docs use the new name.

---

## Decision 002: Use aegize.com as the canonical website

Status: Accepted

Date: 2026-06-27

Decision:
aegize.com is the canonical home for the project. The GitHub repository links to
it, and package metadata points to it.

Rationale:
A single canonical domain anchors brand, docs, and future product surfaces.
Owning the name early avoids fragmentation across URLs.

Consequences:
The site must exist and stay current. Until product surfaces are built, the site
is a static, developer-first homepage that points to the open-source repo.

---

## Decision 003: Mission is "the trust layer for autonomous AI"

Status: Accepted

Date: 2026-06-27

Decision:
The mission is "Build the trust layer for autonomous AI." Trust — an
organization's ability to let agents act without losing control or visibility —
is the organizing idea.

Rationale:
Capability is not the bottleneck for autonomous AI; trust is. Framing the mission
around trust captures why the infrastructure matters without resorting to
fear-based or safety-nonprofit language.

Consequences:
Messaging, roadmap, and feature decisions are evaluated against whether they
increase trust: understandability, control, reviewability, and confidence in
deployment.

---

## Decision 004: Product positioning is "infrastructure for autonomous AI agents"

Status: Accepted

Date: 2026-06-27

Decision:
Publicly, Aegize is "infrastructure for autonomous AI agents" — the runtime layer
between agents and the tools they use.

Rationale:
"Infrastructure" sets the right expectations (deterministic, operable,
composable) and the right peer group (Stripe, Vercel, Cloudflare, Terraform,
OpenTelemetry) rather than positioning Aegize as a research project or a single
security feature.

Consequences:
The product is judged as infrastructure: reliability, clarity, and integration
matter more than novelty. "Trust layer" remains the internal north star; the
public surface leads with infrastructure.

---

## Decision 005: Security is a capability, not the brand

Status: Accepted

Date: 2026-06-27

Decision:
Security is presented as one capability that good infrastructure provides, not as
the product's primary identity. We avoid overusing the word "security" in public
copy.

Rationale:
Leading with security narrows the product and invites the wrong comparisons
(scanners, firewalls, "AI safety"). Identity, policy, approvals, audit, and
observability deliver security *and* operability; collapsing all of that into
"security" undersells it.

Consequences:
Public copy leads with infrastructure and governance. A dedicated security policy
and responsible-disclosure process still exist (the tool governs sensitive
actions), but security is framed as an outcome, not the headline.

---

## Decision 006: Build open source first

Status: Accepted

Date: 2026-06-27

Decision:
The core is open source under the MIT license. Adoption and trust come before any
hosted or commercial surface.

Rationale:
Infrastructure that sits on the critical path of an agent's actions must be
inspectable. Developers will not (and should not) route their actions through a
black box. Open source is the fastest path to trust and to defining the layer's
primitives in the open.

Consequences:
We optimize for readability and a clean, dependency-light core. Any future hosted
offering is built on top of the open SDK, not in place of it.

---

## Decision 007: Python SDK first

Status: Accepted

Date: 2026-06-27

Decision:
The first implementation is a Python SDK.

Rationale:
The current agent ecosystem — frameworks, tool definitions, MCP servers — is
predominantly Python. Meeting developers in that language maximizes early
adoption and feedback.

Consequences:
Primitives and the policy model are designed to be language-agnostic in concept,
so they can be ported. Python is the first surface, not the only intended one.

---

## Decision 008: Runtime governance over prompt-only safety

Status: Accepted

Date: 2026-06-27

Decision:
Aegize governs actions at runtime (deterministic enforcement at the tool
boundary) rather than attempting to constrain behavior through prompting alone.

Rationale:
Prompt-level guidance is advisory and non-deterministic. A trust boundary must be
enforced in code that runs regardless of what the model decides. Runtime
governance is reviewable, testable, and consistent.

Consequences:
The enforcement point is the wrapped tool call, not the model. Aegize composes
with prompt-level techniques but never depends on them for its guarantees.

---

## Decision 009: Default-deny policy model

Status: Accepted

Date: 2026-06-27

Decision:
The policy model is default-deny. An action runs only if a rule explicitly
allows it. Evaluation order is: deny → require_approval → allow → default-deny.
An explicit deny always wins.

Rationale:
Default-deny is the only safe default for a system on the critical path of
real-world actions. It fails closed, and it makes policies auditable: anything not
listed is denied by construction.

Consequences:
Policies must enumerate what is permitted, which is more work up front and far
safer in production. Unknown agents and unknown tools resolve to deny.

---

## Decision 010: Audit every attempted action

Status: Accepted

Date: 2026-06-27

Decision:
Every attempted action is written to an append-only audit log — allowed, denied,
approval-required, and the eventual success or failure. The decision is recorded
before execution is attempted.

Rationale:
"What did the agent try to do?" must always have a precise answer. Auditing only
successful actions would hide exactly the events that matter most (blocked and
gated attempts).

Consequences:
Audit is not optional and not a side effect; it is part of the control loop. The
log format is simple (JSONL) so it is trivial to tail, grep, or ship downstream.

---

## Decision 011: Keep v0.1 local and dependency-light

Status: Accepted

Date: 2026-06-27

Decision:
The initial releases run entirely locally with a single runtime dependency
(PyYAML). No external services, no network calls, no dashboard.

Rationale:
The fastest path to trust is a small surface a developer can read end to end.
Local-first also means Aegize adds no new failure modes or data-exfiltration
paths to an agent's runtime.

Consequences:
Features that imply a service (remote policy, hosted audit, dashboards) are
deferred and designed as opt-in layers on top, never as core requirements.

---

## Decision 012: Temporary logo allowed; final brand mark TBD

Status: Accepted

Date: 2026-06-27

Decision:
Ship a temporary logo now so the project has a coherent visual identity. The
final brand mark is explicitly to be determined.

Rationale:
Waiting for a final mark would block launch for a low-risk, easily-replaced
asset. A placeholder is better than no identity.

Consequences:
The current logo is provisional. The brand guide records the intended visual
direction (gateway / threshold / controlled flow) so the eventual mark is
coherent with the positioning.

---

## Decision 013: Website is simple, developer-first, and free of hype

Status: Accepted

Date: 2026-06-27

Decision:
The homepage is minimal, technical, and confident — closer to Stripe/Vercel/Linear
than to a marketing landing page. No stock imagery, no fake logos, no
testimonials, no pricing, no fear-based messaging.

Rationale:
The audience is developers and infrastructure teams. They trust clarity and
working code, not marketing. The site should look like a company that intends to
define part of the future infrastructure for autonomous AI.

Consequences:
Copy and design are held to an infrastructure-company bar. Subtle motion only;
real artifacts (the runtime pipeline, the terminal demo) over decoration.

---

## Decision 014: Avoid employer affiliation or third-party branding

Status: Accepted

Date: 2026-06-27

Decision:
Aegize is presented as an independent project. No employer affiliation and no
third-party company branding (e.g. Google) appears in the project, its site, or
its materials.

Rationale:
Aegize must be credibly vendor-neutral and independent. Implied affiliation would
undermine that neutrality and create confusion about ownership.

Consequences:
All branding, accounts, and copy are kept independent. Vendor names appear only
as integration targets (e.g. "works across OpenAI, Anthropic, Google, and
open-source models"), never as affiliations.

---

## Decision 015: MCP gateway is an optional deployment shape of the runtime

Status: Accepted

Date: 2026-08-03

Decision:
Ship an MCP policy gateway (`aegize-mcp`, local stdio only) as an **optional
extra** (`pip install "aegize[mcp]"`, Python 3.10+) built on the official MCP
Python SDK. The gateway reuses `PermissionPolicy` and `AuditLog` unchanged and
enforces the same invariants (default deny, deny wins, gated/denied never
execute, audit-first). See [RFC 0009](../rfcs/0009-mcp-policy-gateway.md).

Rationale:
"Protocols over proprietary APIs": MCP is where agents meet tools, and most MCP
servers are third-party code that cannot be wrapped in-process. A protocol-level
gateway extends the runtime's reach without changing its model. Making it an
extra keeps the core dependency-light (Decision 011): the MCP SDK's dependency
tree never touches `pip install aegize`.

Consequences:
The gateway is a deployment shape, not a second enforcement model — RFC 0005's
in-process SDK remains the core. The core stays Python 3.9+/PyYAML-only; the
gateway requires 3.10+. Remote transports, tool-list change propagation, and
per-tool risk mapping are explicitly future work.
