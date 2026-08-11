"""Deterministic classification tests for the L4 Documents content plane."""

from __future__ import annotations

from pathlib import Path

from l4_kernel.content_plane import audit_content_plane, classify_artifact


def _write(root: Path, relative: str, content: str = "x") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_classifies_contract_content_runtime_projection_and_cache(tmp_path: Path) -> None:
    files = {
        "DOMAIN.yaml": "contract",
        "_knowledge/note.md": "content",
        "_control/executors/run.py": "runtime",
        "_control/STATE.md": "projection",
        "_runtime/cache.sqlite": "cache",
    }

    for relative, expected in files.items():
        path = _write(tmp_path, relative)
        assert classify_artifact(tmp_path, path).kind == expected


def test_workspace_bridge_marker_is_not_reported_as_runtime(tmp_path: Path) -> None:
    bridge = _write(
        tmp_path,
        "_runtime/kems-materialize.py",
        "#!/usr/bin/env python3\n# l4-content-plane: workspace-bridge\n",
    )

    result = classify_artifact(tmp_path, bridge)

    assert result.kind == "bridge"
    assert "Workspace" in result.reason


def test_cache_keeps_priority_over_valid_content_archive(tmp_path: Path) -> None:
    archive = tmp_path / "_archive" / "legacy"
    cache = archive / "nested" / "state.sqlite"
    cache.parent.mkdir(parents=True)
    cache.write_text("cache", encoding="utf-8")
    (archive / "CONTENT_ARCHIVE.yaml").write_text(
        """schema: l4.content-archive/v1
owner: personal
reason: historical source
source_kind: historical-source-material
status: frozen
execution_policy: deny
captured_at: '2026-08-11T00:00:00+08:00'
inventory:
  files: 1
  bytes: 5
  tree_sha256: f2ab16080806c39a84ca67417f544d9b562f3a0a5e5447a071e85f2463b75a9c
consumer_evidence:
  scanned_at: '2026-08-11T00:00:00+08:00'
  active_consumers: []
""",
        encoding="utf-8",
    )

    assert classify_artifact(tmp_path, cache).kind == "cache"


def test_archive_manifest_inside_cache_is_contract_and_invalidates_audit(tmp_path: Path) -> None:
    archive = tmp_path / "_archive" / ".cache"
    archive.mkdir(parents=True)
    manifest = _write(archive, "CONTENT_ARCHIVE.yaml", "schema: l4.content-archive/v1\n")

    result = classify_artifact(tmp_path, manifest)

    assert result.kind == "contract"
    assert result.code == "L4-CONTENT-011"
    assert audit_content_plane(tmp_path).ok is False


def test_audit_is_deterministic_and_runtime_or_cache_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "domain"
    root.mkdir()
    _write(root, "z-note.md")
    _write(root, "a-script.sh")
    _write(root, "nested/state.db")

    first = audit_content_plane(root)
    second = audit_content_plane(root)

    assert first.ok is False
    assert first.artifacts == second.artifacts
    assert [item.relative_path for item in first.artifacts] == ["a-script.sh", "nested/state.db", "z-note.md"]
    assert first.counts == {"cache": 1, "content": 1, "runtime": 1}
    assert {item.kind for item in first.violations} == {"cache", "runtime"}


def test_audit_does_not_recurse_through_directory_symlink(tmp_path: Path) -> None:
    domain = tmp_path / "domain"
    outside = tmp_path / "outside"
    domain.mkdir()
    outside.mkdir()
    _write(outside, "secret.py")
    (domain / "linked").symlink_to(outside, target_is_directory=True)

    report = audit_content_plane(domain)

    assert report.artifacts == ()
    assert report.ok is True


def test_audit_reports_runtime_file_symlink_without_following_directory_links(tmp_path: Path) -> None:
    domain = tmp_path / "domain"
    outside = tmp_path / "outside"
    domain.mkdir()
    outside.mkdir()
    runtime = _write(outside, "runner.py")
    (domain / "runtime-link.py").symlink_to(runtime)

    report = audit_content_plane(domain)

    assert len(report.artifacts) == 1
    assert report.artifacts[0].relative_path == "runtime-link.py"
    assert report.artifacts[0].kind == "runtime"
    assert report.ok is False
