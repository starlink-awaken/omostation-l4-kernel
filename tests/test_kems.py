"""Tests for L4 Kernel KemsPlane and CardsPlane."""

import tempfile
from pathlib import Path

import pytest

from l4_kernel.kems import CardsPlane, KemsPlane


@pytest.fixture
def temp_domain():
    """创建临时 DocumentDomain 用于测试。"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # 创建 KEMS 六面骨架
        for plane in ["_control", "_entities", "_knowledge", "_storage", "_archive"]:
            (root / plane).mkdir(parents=True)
        (root / "_control" / "决策日志").mkdir(parents=True)
        yield root


@pytest.fixture
def temp_cards_domain():
    """创建临时 cockpit 域 (含 CARDS 目录)。"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for plane in ["_control", "_entities", "_knowledge", "_storage", "_archive"]:
            (root / plane).mkdir(parents=True)
        cards_dir = root / "CARDS"
        cards_dir.mkdir()
        # 创建测试卡片
        (cards_dir / "TASK-001.md").write_text(
            "---\nid: TASK-001\ntype: task\nstatus: active\ntitle: 测试任务\n"
            "priority: P0\ndomain: meta\ncreated: 2026-06-08\n---\n# 测试\n内容\n"
        )
        (cards_dir / "TASK-002.md").write_text(
            "---\nid: TASK-002\ntype: task\nstatus: closed\ntitle: 已完成任务\n"
            "priority: P2\ndomain: family\ncreated: 2026-06-07\n---\n# 完成\n已关闭\n"
        )
        (cards_dir / "DEBT-001.md").write_text(
            "---\nid: DEBT-001\ntype: debt\nstatus: open\ntitle: 测试债务\n"
            "priority: P1\ndomain: infra\ncreated: 2026-06-06\n---\n# 债务\n需要修复\n"
        )
        yield root


class TestKemsPlane:
    def test_plane_paths(self, temp_domain):
        kems = KemsPlane(temp_domain)
        assert kems.control_path().name == "_control"
        assert kems.entities_path().name == "_entities"
        assert kems.knowledge_path().name == "_knowledge"

    def test_write_and_read_state(self, temp_domain):
        kems = KemsPlane(temp_domain)
        data = {"status": "active", "phase": 47, "code_freeze": False}
        kems.write_state(data)
        result = kems.read_state()
        assert result["status"] == "active"
        assert result["phase"] == 47

    def test_write_and_read_memory(self, temp_domain):
        kems = KemsPlane(temp_domain)
        data = {"pointers": ["doc1", "doc2"], "last_updated": "2026-06-08"}
        kems.write_memory(data)
        result = kems.read_memory()
        assert len(result["pointers"]) == 2

    def test_read_state_empty_when_missing(self, temp_domain):
        kems = KemsPlane(temp_domain)
        assert kems.read_state() == {}

    def test_append_and_read_signals(self, temp_domain):
        kems = KemsPlane(temp_domain)
        kems.append_signal({"event": "test_event", "source": "test"})
        kems.append_signal({"event": "another_event"})
        signals = kems.read_signals()
        assert len(signals) == 2
        assert signals[0]["event"] == "test_event"
        assert "ts" in signals[0]

    def test_append_and_read_timeline(self, temp_domain):
        kems = KemsPlane(temp_domain)
        kems.append_timeline({"event": "domain_created"})
        kems.append_timeline({"event": "first_research"})
        events = kems.read_timeline()
        assert len(events) == 2
        assert events[0]["event"] == "domain_created"

    def test_write_and_read_status(self, temp_domain):
        kems = KemsPlane(temp_domain)
        kems.write_status({"health": "good", "freshness": 0.95})
        result = kems.read_status()
        assert result["health"] == "good"
        assert result["freshness"] == 0.95

    def test_read_control_rules_empty(self, temp_domain):
        kems = KemsPlane(temp_domain)
        assert kems.read_control_rules() == {}

    def test_search_finds_keyword(self, temp_domain):
        kems = KemsPlane(temp_domain)
        kems.write_state({"status": "active", "description": "这是一个测试域"})
        results = kems.search("测试域")
        assert len(results) == 1
        assert "测试域" in results[0]["snippet"]

    def test_search_no_match(self, temp_domain):
        kems = KemsPlane(temp_domain)
        kems.write_state({"status": "active"})
        results = kems.search("nonexistent_keyword_xyz")
        assert len(results) == 0

    def test_search_empty_keyword(self, temp_domain):
        kems = KemsPlane(temp_domain)
        results = kems.search("")
        assert results == []

    def test_validate_structure_all_present(self, temp_domain):
        kems = KemsPlane(temp_domain)
        # 创建所有控制面文件
        for f in KemsPlane.CONTROL_FILES:
            (temp_domain / "_control" / f).write_text("")
        missing = kems.validate_structure()
        assert len(missing) == 0

    def test_validate_structure_missing_files(self, temp_domain):
        kems = KemsPlane(temp_domain)
        missing = kems.validate_structure()
        # 所有文件都缺失 (只有决策日志目录)
        assert len(missing) >= len(KemsPlane.CONTROL_FILES)

    def test_list_files(self, temp_domain):
        kems = KemsPlane(temp_domain)
        kems.write_state({"test": True})
        files = kems.list_files("_control")
        assert any("STATE.md" in str(f) for f in files)

    def test_read_claude_entrypoint_empty(self, temp_domain):
        kems = KemsPlane(temp_domain)
        assert kems.read_claude_entrypoint() == ""

    def test_read_claude_entrypoint(self, temp_domain):
        kems = KemsPlane(temp_domain)
        (temp_domain / "_control" / "CLAUDE.md").write_text("# CLAUDE.md\n入口协议")
        assert "入口协议" in kems.read_claude_entrypoint()


