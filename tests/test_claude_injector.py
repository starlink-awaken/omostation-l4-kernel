"""Tests for L4 Kernel ClaudeInjector."""

import tempfile
from pathlib import Path

import pytest

from l4_kernel.claude_injector import ClaudeInjector, check_injection_status
from l4_kernel.registry import Domain, DomainRegistry
from l4_kernel.templates import init_domain_kems


@pytest.fixture
def temp_domain_with_claude():
    """创建带 CLAUDE.md 的临时域。"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        init_domain_kems(root, domain_name="测试域", owner="test")
        # 覆写 CLAUDE.md 为真实格式
        (root / "_control" / "CLAUDE.md").write_text(
            "# @测试域 — 测试域\n\n"
            "> L4 | KEMS 六面\n\n"
            "## §0 KEMS 六面\n\n"
            "| 平面 | 目录 | 内容 |\n"
            "|------|------|------|\n"
            "| 控制面 | `_control/` | STATE MEMORY |\n\n"
            "## §1 快速路由\n\n"
            "| 意图 | 路径 |\n"
            "|------|------|\n"
            "| 状态 | `_control/STATE.md` |\n\n"
            "## §2 对外接口\n\n"
            "| 系统 | 路径 |\n"
            "|------|------|\n"
            "| 驾驶舱 | `~/Documents/@驾驶舱/` |\n\n"
            "## 会话入口协议\n\n"
            "```\n"
            "1. _control/STATUS.md\n"
            "2. _control/STATE.md\n"
            "```\n"
        )
        yield root


@pytest.fixture
def registry_with_temp_domain(temp_domain_with_claude):
    reg = DomainRegistry()
    reg.register(Domain(
        id="inject-test", name="测试域", domain_type="document",
        path=temp_domain_with_claude, bos_uri="bos://test/**",
        kems_planes=["_control"],
    ))
    return reg


class TestClaudeInjector:
    def test_inject(self, registry_with_temp_domain):
        injector = ClaudeInjector(registry_with_temp_domain)
        result = injector.inject("inject-test")
        assert result["status"] == "ok"
        assert result["injected"] is True

    def test_inject_already_injected(self, registry_with_temp_domain):
        injector = ClaudeInjector(registry_with_temp_domain)
        injector.inject("inject-test")
        result = injector.inject("inject-test")
        assert result["status"] == "skipped"
        assert result["injected"] is False

    def test_inject_content_contains_marker(self, registry_with_temp_domain, temp_domain_with_claude):
        injector = ClaudeInjector(registry_with_temp_domain)
        injector.inject("inject-test")
        content = (temp_domain_with_claude / "_control" / "CLAUDE.md").read_text()
        assert "l4-kernel Schema" in content

    def test_inject_preserves_original_content(self, registry_with_temp_domain, temp_domain_with_claude):
        injector = ClaudeInjector(registry_with_temp_domain)
        injector.inject("inject-test")
        content = (temp_domain_with_claude / "_control" / "CLAUDE.md").read_text()
        assert "## §1 快速路由" in content
        assert "## §2 对外接口" in content
        assert "会话入口协议" in content

    def test_inject_nonexistent(self):
        injector = ClaudeInjector()
        result = injector.inject("nonexistent")
        assert result["status"] == "error"
        assert result["injected"] is False

    def test_inject_compact(self, registry_with_temp_domain, temp_domain_with_claude):
        injector = ClaudeInjector(registry_with_temp_domain)
        injector.inject("inject-test", compact=True)
        content = (temp_domain_with_claude / "_control" / "CLAUDE.md").read_text()
        assert "l4-kernel Schema" in content
        assert "## §1 快速路由" in content  # 原始内容保留

    def test_diff_has_schema_false(self, registry_with_temp_domain):
        injector = ClaudeInjector(registry_with_temp_domain)
        result = injector.diff("inject-test")
        assert result["has_schema"] is False
        assert result["needs_injection"] is True

    def test_diff_has_schema_true(self, registry_with_temp_domain):
        injector = ClaudeInjector(registry_with_temp_domain)
        injector.inject("inject-test")
        result = injector.diff("inject-test")
        assert result["has_schema"] is True
        assert result["needs_injection"] is False

    def test_diff_nonexistent(self):
        injector = ClaudeInjector()
        result = injector.diff("nonexistent")
        assert result["status"] == "not_found"

    def test_validate(self, registry_with_temp_domain):
        injector = ClaudeInjector(registry_with_temp_domain)
        result = injector.validate("inject-test")
        assert result["has_schema"] is False

    def test_validate_all(self):
        injector = ClaudeInjector()
        result = injector.validate_all()
        assert "total" in result
        assert "injected" in result
        assert "missing" in result
        assert "rate" in result
        assert "domains" in result

    def test_remove(self, registry_with_temp_domain, temp_domain_with_claude):
        injector = ClaudeInjector(registry_with_temp_domain)
        injector.inject("inject-test")
        result = injector.remove("inject-test")
        assert result["removed"] is True
        content = (temp_domain_with_claude / "_control" / "CLAUDE.md").read_text()
        assert "l4-kernel Schema" not in content

    def test_remove_not_injected(self, registry_with_temp_domain):
        injector = ClaudeInjector(registry_with_temp_domain)
        result = injector.remove("inject-test")
        assert result["status"] == "not_injected"

    def test_inject_all(self):
        injector = ClaudeInjector()
        results = injector.inject_all(compact=True)
        assert isinstance(results, dict)
        # 至少有一个存在的域
        assert len(results) >= 1

    def test_convenience_functions(self):
        status = check_injection_status()
        assert "total" in status
        assert "injected" in status
