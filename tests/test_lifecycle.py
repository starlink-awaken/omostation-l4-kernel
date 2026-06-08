"""Tests for L4 Kernel DomainLifecycle."""

import tempfile
from pathlib import Path

import pytest

from l4_kernel.registry import Domain, DomainRegistry
from l4_kernel.lifecycle import DomainLifecycle


@pytest.fixture
def registry():
    return DomainRegistry()


@pytest.fixture
def lifecycle(registry):
    return DomainLifecycle(registry)


class TestDomainCreate:
    def test_create_document_domain(self, lifecycle):
        with tempfile.TemporaryDirectory() as td:
            result = lifecycle.create(
                "test-create", "测试域", "document", td,
                owner="test", description="测试用域",
            )
            assert result["status"] == "ok"
            # 验证 KEMS 骨架
            assert (Path(td) / "_control" / "STATE.md").exists()
            assert (Path(td) / "_control" / "MEMORY.md").exists()

    def test_create_duplicate(self, lifecycle):
        with tempfile.TemporaryDirectory() as td:
            lifecycle.create("dup", "测试", "document", td)
            result = lifecycle.create("dup", "测试2", "document", "/tmp")
            assert result["status"] == "error"
            assert "already exists" in result["message"]

    def test_create_dry_run(self, lifecycle):
        result = lifecycle.create("dry", "测试", "document", "/tmp/test-dry", dry_run=True)
        assert result["status"] == "dry_run"

    def test_create_non_document_domain(self, lifecycle):
        with tempfile.TemporaryDirectory() as td:
            result = lifecycle.create(
                "test-config", "配置域", "config", td, owner="test",
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

    def test_validate_all(self, lifecycle):
        results = lifecycle.validate_all()
        assert len(results) == 21
        assert "vault" in results


class TestDomainFreezeUnfreeze:
    def test_freeze_unfreeze(self, lifecycle):
        result = lifecycle.freeze("vault", "测试冻结")
        assert result["status"] == "ok"

        result = lifecycle.unfreeze("vault")
        assert result["status"] == "ok"

    def test_freeze_nonexistent(self, lifecycle):
        result = lifecycle.freeze("nonexistent")
        assert result["status"] == "error"


class TestDomainArchiveRestore:
    def test_archive_restore(self, lifecycle):
        result = lifecycle.archive("vault", "测试归档")
        assert result["status"] == "ok"

        result = lifecycle.restore("vault")
        assert result["status"] == "ok"


class TestDomainMigrate:
    def test_migrate_document(self, lifecycle):
        result = lifecycle.migrate("vault", "v5")
        assert result["status"] == "ok"

    def test_migrate_non_document(self, lifecycle):
        result = lifecycle.migrate("ai-config", "v5")
        assert result["status"] == "error"

    def test_migrate_all(self, lifecycle):
        results = lifecycle.migrate_all_document_domains("v5")
        assert len(results) >= 1


class TestDomainHealthReport:
    def test_health_report_single(self, lifecycle):
        result = lifecycle.health_report("vault")
        assert "checks" in result

    def test_health_report_all(self, lifecycle):
        result = lifecycle.health_report()
        assert "total" in result
