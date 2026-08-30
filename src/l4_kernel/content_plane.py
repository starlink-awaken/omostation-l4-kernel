"""Deterministic Documents content-plane classification and audit."""

from __future__ import annotations

import stat
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from l4_kernel import content_archive
from l4_kernel.content_archive import (
    ARCHIVE_ISSUE_CODE,
    ARCHIVE_MANIFEST_NAME,
    ContentArchiveResolver,
    ContentArchiveValidationError,
)

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
    "invalid_archive": ARCHIVE_ISSUE_CODE,
}
_DEFAULT_AUDIT_ATTEMPTS = 3
_STABILITY_FAILURE_MARKERS = (
    "changed during",
    "identity changed",
    "target changed",
)


@dataclass(frozen=True, slots=True)
class ArtifactClassification:
    """Classification of one regular file under a Documents root."""

    path: Path
    relative_path: str
    kind: str
    reason: str
    issue_code: str | None = None

    @property
    def code(self) -> str | None:
        return self.issue_code or _ISSUE_CODES.get(self.kind)

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
    stability_attempts: int = 1

    @property
    def violations(self) -> tuple[ArtifactClassification, ...]:
        return tuple(
            item for item in self.artifacts if item.kind in {"runtime", "cache", "invalid_archive"} or item.issue_code
        )

    @property
    def ok(self) -> bool:
        return not self.violations

    @property
    def counts(self) -> dict[str, int]:
        return dict(sorted(Counter(item.kind for item in self.artifacts).items()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "stability_attempts": self.stability_attempts,
            "counts": self.counts,
            "violations": [item.to_dict() for item in self.violations],
            "artifacts": [item.to_dict() for item in self.artifacts],
        }

    def summary_dict(self, *, sample_limit: int = 10) -> dict[str, Any]:
        """Return a bounded audit result suitable for routine governance checks."""

        violations = self.violations
        samples = violations[:sample_limit]
        return {
            "root": str(self.root),
            "stability_attempts": self.stability_attempts,
            "counts": self.counts,
            "violation_count": len(violations),
            "truncated_violation_count": len(violations) - len(samples),
            "violation_samples": [item.to_dict() for item in samples],
        }


def _workspace_bridge(path: Path) -> bool:
    if path.suffix.lower() not in _RUNTIME_SUFFIXES:
        return False
    content_archive._stability_hook("workspace-bridge:before-read", path)
    payload, _ = content_archive._stable_read_regular(path, max_bytes=1024)
    return BRIDGE_MARKER in payload.decode("utf-8", errors="ignore")


def _has_shebang(path: Path) -> bool:
    """Detect a `#!` interpreter line; survives lost exec bits that hide runtime scripts."""
    try:
        with path.open("rb") as fh:
            return fh.read(2) == b"#!"
    except OSError:
        return False


def _machine_generated_log(relative: str) -> bool:
    """Identify mutable machine logs without treating historical logs as cache."""

    relative_path = Path(relative)
    if relative_path.suffix.lower() != ".log":
        return False
    parts = tuple(part.lower() for part in relative_path.parts)
    if "_generated" in parts or "_runtime" in parts:
        return True
    if any(parts[index : index + 2] == ("_control", "logs") for index in range(len(parts) - 1)):
        return True
    if len(parts) != 2 or parts[0] != "_inbox":
        return False
    stem = relative_path.stem.lower()
    return stem.endswith("_runner") or stem.endswith("_runner_err")


_FS_TRANSIENT_PREFIXES = (".fuse_hidden", ".nfs")


def _auditable_file(path: Path) -> None | bool:
    """Include every non-directory node without following symlinks; skip filesystem transient files."""
    try:
        if not stat.S_ISDIR(path.lstat().st_mode):
            if path.name.startswith(_FS_TRANSIENT_PREFIXES):
                return False
            return True
    except OSError:
        return True
    return False


def _invalid_node(path: Path, relative: str, reason: str) -> ArtifactClassification:
    return ArtifactClassification(path, relative, "invalid_archive", reason, ARCHIVE_ISSUE_CODE)


def classify_artifact(
    root: Path,
    path: Path,
    *,
    archive_resolver: ContentArchiveResolver | None = None,
) -> ArtifactClassification:
    """Classify one path without executing it or following symlinks."""

    root_absolute = root.expanduser().absolute()
    path_absolute = path.expanduser().absolute()
    relative = path_absolute.relative_to(root_absolute).as_posix()
    parts = {part.lower() for part in Path(relative).parts}
    name = path_absolute.name
    name_lower = name.lower()
    suffix = path_absolute.suffix.lower()
    resolver = archive_resolver or ContentArchiveResolver(root_absolute)

    try:
        path_info = path_absolute.lstat()
    except OSError as error:
        return _invalid_node(path_absolute, relative, f"cannot inspect filesystem node: {error}")
    is_link = stat.S_ISLNK(path_info.st_mode)
    executable = bool(path_info.st_mode & stat.S_IXUSR) if stat.S_ISREG(path_info.st_mode) else False

    if name == ARCHIVE_MANIFEST_NAME:
        archive = resolver.lookup(path_absolute)
        if archive is not None and not archive.ok:
            return ArtifactClassification(
                path_absolute,
                relative,
                "contract",
                f"invalid CONTENT_ARCHIVE.yaml: {archive.message}",
                ARCHIVE_ISSUE_CODE,
            )
        kind, reason = "contract", "declares a frozen historical source archive"
    elif is_link:
        try:
            _, target_metadata = content_archive._stable_readlink(path_absolute)
        except ContentArchiveValidationError as error:
            return _invalid_node(path_absolute, relative, str(error))
        if target_metadata is not None and not stat.S_ISREG(target_metadata[2]):
            return _invalid_node(path_absolute, relative, "symlink target is not a regular file")
        if parts & _CACHE_DIRS or suffix in _CACHE_SUFFIXES:
            kind, reason = "cache", "derived cache or mutable local store belongs in Workspace"
        elif (archive := resolver.lookup(path_absolute)) is not None:
            if archive.ok:
                kind, reason = "content_archive", "frozen historical source material covered by CONTENT_ARCHIVE.yaml"
            else:
                kind, reason = "invalid_archive", f"invalid CONTENT_ARCHIVE.yaml: {archive.message}"
        elif _machine_generated_log(relative):
            kind, reason = "cache", "derived cache or mutable local store belongs in Workspace"
        elif suffix in _RUNTIME_SUFFIXES:
            kind, reason = "runtime", "executable implementation belongs in Workspace"
        else:
            kind, reason = "content", "canonical link artifact"
    elif not stat.S_ISREG(path_info.st_mode):
        return _invalid_node(path_absolute, relative, "unsupported filesystem node in content plane")
    elif parts & _CACHE_DIRS or suffix in _CACHE_SUFFIXES:
        kind, reason = "cache", "derived cache or mutable local store belongs in Workspace"
    else:
        try:
            workspace_bridge = _workspace_bridge(path_absolute)
        except ContentArchiveValidationError as error:
            return _invalid_node(path_absolute, relative, str(error))
        if workspace_bridge:
            kind, reason = "bridge", "thin compatibility bridge to a Workspace-owned capability"
        elif (archive := resolver.lookup(path_absolute)) is not None:
            if archive.ok:
                kind, reason = "content_archive", "frozen historical source material covered by CONTENT_ARCHIVE.yaml"
            else:
                kind, reason = "invalid_archive", f"invalid CONTENT_ARCHIVE.yaml: {archive.message}"
        elif _machine_generated_log(relative):
            kind, reason = "cache", "derived cache or mutable local store belongs in Workspace"
        elif suffix in _RUNTIME_SUFFIXES or ((executable or _has_shebang(path_absolute)) and not suffix):
            kind, reason = "runtime", "executable implementation belongs in Workspace"
        elif name_lower in _PROJECTION_NAMES or "_generated" in parts or "generated" in parts:
            kind, reason = "projection", "mutable or generated view must not become canonical truth"
        elif name_lower in _CONTRACT_NAMES or parts & _CONTRACT_DIRS:
            kind, reason = "contract", "declarative domain constitution or semantic contract"
        elif "_control" in parts and suffix in {".json", ".toml", ".yaml", ".yml"}:
            kind, reason = "contract", "declarative control-plane contract"
        else:
            kind, reason = "content", "canonical human-readable content or source material"

    return ArtifactClassification(path_absolute, relative, kind, reason)


def _has_stability_failure(report: ContentPlaneReport) -> bool:
    return any(
        item.code == ARCHIVE_ISSUE_CODE and any(marker in item.reason for marker in _STABILITY_FAILURE_MARKERS)
        for item in report.artifacts
    )


def _audit_content_plane_once(root: Path) -> ContentPlaneReport:
    """Run one complete content-plane scan without following symlink targets."""

    root_absolute = root.expanduser().absolute()
    try:
        root_info = root_absolute.lstat()
    except OSError as error:
        raise ValueError(f"content-plane root is not a directory: {root_absolute}") from error
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode):
        raise ValueError(f"content-plane root is not a directory: {root_absolute}")

    try:
        first = content_archive._snapshot_tree(root_absolute)
    except ContentArchiveValidationError as error:
        failure = _invalid_node(root_absolute, ".", str(error))
        return ContentPlaneReport(root_absolute, (failure,))
    content_archive._stability_hook("audit:enumerated", root_absolute)
    link_samples: dict[Path, content_archive._LinkSnapshot] = {}
    stability_failures: dict[Path, ArtifactClassification] = {}
    for entry in first.entries:
        if not stat.S_ISLNK(entry.mode):
            continue
        try:
            link_samples[entry.path] = content_archive._stable_readlink(entry.path)
        except ContentArchiveValidationError as error:
            stability_failures[entry.path] = _invalid_node(entry.path, entry.relative_path, str(error))
    resolver = ContentArchiveResolver(root_absolute)
    artifacts = [
        stability_failures.get(entry.path) or classify_artifact(root_absolute, entry.path, archive_resolver=resolver)
        for entry in first.entries
        if _auditable_file(entry.path)
    ]
    content_archive._stability_hook("audit:before-revalidate", root_absolute)
    try:
        second = content_archive._snapshot_tree(root_absolute)
        if not content_archive._same_tree(first, second):
            raise ContentArchiveValidationError("content-plane tree changed during audit enumeration")
        content_archive._revalidate_links(link_samples)
    except ContentArchiveValidationError as error:
        artifacts.append(_invalid_node(root_absolute, ".", str(error)))
    artifacts.sort(key=lambda item: item.relative_path)
    return ContentPlaneReport(root_absolute, tuple(artifacts))


def audit_content_plane(root: Path, *, max_attempts: int = _DEFAULT_AUDIT_ATTEMPTS) -> ContentPlaneReport:
    """Scan one root with bounded whole-attempt retries for transient drift.

    Every attempt keeps the strict snapshot and no-follow checks. A report is
    returned only after a stable attempt or after all attempts fail closed.
    """

    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    attempts_used = 1
    report = _audit_content_plane_once(root)
    while attempts_used < max_attempts and _has_stability_failure(report):
        report = _audit_content_plane_once(root)
        attempts_used += 1
    return replace(report, stability_attempts=attempts_used)
