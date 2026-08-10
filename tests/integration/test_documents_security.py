"""Opt-in security checks against every real Documents domain root."""

import hashlib
import os
from pathlib import Path

import pytest

from l4_kernel.config_loader import resolve_registry_path
from l4_kernel.manifest_registry import ManifestRegistry
from l4_kernel.path_policy import PathPolicyError, resolve_within

pytestmark = pytest.mark.skipif(
    not os.environ.get("L4_DOMAIN_REGISTRY"),
    reason="real Documents security test requires L4_DOMAIN_REGISTRY",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_all_registered_domains_reject_escape_without_external_mutation(tmp_path: Path) -> None:
    registry = ManifestRegistry.load(resolve_registry_path())
    outside = tmp_path / "outside.md"
    outside.write_text("immutable sentinel", encoding="utf-8")
    before = digest(outside)

    for manifest in registry.list_all():
        for requested in ("../../outside.md", "../outside.md", str(outside)):
            with pytest.raises(PathPolicyError) as error:
                resolve_within(manifest.root, requested)
            assert error.value.code == "L4-PATH-006"

    assert digest(outside) == before


def test_symlink_escape_is_rejected_without_external_mutation(tmp_path: Path) -> None:
    root = tmp_path / "domain"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    sentinel = outside / "sentinel.md"
    sentinel.write_text("immutable sentinel", encoding="utf-8")
    before = digest(sentinel)
    (root / "escape").symlink_to(outside, target_is_directory=True)

    with pytest.raises(PathPolicyError) as error:
        resolve_within(root, "escape/sentinel.md")

    assert error.value.code == "L4-PATH-006"
    assert digest(sentinel) == before
