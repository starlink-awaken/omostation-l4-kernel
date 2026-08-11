"""CLI contract, registry, and harness surface tests."""

from __future__ import annotations

import contextlib
import errno
import io
import json
import os
import sys
from pathlib import Path

import pytest
import yaml

from l4_kernel import cli


def write_manifest(root: Path, *, domain_id: str = "sample", archetype: str = "library") -> Path:
    domain = root / domain_id
    domain.mkdir(parents=True)
    path = domain / "DOMAIN.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "l4/v1",
                "kind": "DomainManifest",
                "id": domain_id,
                "display_name": domain_id.title(),
                "archetype": archetype,
                "space_ref": "personal-space",
                "root": ".",
                "owners": ["personal-space-owner"],
                "principal_ref": "personal-space-owner",
                "default_sensitivity": "private",
                "default_visibility": "private",
                "sharing_policy": "deny",
                "retention": "permanent",
                "authority_policy": "reference_library" if archetype == "library" else "canonical_write",
                "harness_profile_ref": f"harness://{archetype}/v1",
                "lifecycle": "active",
                "policy_refs": ["policy://personal-space"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def write_registry(root: Path) -> Path:
    manifest = write_manifest(root)
    index = root / "registry.yaml"
    index.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "l4/v1",
                "kind": "DomainRegistry",
                "id": "test-registry",
                "display_name": "Test Registry",
                "space_ref": "personal-space",
                "status": "active",
                "path_base": "registry_file_parent",
                "manifests": [{"id": "sample", "path": str(manifest.relative_to(root))}],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return index


def invoke(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, dict]:
    monkeypatch.setattr(sys, "argv", ["l4-kernel", *args])
    code = cli.main()
    output = capsys.readouterr().out
    return code, json.loads(output)


def test_contract_validate_json_success(tmp_path: Path, monkeypatch, capsys) -> None:
    manifest = write_manifest(tmp_path)

    code, payload = invoke(monkeypatch, capsys, "contract", "validate", str(manifest), "--json")

    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["id"] == "sample"


def test_contract_validate_json_failure_has_stable_envelope(tmp_path: Path, monkeypatch, capsys) -> None:
    invalid = tmp_path / "DOMAIN.yaml"
    invalid.write_text("apiVersion: l4/v1\nkind: DomainManifest\n", encoding="utf-8")

    code, payload = invoke(monkeypatch, capsys, "contract", "validate", str(invalid), "--json")

    assert code == 1
    assert payload["ok"] is False
    assert payload["error"]["code"] == "L4-CONTRACT-001"
    assert payload["error"]["path"] == str(invalid)


def test_registry_list_uses_explicit_registry(tmp_path: Path, monkeypatch, capsys) -> None:
    index = write_registry(tmp_path)

    code, payload = invoke(monkeypatch, capsys, "registry", "list", "--registry", str(index), "--json")

    assert code == 0
    assert payload["ok"] is True
    assert [domain["id"] for domain in payload["data"]["domains"]] == ["sample"]


def test_registry_list_without_configuration_returns_exit_2(monkeypatch, capsys) -> None:
    monkeypatch.delenv("L4_DOMAIN_REGISTRY", raising=False)

    code, payload = invoke(monkeypatch, capsys, "registry", "list", "--json")

    assert code == 2
    assert payload["error"]["code"] == "L4-CONFIG-002"


def test_harness_run_json(tmp_path: Path, monkeypatch, capsys) -> None:
    index = write_registry(tmp_path)

    code, payload = invoke(
        monkeypatch,
        capsys,
        "harness",
        "run",
        "sample",
        "--registry",
        str(index),
        "--gates",
        "T0,T1,T2,T7",
        "--json",
    )

    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["domain_id"] == "sample"


def test_help_exposes_new_and_marks_old_surfaces_legacy(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["l4-kernel", "--help"])

    assert cli.main() == 0
    output = capsys.readouterr().out
    assert "contract validate" in output
    assert "registry list" in output
    assert "harness run" in output
    assert "content audit" in output
    assert "legacy" in output.lower()


def test_content_audit_json_fails_closed_on_runtime_artifact(tmp_path, monkeypatch, capsys) -> None:
    script = tmp_path / "_runtime" / "run.py"
    script.parent.mkdir()
    script.write_text("print('x')", encoding="utf-8")

    code, payload = invoke(monkeypatch, capsys, "content", "audit", str(tmp_path), "--json")

    assert code == 1
    assert payload["ok"] is False
    assert payload["data"]["counts"]["runtime"] == 1
    assert payload["data"]["violations"][0]["code"] == "L4-CONTENT-008"


def test_content_audit_json_accepts_contracts_and_content(tmp_path, monkeypatch, capsys) -> None:
    root = tmp_path / "domain"
    root.mkdir()
    (root / "CLAUDE.md").write_text("# Constitution", encoding="utf-8")
    (root / "note.md").write_text("# Knowledge", encoding="utf-8")

    code, payload = invoke(monkeypatch, capsys, "content", "audit", str(root), "--json")

    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["counts"] == {"content": 1, "contract": 1}


def test_content_audit_json_reports_invalid_archive_with_stable_code(tmp_path, monkeypatch, capsys) -> None:
    archive = tmp_path / "_runtime" / "legacy"
    archive.mkdir(parents=True)
    (archive / "run.py").write_text("print('old')", encoding="utf-8")
    (archive / "CONTENT_ARCHIVE.yaml").write_text("schema: l4.content-archive/v1\n", encoding="utf-8")

    code, payload = invoke(monkeypatch, capsys, "content", "audit", str(tmp_path), "--json")

    assert code == 1
    assert payload["ok"] is False
    assert {item["code"] for item in payload["data"]["violations"]} == {"L4-CONTENT-011"}


def test_content_audit_json_fails_closed_for_non_string_manifest_key(tmp_path, monkeypatch, capsys) -> None:
    archive = tmp_path / "_archive" / "legacy"
    archive.mkdir(parents=True)
    (archive / "run.py").write_text("print('old')", encoding="utf-8")
    (archive / "CONTENT_ARCHIVE.yaml").write_text("1: invalid\nschema: l4.content-archive/v1\n", encoding="utf-8")

    try:
        code, payload = invoke(monkeypatch, capsys, "content", "audit", str(tmp_path), "--json")
    except (OSError, TypeError) as error:
        pytest.fail(f"content audit must return a stable failure envelope, not raise: {error}")

    assert code == 1
    assert payload["ok"] is False
    assert {item["code"] for item in payload["data"]["violations"]} == {"L4-CONTENT-011"}


@pytest.mark.skipif(os.name != "posix", reason="surrogateescaped filenames require POSIX filesystem semantics")
def test_content_audit_json_serializes_surrogateescaped_path_as_valid_utf8(tmp_path) -> None:
    archive = tmp_path / "_archive"
    archive.mkdir()
    filename = os.fsdecode(b"legacy-\xff.py")
    source = archive / filename
    try:
        source.write_text("print('old')", encoding="utf-8")
    except OSError as error:
        unsupported = {errno.EILSEQ, errno.EINVAL, getattr(errno, "ENOTSUP", -1)}
        if error.errno not in unsupported:
            pytest.fail(f"unexpected error creating surrogateescaped filename: {error}")
        pytest.skip(f"filesystem rejects surrogateescaped POSIX names: {error}")
    (archive / "CONTENT_ARCHIVE.yaml").write_text("schema: l4.content-archive/v1\n", encoding="utf-8")
    output = io.BytesIO()
    stdout = io.TextIOWrapper(output, encoding="utf-8", errors="strict")

    with contextlib.redirect_stdout(stdout):
        code = cli.cmd_content(["audit", str(tmp_path), "--json"])
    stdout.flush()
    payload = json.loads(output.getvalue().decode("utf-8", errors="strict"))

    assert code == 1
    assert any(item["relative_path"] == f"_archive/{filename}" and item["code"] == "L4-CONTENT-011" for item in payload["data"]["violations"])


def test_content_audit_rejects_missing_root(tmp_path, monkeypatch, capsys) -> None:
    missing = tmp_path / "missing"

    code, payload = invoke(monkeypatch, capsys, "content", "audit", str(missing), "--json")

    assert code == 2
    assert payload["error"]["code"] == "L4-CONFIG-002"


@pytest.mark.parametrize("surface", [("skill", "run"), ("workflow", "run")])
def test_legacy_execution_surfaces_fail_closed(surface, monkeypatch, capsys) -> None:
    code, payload = invoke(monkeypatch, capsys, *surface, "vault", "asset")

    assert code == 1
    assert payload["error"]["code"] == "L4-EXECUTION-012"
    assert payload["error"]["authority"] == "omo"
