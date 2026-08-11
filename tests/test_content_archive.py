"""Contract tests for frozen historical source archives."""

from __future__ import annotations

import errno
import hashlib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from l4_kernel import content_archive
from l4_kernel.content_plane import audit_content_plane, classify_artifact


def _inventory(root: Path) -> dict[str, int | str]:
    manifest = root / "CONTENT_ARCHIVE.yaml"
    entries = sorted(
        (
            path
            for path in root.rglob("*")
            if path != manifest
            and (path.is_file() or (path.is_symlink() and (not path.is_dir() or path.name == "CONTENT_ARCHIVE.yaml")))
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    digest = hashlib.sha256()
    total_bytes = 0
    for path in entries:
        contents = os.fsencode(os.readlink(path)) if path.is_symlink() else path.read_bytes()
        total_bytes += len(contents)
        digest_contents = b"symlink\0" + contents if path.is_symlink() else contents
        digest.update(os.fsencode(path.relative_to(root).as_posix()))
        digest.update(b"\0")
        digest.update(str(len(contents)).encode("ascii"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(digest_contents).hexdigest().encode("ascii"))
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
    manifest = _write_archive_manifest(archive)
    payload = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    del payload["execution_policy"]
    manifest.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

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


def test_manifest_with_non_string_key_fails_closed_without_traceback(tmp_path: Path) -> None:
    archive = tmp_path / "_archive" / "old-tools"
    archive.mkdir(parents=True)
    source = archive / "run.py"
    source.write_text("print('old')\n", encoding="utf-8")
    manifest = _write_archive_manifest(archive)
    manifest.write_text(f"1: invalid\n{manifest.read_text(encoding='utf-8')}", encoding="utf-8")

    try:
        report = audit_content_plane(tmp_path)
    except (OSError, TypeError) as error:
        pytest.fail(f"invalid manifest must fail closed, not raise {type(error).__name__}: {error}")

    assert report.ok is False
    assert {item.code for item in report.violations} == {"L4-CONTENT-011"}


def test_invalid_utf8_manifest_fails_closed_without_traceback(tmp_path: Path) -> None:
    archive = tmp_path / "_archive" / "old-tools"
    archive.mkdir(parents=True)
    source = archive / "run.py"
    source.write_text("print('old')\n", encoding="utf-8")
    (archive / "CONTENT_ARCHIVE.yaml").write_bytes(b"\xff\xfe")

    try:
        report = audit_content_plane(tmp_path)
    except UnicodeError as error:
        pytest.fail(f"invalid UTF-8 manifest must fail closed, not raise: {error}")

    assert report.ok is False
    assert {item.code for item in report.violations} == {"L4-CONTENT-011"}


def test_manifest_symlink_to_directory_is_audited_as_invalid_contract(tmp_path: Path) -> None:
    archive = tmp_path / "_archive" / "old-tools"
    target = tmp_path / "outside"
    archive.mkdir(parents=True)
    target.mkdir()
    (target / "secret.py").write_text("print('outside')\n", encoding="utf-8")
    (archive / "CONTENT_ARCHIVE.yaml").symlink_to(target, target_is_directory=True)

    report = audit_content_plane(tmp_path)

    assert report.ok is False
    assert any(item.kind == "contract" and item.code == "L4-CONTENT-011" for item in report.artifacts)
    assert "_archive/old-tools/CONTENT_ARCHIVE.yaml/secret.py" not in {item.relative_path for item in report.artifacts}


def test_nested_manifest_directory_symlink_drifts_parent_inventory(tmp_path: Path) -> None:
    archive = tmp_path / "_archive" / "old-tools"
    target = tmp_path / "outside"
    archive.mkdir(parents=True)
    source = archive / "run.py"
    source.write_text("print('old')\n", encoding="utf-8")
    _write_archive_manifest(archive)
    target.mkdir()
    (target / "secret.py").write_text("print('outside')\n", encoding="utf-8")
    nested = archive / "nested" / "CONTENT_ARCHIVE.yaml"
    nested.parent.mkdir()
    nested.symlink_to(target, target_is_directory=True)

    report = audit_content_plane(tmp_path)

    by_path = {item.relative_path: item for item in report.artifacts}
    assert by_path["_archive/old-tools/run.py"].code == "L4-CONTENT-011"
    assert by_path["_archive/old-tools/nested/CONTENT_ARCHIVE.yaml"].code == "L4-CONTENT-011"
    assert "_archive/old-tools/nested/CONTENT_ARCHIVE.yaml/secret.py" not in by_path


@pytest.mark.skipif(os.name != "posix", reason="surrogateescaped filenames require POSIX filesystem semantics")
def test_surrogateescaped_filename_hashes_without_traceback_and_detects_drift(tmp_path: Path) -> None:
    archive = tmp_path / "_archive" / "old-tools"
    archive.mkdir(parents=True)
    filename = os.fsdecode(b"legacy-\xff.py")
    source = archive / filename
    try:
        source.write_text("print('old')\n", encoding="utf-8")
    except OSError as error:
        unsupported = {errno.EILSEQ, errno.EINVAL, getattr(errno, "ENOTSUP", -1)}
        if error.errno not in unsupported:
            pytest.fail(f"unexpected error creating surrogateescaped filename: {error}")
        pytest.skip(f"filesystem rejects surrogateescaped POSIX names: {error}")
    _write_archive_manifest(archive)

    try:
        assert classify_artifact(tmp_path, source).kind == "content_archive"
    except UnicodeError as error:
        pytest.fail(f"surrogateescaped filename must not raise: {error}")
    source.write_text("print('changed')\n", encoding="utf-8")
    assert classify_artifact(tmp_path, source).code == "L4-CONTENT-011"


def test_lowercase_archive_filename_is_not_a_manifest_contract(tmp_path: Path) -> None:
    archive = tmp_path / "_archive" / "old-tools"
    archive.mkdir(parents=True)
    lower_manifest = archive / "content_archive.yaml"
    lower_manifest.write_text("schema: l4.content-archive/v1\n", encoding="utf-8")

    result = classify_artifact(tmp_path, lower_manifest)

    assert result.kind == "content"
    assert result.code is None


@pytest.mark.parametrize("captured_at", ["2026-08-11", "2026-08-11T00:00:00"])
def test_date_only_or_naive_archive_timestamp_fails_closed(tmp_path: Path, captured_at: str) -> None:
    archive = tmp_path / "_knowledge" / "old-tools"
    archive.mkdir(parents=True)
    source = archive / "run.py"
    source.write_text("print('old')\n", encoding="utf-8")
    _write_archive_manifest(archive, captured_at=captured_at)

    assert classify_artifact(tmp_path, source).code == "L4-CONTENT-011"


def test_aware_archive_timestamp_is_accepted_when_yaml_parses_datetime(tmp_path: Path) -> None:
    archive = tmp_path / "_knowledge" / "old-tools"
    archive.mkdir(parents=True)
    source = archive / "run.py"
    source.write_text("print('old')\n", encoding="utf-8")
    _write_archive_manifest(archive, captured_at=datetime(2026, 8, 11, tzinfo=timezone(timedelta(hours=8))))

    assert classify_artifact(tmp_path, source).kind == "content_archive"


def test_broken_symlink_is_included_in_archive_inventory(tmp_path: Path) -> None:
    archive = tmp_path / "_archive" / "old-tools"
    archive.mkdir(parents=True)
    broken = archive / "missing.py"
    broken.symlink_to("missing-target")
    _write_archive_manifest(archive)

    assert classify_artifact(tmp_path, broken).kind == "content_archive"


def test_inventory_lstat_failure_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "_archive" / "old-tools"
    archive.mkdir(parents=True)
    source = archive / "run.py"
    source.write_text("print('old')\n", encoding="utf-8")
    _write_archive_manifest(archive)
    original_lstat = Path.lstat

    def fail_source_lstat(path: Path):
        if path == source:
            raise OSError("inventory unavailable")
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", fail_source_lstat)

    assert classify_artifact(tmp_path, source).code == "L4-CONTENT-011"


def test_inventory_readlink_failure_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "_archive" / "old-tools"
    archive.mkdir(parents=True)
    target = archive / "target.py"
    target.write_text("print('old')\n", encoding="utf-8")
    link = archive / "linked.py"
    link.symlink_to(target.name)
    _write_archive_manifest(archive)

    monkeypatch.setattr(content_archive.os, "readlink", lambda path: (_ for _ in ()).throw(OSError("readlink unavailable")))

    try:
        result = classify_artifact(tmp_path, link)
    except OSError as error:
        pytest.fail(f"inventory readlink failure must fail closed, not raise: {error}")

    assert result.code == "L4-CONTENT-011"


@pytest.mark.parametrize("plane", ["_control", "_external"])
def test_forbidden_archive_planes_fail_closed(tmp_path: Path, plane: str) -> None:
    archive = tmp_path / plane / "old-tools"
    archive.mkdir(parents=True)
    source = archive / "run.py"
    source.write_text("print('old')\n", encoding="utf-8")
    _write_archive_manifest(archive)

    assert classify_artifact(tmp_path, source).code == "L4-CONTENT-011"


def test_extensionless_executable_in_valid_archive_remains_content(tmp_path: Path) -> None:
    archive = tmp_path / "_storage" / "old-tools"
    archive.mkdir(parents=True)
    source = archive / "runner"
    source.write_text("#!/bin/sh\necho old\n", encoding="utf-8")
    source.chmod(0o755)
    _write_archive_manifest(archive)

    assert classify_artifact(tmp_path, source).kind == "content_archive"


def test_archive_root_is_validated_once_per_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "_storage" / "old-tools"
    archive.mkdir(parents=True)
    for name in ("one.py", "two.py", "three.py"):
        (archive / name).write_text(name, encoding="utf-8")
    _write_archive_manifest(archive)
    calls = 0
    original_validate = content_archive._validate_mapping

    def count_validations(root: Path, archive_root: Path, manifest: Path) -> None:
        nonlocal calls
        calls += 1
        original_validate(root, archive_root, manifest)

    monkeypatch.setattr(content_archive, "_validate_mapping", count_validations)

    assert audit_content_plane(tmp_path).ok is True
    assert calls == 1


def test_directory_probe_error_is_cached_for_all_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "_archive" / "old-tools"
    archive.mkdir(parents=True)
    (archive / "one.py").write_text("one", encoding="utf-8")
    (archive / "two.py").write_text("two", encoding="utf-8")
    original_iterdir = Path.iterdir
    calls = 0

    def fail_once(path: Path):
        nonlocal calls
        if path == archive:
            calls += 1
            if calls == 1:
                raise OSError("transient directory probe failure")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", fail_once)

    report = audit_content_plane(tmp_path)

    assert calls == 1
    archive_items = [item for item in report.artifacts if item.path.parent == archive]
    assert {item.code for item in archive_items} == {"L4-CONTENT-011"}
