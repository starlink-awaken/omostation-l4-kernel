"""Tests for L4 Kernel DomainLifecycle."""

import tempfile
from pathlib import Path

import pytest
import yaml

import l4_kernel.templates as templates
from l4_kernel.content_plane import audit_content_plane
from l4_kernel.lifecycle import DomainLifecycle
from l4_kernel.registry import Domain, DomainRegistry


def write_domain_manifest(root: Path, domain_id: str, owner: str, display_name: str | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "DOMAIN.yaml").write_text(
        yaml.safe_dump(
            {
                "apiVersion": "l4/v1",
                "kind": "DomainManifest",
                "id": domain_id,
                "display_name": display_name or domain_id,
                "archetype": "library",
                "space_ref": "personal-space",
                "root": ".",
                "owners": [owner],
                "principal_ref": owner,
                "default_sensitivity": "private",
                "default_visibility": "private",
                "sharing_policy": "deny",
                "retention": "permanent",
                "authority_policy": "reference_library",
                "harness_profile_ref": "harness://library/v1",
                "lifecycle": "active",
                "policy_refs": ["policy://personal-space"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


@pytest.fixture
def registry(tmp_path):
    """P52-final: 用 tmp_path 构造 path_overrides。"""
    from l4_kernel.testing import default_overrides

    return DomainRegistry(path_overrides=default_overrides(tmp_path))


@pytest.fixture
def lifecycle(registry):
    return DomainLifecycle(registry)


class TestDomainCreate:
    def test_create_document_domain(self, lifecycle):
        with tempfile.TemporaryDirectory() as td:
            result = lifecycle.create(
                "test-create",
                "测试域",
                "document",
                td,
                owner="test",
                description="测试用域",
            )
            assert result["status"] == "ok"
            root = Path(td)
            assert (root / "DOMAIN.yaml").exists()
            assert not (root / "_control" / "signals.md").exists()
            assert audit_content_plane(root).counts.get("runtime", 0) == 0
            assert lifecycle.validate("test-create")["status"] == "ok"

    def test_create_duplicate(self, lifecycle):
        with tempfile.TemporaryDirectory() as td:
            lifecycle.create("dup", "测试", "document", td)
            result = lifecycle.create("dup", "测试2", "document", "/tmp")
            assert result["status"] == "error"
            assert "already exists" in result["message"]

    def test_create_rejects_conflicting_existing_manifest_display_name(self, lifecycle, tmp_path):
        root = tmp_path / "domain"
        write_domain_manifest(root, "test-create", "trusted-owner", display_name="旧名称")

        result = lifecycle.create("test-create", "新名称", "document", root, owner="trusted-owner")

        assert result["status"] == "error"
        assert sorted(path.name for path in root.iterdir()) == ["DOMAIN.yaml"]

    def test_create_exposes_non_destructive_publication_evidence(self, lifecycle, tmp_path, monkeypatch):
        root = tmp_path / "domain"
        original_write = templates._write_contract

        def fail_method(path, content, journal):
            if path.name == "Method.md":
                raise PermissionError("stop publication")
            return original_write(path, content, journal)

        monkeypatch.setattr(templates, "_write_contract", fail_method)

        result = lifecycle.create("publication-id", "声明式域", "document", root, owner="trusted-owner")

        assert result["status"] == "error"
        assert "publication failed" in result["message"]
        assert result["residual_paths"] == [str(root / "DOMAIN.yaml")]
        assert result["uncertain_paths"] == [str(root)]
        assert result["recovery"]["code"] == "L4-PUBLICATION-RECOVERY-001"

    def test_create_exposes_directory_entry_durability_evidence(self, lifecycle, tmp_path, monkeypatch):
        root = tmp_path / "domain"
        original_fsync = templates._fsync_fd

        def fail_directory_fsync(fd, operation):
            if operation == "fsync directory creation":
                raise OSError("directory durability unknown")
            return original_fsync(fd, operation)

        monkeypatch.setattr(templates, "_fsync_fd", fail_directory_fsync)

        result = lifecycle.create("publication-id", "声明式域", "document", root, owner="trusted-owner")

        assert result["status"] == "error"
        assert result["durability_uncertain_paths"] == []
        assert result["directory_entry_durability_uncertain_paths"] == [str(root)]

    def test_create_dry_run(self, lifecycle):
        result = lifecycle.create("dry", "测试", "document", "/tmp/test-dry", dry_run=True)
        assert result["status"] == "dry_run"

    def test_create_non_document_domain(self, lifecycle):
        with tempfile.TemporaryDirectory() as td:
            result = lifecycle.create(
                "test-config",
                "配置域",
                "config",
                td,
                owner="test",
            )
            assert result["status"] == "ok"
            # config 域不应该创建 KEMS _control/
            # 但路径本身存在，所以 exists 为 True
            assert Path(td).exists()


class TestDomainValidate:
    def test_validate_existing(self, lifecycle):
        result = lifecycle.validate("vault")
        assert result["domain_id"] == "vault"
        assert "checks" in result

    def test_validate_nonexistent(self, lifecycle):
        result = lifecycle.validate("nonexistent")
        assert result["status"] == "error"

    def test_validate_rejects_manifest_display_name_drift(self, lifecycle, tmp_path):
        root = tmp_path / "domain"
        write_domain_manifest(root, "display-id", "trusted-owner", display_name="manifest 名称")
        lifecycle.registry.register(
            Domain("display-id", "registry 名称", "document", root, "bos://display-id/**")
        )

        result = lifecycle.validate("display-id")

        assert result["status"] == "error"
        assert "display" in result["checks"]["domain_manifest"].lower()

    def test_validate_all(self, lifecycle):
        results = lifecycle.validate_all()
        assert len(results) == 28
        assert "vault" in results


class TestDomainFreezeUnfreeze:
    def test_freeze_unfreeze(self, lifecycle):
        result = lifecycle.freeze("vault", "测试冻结")
        assert result["status"] == "deprecated"
        assert result["deprecation"]["replacement"] == "OMO/Runtime authority"

        result = lifecycle.unfreeze("vault")
        assert result["status"] == "deprecated"
        assert result["deprecation"]["replacement"] == "OMO/Runtime authority"

    def test_freeze_nonexistent(self, lifecycle):
        result = lifecycle.freeze("nonexistent")
        assert result["status"] == "error"

    def test_document_operations_are_non_mutating_deprecations(self, lifecycle, tmp_path):
        root = tmp_path / "declarative-domain"
        assert lifecycle.create("declarative-id", "声明式域", "document", root, owner="trusted-owner")["status"] == "ok"
        before = sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))

        for operation in (lifecycle.freeze, lifecycle.unfreeze, lifecycle.archive, lifecycle.restore):
            result = operation("declarative-id")
            assert result["status"] == "deprecated"
            assert result["deprecation"]["replacement"] == "OMO/Runtime authority"

        after = sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))
        assert after == before


