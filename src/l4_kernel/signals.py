"""L4 Signal Bus — 跨域信号路由与聚合。

信号分类:
- domain 内信号: 写入域的 signals.md
- 跨域信号: 写入 @驾驶舱 signals.md (来源域/波及域)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from l4_kernel.kems import KemsPlane
from l4_kernel.registry import DomainRegistry

# model-driven 桥接 (可选依赖)
try:
    from model_driven.management.omo_bridge import OMOBridge

    _MD_BRIDGE = OMOBridge()
except ImportError:
    OMOBridge = None  # type: ignore
    _MD_BRIDGE = None

# Omni-Bus Facade 桥接
try:
    from bus_foundation.facade import event as bus_event
except ImportError:
    bus_event = None

SignalType = Literal["✅", "⚠️", "🔴", "ℹ️"]


class SignalBus:
    """跨域信号路由与聚合。

    所有 L4 域的操作都应该通过 SignalBus 发射信号，
    而不是直接写 signals.md。
    """

    def __init__(self, registry: DomainRegistry | None = None):
        self.registry = registry or DomainRegistry.require_explicit()

    # ── 发射信号 ────────────────────────────────────────────────────

    def emit(
        self,
        domain_id: str,
        signal_type: SignalType,
        message: str,
        *,
        source: str = "l4-kernel",
        cross_domain: bool = False,
        affected_domains: list[str] | None = None,
    ) -> bool:
        """发射信号到域的 signals.md。

        Args:
            domain_id: 目标域 ID
            signal_type: 信号类型 (✅⚠️🔴ℹ️)
            message: 信号内容
            source: 信号来源
            cross_domain: 是否同时写入 @驾驶舱
            affected_domains: 跨域时受影响的域列表

        Returns:
            是否成功
        """
        domain = self.registry.get(domain_id)
        if not domain or not domain.exists():
            return False

        kems = KemsPlane(domain.path)
        event = {
            "ts": datetime.now(UTC).isoformat(),
            "type": signal_type,
            "source": source,
            "message": message,
        }
        kems.append_signal(event)

        # 跨域信号 → 同时写入 @驾驶舱 (带文件锁)
        if cross_domain:
            cockpit = self.registry.get("cockpit")
            if cockpit and cockpit.exists():
                import fcntl

                cockpit_kems = KemsPlane(cockpit.path)
                cross_event = {
                    "ts": datetime.now(UTC).isoformat(),
                    "type": signal_type,
                    "source_domain": domain_id,
                    "source": source,
                    "affected": affected_domains or [],
                    "message": message,
                }
                # 文件锁保护并发写入
                sig_file = cockpit.path / "_control" / "signals.md"
                try:
                    with open(sig_file, "a") as f:
                        fcntl.flock(f, fcntl.LOCK_EX)
                        cockpit_kems.append_signal(cross_event)
                        fcntl.flock(f, fcntl.LOCK_UN)
                except (OSError, ValueError):
                    cockpit_kems.append_signal(cross_event)  # 回退: 无锁写入

        # Omni-Bus Facade 投递 (X1 强制路由)
        if bus_event:
            bus_payload = {
                "domain_id": domain_id,
                "message": message,
                "affected": affected_domains or [],
            }
            # The topic can be e.g. "l4.signal.red"
            topic = f"l4.signal.{signal_type}"
            bus_event.publish(topic=topic, payload=bus_payload, source_uri="bos://governance/l4-kernel")

        return True

    def emit_batch(
        self,
        signals: list[dict],
        cross_domain: bool = False,
    ) -> dict[str, bool]:
        """批量发射信号。

        Args:
            signals: [{"domain": "vault", "type": "✅", "message": "..."}, ...]
            cross_domain: 是否写入 @驾驶舱

        Returns:
            {domain_id: success}
        """
        results = {}
        for sig in signals:
            domain_id = sig["domain"]
            signal_type = sig["type"]
            message = sig["message"]
            affected = sig.get("affected", [])
            results[domain_id] = self.emit(
                domain_id,
                signal_type,
                message,
                source=sig.get("source", "l4-kernel"),
                cross_domain=cross_domain,
                affected_domains=affected,
            )
        return results

    # ── 聚合信号 ────────────────────────────────────────────────────

    def aggregate_recent(self, window_hours: int = 24) -> list[dict]:
        """聚合最近 N 小时所有域的信号。"""
        results = []
        cutoff = datetime.now(UTC).timestamp() - window_hours * 3600

        for d in self.registry.list_document_domains():
            if not d.exists():
                continue
            kems = KemsPlane(d.path)
            signals = kems.read_signals()
            if not signals:
                continue
            for sig in signals:
                ts = sig.get("ts", "")
                if ts:
                    try:
                        sig_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if sig_dt.timestamp() >= cutoff:
                            sig["domain_id"] = d.id
                            sig["domain_name"] = d.name
                            results.append(sig)
                    except (ValueError, TypeError):
                        pass

        results.sort(key=lambda s: s.get("ts", ""), reverse=True)
        return results

    def aggregate_by_type(self, window_hours: int = 168) -> dict:
        """按信号类型聚合最近 N 小时的信号 (默认7天)。"""
        recent = self.aggregate_recent(window_hours)
        by_type = {"✅": [], "⚠️": [], "🔴": [], "ℹ️": []}
        for sig in recent:
            t = sig.get("type", "ℹ️")
            if t in by_type:
                by_type[t].append(sig)
        return by_type

    # ── 模式检测 ────────────────────────────────────────────────────

    def detect_patterns(self, window_hours: int = 72) -> list[dict]:
        """检测跨域信号模式。

        检测:
        - 多域同时 ⚠️ → 系统性风险
        - 同域连续 🔴 → 升级 CRITICAL
        - 跨域信号未闭环 → 跟踪
        """
        patterns = []
        recent = self.aggregate_recent(window_hours)

        # 按域分组
        by_domain: dict[str, list[dict]] = {}
        for sig in recent:
            did = sig.get("domain_id", "unknown")
            by_domain.setdefault(did, []).append(sig)

        # 检测 1: 同域连续 🔴
        for did, sigs in by_domain.items():
            reds = [s for s in sigs if s.get("type") == "🔴"]
            if len(reds) >= 3:
                patterns.append(
                    {
                        "pattern": "consecutive_red",
                        "domain": did,
                        "count": len(reds),
                        "level": "🔴",
                        "message": f"Domain {did} has {len(reds)} 🔴 signals in {window_hours}h — consider upgrading to CRITICAL",
                    }
                )

        # 检测 2: 多域同时 ⚠️
        warning_domains = set()
        for sig in recent:
            if sig.get("type") == "⚠️":
                warning_domains.add(sig.get("domain_id", ""))
        if len(warning_domains) >= 3:
            patterns.append(
                {
                    "pattern": "multi_domain_warning",
                    "domains": sorted(warning_domains),
                    "count": len(warning_domains),
                    "level": "⚠️",
                    "message": f"{len(warning_domains)} domains have ⚠️ signals — possible systemic issue",
                }
            )

        # 检测 3: 跨域信号无闭环
        cross_sigs = [s for s in recent if s.get("source_domain")]
        if cross_sigs:
            affected_ids = set()
            for s in cross_sigs:
                for a in s.get("affected", []):
                    affected_ids.add(a)
            if affected_ids:
                patterns.append(
                    {
                        "pattern": "cross_domain_pending",
                        "source_domains": sorted(set(s.get("source_domain", "") for s in cross_sigs)),
                        "affected_domains": sorted(affected_ids),
                        "level": "ℹ️",
                        "message": f"Cross-domain signals pending closure: {sorted(affected_ids)}",
                    }
                )

        return patterns

    # ── 健康信号 ────────────────────────────────────────────────────

    def emit_violation_signal(self, domain_id: str, violations: list[dict]) -> None:
        """将 KemsValidator 的 violations 转为信号发射。"""
        errors = [v for v in violations if v["severity"] == "error"]
        warnings = [v for v in violations if v["severity"] == "warning"]

        if errors:
            msgs = [e["message"] for e in errors]
            self.emit(domain_id, "🔴", f"Schema violations: {'; '.join(msgs[:3])}", source="KemsValidator")
            # OMO 桥接: 严重违规自动注册债务
            if _MD_BRIDGE:
                for e in errors:
                    _MD_BRIDGE.register_debt_and_persist(
                        title=f"Schema violation: {domain_id}",
                        description=e["message"],
                        severity="high",
                    )
        elif warnings:
            msgs = [w["message"] for w in warnings[:3]]
            self.emit(domain_id, "⚠️", f"Schema warnings: {'; '.join(msgs)}", source="KemsValidator")
        else:
            self.emit(domain_id, "✅", "Schema validation passed", source="KemsValidator")
