"""Deterministic Phase 0 harness tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from l4_kernel.contracts import DomainManifest
from l4_kernel.harness import HarnessRunner
from l4_kernel.harness_profiles import GATES, PROFILE_GATES

FIXTURES = Path(__file__).parent / "fixtures" / "harness"


def make_manifest(root: Path, *, archetype: str = "operational") -> DomainManifest:
    return DomainManifest(
        api_version="l4/v1",
        kind="DomainManifest",
        id="test-domain",
        display_name="Test Domain",
        archetype=archetype,
        space_ref="personal-space",
        root=root,
        owners=("personal-space-owner",),
        principal_ref="personal-space-owner",
        default_sensitivity="private",
        default_visibility="private",
        sharing_policy="deny",
        retention="permanent",
        authority_policy="canonical_write",
        harness_profile_ref=f"harness://{archetype}/v1",
        lifecycle="active",
        policy_refs=("policy://personal-space",),
    )


def test_profiles_select_deterministic_gates() -> None:
    assert GATES == ("T0", "T1", "T2", "T4", "T7", "T8")
    assert PROFILE_GATES["private-core"] == ("T0", "T1", "T2", "T4", "T7")
    assert PROFILE_GATES["library"] == ("T0", "T1", "T2", "T7")


def test_compile_assets_rejects_dangling_action() -> None:
    result = HarnessRunner().compile_assets(FIXTURES / "dangling-action")

    assert result.ok is False
    assert result.issues[0].code == "L4-COMPILE-004"
    assert result.issues[0].path == FIXTURES / "dangling-action" / "_control" / "workflows" / "dangling.yaml"


def test_compile_assets_rejects_duplicate_ids(tmp_path: Path) -> None:
    skills = tmp_path / "_control" / "skills"
    skills.mkdir(parents=True)
    (skills / "a.yaml").write_text("skill:\n  id: duplicate\n  steps: []\n", encoding="utf-8")
    (skills / "b.yaml").write_text("skill:\n  id: duplicate\n  steps: []\n", encoding="utf-8")

    result = HarnessRunner().compile_assets(tmp_path)

    assert any(issue.code == "L4-COMPILE-004" and "duplicate" in issue.message for issue in result.issues)


def test_compile_assets_rejects_dangling_skill_reference(tmp_path: Path) -> None:
    workflows = tmp_path / "_control" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "wf.yaml").write_text(
        "workflow:\n  id: example/workflow\n  skills:\n    - missing/skill\n",
        encoding="utf-8",
    )

    result = HarnessRunner().compile_assets(tmp_path)

    assert any("unresolved skill reference" in issue.message for issue in result.issues)


def test_compile_assets_preserves_repeated_top_level_declarations(tmp_path: Path) -> None:
    skills = tmp_path / "_control" / "skills"
    workflows = tmp_path / "_control" / "workflows"
    skills.mkdir(parents=True)
    workflows.mkdir(parents=True)
    (skills / "bundle.yaml").write_text(
        "skill:\n  id: first\n  steps: []\nskill:\n  id: second\n  steps: []\n",
        encoding="utf-8",
    )
    (workflows / "bundle.yaml").write_text(
        "workflow:\n  id: bundled\n  skills: [first, second]\n",
        encoding="utf-8",
    )

    assert HarnessRunner().compile_assets(tmp_path).ok is True


def test_compile_assets_ignores_comment_only_retired_index(tmp_path: Path) -> None:
    skills = tmp_path / "_control" / "skills"
    skills.mkdir(parents=True)
    (skills / "retired.yaml").write_text("# retired index\n# no active definitions\n", encoding="utf-8")

    assert HarnessRunner().compile_assets(tmp_path).ok is True


def test_compile_assets_supports_fenced_legacy_declaration(tmp_path: Path) -> None:
    skills = tmp_path / "_control" / "skills"
    skills.mkdir(parents=True)
    (skills / "legacy.yaml").write_text(
        "# Legacy catalog\n\n```yaml\nid: legacy/skill\nsteps:\n  - action: read_file\n```\n",
        encoding="utf-8",
    )

    assert HarnessRunner().compile_assets(tmp_path).ok is True


def test_library_profile_does_not_require_workflow_compilation(tmp_path: Path) -> None:
    workflows = tmp_path / "_control" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "broken.yaml").write_text("not: [valid", encoding="utf-8")
    manifest = make_manifest(tmp_path, archetype="library")

    health = HarnessRunner().run(manifest, PROFILE_GATES["library"])

    assert health.ok is True
    assert all(issue.gate != "T4" for issue in health.issues)


def test_private_core_requires_private_or_stronger_sensitivity(tmp_path: Path) -> None:
    manifest = replace(make_manifest(tmp_path, archetype="private-core"), default_sensitivity="internal")

    health = HarnessRunner().run(manifest, ("T7",))

    assert health.ok is False
    assert health.issues[0].code == "L4-POLICY-007"


def test_projection_and_federation_forbid_canonical_write(tmp_path: Path) -> None:
    manifest = replace(make_manifest(tmp_path, archetype="projection"), authority_policy="canonical_write")

    health = HarnessRunner().run(manifest, ("T7",))

    assert any("canonical_write" in issue.message for issue in health.issues)


def test_t7_rejects_missing_principal_or_space(tmp_path: Path) -> None:
    manifest = replace(make_manifest(tmp_path), principal_ref="", space_ref="")

    health = HarnessRunner().run(manifest, ("T7",))

    assert len([issue for issue in health.issues if issue.code == "L4-POLICY-007"]) == 2


def test_same_input_produces_same_issues(tmp_path: Path) -> None:
    manifest = replace(make_manifest(tmp_path, archetype="federation"), authority_policy="canonical_write")
    runner = HarnessRunner()

    first = runner.run(manifest, GATES)
    second = runner.run(manifest, GATES)

    assert first.issues == second.issues
    assert first.to_dict()["issues"] == second.to_dict()["issues"]


def test_t8_reports_content_plane_violation(tmp_path: Path) -> None:
    (tmp_path / "run.py").write_text("print('x')", encoding="utf-8")

    health = HarnessRunner().run(make_manifest(tmp_path), ("T8",))

    assert health.ok is False
    assert health.issues[0].code == "L4-CONTENT-008"
    assert health.issues[0].gate == "T8"


def test_t8_reports_projection_as_advisory(tmp_path: Path) -> None:
    (tmp_path / "STATE.md").write_text("# generated state", encoding="utf-8")

    health = HarnessRunner().run(make_manifest(tmp_path), ("T8",))

    assert health.ok is True
    assert health.issues[0].code == "L4-CONTENT-010"
    assert health.issues[0].severity == "warning"


def test_t8_rejects_invalid_content_archive(tmp_path: Path) -> None:
    archive = tmp_path / "_runtime" / "legacy"
    archive.mkdir(parents=True)
    (archive / "run.py").write_text("print('old')", encoding="utf-8")
    (archive / "CONTENT_ARCHIVE.yaml").write_text("schema: l4.content-archive/v1\n", encoding="utf-8")

    health = HarnessRunner().run(make_manifest(tmp_path), ("T8",))

    assert health.ok is False
    assert {issue.code for issue in health.issues} == {"L4-CONTENT-011"}


def test_t8_reports_missing_root_without_raising(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    health = HarnessRunner().run(make_manifest(missing), ("T0", "T8"))

    assert health.ok is False
    assert any(issue.code == "L4-ROOT-000" and issue.gate == "T8" for issue in health.issues)
