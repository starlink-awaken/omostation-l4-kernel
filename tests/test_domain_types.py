"""Tests for L4 Kernel domain_types — 7 种域类型特化。"""

import tempfile
from pathlib import Path

import pytest

from l4_kernel.domain_types import (
    ConfigDomain,
    DocumentDomain,
    EngineDomain,
    ModelDomain,
    StorageDomain,
    ToolDomain,
    WorkspaceDomain,
    clear_wrap_cache,
    wrap_domain,
)
from l4_kernel.registry import Domain


@pytest.fixture
def temp_doc_domain():
    """临时 DocumentDomain。"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for plane in ["_control", "_entities", "_knowledge", "_storage", "_archive"]:
            (root / plane).mkdir(parents=True)
        (root / "_control" / "STATE.md").write_text("---\nstatus: active\n---\n")
        (root / "_control" / "MEMORY.md").write_text("---\npointers: []\n---\n")
        (root / "_control" / "CLAUDE.md").write_text("# Entry\n")
        (root / "_control" / "决策日志").mkdir()
        # Add some storage files
        (root / "_storage" / "doc1.md").write_text("# Doc 1\nContent\n" * 10)
        yield root


@pytest.fixture
def temp_config_domain():
    """临时 ConfigDomain。"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "config.yaml").write_text("key: value\nnested:\n  sub: 1\n")
        (root / "settings.json").write_text('{"port": 8080, "debug": true}')
        yield root


