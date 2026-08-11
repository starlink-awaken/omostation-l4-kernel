"""Strict, read-only contracts for frozen historical source archives."""

from __future__ import annotations

import hashlib
import os
import stat
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


class ContentArchiveValidationError(ValueError):
    """A malformed archive declaration or unreadable archive inventory."""


def _timestamp(value: Any, field: str) -> None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ContentArchiveValidationError(f"{field} must be an ISO-8601 datetime") from error
    else:
        raise ContentArchiveValidationError(f"{field} must be an ISO-8601 datetime")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContentArchiveValidationError(f"{field} must include a timezone offset")


def _nonempty_string(raw: dict[str, Any], field: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ContentArchiveValidationError(f"missing or invalid field: {field}")
    return value


def _inventory(root: Path) -> dict[str, int | str]:
    """Build the deterministic inventory, excluding the root declaration itself."""

    manifest = root / ARCHIVE_MANIFEST_NAME
    entries: list[tuple[Path, bool]] = []
    try:
        for path in root.rglob("*"):
            if path == manifest:
                continue
            try:
                path_stat = path.lstat()
            except OSError as error:
                raise ContentArchiveValidationError(f"cannot stat archive inventory entry: {path}") from error
            is_link = stat.S_ISLNK(path_stat.st_mode)
            if is_link:
                try:
                    if path.is_dir() and path.name != ARCHIVE_MANIFEST_NAME:
                        continue
                except OSError as error:
                    raise ContentArchiveValidationError(f"cannot inspect archive symlink: {path}") from error
            elif not stat.S_ISREG(path_stat.st_mode):
                continue
            entries.append((path, is_link))
    except OSError as error:
        raise ContentArchiveValidationError(f"cannot scan archive inventory: {root}") from error
    entries.sort(key=lambda item: item[0].relative_to(root).as_posix())
    tree = hashlib.sha256()
    total_bytes = 0
    for path, is_link in entries:
        relative = path.relative_to(root).as_posix()
        try:
            payload = os.fsencode(os.readlink(path)) if is_link else path.read_bytes()
        except OSError as error:
            raise ContentArchiveValidationError(f"cannot read archive inventory entry: {path}") from error
        size = len(payload)
        digest_payload = b"symlink\0" + payload if is_link else payload
        total_bytes += size
        tree.update(os.fsencode(relative))
        tree.update(b"\0")
        tree.update(str(size).encode("ascii"))
        tree.update(b"\0")
        tree.update(hashlib.sha256(digest_payload).hexdigest().encode("ascii"))
        tree.update(b"\n")
    return {"files": len(entries), "bytes": total_bytes, "tree_sha256": tree.hexdigest()}


def _validate_placement(root: Path, archive_root: Path) -> None:
    try:
        parts = {part.lower() for part in archive_root.relative_to(root).parts}
    except ValueError as error:
        raise ContentArchiveValidationError("archive root escapes content-plane root") from error
    if parts & _FORBIDDEN_PLANES:
        raise ContentArchiveValidationError("CONTENT_ARCHIVE.yaml is declared in a forbidden plane")
    if not parts & _ALLOWED_PLANES:
        raise ContentArchiveValidationError("CONTENT_ARCHIVE.yaml must be below _archive, _storage, or _knowledge")


def _validate_mapping(root: Path, archive_root: Path, manifest: Path) -> None:
    _validate_placement(root, archive_root)
    try:
        if manifest.is_symlink():
            raise ContentArchiveValidationError("CONTENT_ARCHIVE.yaml must not be a symlink")
    except OSError as error:
        raise ContentArchiveValidationError("cannot inspect CONTENT_ARCHIVE.yaml") from error
    try:
        raw = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ContentArchiveValidationError(f"invalid CONTENT_ARCHIVE.yaml: {error}") from error
    if not isinstance(raw, dict):
        raise ContentArchiveValidationError("CONTENT_ARCHIVE.yaml must be a mapping")
    if any(not isinstance(key, str) for key in raw):
        raise ContentArchiveValidationError("CONTENT_ARCHIVE.yaml keys must be strings")
    unknown = sorted(set(raw) - _FIELDS)
    if unknown:
        raise ContentArchiveValidationError(f"unknown fields: {', '.join(unknown)}")
    missing = sorted(_FIELDS - set(raw))
    if missing:
        raise ContentArchiveValidationError(f"missing required fields: {', '.join(missing)}")
    if _nonempty_string(raw, "schema") != _ARCHIVE_SCHEMA:
        raise ContentArchiveValidationError(f"unsupported schema: {raw['schema']}")
    _nonempty_string(raw, "owner")
    _nonempty_string(raw, "reason")
    if _nonempty_string(raw, "source_kind") != "historical-source-material":
        raise ContentArchiveValidationError("source_kind must be historical-source-material")
    if _nonempty_string(raw, "status") != "frozen":
        raise ContentArchiveValidationError("status must be frozen")
    if _nonempty_string(raw, "execution_policy") != "deny":
        raise ContentArchiveValidationError("execution_policy must be deny")
    _timestamp(raw["captured_at"], "captured_at")

    inventory = raw["inventory"]
    if not isinstance(inventory, dict) or any(not isinstance(key, str) for key in inventory) or set(inventory) != _INVENTORY_FIELDS:
        raise ContentArchiveValidationError("inventory must contain files, bytes, and tree_sha256")
    if any(not isinstance(inventory[field], int) or isinstance(inventory[field], bool) or inventory[field] < 0 for field in ("files", "bytes")):
        raise ContentArchiveValidationError("inventory files and bytes must be non-negative integers")
    fingerprint = inventory["tree_sha256"]
    if not isinstance(fingerprint, str) or len(fingerprint) != 64 or any(char not in "0123456789abcdef" for char in fingerprint):
        raise ContentArchiveValidationError("inventory tree_sha256 must be a lowercase SHA-256 digest")

    evidence = raw["consumer_evidence"]
    if not isinstance(evidence, dict) or any(not isinstance(key, str) for key in evidence) or set(evidence) != _CONSUMER_EVIDENCE_FIELDS:
        raise ContentArchiveValidationError("consumer_evidence must contain scanned_at and active_consumers")
    _timestamp(evidence["scanned_at"], "consumer_evidence.scanned_at")
    if not isinstance(evidence["active_consumers"], list) or evidence["active_consumers"]:
        raise ContentArchiveValidationError("consumer_evidence.active_consumers must be an empty list")

    actual = _inventory(archive_root)
    if inventory != actual:
        raise ContentArchiveValidationError("archive inventory does not match files, bytes, or tree_sha256")


class ContentArchiveResolver:
    """Resolve the nearest manifest while scanning each declared root only once."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().absolute()
        self._manifest_entries: dict[Path, Path | None | ArchiveValidation] = {}

    def lookup(self, path: Path) -> ArchiveValidation | None:
        current = path.expanduser().absolute().parent
        while True:
            try:
                current.relative_to(self.root)
            except ValueError:
                return None
            if current not in self._manifest_entries:
                try:
                    entry: Path | None | ArchiveValidation = next(
                        (candidate for candidate in current.iterdir() if candidate.name == ARCHIVE_MANIFEST_NAME), None
                    )
                except OSError as error:
                    entry = ArchiveValidation(
                        current,
                        current / ARCHIVE_MANIFEST_NAME,
                        f"cannot inspect CONTENT_ARCHIVE.yaml: {error}",
                    )
                self._manifest_entries[current] = entry
            entry = self._manifest_entries[current]
            if isinstance(entry, ArchiveValidation):
                return entry
            if entry is not None:
                result = self._validate(current, entry)
                self._manifest_entries[current] = result
                return result
            if current == self.root:
                return None
            current = current.parent

    def _validate(self, archive_root: Path, manifest: Path) -> ArchiveValidation:
        try:
            _validate_mapping(self.root, archive_root, manifest)
        except ContentArchiveValidationError as error:
            return ArchiveValidation(archive_root, manifest, str(error))
        else:
            return ArchiveValidation(archive_root, manifest)
