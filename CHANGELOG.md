# Changelog

All notable changes to Aegize are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.2] - 2026-08-04

### Added

- `aegize-mcp inspect --json` — print the upstream tool surface as
  deterministic JSON (sorted by name, stable field order: name, title,
  description, input/output schemas). Commit the snapshot and diff it in CI to
  catch tool renames, removals, and schema changes — useful for MCP server
  *authors* as a surface-regression test, with no Aegize policy required.
  Mutually exclusive with `--emit-policy`.

## [0.4.1] - 2026-08-03

### Added

- **Policy drift tooling** for the MCP gateway:
  - `aegize-mcp check --policy <file> --agent-id <id> -- <server>` — compares
    the policy against the live upstream tool list, reports the decision each
    tool would get plus UNLISTED (default-denied) tools and stale rules, and
    exits non-zero on drift, so it drops into CI.
  - `aegize-mcp inspect --emit-policy [--agent-id --tool-prefix]` — prints a
    full-coverage policy skeleton with every discovered tool under
    `require_approval` (nothing runs silently, nothing is silently blocked).
  - The gateway now warns on stderr at startup when discovered tools have no
    policy rule for the agent (naming them), when policy rules reference tools
    that no longer exist upstream, and when the agent id is absent from the
    policy.

### Changed

- The `aegize-mcp` "extra not installed" error now explains the isolated
  install path (`uv tool install --python 3.12 "aegize[mcp]"` / `pipx`) that
  works regardless of the project's own Python version.
- The upstream subprocess's stderr stream now falls back to the original
  stderr (or devnull) when `sys.stderr` is not fd-backed, instead of failing
  to spawn.

## [0.4.0] - 2026-08-03

### Added

- **MCP policy gateway** (`aegize-mcp`, [RFC 0009](./rfcs/0009-mcp-policy-gateway.md)):
  a local stdio proxy that sits between an MCP host (Claude Code, Claude
  Desktop, Cursor, …) and any local stdio MCP server. It launches the upstream
  server as a subprocess, discovers and mirrors its tools, evaluates every
  `tools/call` through the Aegize runtime, and forwards only allowed calls —
  denied and approval-gated calls never reach the upstream server, and every
  attempt is audited (decision before forwarding, outcome after).
  - `aegize-mcp proxy` — flags and/or `--config` YAML; everything after `--`
    is the upstream command (argv, never a shell).
  - `aegize-mcp inspect` — list an upstream server's tools/schemas and exit,
    for writing the policy.
  - Failure taxonomy in audit records and host-facing errors:
    `policy_denied`, `approval_required`, `malformed_request`,
    `policy_unavailable`, `upstream_unavailable`, `upstream_tool_error`,
    `timeout`, `internal_gateway_error`.
  - Sensitive-looking argument values (password/secret/token/key/auth/…) are
    redacted from audit summaries; a SHA-256 argument hash keeps calls
    correlatable. Upstream env values are never logged.
  - Installed via the new optional extra `pip install "aegize[mcp]"`
    (official MCP SDK, Python 3.10+). The core package is unchanged and stays
    PyYAML-only on Python 3.9+.
- Worked example: `examples/mcp/extentos/` (config, placeholder policy,
  Claude Code registration, expected audit output, troubleshooting).

### Notes

- Local stdio proxying only; remote (Streamable HTTP) MCP servers are not yet
  supported. `require_approval` is a hard gate — no durable approval queue yet.
- The upstream tool list is a startup snapshot; `tools/list_changed` is not
  yet propagated.
- No changes to the existing public Python API.

## [0.3.0] - 2026-06-29

### Added

- **`aegize` command-line interface** with its first subcommand,
  `aegize policy test <policy_file> <test_file>`. It evaluates declarative test
  cases against a policy and reports pass/fail, exiting `0` when every case
  passes, `1` on any mismatch, and `2` on a missing or malformed file. It only
  runs policy evaluation — it never executes a tool — and is built on the stdlib
  (argparse) to keep the package dependency-light. This is the first step of the
  policy-as-code lifecycle ([RFC 0008](./rfcs/0008-policy-as-code-lifecycle.md)).
- `examples/policy_tests.yaml` — runnable policy tests for `examples/aegize.yaml`.
- "Policy tests" section in the README.

### Notes

- No changes to the existing public Python API; the CLI is additive and reachable
  via the new `aegize` console script.

## [0.2.0] - 2026-06-27

### Added

- `@guarded_tool` decorator, `GuardContext`, and the `guard()` adapter for
  signature-preserving integration with tool registries and MCP.
- Per-call metadata (e.g. `path`) for allowlist matching.

## [0.1.0]

### Added

- Initial SDK: `AgentIdentity`, `ToolAction`, `PermissionPolicy`, `GuardedTool`,
  and `AuditLog`.
- Default-deny policy engine (`deny → require_approval → allow → default-deny`),
  `risk_level_max` ceilings, glob path allowlists, and append-only JSONL audit.

[0.4.2]: https://github.com/gggaswint/aegize/releases/tag/v0.4.2
[0.4.1]: https://github.com/gggaswint/aegize/releases/tag/v0.4.1
[0.4.0]: https://github.com/gggaswint/aegize/releases/tag/v0.4.0
[0.3.0]: https://github.com/gggaswint/aegize/releases/tag/v0.3.0
[0.2.0]: https://github.com/gggaswint/aegize/releases/tag/v0.2.0
[0.1.0]: https://github.com/gggaswint/aegize/releases/tag/v0.1.0
