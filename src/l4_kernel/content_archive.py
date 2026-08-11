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


def _stability_hook(stage: str, path: Path) -> None:
    """Deterministic test seam for mutations inside a validation window."""

    del stage, path


@dataclass(frozen=True, slots=True)
class _TreeEntry:
    path: Path
    relative_path: str
    mode: int
    metadata: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _TreeSnapshot:
    root_metadata: tuple[int, ...]
    entries: tuple[_TreeEntry, ...]

    @property
    def fingerprint(self) -> tuple[tuple[str, tuple[int, ...]], ...]:
        return tuple((entry.relative_path, entry.metadata) for entry in self.entries)


def _stat_metadata(info: os.stat_result) -> tuple[int, ...]:
    """Capture identity and content-relevant metadata, excluding mutable atime."""

    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _snapshot_tree(root: Path) -> _TreeSnapshot:
    """Enumerate a tree without following links and reject in-scan drift."""

    try:
        root_info = root.lstat()
    except OSError as error:
        raise ContentArchiveValidationError(f"cannot stat content tree root: {root}") from error
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode):
        raise ContentArchiveValidationError(f"content tree root is not a no-follow directory: {root}")

    entries: list[_TreeEntry] = []

    def visit(directory: Path) -> None:
        try:
            before = directory.lstat()
            with os.scandir(directory) as scanner:
                children = sorted((Path(item.path) for item in scanner), key=lambda child: os.fsencode(child.name))
            for child in children:
                child_info = child.lstat()
                relative = child.relative_to(root).as_posix()
                entries.append(_TreeEntry(child, relative, child_info.st_mode, _stat_metadata(child_info)))
                if stat.S_ISDIR(child_info.st_mode):
                    visit(child)
            after = directory.lstat()
        except OSError as error:
            raise ContentArchiveValidationError(f"cannot scan content tree directory: {directory}") from error
        if _stat_metadata(before) != _stat_metadata(after):
            raise ContentArchiveValidationError(f"content tree directory changed during enumeration: {directory}")

    visit(root)
    entries.sort(key=lambda entry: os.fsencode(entry.relative_path))
    try:
        root_after = root.lstat()
    except OSError as error:
        raise ContentArchiveValidationError(f"cannot revalidate content tree root: {root}") from error
    root_metadata = _stat_metadata(root_info)
    if root_metadata != _stat_metadata(root_after):
        raise ContentArchiveValidationError(f"content tree root changed during enumeration: {root}")
    return _TreeSnapshot(root_metadata, tuple(entries))


def _same_tree(first: _TreeSnapshot, second: _TreeSnapshot) -> bool:
    return first.root_metadata == second.root_metadata and first.fingerprint == second.fingerprint


def _stable_read_regular(path: Path, *, max_bytes: int | None = None) -> tuple[bytes, tuple[int, ...]]:
    """Read one regular file through a no-follow fd and verify its stable identity."""

    if not hasattr(os, "O_NOFOLLOW"):
        raise ContentArchiveValidationError("no-follow archive reads are unsupported on this platform")
    try:
        path_before = path.lstat()
        if not stat.S_ISREG(path_before.st_mode):
            raise ContentArchiveValidationError(f"unsupported archive filesystem node: {path}")
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
    except ContentArchiveValidationError:
        raise
    except OSError as error:
        raise ContentArchiveValidationError(f"cannot open archive entry without following links: {path}") from error

    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or _stat_metadata(path_before) != _stat_metadata(before):
            raise ContentArchiveValidationError(f"archive entry identity changed before read: {path}")
        chunks: list[bytes] = []
        remaining = max_bytes
        while remaining is None or remaining > 0:
            read_size = 1024 * 1024 if remaining is None else min(1024 * 1024, remaining)
            chunk = os.read(descriptor, read_size)
            if not chunk:
                break
            chunks.append(chunk)
            if remaining is not None:
                remaining -= len(chunk)
        _stability_hook("read:after", path)
        after = os.fstat(descriptor)
        path_after = path.lstat()
    except ContentArchiveValidationError:
        raise
    except OSError as error:
        raise ContentArchiveValidationError(f"cannot read archive inventory entry: {path}") from error
    finally:
        os.close(descriptor)

    metadata = _stat_metadata(before)
    if metadata != _stat_metadata(after) or metadata != _stat_metadata(path_after):
        raise ContentArchiveValidationError(f"archive entry changed during read: {path}")
    return b"".join(chunks), metadata


