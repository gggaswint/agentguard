"""Configuration for the MCP policy gateway.

Configuration comes from a YAML file, command-line flags, or both; flags
override file values. This module deliberately does not import the ``mcp`` SDK
so config parsing stays testable and importable everywhere.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from ..identity import VALID_ENVIRONMENTS
from .errors import GatewayConfigError

# Common aliases normalized to the core AgentIdentity vocabulary.
_ENVIRONMENT_ALIASES = {
    "development": "dev",
    "production": "prod",
    "stage": "staging",
}

DEFAULT_STARTUP_TIMEOUT = 20.0
DEFAULT_CALL_TIMEOUT = 120.0


def _normalize_environment(value: str) -> str:
    env = _ENVIRONMENT_ALIASES.get(value, value)
    if env not in VALID_ENVIRONMENTS:
        raise GatewayConfigError(
            f"environment must be one of {VALID_ENVIRONMENTS} "
            f"(or an alias: {sorted(_ENVIRONMENT_ALIASES)}), got {value!r}"
        )
    return env


def _reject_recursive(command: str, args: list[str]) -> None:
    """Refuse a configuration where the gateway would launch itself."""
    tokens = [os.path.basename(str(command))] + [str(a) for a in args]
    if any("aegize-mcp" in token for token in tokens):
        raise GatewayConfigError(
            "upstream command must not launch the gateway itself (aegize-mcp)"
        )


@dataclass(frozen=True)
class UpstreamConfig:
    """The upstream MCP server: an argv list, never a shell string."""

    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None

    def __post_init__(self) -> None:
        if not self.command:
            raise GatewayConfigError("upstream command must be a non-empty string")
        _reject_recursive(self.command, self.args)


@dataclass(frozen=True)
class GatewaySettings:
    tool_prefix: str = ""
    startup_timeout_seconds: float = DEFAULT_STARTUP_TIMEOUT
    call_timeout_seconds: float = DEFAULT_CALL_TIMEOUT

    def __post_init__(self) -> None:
        if self.startup_timeout_seconds <= 0 or self.call_timeout_seconds <= 0:
            raise GatewayConfigError("timeouts must be positive")


@dataclass(frozen=True)
class MCPGatewayConfig:
    """Everything the gateway needs to run."""

    agent_id: str
    owner: str
    policy_file: str
    audit_log: str
    upstream: UpstreamConfig
    agent_name: str = ""
    environment: str = "dev"
    gateway: GatewaySettings = field(default_factory=GatewaySettings)

    def __post_init__(self) -> None:
        if not self.agent_id:
            raise GatewayConfigError("agent id must be a non-empty string")
        if not self.policy_file:
            raise GatewayConfigError("a policy file is required")
        if not self.audit_log:
            raise GatewayConfigError("an audit_log path is required")
        object.__setattr__(self, "environment", _normalize_environment(self.environment))
        if not self.agent_name:
            object.__setattr__(self, "agent_name", self.agent_id)

    # -- construction ----------------------------------------------------

    @classmethod
    def from_yaml(cls, path: str | Path) -> MCPGatewayConfig:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise GatewayConfigError("PyYAML is required to load gateway config") from exc

        path = Path(path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise GatewayConfigError(f"could not read config file: {path}") from exc
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise GatewayConfigError(f"could not parse config YAML: {path}") from exc
        if not isinstance(data, dict):
            raise GatewayConfigError(f"config root must be a mapping: {path}")
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPGatewayConfig:
        agent = data.get("agent") or {}
        if not isinstance(agent, dict):
            raise GatewayConfigError("'agent' must be a mapping")
        upstream_data = data.get("upstream") or {}
        if not isinstance(upstream_data, dict):
            raise GatewayConfigError("'upstream' must be a mapping")
        gateway_data = data.get("gateway") or {}
        if not isinstance(gateway_data, dict):
            raise GatewayConfigError("'gateway' must be a mapping")

        env_map = upstream_data.get("env") or {}
        if not isinstance(env_map, dict):
            raise GatewayConfigError("'upstream.env' must be a mapping")

        upstream = UpstreamConfig(
            command=str(upstream_data.get("command") or ""),
            args=[str(a) for a in upstream_data.get("args") or []],
            env={str(k): str(v) for k, v in env_map.items()},
            cwd=upstream_data.get("cwd"),
        )
        settings = GatewaySettings(
            tool_prefix=str(gateway_data.get("tool_prefix") or ""),
            startup_timeout_seconds=float(
                gateway_data.get("startup_timeout_seconds") or DEFAULT_STARTUP_TIMEOUT
            ),
            call_timeout_seconds=float(
                gateway_data.get("call_timeout_seconds") or DEFAULT_CALL_TIMEOUT
            ),
        )
        return cls(
            agent_id=str(agent.get("id") or ""),
            agent_name=str(agent.get("name") or ""),
            owner=str(agent.get("owner") or ""),
            environment=str(agent.get("environment") or "dev"),
            policy_file=str(data.get("policy") or ""),
            audit_log=str(data.get("audit_log") or ""),
            upstream=upstream,
            gateway=settings,
        )

    # -- merging ---------------------------------------------------------

    def with_overrides(
        self,
        *,
        agent_id: str | None = None,
        agent_name: str | None = None,
        owner: str | None = None,
        environment: str | None = None,
        policy_file: str | None = None,
        audit_log: str | None = None,
        tool_prefix: str | None = None,
        startup_timeout_seconds: float | None = None,
        call_timeout_seconds: float | None = None,
        upstream_argv: list[str] | None = None,
    ) -> MCPGatewayConfig:
        """Return a new config with any provided values replacing the current ones.

        Used to let command-line flags override config-file values.
        """
        upstream = self.upstream
        if upstream_argv:
            upstream = UpstreamConfig(
                command=upstream_argv[0],
                args=list(upstream_argv[1:]),
                env=dict(self.upstream.env),
                cwd=self.upstream.cwd,
            )
        settings = replace(
            self.gateway,
            **{
                k: v
                for k, v in {
                    "tool_prefix": tool_prefix,
                    "startup_timeout_seconds": startup_timeout_seconds,
                    "call_timeout_seconds": call_timeout_seconds,
                }.items()
                if v is not None
            },
        )
        return MCPGatewayConfig(
            agent_id=agent_id if agent_id is not None else self.agent_id,
            agent_name=agent_name if agent_name is not None else self.agent_name,
            owner=owner if owner is not None else self.owner,
            environment=environment if environment is not None else self.environment,
            policy_file=policy_file if policy_file is not None else self.policy_file,
            audit_log=audit_log if audit_log is not None else self.audit_log,
            upstream=upstream,
            gateway=settings,
        )
