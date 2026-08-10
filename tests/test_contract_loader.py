"""L4 Phase 0 contract loading tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from l4_kernel.contracts import (
    ContractError,
    DomainHealth,
    HarnessProfile,
    ValidationIssue,
    ValidationResult,
    load_domain_manifest,
    load_harness_profile,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _write_manifest(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "DOMAIN.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def _valid_manifest_text(**overrides: object) -> str:
    values: dict[str, object] = {
        "apiVersion": "l4/v1",
        "kind": "DomainManifest",
        "id": "vault",
        "display_name": "Vault",
        "archetype": "private-core",
        "space_ref": "personal-space",
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
        "policy_refs": ["policy://l4/phase0"],
    }
    values.update(overrides)
    lines: list[str] = []
    for key, value in values.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {item}" for item in value)
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


def test_load_domain_manifest_returns_immutable_model() -> None:
    manifest = load_domain_manifest(FIXTURES / "domain-manifest-valid.yaml")

    assert manifest.id == "vault"
    assert manifest.root == FIXTURES.resolve()
    assert manifest.owners == ("personal-space-owner",)
    assert manifest.policy_refs == ("policy://l4/phase0",)
    with pytest.raises(FrozenInstanceError):
        manifest.id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "field",
    [
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
    ],
)
def test_load_domain_manifest_rejects_missing_required_field(tmp_path: Path, field: str) -> None:
    text = _valid_manifest_text()
    lines = text.splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith(f"{field}:"))
    end = start + 1
    while end < len(lines) and lines[end].startswith("  - "):
        end += 1
    path = _write_manifest(tmp_path, "\n".join(lines[:start] + lines[end:]) + "\n")

    with pytest.raises(ContractError) as exc:
        load_domain_manifest(path)

    assert exc.value.code == "L4-CONTRACT-001"
    assert field in exc.value.message
    assert exc.value.path == path


@pytest.mark.parametrize("body", ["", "- not\n- a\n- mapping\n"])
def test_load_domain_manifest_rejects_non_mapping_yaml(tmp_path: Path, body: str) -> None:
    path = _write_manifest(tmp_path, body)

    with pytest.raises(ContractError, match="mapping") as exc:
        load_domain_manifest(path)

    assert exc.value.code == "L4-CONTRACT-001"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("apiVersion", "l4/v2", "apiVersion"),
        ("kind", "SomethingElse", "kind"),
        ("archetype", "mystery", "archetype"),
        ("default_sensitivity", "secret-ish", "default_sensitivity"),
        ("default_visibility", "world", "default_visibility"),
        ("sharing_policy", "anyone", "sharing_policy"),
        ("retention", "forever-ish", "retention"),
        ("authority_policy", "superuser", "authority_policy"),
        ("lifecycle", "unknown", "lifecycle"),
    ],
)
def test_load_domain_manifest_rejects_unknown_enum(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    path = _write_manifest(tmp_path, _valid_manifest_text(**{field: value}))

    with pytest.raises(ContractError, match=message) as exc:
        load_domain_manifest(path)

    assert exc.value.code == "L4-CONTRACT-001"


@pytest.mark.parametrize("root", ["../outside", "../../outside", "/tmp/outside"])
def test_load_domain_manifest_rejects_root_escape(tmp_path: Path, root: str) -> None:
    path = _write_manifest(tmp_path, _valid_manifest_text(root=root))

    with pytest.raises(ContractError, match="root") as exc:
        load_domain_manifest(path)

    assert exc.value.code == "L4-CONTRACT-001"


def test_load_domain_manifest_rejects_duplicate_owner(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        _valid_manifest_text(owners=["personal-space-owner", "personal-space-owner"]),
    )

    with pytest.raises(ContractError, match="owners"):
        load_domain_manifest(path)


def test_load_domain_manifest_requires_principal_to_be_owner(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _valid_manifest_text(principal_ref="unknown-owner"))

    with pytest.raises(ContractError, match="principal_ref"):
        load_domain_manifest(path)


def test_load_domain_manifest_rejects_unknown_fields(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _valid_manifest_text(surprise="value"))

    with pytest.raises(ContractError, match="unknown fields"):
        load_domain_manifest(path)


def test_load_harness_profile_partitions_known_gates(tmp_path: Path) -> None:
    path = tmp_path / "profile.yaml"
    path.write_text(
        "\n".join(
            [
                "apiVersion: l4/v1",
                "kind: HarnessProfile",
                "id: harness://private-core/v1",
                "archetype: private-core",
                "required_gates: [T0, T1, T2, T4, T7]",
                "advisory_gates: []",
                "disabled_gates: []",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    profile = load_harness_profile(path)

    assert isinstance(profile, HarnessProfile)
    assert profile.required_gates == ("T0", "T1", "T2", "T4", "T7")


@pytest.mark.parametrize(
    "line",
    [
        "required_gates: [T0, T9]",
        "advisory_gates: [T0]",
    ],
)
def test_load_harness_profile_rejects_unknown_or_duplicate_gate(tmp_path: Path, line: str) -> None:
    path = tmp_path / "profile.yaml"
    path.write_text(
        "\n".join(
            [
                "apiVersion: l4/v1",
                "kind: HarnessProfile",
                "id: harness://private-core/v1",
                "archetype: private-core",
                "required_gates: [T0, T1]",
                line,
                "disabled_gates: []",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ContractError):
        load_harness_profile(path)


def test_validation_result_and_domain_health_fail_only_on_errors() -> None:
    warning = ValidationIssue(code="L4-WARN-001", severity="warning", message="warning")
    error = ValidationIssue(code="L4-CONTRACT-001", severity="error", message="broken")

    assert ValidationResult(issues=(warning,)).ok is True
    assert ValidationResult(issues=(warning, error)).ok is False
    assert DomainHealth(
        domain_id="vault",
        profile_id="harness://private-core/v1",
        checked_at="2026-08-10T00:00:00Z",
        issues=(warning,),
    ).ok is True
    assert DomainHealth(
        domain_id="vault",
        profile_id="harness://private-core/v1",
        checked_at="2026-08-10T00:00:00Z",
        issues=(error,),
    ).ok is False