_LinkSnapshot = tuple[bytes, tuple[int, ...] | None]


def _stable_readlink(path: Path) -> _LinkSnapshot:
    """Read stable link text and sample the target node type twice."""

    try:
        before = path.lstat()
        if not stat.S_ISLNK(before.st_mode):
            raise ContentArchiveValidationError(f"archive link identity changed before read: {path}")
        target = os.readlink(path)
        _stability_hook("readlink:after", path)
        after = path.lstat()
        target_after = os.readlink(path)
    except ContentArchiveValidationError:
        raise
    except OSError as error:
        raise ContentArchiveValidationError(f"cannot read archive symlink: {path}") from error
    if _stat_metadata(before) != _stat_metadata(after) or target != target_after:
        raise ContentArchiveValidationError(f"archive symlink changed during read: {path}")

    target_path = Path(target)
    if not target_path.is_absolute():
        target_path = path.parent / target_path
    try:
        target_before = target_path.lstat()
    except FileNotFoundError:
        target_before = None
    except OSError as error:
        raise ContentArchiveValidationError(f"cannot inspect archive symlink target node: {path}") from error
    _stability_hook("symlink-target:sampled", path)
    try:
        target_after = target_path.lstat()
    except FileNotFoundError:
        target_after = None
    except OSError as error:
        raise ContentArchiveValidationError(f"cannot revalidate archive symlink target node: {path}") from error
    try:
        link_final = path.lstat()
        target_final = os.readlink(path)
    except OSError as error:
        raise ContentArchiveValidationError(f"cannot revalidate archive symlink: {path}") from error
    if _stat_metadata(before) != _stat_metadata(link_final) or target != target_final:
        raise ContentArchiveValidationError(f"archive symlink changed during target inspection: {path}")
    if (target_before is None) != (target_after is None):
        raise ContentArchiveValidationError(f"archive symlink target node changed during inspection: {path}")
    if target_before is None:
        return os.fsencode(target), None
    target_metadata = _stat_metadata(target_before)
    if target_metadata != _stat_metadata(target_after):
        raise ContentArchiveValidationError(f"archive symlink target node changed during inspection: {path}")
    return os.fsencode(target), target_metadata


def _revalidate_links(samples: dict[Path, _LinkSnapshot]) -> None:
    """Bind link text and target signatures to the enclosing validation window."""

    for path, expected in samples.items():
        if _stable_readlink(path) != expected:
            raise ContentArchiveValidationError(f"archive symlink target changed during validation: {path}")


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


