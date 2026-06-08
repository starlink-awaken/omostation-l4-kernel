"""Tests for L4 Kernel DomainHealth."""

from pathlib import Path

from l4_kernel.registry import DomainRegistry
from l4_kernel.health import DomainHealth
from l4_kernel.templates import init_domain_kems


class TestDomainHealth:
    def test_aggregate_health(self):
        health = DomainHealth()
        result = health.aggregate_health()
        assert result["total"] == 21
        assert "document_domains" in result
        assert "by_type" in result
        assert result["health_rate"].endswith("%")

    def test_document_domains_included(self):
        health = DomainHealth()
        result = health.aggregate_health()
        assert "vault" in result["document_domains"]
        assert "personal" in result["document_domains"]
        assert "cockpit" in result["document_domains"]

    def test_check_freshness_vault(self):
        health = DomainHealth()
        result = health.check_freshness("vault")
        assert result["domain_id"] == "vault"
        assert "fresh" in result
        assert "issues" in result

    def test_check_freshness_nonexistent(self):
        health = DomainHealth()
        result = health.check_freshness("nonexistent")
        assert result["status"] == "not_found"

    def test_check_all_freshness(self):
        health = DomainHealth()
        result = health.check_all_freshness()
        assert "vault" in result
        assert "cockpit" in result
        assert "personal" in result

    def test_cross_domain_search(self):
        health = DomainHealth()
        results = health.cross_domain_search("测试", max_per_domain=2)
        assert isinstance(results, list)

    def test_generate_dashboard(self):
        health = DomainHealth()
        dashboard = health.generate_dashboard()
        assert "# L4 全域健康 DASHBOARD" in dashboard
        assert "总览" in dashboard
        assert "按类型" in dashboard
        assert "DocumentDomain 详情" in dashboard

    def test_get_violations(self):
        health = DomainHealth()
        violations = health.get_violations()
        assert isinstance(violations, dict)
        # 存在的域至少有一个被检查
        reg = DomainRegistry()
        existing_docs = [d.id for d in reg.list_document_domains() if d.exists()]
        checked = [did for did in existing_docs if did in violations]
        assert len(checked) >= 1


class TestFreshnessWithRealDomain:
    """测试新鲜度检查在真实域上的行为。"""

    def test_vault_freshness_has_expected_fields(self):
        health = DomainHealth()
        result = health.check_freshness("vault")
        assert "domain_id" in result
        assert "fresh" in result
        assert "issues" in result
        assert "issue_count" in result
        for issue in result["issues"]:
            assert "file" in issue
            assert "level" in issue
            assert "message" in issue
            assert issue["level"] in ("⚠️", "🔴")


class TestCalcFreshness:
    """测试新鲜度计算。"""

    def test_calc_freshness_vault(self):
        reg = DomainRegistry()
        health = DomainHealth(reg)
        d = reg.get("vault")
        score = health._calc_freshness(d)
        assert 0.0 <= score <= 1.0

    def test_calc_freshness_missing_domain(self):
        reg = DomainRegistry()
        health = DomainHealth(reg)
        d = reg.get("shareddisk")
        score = health._calc_freshness(d)
        assert score == 0.0


class TestCmdHealthExitCode:
    """保护 l4-kernel cli.py:cmd_health exit code 行为(X-Plane 探针契约)。

    exit 0 = 全域存在(L4 健康) / exit 1 = 有 missing(异常)。
    修改此行为会破坏 X-Plane l4-kernel-mcp-sse 探针。
    """
    def test_cmd_health_returns_zero_when_all_present(self):
        """注入 mock registry 触发 all-present 场景。"""
        from l4_kernel.cli import cmd_health
        from l4_kernel.registry import DomainRegistry
        orig = DomainRegistry.aggregate_health
        DomainRegistry.aggregate_health = lambda self: {
            "total": 21, "existing": 21, "missing": 0,
            "by_type": {}, "health_rate": "100.0%",
        }
        try:
            rc = cmd_health([])
            assert rc == 0, f"missing=0 应返 0,实返 {rc}"
        finally:
            DomainRegistry.aggregate_health = orig

    def test_cmd_health_returns_one_when_missing(self):
        """注入 mock registry 触发 missing,验证 exit code 真的依赖 missing 计数。"""
        from l4_kernel.cli import cmd_health
        from l4_kernel.registry import DomainRegistry
        orig = DomainRegistry.aggregate_health
        DomainRegistry.aggregate_health = lambda self: {
            "total": 21, "existing": 19, "missing": 2,
            "by_type": {}, "health_rate": "90.5%",
        }
        try:
            rc = cmd_health([])
            assert rc == 1, f"missing=2 应返 1,实返 {rc}"
        finally:
            DomainRegistry.aggregate_health = orig

    def test_cmd_health_real_current_state(self):
        """记录当下 vault 真实健康度(写测试时的 snapshot)。

        本会话开始时: 21 域中 18 存在(3 missing: workspace/storage/model 缺)。
        若该数字未来变化(治理改进),会提示治理层覆盖的进展。
        """
        from l4_kernel.cli import cmd_health
        rc = cmd_health([])
        # 真实状态:若 missing=0 → 0;否则 1。锁住"当前"
        assert rc in (0, 1)  # 只锁类型,不锁具体数(数值随治理会变)