@pytest.fixture
def temp_tool_domain():
    """临时 ToolDomain。"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        script = root / "hello.sh"
        script.write_text("#!/bin/bash\necho hello\n")
        script.chmod(0o755)
        (root / "README.md").write_text("# Tools\n")
        yield root


def make_domain(domain_type: str, path: Path, **kwargs) -> Domain:
    return Domain(
        id=f"test-{domain_type}",
        name=f"Test {domain_type}",
        domain_type=domain_type,
        path=path,
        bos_uri=f"bos://test-{domain_type}/**",
        kems_planes=kwargs.get("kems_planes", []),
    )


# ── DocumentDomain ──────────────────────────────────────────────────


class TestDocumentDomain:
    def test_validate_kems_planes_all_present(self, temp_doc_domain):
        d = wrap_domain(
            make_domain(
                "document", temp_doc_domain, kems_planes=["_control", "_entities", "_knowledge", "_storage", "_archive"]
            )
        )
        assert isinstance(d, DocumentDomain)
        missing = d.validate_kems_planes()
        assert len(missing) == 0

    def test_validate_kems_planes_missing(self, temp_doc_domain):
        d = wrap_domain(make_domain("document", temp_doc_domain, kems_planes=["_control", "_runtime"]))
        missing = d.validate_kems_planes()
        assert "_runtime" in missing[0]

    def test_get_control_files(self, temp_doc_domain):
        d = wrap_domain(make_domain("document", temp_doc_domain))
        files = d.get_control_files()
        assert files["STATE.md"] is True
        assert files["MEMORY.md"] is True
        assert files["CLAUDE.md"] is True
        assert files["决策日志/"] is True

    def test_get_storage_stats(self, temp_doc_domain):
        d = wrap_domain(make_domain("document", temp_doc_domain))
        stats = d.get_storage_stats()
        assert stats["files"] >= 1
        assert stats["total_size_mb"] >= 0


# ── ConfigDomain ────────────────────────────────────────────────────


class TestConfigDomain:
    def test_list_configs(self, temp_config_domain):
        d = wrap_domain(make_domain("config", temp_config_domain))
        assert isinstance(d, ConfigDomain)
        configs = d.list_configs()
        assert len(configs) == 2

    def test_read_yaml_config(self, temp_config_domain):
        d = wrap_domain(make_domain("config", temp_config_domain))
        data = d.read_config("config.yaml")
        assert data is not None
        assert data["key"] == "value"

    def test_read_json_config(self, temp_config_domain):
        d = wrap_domain(make_domain("config", temp_config_domain))
        data = d.read_config("settings.json")
        assert data is not None
        assert data["port"] == 8080

    def test_read_missing_config(self, temp_config_domain):
        d = wrap_domain(make_domain("config", temp_config_domain))
        assert d.read_config("nonexistent.yaml") is None

    def test_validate_schema_valid(self, temp_config_domain):
        d = wrap_domain(make_domain("config", temp_config_domain))
        result = d.validate_schema("config.yaml")
        assert result["valid"] is True
        assert "key" in result["keys"]

    def test_validate_schema_missing(self, temp_config_domain):
        d = wrap_domain(make_domain("config", temp_config_domain))
        result = d.validate_schema("nonexistent.yaml")
        assert result["valid"] is False


# ── ToolDomain ──────────────────────────────────────────────────────


class TestToolDomain:
    def test_list_tools(self, temp_tool_domain):
        d = wrap_domain(make_domain("tool", temp_tool_domain))
        assert isinstance(d, ToolDomain)
        tools = d.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "hello.sh"

    def test_check_tool_exists(self, temp_tool_domain):
        d = wrap_domain(make_domain("tool", temp_tool_domain))
        result = d.check_tool("hello.sh")
        assert result["status"] == "ok"
        assert result["executable"] is True

    def test_check_tool_not_found(self, temp_tool_domain):
        d = wrap_domain(make_domain("tool", temp_tool_domain))
        result = d.check_tool("nonexistent.sh")
        assert result["status"] == "not_found"


# ── WorkspaceDomain ─────────────────────────────────────────────────


class TestWorkspaceDomain:
    def test_index_files(self, temp_config_domain):
        d = wrap_domain(make_domain("workspace", temp_config_domain))
        assert isinstance(d, WorkspaceDomain)
        files = d.index_files(max_depth=1)
        assert len(files) == 2  # config.yaml + settings.json

    def test_search_files(self, temp_config_domain):
        d = wrap_domain(make_domain("workspace", temp_config_domain))
        results = d.search_files("config")
        assert len(results) == 1
        assert "config.yaml" in results[0]

    def test_search_no_match(self, temp_config_domain):
        d = wrap_domain(make_domain("workspace", temp_config_domain))
        assert d.search_files("nonexistent_xyz") == []


# ── StorageDomain ───────────────────────────────────────────────────


class TestStorageDomain:
    def test_get_disk_usage_root(self, registry):
        d = wrap_domain(make_domain("storage", Path("/")))
        assert isinstance(d, StorageDomain)
        usage = d.get_disk_usage()
        assert "status" in usage
        # root is always mounted
        if usage["status"] == "mounted":
            assert "use_percent" in usage

    def test_check_mount_status(self, registry):
        d = wrap_domain(make_domain("storage", Path("/")))
        status = d.check_mount_status()
        assert status["mounted"] is True

    def test_check_mount_status_missing(self, registry):
        d = wrap_domain(make_domain("storage", Path("/nonexistent_volume_xyz")))
        status = d.check_mount_status()
        assert status["mounted"] is False


# ── ModelDomain ─────────────────────────────────────────────────────


class TestModelDomain:
    def test_list_models(self, temp_config_domain):
        d = wrap_domain(make_domain("model", temp_config_domain))
        assert isinstance(d, ModelDomain)
        models = d.list_models()
        assert len(models) == 2

    def test_get_model_checksum(self, temp_config_domain):
        d = wrap_domain(make_domain("model", temp_config_domain))
        checksum = d.get_model_checksum("config.yaml")
        assert checksum is not None
        assert len(checksum) == 64  # SHA256

    def test_get_model_checksum_missing(self, temp_config_domain):
        d = wrap_domain(make_domain("model", temp_config_domain))
        assert d.get_model_checksum("nonexistent.bin") is None


# ── EngineDomain ────────────────────────────────────────────────────


class TestEngineDomain:
    def test_check_process(self, registry):
        d = wrap_domain(make_domain("engine", Path.home()))
        assert isinstance(d, EngineDomain)
        result = d.check_process("launchd")
        assert result["running"] is True

    def test_check_process_nonexistent(self, registry):
        d = wrap_domain(make_domain("engine", Path.home()))
        result = d.check_process("nonexistent_process_xyz_12345")
        assert result["running"] is False

    def test_get_config_missing(self, temp_config_domain):
        # temp_config_domain already has config.yaml — use a different empty dir
        with tempfile.TemporaryDirectory() as td:
            d = wrap_domain(make_domain("engine", Path(td)))
            assert d.get_config() is None

    def test_get_config(self, temp_config_domain):
        # Create a config.yaml
        (temp_config_domain / "config.yaml").write_text("port: 8765\n")
        d = wrap_domain(make_domain("engine", temp_config_domain))
        config = d.get_config()
        assert config is not None
        assert config["port"] == 8765

    def test_get_logs_empty(self, temp_config_domain):
        d = wrap_domain(make_domain("engine", temp_config_domain))
        assert d.get_logs() == []


# ── wrap_domain ─────────────────────────────────────────────────────


class TestWrapDomain:
    def test_wrap_document(self, registry):
        clear_wrap_cache()
        d = Domain(id="v", name="V", domain_type="document", path=Path("/tmp"), bos_uri="bos://v/**")
        wrapped = wrap_domain(d)
        assert isinstance(wrapped, DocumentDomain)
        assert wrapped.id == "v"
        # 再次调用应返回缓存实例
        wrapped2 = wrap_domain(d)
        assert wrapped is wrapped2

    def test_wrap_config(self, registry):
        d = Domain(id="c", name="C", domain_type="config", path=Path("/tmp"), bos_uri="bos://c/**")
        wrapped = wrap_domain(d)
        assert isinstance(wrapped, ConfigDomain)

    def test_wrap_tool(self, registry):
        d = Domain(id="t", name="T", domain_type="tool", path=Path("/tmp"), bos_uri="bos://t/**")
        wrapped = wrap_domain(d)
        assert isinstance(wrapped, ToolDomain)

    def test_wrap_all_types_from_registry(self, registry):
        clear_wrap_cache()
        reg = registry
        for domain in reg.list_all():
            wrapped = wrap_domain(domain)
            type_to_class = {
                "document": DocumentDomain,
                "config": ConfigDomain,
                "tool": ToolDomain,
                "workspace": WorkspaceDomain,
                "storage": StorageDomain,
                "model": ModelDomain,
                "engine": EngineDomain,
            }
            expected = type_to_class.get(domain.domain_type)
            if expected:
                assert isinstance(wrapped, expected), (
                    f"{domain.id}: expected {expected.__name__}, got {type(wrapped).__name__}"
                )
