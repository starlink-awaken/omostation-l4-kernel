"""Domain path containment and Phase 0 direct-mutation policy."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class PathPolicyError(ValueError):
    """A caller-supplied path crossed the domain security boundary."""

    def __init__(self, code: str, message: str, requested: str) -> None:
        self.code = code
        self.message = message
        self.requested = requested
        super().__init__(f"{code}: {message}: {requested}")

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "path": self.requested}


def resolve_within(root: Path, requested: str) -> Path:
    """Resolve a relative caller path without permitting root escape."""

    if not requested or "\x00" in requested:
        raise PathPolicyError("L4-PATH-006", "empty or invalid path", requested)

    root_resolved = root.expanduser().resolve()
    candidate = Path(requested)
    if candidate.is_absolute():
        raise PathPolicyError("L4-PATH-006", "absolute paths are forbidden", requested)

    resolved = (root_resolved / candidate).resolve(strict=False)
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise PathPolicyError("L4-PATH-006", "path escapes domain root", requested) from exc
    return resolved


def direct_mutation_allowed() -> bool:
    """Permit legacy direct writes only through one explicit rollback switch."""

    return os.environ.get("L4_LEGACY_DIRECT_WRITE") == "1"


def mutation_denied() -> dict[str, Any]:
    """Return the stable default-deny mutation envelope."""

    return {
        "ok": False,
        "error": {
            "code": "L4-MUTATION-011",
            "message": "direct mutation disabled; submit an EvolutionProposal through OMO",
        },
    }
