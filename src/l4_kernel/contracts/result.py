"""Structured validation results shared by contracts and the harness."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One stable, machine-readable validation finding."""

    code: str
    severity: str
    message: str
    path: Path | None = None
    line: int | None = None
    gate: str | None = None

    def __post_init__(self) -> None:
        if self.severity not in {"error", "warning", "info"}:
            raise ValueError(f"unsupported issue severity: {self.severity}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "path": str(self.path) if self.path is not None else None,
            "line": self.line,
            "gate": self.gate,
        }


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Result of validating or compiling one contract surface."""

    issues: tuple[ValidationIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "issues": [issue.to_dict() for issue in self.issues]}


@dataclass(frozen=True, slots=True)
class DomainHealth:
    """Deterministic harness result for one domain."""

    domain_id: str
    profile_id: str
    checked_at: str
    issues: tuple[ValidationIssue, ...]
    # 本次实际执行的 gate 清单与其声明的输入面（由 harness 填充）。
    # 二者随结果一起输出，使 `ok: true` 与"什么都没查"可区分 —— 见 harness_profiles.GATE_SURFACES。
    gates: tuple[str, ...] = ()
    surfaces: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain_id": self.domain_id,
            "profile_id": self.profile_id,
            "checked_at": self.checked_at,
            "ok": self.ok,
            "gates": list(self.gates),
            "surfaces": list(self.surfaces),
            "issues": [issue.to_dict() for issue in self.issues],
        }
