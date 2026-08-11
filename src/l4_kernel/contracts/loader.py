"""Strict YAML loaders for L4 Phase 0 contracts."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from l4_kernel.contracts.models import DomainManifest, HarnessProfile

DOMAIN_ARCHETYPES = (
    "constitutional",
    "private-core",
    "operational",
    "library",
    "federation",
    "projection",
)
SENSITIVITY_LEVELS = ("internal", "private", "confidential", "restricted")
VISIBILITY_LEVELS = ("private",)
SHARING_POLICIES = ("deny", "explicit_publish")
RETENTION_POLICIES = ("permanent", "policy_managed", "rebuildable")
AUTHORITY_POLICIES = (
    "canonical_write",
    "reference_library",
    "federation_only",
    "projection_only",
)
LIFECYCLE_STATES = ("draft", "active", "suspended", "archived")
PHASE0_GATES = ("T0", "T1", "T2", "T4", "T7")

_DOMAIN_FIELDS = {
    "apiVersion",
    "kind",
    "id",
    "display_name",
    "archetype",
    "space_ref",
    "root",
    "owners",
    "principal_ref",
    "default_sensitivity",
    "default_visibility",
    "sharing_policy",
    "retention",
    "authority_policy",
    "harness_profile_ref",
    "lifecycle",
    "policy_refs",
}
_PROFILE_FIELDS = {
    "apiVersion",
    "kind",
    "id",
    "archetype",
    "required_gates",
    "advisory_gates",
    "disabled_gates",
}


class ContractError(ValueError):
    """Stable configuration failure raised by strict contract loaders."""

    def __init__(self, code: str, message: str, path: Path | None = None) -> None:
        self.code = code
        self.message = message
        self.path = path
        super().__init__(f"{code}: {message}")


def _load_mapping(path: Path) -> Mapping[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ContractError("L4-CONTRACT-001", str(exc), path) from exc
    if not isinstance(raw, Mapping):
        raise ContractError("L4-CONTRACT-001", "document must be a mapping", path)
    return raw


def _require(mapping: Mapping[str, Any], field: str, path: Path) -> Any:
    value = mapping.get(field)
    if value is None or value == "":
        raise ContractError("L4-CONTRACT-001", f"missing required field: {field}", path)
    return value


def _string(mapping: Mapping[str, Any], field: str, path: Path) -> str:
    value = _require(mapping, field, path)
    if not isinstance(value, str) or not value.strip():
        raise ContractError("L4-CONTRACT-001", f"{field} must be a non-empty string", path)
    return value.strip()


def _string_tuple(
    value: Any,
    field: str,
    path: Path,
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ContractError("L4-CONTRACT-001", f"{field} must be a list", path)
    if not value and not allow_empty:
        raise ContractError("L4-CONTRACT-001", f"{field} must not be empty", path)
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ContractError("L4-CONTRACT-001", f"{field} must contain non-empty strings", path)
    normalized = tuple(item.strip() for item in value)
    if len(normalized) != len(set(normalized)):
        raise ContractError("L4-CONTRACT-001", f"{field} must not contain duplicates", path)
    return normalized


def _enum(mapping: Mapping[str, Any], field: str, allowed: tuple[str, ...], path: Path) -> str:
    value = _string(mapping, field, path)
    if value not in allowed:
        raise ContractError(
            "L4-CONTRACT-001",
            f"unsupported {field}: {value}; expected one of {', '.join(allowed)}",
            path,
        )
    return value


def _reject_unknown(mapping: Mapping[str, Any], allowed: set[str], path: Path) -> None:
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        raise ContractError("L4-CONTRACT-001", f"unknown fields: {', '.join(unknown)}", path)


def _resolve_manifest_root(source: Path, raw_root: str) -> Path:
    candidate = Path(raw_root)
    if candidate.is_absolute():
        raise ContractError("L4-CONTRACT-001", "root must be relative to DOMAIN.yaml", source)
    base = source.resolve().parent
    resolved = (base / candidate).resolve(strict=False)
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ContractError("L4-CONTRACT-001", "root escapes DOMAIN.yaml directory", source) from exc
    return resolved


def load_domain_manifest(path: Path) -> DomainManifest:
    """Load one DomainManifest without fallback or implicit defaults."""

    raw = _load_mapping(path)
    _reject_unknown(raw, _DOMAIN_FIELDS, path)
    api_version = _string(raw, "apiVersion", path)
    kind = _string(raw, "kind", path)
    if api_version != "l4/v1":
        raise ContractError("L4-CONTRACT-001", f"unsupported apiVersion: {api_version}", path)
    if kind != "DomainManifest":
        raise ContractError("L4-CONTRACT-001", f"unsupported kind: {kind}", path)

    owners = _string_tuple(_require(raw, "owners", path), "owners", path, allow_empty=False)
    principal_ref = _string(raw, "principal_ref", path)
    if principal_ref not in owners:
        raise ContractError("L4-CONTRACT-001", "principal_ref must reference an owner", path)

    policy_refs = _string_tuple(raw.get("policy_refs", []), "policy_refs", path, allow_empty=True)
    root = _resolve_manifest_root(path, _string(raw, "root", path))

    return DomainManifest(
        api_version=api_version,
        kind=kind,
        id=_string(raw, "id", path),
        display_name=_string(raw, "display_name", path),
        archetype=_enum(raw, "archetype", DOMAIN_ARCHETYPES, path),
        space_ref=_string(raw, "space_ref", path),
        root=root,
        owners=owners,
        principal_ref=principal_ref,
        default_sensitivity=_enum(raw, "default_sensitivity", SENSITIVITY_LEVELS, path),
        default_visibility=_enum(raw, "default_visibility", VISIBILITY_LEVELS, path),
        sharing_policy=_enum(raw, "sharing_policy", SHARING_POLICIES, path),
        retention=_enum(raw, "retention", RETENTION_POLICIES, path),
        authority_policy=_enum(raw, "authority_policy", AUTHORITY_POLICIES, path),
        harness_profile_ref=_string(raw, "harness_profile_ref", path),
        lifecycle=_enum(raw, "lifecycle", LIFECYCLE_STATES, path),
        policy_refs=policy_refs,
    )


def load_harness_profile(path: Path) -> HarnessProfile:
    """Load a deterministic Phase 0 HarnessProfile."""

    raw = _load_mapping(path)
    _reject_unknown(raw, _PROFILE_FIELDS, path)
    if _string(raw, "apiVersion", path) != "l4/v1":
        raise ContractError("L4-CONTRACT-001", "unsupported HarnessProfile apiVersion", path)
    if _string(raw, "kind", path) != "HarnessProfile":
        raise ContractError("L4-CONTRACT-001", "unsupported HarnessProfile kind", path)

    required = _string_tuple(
        _require(raw, "required_gates", path),
        "required_gates",
        path,
        allow_empty=False,
    )
    advisory = _string_tuple(raw.get("advisory_gates", []), "advisory_gates", path, allow_empty=True)
    disabled = _string_tuple(raw.get("disabled_gates", []), "disabled_gates", path, allow_empty=True)
    selected = required + advisory + disabled
    unknown = sorted(set(selected) - set(PHASE0_GATES))
    if unknown:
        raise ContractError("L4-CONTRACT-001", f"unknown gates: {', '.join(unknown)}", path)
    if len(selected) != len(set(selected)):
        raise ContractError("L4-CONTRACT-001", "gate sets must not overlap", path)

    return HarnessProfile(
        id=_string(raw, "id", path),
        archetype=_enum(raw, "archetype", DOMAIN_ARCHETYPES, path),
        required_gates=required,
        advisory_gates=advisory,
        disabled_gates=disabled,
    )
