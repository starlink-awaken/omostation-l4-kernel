"""Tests for L4 Kernel domain_plugins — 6 种域类型插件。"""

import tempfile
from pathlib import Path

import pytest

from l4_kernel.domain_plugins import (
    ConfigDomainPlugin,
    EngineDomainPlugin,
    ModelDomainPlugin,
    StorageDomainPlugin,
    ToolDomainPlugin,
    WorkspaceDomainPlugin,
)


class TestConfigDomainPlugin:
    @pytest.fixture
    def plugin(self):
        return ConfigDomainPlugin()

    @pytest.fixture
    def config_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "config.yaml").write_text("key: value\n")
            (root / "settings.json").write_text('{"port": 8080}')
            yield root

    def test_domain_type(self, plugin):
        assert plugin.domain_type == "config"

    def test_get_actions(self, plugin):
        actions = plugin.get_actions()
        assert "config_audit" in actions
        assert "config_backup" in actions
        assert "config_validate_all" in actions

    def test_config_audit(self, plugin, config_path):
        result = plugin._action_config_audit(config_path)
        assert result["total"] == 2
        assert result["valid"] == 2

    def test_config_backup(self, plugin, config_path):
        result = plugin._action_config_backup(config_path)
        assert result["backed_up"] >= 1

    def test_get_workflows(self, plugin):
        wf = plugin.get_workflows()
        assert "config_health_check" in wf


class TestToolDomainPlugin:
    @pytest.fixture
    def plugin(self):
        return ToolDomainPlugin()

    @pytest.fixture
    def tool_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            script = root / "hello.sh"
            script.write_text("#!/bin/bash\necho hello\n")
            script.chmod(0o755)
            yield root

    def test_domain_type(self, plugin):
        assert plugin.domain_type == "tool"

    def test_tool_inventory(self, plugin, tool_path):
        result = plugin._action_tool_inventory(tool_path)
        assert result["total"] == 1

    def test_tool_health_check(self, plugin, tool_path):
        result = plugin._action_tool_health_check(tool_path)
        assert result["healthy"] == 1

    def test_tool_deprecation_scan(self, plugin, tool_path):
        result = plugin._action_tool_deprecation_scan(tool_path)
        assert result["total"] == 1


class TestEngineDomainPlugin:
    def test_domain_type(self):
        plugin = EngineDomainPlugin()
        assert plugin.domain_type == "engine"

    def test_get_actions(self):
        plugin = EngineDomainPlugin()
        actions = plugin.get_actions()
        assert "engine_health_check" in actions
        assert "engine_config_rotate" in actions
        assert "engine_log_analyze" in actions

    def test_engine_config_rotate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "config.yaml").write_text("port: 8765\n")
            plugin = EngineDomainPlugin()
            result = plugin._action_engine_config_rotate(root)
            assert result["status"] == "ok"


class TestStorageDomainPlugin:
    def test_domain_type(self):
        plugin = StorageDomainPlugin()
        assert plugin.domain_type == "storage"

    def test_get_actions(self):
        plugin = StorageDomainPlugin()
        actions = plugin.get_actions()
        assert "disk_monitor" in actions
        assert "mount_check" in actions

    def test_disk_monitor(self):
        plugin = StorageDomainPlugin()
        result = plugin._action_disk_monitor(Path("/"))
        assert result["action"] == "disk_monitor"
        assert result["status"] in ("ok", "warning", "critical")


class TestModelDomainPlugin:
    def test_domain_type(self):
        plugin = ModelDomainPlugin()
        assert plugin.domain_type == "model"

    def test_get_actions(self):
        plugin = ModelDomainPlugin()
        actions = plugin.get_actions()
        assert "model_inventory" in actions
        assert "checksum_verify" in actions

    def test_model_inventory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "model.bin").write_text("fake model data\n" * 100)
            plugin = ModelDomainPlugin()
            result = plugin._action_model_inventory(root)
            assert result["total"] == 1


class TestWorkspaceDomainPlugin:
    def test_domain_type(self):
        plugin = WorkspaceDomainPlugin()
        assert plugin.domain_type == "workspace"

    def test_get_actions(self):
        plugin = WorkspaceDomainPlugin()
        actions = plugin.get_actions()
        assert "workspace_index" in actions
        assert "stale_project_detect" in actions

    def test_workspace_index(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "README.md").write_text("# Test\n")
            plugin = WorkspaceDomainPlugin()
            result = plugin._action_workspace_index(root)
            assert result["total"] == 1
