"""Tests for L4 Kernel MCP Server tools."""

import json
from pathlib import Path

from l4_kernel.mcp_server import (
    TOOLS,
    l4_cards_list,
    l4_claude_validate,
    l4_config_read,
    l4_contract_validate,
    l4_cross_search,
    l4_dashboard,
    l4_domain_info,
    l4_domain_validate,
    l4_domains_list,
    l4_engine_logs,
    l4_entry_create,
    l4_file_append,
    l4_file_read,
    l4_file_write,
    l4_files_list,
    l4_harness_run,
    l4_health,
    l4_kems_validate,
    l4_memory_read,
    l4_plugin_actions,
    l4_plugin_run_action,
    l4_plugin_run_mechanism,
    l4_plugin_specs,
    l4_plugin_workflows,
    l4_search,
    l4_signal_emit,
    l4_signal_patterns,
    l4_signals_list,
    l4_skill_run,
    l4_state_read,
    l4_status_read,
    l4_workflow_run,
)


class TestDomainTools:
    def test_domains_list_all(self):
        result = json.loads(l4_domains_list())
        assert len(result) == 28

    def test_domains_list_by_type(self):
        result = json.loads(l4_domains_list("document"))
        assert len(result) == 12  # family-shared 已并入 family (2026-07-01)

    def test_domain_info(self):
        result = json.loads(l4_domain_info("vault"))
        assert result["id"] == "vault"

    def test_domain_info_nonexistent(self):
        result = json.loads(l4_domain_info("nonexistent"))
        assert result["status"] == "error"

    def test_domain_validate(self):
        result = json.loads(l4_domain_validate("vault"))
        assert "checks" in result


class TestKemsTools:
    def test_state_read(self):
        result = json.loads(l4_state_read("vault"))
        assert isinstance(result, dict)

    def test_state_read_nonexistent(self):
        result = json.loads(l4_state_read("nonexistent"))
        assert result["status"] == "error"

    def test_memory_read(self):
        result = json.loads(l4_memory_read("vault"))
        assert isinstance(result, dict)

    def test_signals_list(self):
        result = json.loads(l4_signals_list("vault", 5))
        assert isinstance(result, list)

    def test_status_read(self):
        result = json.loads(l4_status_read("vault"))
        assert isinstance(result, dict)

    def test_legacy_skill_and_workflow_execution_fail_closed(self):
        skill = json.loads(l4_skill_run("vault", "test/skill"))
        workflow = json.loads(l4_workflow_run("vault", "test/workflow"))

        assert skill["error"]["code"] == "L4-EXECUTION-012"
        assert workflow["error"]["code"] == "L4-EXECUTION-012"


class TestSearchTools:
    def test_search(self):
        result = json.loads(l4_search("vault", "测试", 5))
        assert isinstance(result, list)

    def test_cross_search(self):
        result = json.loads(l4_cross_search("测试", 3))
        assert isinstance(result, list)

    def test_kems_validate(self):
        result = json.loads(l4_kems_validate("vault"))
        assert isinstance(result, list)


class TestHealthTools:
    def test_health(self):
        result = json.loads(l4_health())
        assert "total" in result

    def test_health_single(self):
        result = json.loads(l4_health("vault"))
        assert "checks" in result

    def test_dashboard(self):
        result = json.loads(l4_dashboard())
        assert "dashboard" in result

    def test_signal_patterns(self):
        result = json.loads(l4_signal_patterns(72))
        assert isinstance(result, list)

    def test_claude_validate(self):
        result = json.loads(l4_claude_validate())
        assert "total" in result


class TestPluginTools:
    def test_plugin_actions(self):
        result = json.loads(l4_plugin_actions("document"))
        assert isinstance(result, dict)
        assert len(result) >= 12

    def test_plugin_workflows(self):
        result = json.loads(l4_plugin_workflows("document"))
        assert "daily_checkin" in result
        assert "weekly_review" in result

    def test_plugin_specs(self):
        result = json.loads(l4_plugin_specs("document"))
        assert "SPEC-STATE" in result
        assert "SPEC-STATUS" in result

    def test_legacy_plugin_execution_surfaces_fail_closed(self):
        action = json.loads(l4_plugin_run_action("workspace", "file_search", "sharedwork"))
        mechanism = json.loads(l4_plugin_run_mechanism("document", "freshness_auto_alert", "vault"))

        assert action["error"]["code"] == "L4-EXECUTION-012"
        assert mechanism["error"]["code"] == "L4-EXECUTION-012"


