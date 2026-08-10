"""Dynamic DomainManifest registry tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from l4_kernel.config_loader import resolve_registry_path
from l4_kernel.consistency import check_consistency, compare_registry_sources
from l4_kernel.contracts import ContractError
from l4_kernel.manifest_registry import ManifestRegistry


def _write_manifest(root: Path, domain_id: str, *, space_ref: str = "personal-space") -> Path:
    domain = root / domain_id
    domain.mkdir(parents=True)
    path = domain / "DOMAIN.yaml"
    payload = {
        "apiVersion": "l4/v1",
        "kind": "DomainManifest",
        "id": domain_id,
        "display_name": domain_id.title(),
        "archetype": "private-core",
        "space_ref": space_ref,
        "root": ".",
        "owners": ["personal-space-owner"],
        "principal_ref": "personal-space-owner",
        "default_sensitivity": "private",
        "default_visibility": "private",
        "sharing_policy": "explicit_publish",
        "retention": "permanent",
        "authority_policy": "canonical_write",
        "harness_profile_ref": "harness://private-core/v1",
        "lifecycle": "active",
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _write_registry(root: Path, ids: list[str]) -> Path:
    for domain_id in ids:
        _write_manifest(root, domain_id)
    path = root / "registry.yaml"
    payload = {
        "apiVersion": "l4/v1",
        "kind": "DomainRegistry",
        "id": "test-registry",
        "display_name": "Test Registry",
        "space_ref": "personal-space",
        "status": "active",
        "path_base": "registry_file_parent",
        "manifests": [{"id": domain_id, "path": f"{domain_id}/DOMAIN.yaml"} for domain_id in ids],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_registry_loads_only_manifest_entries(tmp_path: Path) -> None:
    index = _write_registry(tmp_path, ["vault", "work-weijian"])

    registry = ManifestRegistry.load(index)

    assert [item.id for item in registry.list_all()] == ["vault", "work-weijian"]
    assert registry.get("model-volume") is None
    assert registry.resolve_path("vault") == (tmp_path / "vault").resolve()


def test_registry_rejects_duplicate_ids(tmp_path: Path) -> None:
    index = _write_registry(tmp_path, ["vault"])
    payload = yaml.safe_load(index.read_text(encoding="utf-8"))
    payload["manifests"].append({"id": "vault", "path": "vault/DOMAIN.yaml"})
    index.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ContractError, match="duplicate manifest id"):
        ManifestRegistry.load(index)


def test_registry_rejects_manifest_id_mismatch(tmp_path: Path) -> None:
    index = _write_registry(tmp_path, ["vault"])
    payload = yaml.safe_load(index.read_text(encoding="utf-8"))
    payload["manifests"][0]["id"] = "other"
    index.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ContractError, match="manifest id mismatch"):
        ManifestRegistry.load(index)


def test_registry_rejects_absolute_manifest_path(tmp_path: Path) -> None:
    index = _write_registry(tmp_path, ["vault"])
    payload = yaml.safe_load(index.read_text(encoding="utf-8"))
    payload["manifests"][0]["path"] = str((tmp_path / "vault/DOMAIN.yaml").resolve())
    index.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ContractError, match="relative"):
        ManifestRegistry.load(index)


def test_registry_rejects_cross_space_manifest(tmp_path: Path) -> None:
    index = _write_registry(tmp_path, ["vault"])
    manifest_path = tmp_path / "vault/DOMAIN.yaml"
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    payload["space_ref"] = "team-space"
    manifest_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ContractError, match="space_ref"):
        ManifestRegistry.load(index)


def test_registry_adapts_to_readonly_legacy_registry(tmp_path: Path) -> None:
    registry = ManifestRegistry.load(_write_registry(tmp_path, ["vault"]))

    legacy = registry.as_legacy_registry()

    domain = legacy.get("vault")
    assert domain is not None
    assert domain.path == (tmp_path / "vault").resolve()
    assert domain.capabilities == ["knowledge.read", "knowledge.validate"]
    assert legacy.get("model-volume") is None


def test_consistency_accepts_explicit_manifest_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry = ManifestRegistry.load(_write_registry(tmp_path, ["vault"]))
    monkeypatch.setattr("l4_kernel.consistency.load_vault_paths", lambda: {})
    monkeypatch.setattr("l4_kernel.consistency.load_domain_index", lambda: [])

    report = check_consistency(registry)

    assert report["total_registry"] == 1
    assert report["status"] == "ok"
    assert compare_registry_sources(
        registry_domains=registry.list_all(),
        vault_paths={},
        index_domains=[],
    ) == report


def test_resolve_registry_path_prefers_explicit_then_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    explicit = tmp_path / "explicit.yaml"
    env_path = tmp_path / "env.yaml"
    monkeypatch.setenv("L4_DOMAIN_REGISTRY", str(env_path))

    assert resolve_registry_path(explicit) == explicit.resolve()
    assert resolve_registry_path() == env_path.resolve()


def test_resolve_registry_path_requires_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("L4_DOMAIN_REGISTRY", raising=False)

    with pytest.raises(FileNotFoundError, match="L4 domain registry not configured"):
        resolve_registry_path()


def test_example_registry_is_portable() -> None:
    example = Path(__file__).resolve().parents[1] / "etc" / "l4-domain-registry.example.yaml"

    payload = yaml.safe_load(example.read_text(encoding="utf-8"))

    assert payload["kind"] == "DomainRegistry"
    assert payload["space_ref"] == "personal-space"
    assert all(not Path(entry["path"]).is_absolute() for entry in payload["manifests"])
