"""Dynamic registry backed by explicit L4 DomainManifest files."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from l4_kernel.contracts import ContractError, load_domain_manifest
from l4_kernel.registry import Domain, DomainRegistry

if TYPE_CHECKING:
    from l4_kernel.contracts import DomainManifest


_INDEX_FIELDS = {
    "apiVersion",
    "kind",
    "id",
    "display_name",
    "space_ref",
    "status",
    "path_base",
    "manifests",
}


class ManifestRegistry:
    """Validated, ordered collection of knowledge-domain manifests."""

    def __init__(self, *, index_path: Path, registry_id: str, manifests: tuple[DomainManifest, ...]) -> None:
        self.index_path = index_path
        self.id = registry_id
        self._manifests = manifests
        self._by_id = {manifest.id: manifest for manifest in manifests}

    @classmethod
    def load(cls, index_path: Path) -> ManifestRegistry:
        """Load an explicit registry index and every referenced manifest."""

        try:
            raw = yaml.safe_load(index_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ContractError("L4-CONTRACT-001", str(exc), index_path) from exc
        if not isinstance(raw, dict):
            raise ContractError("L4-CONTRACT-001", "registry document must be a mapping", index_path)
        unknown = sorted(set(raw) - _INDEX_FIELDS)
        if unknown:
            raise ContractError("L4-CONTRACT-001", f"unknown registry fields: {', '.join(unknown)}", index_path)
        if raw.get("apiVersion") != "l4/v1" or raw.get("kind") != "DomainRegistry":
            raise ContractError("L4-CONTRACT-001", "unsupported registry apiVersion or kind", index_path)
        if raw.get("space_ref") != "personal-space":
            raise ContractError("L4-CONTRACT-001", "Phase 0 registry space_ref must be personal-space", index_path)
        if raw.get("path_base") != "registry_file_parent":
            raise ContractError("L4-CONTRACT-001", "path_base must be registry_file_parent", index_path)
        registry_id = raw.get("id")
        if not isinstance(registry_id, str) or not registry_id.strip():
            raise ContractError("L4-CONTRACT-001", "missing required field: id", index_path)
        entries = raw.get("manifests")
        if not isinstance(entries, list) or not entries:
            raise ContractError("L4-CONTRACT-001", "manifests must be a non-empty list", index_path)

        manifests: list[DomainManifest] = []
        seen: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"id", "path"}:
                raise ContractError("L4-CONTRACT-001", "manifest entry requires only id and path", index_path)
            entry_id = entry.get("id")
            entry_path = entry.get("path")
            if not isinstance(entry_id, str) or not entry_id.strip():
                raise ContractError("L4-CONTRACT-001", "manifest entry id must be non-empty", index_path)
            if entry_id in seen:
                raise ContractError("L4-CONTRACT-001", f"duplicate manifest id: {entry_id}", index_path)
            if not isinstance(entry_path, str) or not entry_path.strip():
                raise ContractError("L4-CONTRACT-001", f"manifest path missing for {entry_id}", index_path)
            relative = Path(entry_path)
            if relative.is_absolute():
                raise ContractError("L4-CONTRACT-001", "manifest path must be relative", index_path)

            manifest = load_domain_manifest((index_path.resolve().parent / relative).resolve())
            if manifest.id != entry_id:
                raise ContractError(
                    "L4-CONTRACT-001",
                    f"manifest id mismatch: index={entry_id}, manifest={manifest.id}",
                    index_path,
                )
            if manifest.space_ref != raw["space_ref"]:
                raise ContractError(
                    "L4-CONTRACT-001",
                    f"manifest {entry_id} space_ref does not match registry space_ref",
                    index_path,
                )
            seen.add(entry_id)
            manifests.append(manifest)

        return cls(index_path=index_path.resolve(), registry_id=registry_id.strip(), manifests=tuple(manifests))

    def get(self, domain_id: str) -> DomainManifest | None:
        return self._by_id.get(domain_id)

    def list_all(self) -> list[DomainManifest]:
        return list(self._manifests)

    def resolve_path(self, domain_id: str) -> Path | None:
        manifest = self.get(domain_id)
        return manifest.root if manifest is not None else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "index_path": str(self.index_path),
            "domains": [
                {
                    "id": manifest.id,
                    "display_name": manifest.display_name,
                    "archetype": manifest.archetype,
                    "space_ref": manifest.space_ref,
                    "root": str(manifest.root),
                    "authority_policy": manifest.authority_policy,
                }
                for manifest in self._manifests
            ],
        }

    def as_legacy_registry(self) -> DomainRegistry:
        """Expose read-only knowledge domains to legacy callers during migration."""

        domains = [
            Domain(
                id=manifest.id,
                name=manifest.display_name,
                domain_type="document",
                path=manifest.root,
                bos_uri=f"bos://{manifest.id}/**",
                governance_tier=1,
                capabilities=["knowledge.read", "knowledge.validate"],
            )
            for manifest in self._manifests
        ]
        return DomainRegistry.from_domains(domains)