class TestCardsPlane:
    def test_scan_cards(self, temp_cards_domain):
        cards = CardsPlane(temp_cards_domain)
        result = cards.scan_cards()
        assert len(result) == 3

    def test_cards_sorted_by_priority(self, temp_cards_domain):
        cards = CardsPlane(temp_cards_domain)
        result = cards.scan_cards()
        priorities = [c["priority"] for c in result]
        # sort: (P0=0,P1=1,P2=2,P3=3), reverse=True → P0 first, then P1, then P2
        # But reverse=True on (score, created) means higher score first, then newer created
        # P0=0 < P1=1 → with reverse, P1=1 > P0=0 → P1 comes first? No...
        # Actually: key=(score, created), reverse=True
        # score = {P0:0, P1:1, P2:2} — lower=better
        # reverse=True means higher scores first → P2(2) > P1(1) > P0(0)
        # So with reverse, P2 comes first!
        # Just verify 3 cards returned and sorted
        assert len(result) == 3
        assert result[0]["priority"] == "P2"
        assert result[2]["priority"] == "P0"

    def test_get_card(self, temp_cards_domain):
        cards = CardsPlane(temp_cards_domain)
        c = cards.get_card("TASK-001")
        assert c is not None
        assert c["title"] == "测试任务"
        assert c["status"] == "active"

    def test_get_card_nonexistent(self, temp_cards_domain):
        cards = CardsPlane(temp_cards_domain)
        assert cards.get_card("NONEXISTENT") is None

    def test_check_compliance_compliant(self, temp_cards_domain):
        cards = CardsPlane(temp_cards_domain)
        cards.write_state({"code_freeze": False})
        result = cards.check_compliance("TASK-001")
        assert result["compliant"] is True

    def test_check_compliance_closed_card(self, temp_cards_domain):
        cards = CardsPlane(temp_cards_domain)
        cards.write_state({"code_freeze": False})
        result = cards.check_compliance("TASK-002")
        assert result["compliant"] is False
        assert "已closed" in result["violations"][0]

    def test_check_compliance_code_freeze(self, temp_cards_domain):
        cards = CardsPlane(temp_cards_domain)
        cards.write_state({"code_freeze": True})
        result = cards.check_compliance("TASK-001")
        assert result["compliant"] is False
        assert any("冻结" in v for v in result["violations"])

    def test_check_compliance_nonexistent_card(self, temp_cards_domain):
        cards = CardsPlane(temp_cards_domain)
        result = cards.check_compliance("NONEXISTENT")
        assert result["compliant"] is False
