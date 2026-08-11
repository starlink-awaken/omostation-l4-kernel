"""Security boundary tests for paths supplied by callers."""

from pathlib import Path

import pytest

from l4_kernel.path_policy import PathPolicyError, direct_mutation_allowed, resolve_within


@pytest.mark.parametrize("value", ["../../outside.md", "/tmp/outside.md", "../x"])
def test_resolve_within_rejects_escape(tmp_path: Path, value: str) -> None:
    with pytest.raises(PathPolicyError) as exc:
        resolve_within(tmp_path / "domain", value)

    assert exc.value.code == "L4-PATH-006"


@pytest.mark.parametrize("value", ["", "bad\x00path"])
def test_resolve_within_rejects_empty_or_invalid_path(tmp_path: Path, value: str) -> None:
    with pytest.raises(PathPolicyError, match="empty or invalid"):
        resolve_within(tmp_path / "domain", value)


def test_resolve_within_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "domain"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "escape").symlink_to(outside, target_is_directory=True)

    with pytest.raises(PathPolicyError, match="escapes domain root"):
        resolve_within(root, "escape/secret.md")


def test_resolve_within_accepts_nested_relative_path(tmp_path: Path) -> None:
    root = tmp_path / "domain"
    root.mkdir()

    assert resolve_within(root, "notes/today.md") == root / "notes" / "today.md"


def test_direct_mutation_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("L4_LEGACY_DIRECT_WRITE", raising=False)
    assert direct_mutation_allowed() is False


@pytest.mark.parametrize("value", ["true", "yes", "0", "01"])
def test_direct_mutation_requires_exact_legacy_switch(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("L4_LEGACY_DIRECT_WRITE", value)
    assert direct_mutation_allowed() is False


def test_direct_mutation_explicit_legacy_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("L4_LEGACY_DIRECT_WRITE", "1")
    assert direct_mutation_allowed() is True