class TestDomainArchiveRestore:
    def test_archive_restore(self, lifecycle):
        result = lifecycle.archive("vault", "测试归档")
        assert result["status"] == "deprecated"
        assert result["deprecation"]["replacement"] == "OMO/Runtime authority"

        result = lifecycle.restore("vault")
        assert result["status"] == "deprecated"
        assert result["deprecation"]["replacement"] == "OMO/Runtime authority"


class TestDomainMigrate:
    def test_migrate_document(self, lifecycle):
        domain = lifecycle.registry.get("vault")
        assert domain is not None
        write_domain_manifest(domain.path, "vault", "trusted-owner", display_name=domain.name)
        result = lifecycle.migrate("vault", "v5")
        assert result["status"] == "ok"
        assert result["deprecation"]["replacement"] == "l4-kernel domain init-content-contracts"
        assert "trusted-owner" in (domain.path / "profiles" / "Profile.md").read_text(encoding="utf-8")
        report = audit_content_plane(domain.path)
        assert report.counts.get("runtime", 0) == 0
        assert report.counts.get("cache", 0) == 0

    def test_migrate_non_document(self, lifecycle):
        result = lifecycle.migrate("ai-config", "v5")
        assert result["status"] == "error"

    def test_migrate_all(self, lifecycle):
        results = lifecycle.migrate_all_document_domains("v5")
        assert len(results) >= 1

    def test_migrate_uses_manifest_identity_and_authoritative_owner(self, lifecycle, tmp_path):
        root = tmp_path / "path-basename-must-not-win"
        write_domain_manifest(root, "registry-id", "trusted-owner", display_name="注册表域")
        lifecycle.registry.register(
            Domain(
                id="registry-id",
                name="注册表域",
                domain_type="document",
                path=root,
                bos_uri="bos://registry-id/**",
            )
        )

        result = lifecycle.migrate("registry-id")

        assert result["status"] == "ok"
        assert "trusted-owner" in (root / "profiles" / "Profile.md").read_text(encoding="utf-8")
        assert "registry-id" in (root / "DOMAIN.yaml").read_text(encoding="utf-8")

    def test_migrate_rejects_manifest_display_name_drift(self, lifecycle, tmp_path):
        root = tmp_path / "domain"
        write_domain_manifest(root, "display-id", "trusted-owner", display_name="manifest 名称")
        lifecycle.registry.register(Domain("display-id", "registry 名称", "document", root, "bos://display-id/**"))

        result = lifecycle.migrate("display-id")

        assert result["status"] == "error"
        assert result["changes"] == []

    def test_migrate_without_trusted_owner_fails_closed(self, lifecycle):
        result = lifecycle.migrate("vault")

        assert result["status"] == "error"
        assert result["deprecation"]["replacement"] == "l4-kernel domain init-content-contracts"

    def test_migrate_returns_stable_error_when_contract_preflight_rejects_path(self, lifecycle, tmp_path):
        root = tmp_path / "unsafe-domain"
        external = tmp_path / "external"
        write_domain_manifest(root, "unsafe-id", "trusted-owner")
        external.mkdir()
        (root / "profiles").symlink_to(external, target_is_directory=True)
        lifecycle.registry.register(
            Domain(
                id="unsafe-id",
                name="不安全域",
                domain_type="document",
                path=root,
                bos_uri="bos://unsafe-id/**",
            )
        )

        result = lifecycle.migrate("unsafe-id")

        assert result["status"] == "error"
        assert result["changes"] == []
        assert list(external.iterdir()) == []

    def test_migrate_write_error_reports_no_changes_without_published_file(self, lifecycle, tmp_path, monkeypatch):
        root = tmp_path / "domain"
        write_domain_manifest(root, "publication-id", "trusted-owner")
        lifecycle.registry.register(Domain("publication-id", "publication-id", "document", root, "bos://publication-id/**"))
        original_write = templates._write_contract

        def fail_method(path, content, created):
            if path.name == "Method.md":
                raise PermissionError("denied writing Method")
            return original_write(path, content, created)

        monkeypatch.setattr(templates, "_write_contract", fail_method)

        result = lifecycle.migrate("publication-id")

        assert result["status"] == "error"
        assert result["changes"] == []
        assert sorted(path.name for path in root.iterdir()) == ["DOMAIN.yaml"]

    def test_migrate_exposes_directory_entry_durability_evidence(self, lifecycle, tmp_path, monkeypatch):
        root = tmp_path / "domain"
        write_domain_manifest(root, "publication-id", "trusted-owner")
        lifecycle.registry.register(Domain("publication-id", "publication-id", "document", root, "bos://publication-id/**"))
        original_fsync = templates._fsync_fd

        def fail_directory_fsync(fd, operation):
            if operation == "fsync directory creation":
                raise OSError("directory durability unknown")
            return original_fsync(fd, operation)

        monkeypatch.setattr(templates, "_fsync_fd", fail_directory_fsync)

        result = lifecycle.migrate("publication-id")

        assert result["status"] == "error"
        assert result["durability_uncertain_paths"] == []
        assert result["directory_entry_durability_uncertain_paths"] == [str(root / "profiles")]


class TestDomainHealthReport:
    def test_health_report_single(self, lifecycle):
        result = lifecycle.health_report("vault")
        assert "checks" in result

    def test_health_report_all(self, lifecycle):
        result = lifecycle.health_report()
        assert "total" in result
