"""Immutable runtime models for the L4 Phase 0 contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DomainManifest:
    """A validated knowledge-domain manifest."""

    api_version: str
    kind: str
    id: str
    display_name: str
    archetype: str
    space_ref: str
    root: Path
    owners: tuple[str, ...]
    principal_ref: str
    default_sensitivity: str
    default_visibility: str
    sharing_policy: str
    retention: str
    authority_policy: str
    harness_profile_ref: str
    lifecycle: str
    policy_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HarnessProfile:
    """Deterministic gate selection for one domain archetype."""

    id: str
    archetype: str
    required_gates: tuple[str, ...]
    advisory_gates: tuple[str, ...] = ()
    disabled_gates: tuple[str, ...] = ()