class TestCardsTools:
    def test_cards_list(self):
        result = json.loads(l4_cards_list())
        assert isinstance(result, list)

    def test_cards_list_p0(self):
        result = json.loads(l4_cards_list(priority="P0"))
        assert isinstance(result, list)


class TestSignalTools:
    def test_signal_emit(self):
        result = json.loads(l4_signal_emit("vault", "✅", "MCP test signal"))
        assert result["status"] == "ok"


class TestFilePolicy:
    def test_file_list_rejects_plane_escape(self):
        result = json.loads(l4_files_list("vault", "../../"))

        assert result["ok"] is False
        assert result["error"]["code"] == "L4-PATH-006"

    def test_read_rejects_traversal(self):
        result = json.loads(l4_file_read("vault", "../../outside.md"))

        assert result["ok"] is False
        assert result["error"]["code"] == "L4-PATH-006"

    def test_write_is_denied_by_default(self, monkeypatch):
        monkeypatch.delenv("L4_LEGACY_DIRECT_WRITE", raising=False)

        result = json.loads(l4_file_write("vault", "notes/new.md", "blocked"))

        assert result["ok"] is False
        assert result["error"]["code"] == "L4-MUTATION-011"

    def test_append_and_create_are_denied_by_default(self, monkeypatch):
        monkeypatch.delenv("L4_LEGACY_DIRECT_WRITE", raising=False)

        append = json.loads(l4_file_append("vault", "notes/new.md", "blocked"))
        create = json.loads(l4_entry_create("vault", "notes", "new", "blocked"))

        assert append["error"]["code"] == "L4-MUTATION-011"
        assert create["error"]["code"] == "L4-MUTATION-011"

    def test_legacy_write_stays_inside_domain(self, monkeypatch, l4_test_config: dict[str, Path]):
        monkeypatch.setenv("L4_LEGACY_DIRECT_WRITE", "1")

        result = json.loads(l4_file_write("vault", "notes/new.md", "allowed"))

        assert result["status"] == "ok"
        assert (l4_test_config["vault"] / "notes" / "new.md").read_text(encoding="utf-8") == "allowed"

    def test_legacy_write_still_rejects_escape(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("L4_LEGACY_DIRECT_WRITE", "1")
        outside = tmp_path / "outside.md"

        result = json.loads(l4_file_write("vault", str(outside), "blocked"))

        assert result["error"]["code"] == "L4-PATH-006"
        assert not outside.exists()

    def test_legacy_config_read_rejects_escape(self):
        result = json.loads(l4_config_read("ai-config", "../../outside.yaml"))

        assert result["error"]["code"] == "L4-PATH-006"

    def test_legacy_engine_log_read_rejects_escape(self):
        result = json.loads(l4_engine_logs("minerva", "../../outside.log"))

        assert result["error"]["code"] == "L4-PATH-006"


class TestToolRegistry:
    def test_tools_registered(self):
        assert len(TOOLS) >= 42

    def test_all_tools_callable(self):
        for name, fn in TOOLS.items():
            assert callable(fn), f"{name} is not callable"

    def test_phase0_readonly_tools_registered(self):
        assert TOOLS["l4_contract_validate"] is l4_contract_validate
        assert TOOLS["l4_harness_run"] is l4_harness_run

    def test_contract_validate_returns_stable_error(self, tmp_path: Path):
        invalid = tmp_path / "DOMAIN.yaml"
        invalid.write_text("apiVersion: l4/v1\nkind: DomainManifest\n", encoding="utf-8")

        result = json.loads(l4_contract_validate(str(invalid)))

        assert result["ok"] is False
        assert result["error"]["code"] == "L4-CONTRACT-001"
