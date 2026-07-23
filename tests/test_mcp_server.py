"""Tests for L4 Kernel MCP Server tools."""

import json

from l4_kernel.mcp_server import (
    TOOLS,
    l4_cards_list,
    l4_claude_validate,
    l4_cross_search,
    l4_dashboard,
    l4_domain_info,
    l4_domain_validate,
    l4_domains_list,
    l4_health,
    l4_kems_validate,
    l4_memory_read,
    l4_plugin_actions,
    l4_plugin_specs,
    l4_plugin_workflows,
    l4_search,
    l4_signal_emit,
    l4_signal_patterns,
    l4_signals_list,
    l4_state_read,
    l4_status_read,
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


class TestToolRegistry:
    def test_tools_registered(self):
        assert len(TOOLS) >= 42

    def test_all_tools_callable(self):
        for name, fn in TOOLS.items():
            assert callable(fn), f"{name} is not callable"
