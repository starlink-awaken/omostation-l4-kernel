"""Deterministic Documents content-plane classification and audit."""

from __future__ import annotations

import stat
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BRIDGE_MARKER = "l4-content-plane: workspace-bridge"

_CACHE_DIRS = {
    ".cache",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
}
_CACHE_SUFFIXES = {".db", ".index", ".pyc", ".pyo", ".shm", ".sqlite", ".sqlite3", ".wal"}
_RUNTIME_SUFFIXES = {".bash", ".command", ".fish", ".js", ".mjs", ".cjs", ".pl", ".py", ".rb", ".sh", ".ts", ".zsh"}
_PROJECTION_NAMES = {
    "brief.md",
    "dashboard.md",
    "health.md",
    "index.json",
    "signals-machine.jsonl",
    "state.md",
    "status.md",
    "timeline.md",
}
_CONTRACT_NAMES = {
    "agents.md",
    "agent.md",
    "claude.md",
    "domain.yaml",
    "domain.yml",
    "manifest.json",
    "manifest.yaml",
    "manifest.yml",
    "skill.md",
}
_CONTRACT_DIRS = {
    "_gates",
    "_meta-standard",
    "_rules",
    "_skills",
    "ontology",
    "policies",
    "profiles",
    "rubrics",
}

_ISSUE_CODES = {
    "runtime": "L4-CONTENT-008",
    "cache": "L4-CONTENT-009",
    "projection": "L4-CONTENT-010",
}


@dataclass(frozen=True, slots=True)
class ArtifactClassification:
    """Classification of one regular file under a Documents root."""

    path: Path
    relative_path: str
    kind: str
    reason: str

    @property
    def code(self) -> str | None:
        return _ISSUE_CODES.get(self.kind)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "relative_path": self.relative_path,
            "kind": self.kind,
            "reason": self.reason,
            "code": self.code,
        }


@dataclass(frozen=True, slots=True)
class ContentPlaneReport:
    """Deterministic report for a Documents content-plane root."""

    root: Path
    artifacts: tuple[ArtifactClassification, ...]

    @property
    def violations(self) -> tuple[ArtifactClassification, ...]:
        return tuple(item for item in self.artifacts if item.kind in {"runtime", "cache"})

    @property
    def ok(self) -> bool:
        return not self.violations

    @property
    def counts(self) -> dict[str, int]:
        return dict(sorted(Counter(item.kind for item in self.artifacts).items()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "counts": self.counts,
            "violations": [item.to_dict() for item in self.violations],
            "artifacts": [item.to_dict() for item in self.artifacts],
        }


def _workspace_bridge(path: Path) -> bool:
    if path.suffix.lower() not in _RUNTIME_SUFFIXES:
        return False
    try:
        return BRIDGE_MARKER in path.read_text(encoding="utf-8", errors="ignore")[:1024]
    except OSError:
        return False


def _auditable_file(path: Path) -> bool:
    """Include file links as artifacts while refusing directory-link recursion."""

    if path.is_symlink():
        return not path.is_dir()
    return path.is_file()


def classify_artifact(root: Path, path: Path) -> ArtifactClassification:
    """Classify one path without executing it or following symlinks."""

    root_absolute = root.expanduser().absolute()
    path_absolute = path.expanduser().absolute()
    relative = path_absolute.relative_to(root_absolute).as_posix()
    parts = {part.lower() for part in Path(relative).parts}
    name = path_absolute.name.lower()
    suffix = path_absolute.suffix.lower()

    try:
        executable = bool(path_absolute.stat().st_mode & stat.S_IXUSR)
    except OSError:
        executable = False

    if parts & _CACHE_DIRS or suffix in _CACHE_SUFFIXES:
        kind, reason = "cache", "derived cache or mutable local store belongs in Workspace"
    elif _workspace_bridge(path_absolute):
        kind, reason = "bridge", "thin compatibility bridge to a Workspace-owned capability"
    elif suffix in _RUNTIME_SUFFIXES or (executable and not suffix):
        kind, reason = "runtime", "executable implementation belongs in Workspace"
    elif name in _PROJECTION_NAMES or "_generated" in parts or "generated" in parts:
        kind, reason = "projection", "mutable or generated view must not become canonical truth"
    elif name in _CONTRACT_NAMES or parts & _CONTRACT_DIRS:
        kind, reason = "contract", "declarative domain constitution or semantic contract"
    elif "_control" in parts and suffix in {".json", ".toml", ".yaml", ".yml"}:
        kind, reason = "contract", "declarative control-plane contract"
    else:
        kind, reason = "content", "canonical human-readable content or source material"

    return ArtifactClassification(path_absolute, relative, kind, reason)


def audit_content_plane(root: Path) -> ContentPlaneReport:
    """Scan one root deterministically without following symlink targets."""

    root_absolute = root.expanduser().absolute()
    if not root_absolute.is_dir():
        raise ValueError(f"content-plane root is not a directory: {root_absolute}")

    artifacts = [classify_artifact(root_absolute, path) for path in root_absolute.rglob("*") if _auditable_file(path)]
    artifacts.sort(key=lambda item: item.relative_path)
    return ContentPlaneReport(root_absolute, tuple(artifacts))
