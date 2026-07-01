"""Tests for L4 Kernel SignalBus."""

import tempfile
from pathlib import Path

from l4_kernel.registry import Domain
from l4_kernel.signals import SignalBus
from l4_kernel.templates import init_domain_kems


class TestSignalBus:
    def test_emit_to_domain(self, registry):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_domain_kems(root, domain_name="测试域", owner="test")

            # 创建临时注册表
            reg = registry
            reg.register(
                Domain(
                    id="test-domain",
                    name="测试域",
                    domain_type="document",
                    path=root,
                    bos_uri="bos://test/**",
                    kems_planes=["_control", "_entities", "_knowledge", "_storage", "_archive"],
                )
            )

            bus = SignalBus(reg)
            result = bus.emit("test-domain", "✅", "测试信号", source="test")
            assert result is True

            # 验证信号已写入
            from l4_kernel.kems import KemsPlane

            kems = KemsPlane(root)
            signals = kems.read_signals()
            assert len(signals) >= 1  # 至少有新信号
            assert signals[-1]["type"] == "✅"
            assert signals[-1]["message"] == "测试信号"

    def test_emit_to_nonexistent(self, registry):
        reg = registry
        bus = SignalBus(reg)
        result = bus.emit("nonexistent", "✅", "test")
        assert result is False

    def test_emit_batch(self, registry):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_domain_kems(root, domain_name="测试", owner="test")
            reg = registry
            reg.register(
                Domain(
                    id="batch-test",
                    name="测试",
                    domain_type="document",
                    path=root,
                    bos_uri="bos://test/**",
                    kems_planes=["_control"],
                )
            )
            bus = SignalBus(reg)
            signals = [
                {"domain": "batch-test", "type": "✅", "message": "sig1"},
                {"domain": "batch-test", "type": "⚠️", "message": "sig2"},
                {"domain": "batch-test", "type": "🔴", "message": "sig3"},
            ]
            results = bus.emit_batch(signals)
            assert results["batch-test"] is True

            from l4_kernel.kems import KemsPlane

            kems = KemsPlane(root)
            all_sigs = kems.read_signals()
            assert len(all_sigs) >= 3  # 至少 3 个信号

    def test_aggregate_recent(self, registry):
        reg = registry
        bus = SignalBus(reg)
        recent = bus.aggregate_recent(window_hours=24)
        assert isinstance(recent, list)
        for sig in recent:
            assert "domain_id" in sig
            assert "domain_name" in sig

    def test_aggregate_by_type(self, registry):
        reg = registry
        bus = SignalBus(reg)
        by_type = bus.aggregate_by_type(window_hours=168)
        assert "✅" in by_type
        assert "⚠️" in by_type
        assert "🔴" in by_type
        assert "ℹ️" in by_type

    def test_detect_patterns(self, registry):
        reg = registry
        bus = SignalBus(reg)
        patterns = bus.detect_patterns(window_hours=72)
        assert isinstance(patterns, list)
        # 每个 pattern 都有标准字段
        for p in patterns:
            assert "pattern" in p
            assert "level" in p
            assert "message" in p

    def test_emit_violation_signal(self, registry):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_domain_kems(root, domain_name="测试", owner="test")
            reg = registry
            reg.register(
                Domain(
                    id="viol-test",
                    name="测试",
                    domain_type="document",
                    path=root,
                    bos_uri="bos://test/**",
                    kems_planes=["_control"],
                )
            )
            bus = SignalBus(reg)

            violations = [
                {"severity": "error", "message": "missing file", "rule": "V-CONTROL-01"},
                {"severity": "warning", "message": "missing field", "rule": "V-CONTROL-02"},
            ]
            bus.emit_violation_signal("viol-test", violations)

            from l4_kernel.kems import KemsPlane

            kems = KemsPlane(root)
            signals = kems.read_signals()
            assert len(signals) >= 1  # 至少有新信号
            last_sig = signals[-1]
            assert last_sig["type"] == "🔴"
            assert "missing" in last_sig["message"]

    def test_emit_violation_signal_no_errors(self, registry):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_domain_kems(root, domain_name="测试", owner="test")
            reg = registry
            reg.register(
                Domain(
                    id="clean-test",
                    name="测试",
                    domain_type="document",
                    path=root,
                    bos_uri="bos://test/**",
                    kems_planes=["_control"],
                )
            )
            bus = SignalBus(reg)

            # 无 violation
            bus.emit_violation_signal("clean-test", [])

            from l4_kernel.kems import KemsPlane

            kems = KemsPlane(root)
            signals = kems.read_signals()
            last_sig = signals[-1]
            assert last_sig["type"] == "✅"
            assert "passed" in last_sig["message"]
