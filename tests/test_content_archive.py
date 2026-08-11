"""Contract tests for frozen historical source archives."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from l4_kernel.content_plane import audit_content_plane, classify_artifact


def _inventory(root: Path) -> dict[str, int | str]:
    entries = sorted(
        (path for path in root.rglob("*") if path.is_file() and path.name != "CONTENT_ARCHIVE.yaml"),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    digest = hashlib.sha256()
    total_bytes = 0
    for path in entries:
        contents = path.read_bytes()
        total_bytes += len(contents)
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(contents)).encode("ascii"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(contents).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return {"files": len(entries), "bytes": total_bytes, "tree_sha256": digest.hexdigest()}


def _write_archive_manifest(archive: Path, **overrides: object) -> Path:
    payload: dict[str, object] = {
        "schema": "l4.content-archive/v1",
        "owner": "personal",
        "reason": "职业历史代码资料",
        "source_kind": "historical-source-material",
        "status": "frozen",
        "execution_policy": "deny",
        "captured_at": "2026-08-11T00:00:00+08:00",
        "inventory": _inventory(archive),
        "consumer_evidence": {"scanned_at": "2026-08-11T00:00:00+08:00", "active_consumers": []},
    }
    payload.update(overrides)
    manifest = archive / "CONTENT_ARCHIVE.yaml"
    manifest.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return manifest


def test_valid_frozen_archive_classifies_historical_code_and_manifest(tmp_path: Path) -> None:
    archive = tmp_path / "_storage" / "career-history"
    archive.mkdir(parents=True)
    source = archive / "legacy.py"
    source.write_text("print('historical')\n", encoding="utf-8")
    manifest = _write_archive_manifest(archive)

    assert classify_artifact(tmp_path, source).kind == "content_archive"
    assert classify_artifact(tmp_path, manifest).kind == "contract"
    assert audit_content_plane(tmp_path).ok is True


def test_archive_manifest_outside_permitted_plane_fails_closed(tmp_path: Path) -> None:
    archive = tmp_path / "legacy"
    archive.mkdir()
    source = archive / "run.py"
    source.write_text("print('old')\n", encoding="utf-8")
    _write_archive_manifest(archive)

    result = classify_artifact(tmp_path, source)

    assert result.kind == "invalid_archive"
    assert result.code == "L4-CONTENT-011"
    assert audit_content_plane(tmp_path).ok is False


def test_missing_archive_field_fails_closed_with_stable_issue_code(tmp_path: Path) -> None:
    archive = tmp_path / "_archive" / "old-tools"
    archive.mkdir(parents=True)
    source = archive / "run.py"
    source.write_text("print('old')\n", encoding="utf-8")
    _write_archive_manifest(archive, execution_policy=None)

    result = classify_artifact(tmp_path, source)

    assert result.kind == "invalid_archive"
    assert result.code == "L4-CONTENT-011"


def test_archive_inventory_drift_fails_closed(tmp_path: Path) -> None:
    archive = tmp_path / "_knowledge" / "historical-code"
    archive.mkdir(parents=True)
    source = archive / "run.py"
    source.write_text("print('old')\n", encoding="utf-8")
    _write_archive_manifest(archive)
    source.write_text("print('changed')\n", encoding="utf-8")

    result = classify_artifact(tmp_path, source)

    assert result.kind == "invalid_archive"
    assert result.code == "L4-CONTENT-011"


def test_archive_inventory_includes_nested_archive_declarations(tmp_path: Path) -> None:
    archive = tmp_path / "_archive" / "old-tools"
    archive.mkdir(parents=True)
    source = archive / "run.py"
    source.write_text("print('old')\n", encoding="utf-8")
    _write_archive_manifest(archive)
    nested = archive / "nested" / "CONTENT_ARCHIVE.yaml"
    nested.parent.mkdir()
    nested.write_text("schema: l4.content-archive/v1\n", encoding="utf-8")

    result = classify_artifact(tmp_path, source)

    assert result.kind == "invalid_archive"
    assert result.code == "L4-CONTENT-011"


def test_archive_with_active_consumer_evidence_fails_closed(tmp_path: Path) -> None:
    archive = tmp_path / "_archive" / "old-tools"
    archive.mkdir(parents=True)
    source = archive / "run.py"
    source.write_text("print('old')\n", encoding="utf-8")
    _write_archive_manifest(
        archive,
        consumer_evidence={"scanned_at": "2026-08-11T00:00:00+08:00", "active_consumers": ["cron"]},
    )

    result = classify_artifact(tmp_path, source)

    assert result.kind == "invalid_archive"
    assert result.code == "L4-CONTENT-011"
