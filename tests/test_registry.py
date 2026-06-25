"""Tests for L4 Kernel DomainRegistry."""

from pathlib import Path

from l4_kernel import Domain, DomainRegistry


class TestDomain:
    def test_create_document_domain(self):
        d = Domain(
            id="vault",
            name="@学习进化",
            domain_type="document",
            path=Path.home() / "Documents" / "@学习进化",
            bos_uri="bos://vault/**",
            kems_planes=["_control", "_entities", "_knowledge", "_storage", "_archive"],
        )
        assert d.id == "vault"
        assert d.domain_type == "document"
        assert len(d.kems_planes) == 5

    def test_to_dict(self):
        d = Domain(id="test", name="Test", domain_type="config", path=Path("/tmp"), bos_uri="bos://test/**")
        dct = d.to_dict()
        assert dct["id"] == "test"
        assert dct["type"] == "config"
        assert "exists" in dct

    def test_exists_true_for_home(self):
        d = Domain(id="home", name="Home", domain_type="config", path=Path.home(), bos_uri="bos://home/**")
        assert d.exists() is True

    def test_exists_false_for_missing(self):
        d = Domain(
            id="missing", name="Missing", domain_type="config", path=Path("/nonexistent"), bos_uri="bos://missing/**"
        )
        assert d.exists() is False


class TestDomainRegistry:
    def test_list_all_returns_builtin_count(self):
        """动态计算断言值，避免每次增减域都需要改测试。"""
        reg = DomainRegistry()
        all_d = reg.list_all()
        expected_ids = {
            "cockpit",
            "vault",
            "creative",
            "personal",
            "shared",
            "family",
            "work-weijian",
            "work-guozhuan",
            "work-docs",
            "opc",
            "family-shared",
            "obsidian-vault",
            "ai-config",
            "agents-config",
            "icloud-sharedconf",
            "bin",
            "toolbox-tools",
            "sharedwork",
            "shareddisk",
            "model-volume",
            "sharedmodel",
            "minerva",
            "knowledge-engine",
            "l4-kernel",
            "ecos-workbench",
            "omo-governance",
            "spaces",
            "runtime",
        }
        assert len(all_d) == len(expected_ids), (
            f"Expected {len(expected_ids)} domains, got {len(all_d)}: {[d.id for d in all_d]}"
        )

    def test_list_by_type_all_ids_known(self):
        reg = DomainRegistry()
        all_d = reg.list_all()
        known = {d.id for d in all_d}
        # Spot-check: verify all key domains are present
        assert "vault" in known
        assert "cockpit" in known
        assert "opc" in known
        assert "family-shared" in known

    def test_list_by_type_document(self):
        reg = DomainRegistry()
        docs = reg.list_by_type("document")
        assert len(docs) == 12  # 9 original + obsidian-vault + opc + family-shared + work-docs

    def test_list_by_type_config(self):
        reg = DomainRegistry()
        configs = reg.list_by_type("config")
        assert len(configs) == 3

    def test_list_by_type_engine(self):
        reg = DomainRegistry()
        engines = reg.list_by_type("engine")
        assert len(engines) == 3  # minerva + knowledge-engine + l4-kernel

    def test_list_by_type_workspace(self):
        reg = DomainRegistry()
        workspaces = reg.list_by_type("workspace")
        assert len(workspaces) == 5  # sharedwork + ecos-workbench + runtime + omo-governance + spaces

    def test_get_vault(self):
        reg = DomainRegistry()
        d = reg.get("vault")
        assert d is not None
        assert d.name == "@学习进化"
        assert d.domain_type == "document"

    def test_get_nonexistent(self):
        reg = DomainRegistry()
        assert reg.get("nonexistent") is None

    def test_resolve_path(self):
        reg = DomainRegistry()
        path = reg.resolve_path("vault")
        assert path is not None
        assert path.name == "@学习进化"

    def test_resolve_bos_uri(self):
        reg = DomainRegistry()
        uri = reg.resolve_bos_uri("vault")
        assert uri == "bos://vault/**"

    def test_register_new_domain(self):
        reg = DomainRegistry()
        d = Domain(id="test-new", name="Test", domain_type="config", path=Path("/tmp/test"), bos_uri="bos://test/**")
        reg.register(d)
        assert reg.get("test-new") is not None

    def test_unregister(self):
        reg = DomainRegistry()
        reg.register(Domain(id="tmp", name="Tmp", domain_type="config", path=Path("/tmp"), bos_uri="bos://tmp/**"))
        assert reg.unregister("tmp") is True
        assert reg.get("tmp") is None

    def test_unregister_nonexistent(self):
        reg = DomainRegistry()
        assert reg.unregister("nonexistent") is False

    def test_health_check(self):
        reg = DomainRegistry()
        h = reg.health_check("vault")
        assert h["id"] == "vault"
        assert "status" in h

    def test_health_check_not_registered(self):
        reg = DomainRegistry()
        h = reg.health_check("nonexistent")
        assert h["status"] == "not_registered"

    def test_aggregate_health(self):
        reg = DomainRegistry()
        h = reg.aggregate_health()
        assert h["total"] == len(reg.list_all())
        assert "document" in h["by_type"]

    def test_to_dict(self):
        reg = DomainRegistry()
        d = reg.to_dict()
        assert len(d["domains"]) == len(reg.list_all())
        assert "health" in d

    def test_list_document_domains(self):
        reg = DomainRegistry()
        docs = reg.list_document_domains()
        assert len(docs) == 12  # 9 original + obsidian-vault + opc + family-shared + work-docs
        assert all(d.domain_type == "document" for d in docs)

    def test_work_weijian_path(self):
        """验证 #卫健委 路径 bug 已修复。"""
        reg = DomainRegistry()
        d = reg.get("work-weijian")
        assert d is not None
        assert "工作文档" in str(d.path)
