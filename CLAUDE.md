# CLAUDE.md

Operating instructions for AI coding sessions (Claude or otherwise) working in
this repository. Read this first.

Aegize is **infrastructure for autonomous AI agents** — the runtime layer between
an agent and the tools it uses (identity, policy, permissions, approvals, audit,
observability). Mission: **build the trust layer for autonomous AI.** Core idea:
*every meaningful AI action should pass through trusted runtime infrastructure
before reaching the outside world.*

## Source of truth — read before significant changes

Before any **architectural, product, branding, or significant code change**, read
these documents and treat them as the source of truth. Do not infer the project's
direction from the code alone.

- [`docs/vision.md`](./docs/vision.md) — thesis, problem, what Aegize is / is not.
- [`docs/principles.md`](./docs/principles.md) — the tie-breakers (default deny,
  runtime first, vendor neutral, simple beats clever, …).
- [`docs/decisions.md`](./docs/decisions.md) — decisions already made, and why.
- [`docs/roadmap.md`](./docs/roadmap.md) — where the project is and is going.
- [`docs/brand.md`](./docs/brand.md) — positioning, messaging, and visual language.
- [`docs/architecture.md`](./docs/architecture.md) — primitives, runtime flow, trust model.

Also useful: [`docs/anti-goals.md`](./docs/anti-goals.md),
[`docs/questions.md`](./docs/questions.md), and the [RFC process](./rfcs/README.md).

Run `python scripts/context_check.py` to confirm these docs are present.

## How to work here

1. **Treat the docs as source of truth.** If code and docs disagree, the docs
   describe the intended state. Align to them, or change them deliberately.
2. **Flag conflicts; do not silently implement.** If a request conflicts with the
   vision, principles, decisions, brand, or anti-goals, point out the conflict
   *before* implementing. Surfacing the tension is the job — do not quietly pick a
   side.
3. **Keep the positioning.** Aegize is **infrastructure for autonomous AI agents**
   and **the trust layer for autonomous AI**. Do not silently change product
   positioning. Keep language aligned with `brand.md`: lead with infrastructure
   and governance, use the approved vocabulary, avoid the words-to-avoid list.
4. **No security-first or AI-doom framing.** Security is one capability, not the
   brand — do not overuse security-first language. Never use fear-based or
   existential-risk messaging, and do not reframe Aegize as an AI-safety nonprofit.
5. **Preserve the public API** unless the task is explicitly to change it. The
   public surface is what `src/aegize/__init__.py` exports. If a change is
   warranted, call it out, and for anything significant prefer an
   [RFC](./rfcs/README.md).
6. **Run tests and lint after code changes, when relevant** (see below). Do not
   claim success without running them. Docs-only changes do not need them.
7. **Prefer small, focused changes.** One concern per change. Match the
   surrounding code's style and conventions. Readable beats clever — this is
   trust infrastructure.

## Repository layout

- `src/aegize/` — the Python SDK (the product). Core primitives:
  `AgentIdentity`, `ToolAction`, `PermissionPolicy`, `GuardedTool`,
  `GuardContext`, `AuditLog`, plus `@guarded_tool` / `guard()` and the exceptions.
  `src/aegize/mcp/` — the optional MCP policy gateway (`aegize-mcp`, RFC 0009).
- `tests/` — pytest suite. `examples/` — runnable examples.
- `docs/` — source-of-truth documents (read these). `rfcs/` — the RFC process.
- `web/` — the aegize.com site (Next.js 15, static export). Self-contained.
- `scripts/` — asset generators (demo GIF, montage, end card). `assets/` — images.

## Commands

Python SDK (run from the repo root, using the project's virtualenv):

```bash
python -m pytest        # full test suite — must pass
ruff check .            # lint — must be clean
```

MCP gateway (`src/aegize/mcp/`, optional `aegize[mcp]` extra): the official MCP
SDK requires **Python 3.10+**, while the base package supports 3.9. The repo
has two virtualenvs: `.venv` (3.9, base — `tests/mcp_gateway/` is auto-skipped)
and `.venv312` (3.12, installed with `-e ".[mcp]"` — runs the full suite
including the gateway integration tests). Run both before claiming green. Keep
`aegize.mcp` imports out of the core package.

Website (only when touching `web/`):

```bash
cd web
npm install             # first time
npm run build           # static export to web/out — must succeed
```

## Non-negotiable invariants

These reflect decisions in `decisions.md` and `principles.md`. Do not weaken them
without an explicit, recorded decision:

- **Default deny.** No matching allow rule means the action is denied. Unknown
  agent or tool → deny.
- **Deny wins** over approval and allow.
- **Gated and denied actions never execute** the wrapped function.
- **Audit-first:** the decision is recorded before execution is attempted; the
  result is recorded after.
- **Dependency-light core.** The SDK runtime depends on PyYAML and nothing else.
  New runtime dependencies are a hard sell and need justification.

## When in doubt

Ask, or write it down. If a question is bigger than the change in front of you,
add it to [`docs/questions.md`](./docs/questions.md) or open an
[RFC](./rfcs/README.md) rather than guessing in code.