def _inventory(root: Path, *, link_samples: dict[Path, _LinkSnapshot] | None = None) -> dict[str, int | str]:
    """Build the deterministic inventory, excluding the root declaration itself."""

    manifest = root / ARCHIVE_MANIFEST_NAME
    first = _snapshot_tree(root)
    _stability_hook("inventory:enumerated", root)
    tree = hashlib.sha256()
    total_bytes = 0
    file_count = 0
    unsupported: str | None = None
    observed_links: dict[Path, _LinkSnapshot] = {}
    for entry in first.entries:
        path = entry.path
        if path == manifest or stat.S_ISDIR(entry.mode):
            continue
        is_link = stat.S_ISLNK(entry.mode)
        if is_link:
            link_snapshot = _stable_readlink(path)
            payload, target_metadata = link_snapshot
            observed_links[path] = link_snapshot
            if target_metadata is not None and not stat.S_ISREG(target_metadata[2]):
                unsupported = unsupported or f"unsupported archive symlink target node: {path}"
        elif stat.S_ISREG(entry.mode):
            payload, _ = _stable_read_regular(path)
        else:
            unsupported = unsupported or f"unsupported archive filesystem node: {path}"
            continue
        relative = entry.relative_path
        size = len(payload)
        digest_payload = b"symlink\0" + payload if is_link else payload
        file_count += 1
        total_bytes += size
        tree.update(os.fsencode(relative))
        tree.update(b"\0")
        tree.update(str(size).encode("ascii"))
        tree.update(b"\0")
        tree.update(hashlib.sha256(digest_payload).hexdigest().encode("ascii"))
        tree.update(b"\n")
    _stability_hook("inventory:before-revalidate", root)
    second = _snapshot_tree(root)
    if not _same_tree(first, second):
        raise ContentArchiveValidationError("archive tree changed during inventory enumeration")
    _revalidate_links(observed_links)
    if unsupported is not None:
        raise ContentArchiveValidationError(unsupported)
    if link_samples is not None:
        link_samples.update(observed_links)
    return {"files": file_count, "bytes": total_bytes, "tree_sha256": tree.hexdigest()}


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
        manifest_info = manifest.lstat()
        if stat.S_ISLNK(manifest_info.st_mode):
            raise ContentArchiveValidationError("CONTENT_ARCHIVE.yaml must not be a symlink")
        if not stat.S_ISREG(manifest_info.st_mode):
            raise ContentArchiveValidationError("CONTENT_ARCHIVE.yaml must be a regular file")
    except OSError as error:
        raise ContentArchiveValidationError("cannot inspect CONTENT_ARCHIVE.yaml") from error
    try:
        manifest_bytes, manifest_metadata = _stable_read_regular(manifest)
        raw = yaml.safe_load(manifest_bytes.decode("utf-8"))
    except (UnicodeError, yaml.YAMLError) as error:
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
    if (
        not isinstance(inventory, dict)
        or any(not isinstance(key, str) for key in inventory)
        or set(inventory) != _INVENTORY_FIELDS
    ):
        raise ContentArchiveValidationError("inventory must contain files, bytes, and tree_sha256")
    if any(
        not isinstance(inventory[field], int) or isinstance(inventory[field], bool) or inventory[field] < 0
        for field in ("files", "bytes")
    ):
        raise ContentArchiveValidationError("inventory files and bytes must be non-negative integers")
    fingerprint = inventory["tree_sha256"]
    if (
        not isinstance(fingerprint, str)
        or len(fingerprint) != 64
        or any(char not in "0123456789abcdef" for char in fingerprint)
    ):
        raise ContentArchiveValidationError("inventory tree_sha256 must be a lowercase SHA-256 digest")

    evidence = raw["consumer_evidence"]
    if (
        not isinstance(evidence, dict)
        or any(not isinstance(key, str) for key in evidence)
        or set(evidence) != _CONSUMER_EVIDENCE_FIELDS
    ):
        raise ContentArchiveValidationError("consumer_evidence must contain scanned_at and active_consumers")
    _timestamp(evidence["scanned_at"], "consumer_evidence.scanned_at")
    if not isinstance(evidence["active_consumers"], list) or evidence["active_consumers"]:
        raise ContentArchiveValidationError("consumer_evidence.active_consumers must be an empty list")

    link_samples: dict[Path, _LinkSnapshot] = {}
    actual = _inventory(archive_root, link_samples=link_samples)
    _stability_hook("manifest:before-revalidate", manifest)
    final_bytes, final_metadata = _stable_read_regular(manifest)
    if manifest_bytes != final_bytes or manifest_metadata != final_metadata:
        raise ContentArchiveValidationError("CONTENT_ARCHIVE.yaml changed during archive validation")
    _revalidate_links(link_samples)
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
