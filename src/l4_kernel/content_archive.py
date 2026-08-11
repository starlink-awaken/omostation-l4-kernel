"""Strict, read-only contracts for frozen historical source archives."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

ARCHIVE_MANIFEST_NAME = "CONTENT_ARCHIVE.yaml"
ARCHIVE_ISSUE_CODE = "L4-CONTENT-011"

_ARCHIVE_SCHEMA = "l4.content-archive/v1"
_ALLOWED_PLANES = {"_archive", "_storage", "_knowledge"}
_FORBIDDEN_PLANES = {"_runtime", "_control", "_external"}
_FIELDS = {
    "schema",
    "owner",
    "reason",
    "source_kind",
    "status",
    "execution_policy",
    "captured_at",
    "inventory",
    "consumer_evidence",
}
_INVENTORY_FIELDS = {"files", "bytes", "tree_sha256"}
_CONSUMER_EVIDENCE_FIELDS = {"scanned_at", "active_consumers"}


@dataclass(frozen=True, slots=True)
class ArchiveValidation:
    """The cached validation result for one declared archive root."""

    root: Path
    manifest: Path
    message: str | None = None

    @property
    def ok(self) -> bool:
        return self.message is None


def _timestamp(value: Any, field: str) -> None:
    if isinstance(value, datetime):
        return
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be an ISO-8601 timestamp")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from error


def _nonempty_string(raw: dict[str, Any], field: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing or invalid field: {field}")
    return value


def _inventory(root: Path) -> dict[str, int | str]:
    """Build the deterministic inventory, excluding the root declaration itself."""

    manifest = root / ARCHIVE_MANIFEST_NAME
    entries = sorted(
        (path for path in root.rglob("*") if path.is_file() and path != manifest),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    tree = hashlib.sha256()
    total_bytes = 0
    for path in entries:
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            payload = os.readlink(path).encode("utf-8", errors="surrogateescape")
        else:
            payload = path.read_bytes()
        size = len(payload)
        total_bytes += size
        tree.update(relative.encode("utf-8"))
        tree.update(b"\0")
        tree.update(str(size).encode("ascii"))
        tree.update(b"\0")
        tree.update(hashlib.sha256(payload).hexdigest().encode("ascii"))
        tree.update(b"\n")
    return {"files": len(entries), "bytes": total_bytes, "tree_sha256": tree.hexdigest()}


def _validate_placement(root: Path, archive_root: Path) -> None:
    try:
        parts = {part.lower() for part in archive_root.relative_to(root).parts}
    except ValueError as error:
        raise ValueError("archive root escapes content-plane root") from error
    if parts & _FORBIDDEN_PLANES:
        raise ValueError("CONTENT_ARCHIVE.yaml is declared in a forbidden plane")
    if not parts & _ALLOWED_PLANES:
        raise ValueError("CONTENT_ARCHIVE.yaml must be below _archive, _storage, or _knowledge")


def _validate_mapping(root: Path, archive_root: Path, manifest: Path) -> None:
    _validate_placement(root, archive_root)
    if manifest.is_symlink():
        raise ValueError("CONTENT_ARCHIVE.yaml must not be a symlink")
    try:
        raw = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"invalid CONTENT_ARCHIVE.yaml: {error}") from error
    if not isinstance(raw, dict):
        raise ValueError("CONTENT_ARCHIVE.yaml must be a mapping")
    unknown = sorted(set(raw) - _FIELDS)
    if unknown:
        raise ValueError(f"unknown fields: {', '.join(unknown)}")
    missing = sorted(_FIELDS - set(raw))
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")
    if _nonempty_string(raw, "schema") != _ARCHIVE_SCHEMA:
        raise ValueError(f"unsupported schema: {raw['schema']}")
    _nonempty_string(raw, "owner")
    _nonempty_string(raw, "reason")
    if _nonempty_string(raw, "source_kind") != "historical-source-material":
        raise ValueError("source_kind must be historical-source-material")
    if _nonempty_string(raw, "status") != "frozen":
        raise ValueError("status must be frozen")
    if _nonempty_string(raw, "execution_policy") != "deny":
        raise ValueError("execution_policy must be deny")
    _timestamp(raw["captured_at"], "captured_at")

    inventory = raw["inventory"]
    if not isinstance(inventory, dict) or set(inventory) != _INVENTORY_FIELDS:
        raise ValueError("inventory must contain files, bytes, and tree_sha256")
    if any(not isinstance(inventory[field], int) or isinstance(inventory[field], bool) or inventory[field] < 0 for field in ("files", "bytes")):
        raise ValueError("inventory files and bytes must be non-negative integers")
    fingerprint = inventory["tree_sha256"]
    if not isinstance(fingerprint, str) or len(fingerprint) != 64 or any(char not in "0123456789abcdef" for char in fingerprint):
        raise ValueError("inventory tree_sha256 must be a lowercase SHA-256 digest")

    evidence = raw["consumer_evidence"]
    if not isinstance(evidence, dict) or set(evidence) != _CONSUMER_EVIDENCE_FIELDS:
        raise ValueError("consumer_evidence must contain scanned_at and active_consumers")
    _timestamp(evidence["scanned_at"], "consumer_evidence.scanned_at")
    if not isinstance(evidence["active_consumers"], list) or evidence["active_consumers"]:
        raise ValueError("consumer_evidence.active_consumers must be an empty list")

    actual = _inventory(archive_root)
    if inventory != actual:
        raise ValueError("archive inventory does not match files, bytes, or tree_sha256")


class ContentArchiveResolver:
    """Resolve the nearest manifest while scanning each declared root only once."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().absolute()
        self._results: dict[Path, ArchiveValidation] = {}

    def lookup(self, path: Path) -> ArchiveValidation | None:
        current = path.expanduser().absolute().parent
        while True:
            try:
                current.relative_to(self.root)
            except ValueError:
                return None
            manifest = current / ARCHIVE_MANIFEST_NAME
            if manifest.is_file() or manifest.is_symlink():
                return self._validate(current, manifest)
            if current == self.root:
                return None
            current = current.parent

    def _validate(self, archive_root: Path, manifest: Path) -> ArchiveValidation:
        cached = self._results.get(archive_root)
        if cached is not None:
            return cached
        try:
            _validate_mapping(self.root, archive_root, manifest)
        except ValueError as error:
            result = ArchiveValidation(archive_root, manifest, str(error))
        else:
            result = ArchiveValidation(archive_root, manifest)
        self._results[archive_root] = result
        return result
