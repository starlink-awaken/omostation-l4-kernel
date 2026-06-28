"""L4 Domain Health — 跨域健康聚合与 DASHBOARD 生成。

基于 DomainRegistry + KemsValidator，提供:
- 全域健康聚合
- X2 新鲜度检查
- 跨域全文搜索
- DASHBOARD 生成
"""

from __future__ import annotations

from datetime import UTC, datetime

from l4_kernel.kems import KemsPlane
from l4_kernel.registry import Domain, DomainRegistry
from l4_kernel.templates import KemsValidator


class DomainHealth:
    """跨域健康聚合器。

    为 L4 全域提供统一的健康视图和 DASHBOARD。
    """

    def __init__(self, registry: DomainRegistry | None = None):
        self.registry = registry or DomainRegistry()

    # ── 聚合健康 ────────────────────────────────────────────────────

    def aggregate_health(self) -> dict:
        """全域健康聚合 (含 DocumentDomain KEMS 校验)。"""
        all_domains = self.registry.list_all()
        existing = sum(1 for d in all_domains if d.exists())
        total = len(all_domains)

        result = {
            "total": total,
            "existing": existing,
            "missing": total - existing,
            "health_rate": f"{existing / max(total, 1) * 100:.1f}%",
            "timestamp": datetime.now(UTC).isoformat(),
            "by_type": {},
            "document_domains": {},
        }

        for t in ("document", "config", "engine", "tool", "workspace", "storage", "model"):
            typed = self.registry.list_by_type(t)
            result["by_type"][t] = {
                "total": len(typed),
                "existing": sum(1 for d in typed if d.exists()),
                "missing": len(typed) - sum(1 for d in typed if d.exists()),
            }

        # DocumentDomain 详细健康
        for d in self.registry.list_document_domains():
            result["document_domains"][d.id] = self._check_document_health(d)

        return result

    def _check_document_health(self, domain: Domain) -> dict:
        """检查单个 DocumentDomain 的健康度。"""
        health = {
            "id": domain.id,
            "name": domain.name,
            "exists": domain.exists(),
            "status": "unknown",
            "kems_valid": False,
            "violations": 0,
            "violation_details": [],
            "freshness_score": 0.0,
            "last_signal_ts": None,
        }

        if not domain.exists():
            health["status"] = "missing"
            return health

        # KEMS 校验
        validator = KemsValidator(domain.path)
        violations = validator.validate_all()
        errors = [v for v in violations if v["severity"] == "error"]
        health["violations"] = len(violations)
        health["violation_details"] = violations[:10]
        health["kems_valid"] = len(errors) == 0

        # STATUS 读取
        kems = KemsPlane(domain.path)
        status_data = kems.read_status()
        if status_data:
            # 尝试从内容解析当前状态
            try:
                status_text = (domain.path / "_control" / "STATUS.md").read_text(encoding="utf-8")
                import re

                m = re.search(r"当前状态[：:]\s*(\w+)", status_text)
                if m:
                    health["status"] = m.group(1)
            except Exception:  # noqa: BLE001  # defensive fallback
                pass

        # 新鲜度
        health["freshness_score"] = self._calc_freshness(domain)

        # 最近信号
        signals = kems.read_signals()
        if signals:
            health["last_signal_ts"] = signals[-1].get("ts", "")

        return health

    # ── 新鲜度 (X2) ────────────────────────────────────────────────

    def check_freshness(self, domain_id: str) -> dict:
        """X2 新鲜度检查。

        检查项:
        - STATE.md last-reviewed > 30 天 → ⚠️
        - signals.md 最近 7 天无更新 → ⚠️
        - STATUS.md 在 ALERT 状态 > 7 天 → 🔴
        """
        domain = self.registry.get(domain_id)
        if not domain or not domain.exists():
            return {"domain_id": domain_id, "status": "not_found"}

        kems = KemsPlane(domain.path)
        issues = []

        # 检查 STATE.md 新鲜度
        state = kems.read_state()
        if state:
            reviewed = state.get("last-reviewed", "")
            if reviewed:
                try:
                    reviewed_dt = datetime.fromisoformat(reviewed.replace("Z", "+00:00"))
                    days_since = (datetime.now(UTC) - reviewed_dt).days
                    if days_since > 30:
                        issues.append(
                            {
                                "file": "STATE.md",
                                "field": "last-reviewed",
                                "days_since_review": days_since,
                                "level": "⚠️",
                                "message": f"STATE.md last-reviewed is {days_since} days old (>30 days)",
                            }
                        )
                except (ValueError, TypeError):
                    pass

        # 检查 signals 新鲜度
        signals = kems.read_signals()
        if signals:
            last_signal = signals[-1].get("ts", "")
            if last_signal:
                try:
                    last_dt = datetime.fromisoformat(last_signal.replace("Z", "+00:00"))
                    days_since = (datetime.now(UTC) - last_dt).days
                    if days_since > 7:
                        issues.append(
                            {
                                "file": "signals.md",
                                "days_since_last_signal": days_since,
                                "level": "⚠️",
                                "message": f"No signals in {days_since} days (>7 days)",
                            }
                        )
                except (ValueError, TypeError):
                    pass
        else:
            issues.append(
                {
                    "file": "signals.md",
                    "level": "⚠️",
                    "message": "signals.md is empty or unreadable",
                }
            )

        # 检查 STATUS ALERT 持续
        status_data = kems.read_status()
        if status_data:
            try:
                status_text = (domain.path / "_control" / "STATUS.md").read_text(encoding="utf-8")
                import re

                m = re.search(r"当前状态[：:]\s*(\w+)", status_text)
                if m and m.group(1) == "ALERT":
                    # 检查状态变更日志
                    changes = status_data.get("状态变更日志", [])
                    if changes:
                        last_change = changes[-1]
                        last_date = last_change.get("日期", "")
                        if last_date:
                            try:
                                last_dt = datetime.strptime(last_date, "%Y-%m-%d").replace(tzinfo=UTC)
                                days_in_alert = (datetime.now(UTC) - last_dt).days
                                if days_in_alert > 7:
                                    issues.append(
                                        {
                                            "file": "STATUS.md",
                                            "level": "🔴",
                                            "message": f"STATUS has been ALERT for {days_in_alert} days (>7 days)",
                                        }
                                    )
                            except ValueError:
                                pass
            except Exception:  # noqa: BLE001  # defensive fallback
                pass

        return {
            "domain_id": domain_id,
            "fresh": len(issues) == 0,
            "issues": issues,
            "issue_count": len(issues),
        }

    def check_all_freshness(self) -> dict[str, dict]:
        """检查所有 DocumentDomain 的新鲜度。"""
        result = {}
        for d in self.registry.list_document_domains():
            result[d.id] = self.check_freshness(d.id)
        return result

    def _calc_freshness(self, domain: Domain) -> float:
        """计算域新鲜度分数 (0.0-1.0)。

        基于:
        - 文件最近修改时间 (50%)
        - signals 最近更新 (30%)
        - STATUS 更新时间 (20%)
        """
        score = 0.0
        weights = 0.0

        # 文件修改时间
        control = domain.path / "_control"
        if control.is_dir():
            newest = 0.0
            for f in control.rglob("*.md"):
                try:
                    mtime = f.stat().st_mtime
                    if mtime > newest:
                        newest = mtime
                except OSError:
                    pass
            if newest > 0:
                days = (datetime.now().timestamp() - newest) / 86400
                file_score = max(0.0, 1.0 - days / 30)  # 30天内满分
                score += file_score * 0.5
                weights += 0.5

        # signals 新鲜度
        kems = KemsPlane(domain.path)
        signals = kems.read_signals()
        if signals:
            last_ts = signals[-1].get("ts", "")
            if last_ts:
                try:
                    last_dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                    days = (datetime.now(UTC) - last_dt).days
                    sig_score = max(0.0, 1.0 - days / 14)  # 14天内满分
                    score += sig_score * 0.3
                    weights += 0.3
                except (ValueError, TypeError):
                    pass

        # STATUS 更新时间
        status = kems.read_status()
        if status:
            reviewed = status.get("last-reviewed", "")
            if reviewed:
                try:
                    reviewed_dt = datetime.fromisoformat(reviewed.replace("Z", "+00:00"))
                    days = (datetime.now(UTC) - reviewed_dt).days
                    stat_score = max(0.0, 1.0 - days / 30)
                    score += stat_score * 0.2
                    weights += 0.2
                except (ValueError, TypeError):
                    pass

        return round(score / max(weights, 1.0), 2)

    # ── 跨域搜索 ────────────────────────────────────────────────────

    def cross_domain_search(self, query: str, max_per_domain: int = 5) -> list[dict]:
        """跨所有 DocumentDomain 全文搜索。"""
        results = []
        for d in self.registry.list_document_domains():
            if not d.exists():
                continue
            kems = KemsPlane(d.path)
            domain_results = kems.search(query, max_results=max_per_domain)
            for r in domain_results:
                r["domain"] = d.id
                r["domain_name"] = d.name
            results.extend(domain_results)
        return results

    # ── DASHBOARD ───────────────────────────────────────────────────

    def generate_dashboard(self) -> str:
        """生成 Markdown 格式的全域 DASHBOARD。"""
        health = self.aggregate_health()
        lines = [
            "# L4 全域健康 DASHBOARD",
            "",
            f"> 更新时间: {health['timestamp']}",
            "",
            "## 总览",
            "",
            f"- **总计**: {health['total']} 域",
            f"- **存在**: {health['existing']} 域",
            f"- **缺失**: {health['missing']} 域",
            f"- **健康率**: {health['health_rate']}",
            "",
            "## 按类型",
            "",
            "| 类型 | 存在/总数 | 状态 |",
            "|------|----------|------|",
        ]
        for t, s in health["by_type"].items():
            icon = "✅" if s["missing"] == 0 else "⚠️"
            lines.append(f"| {t} | {s['existing']}/{s['total']} | {icon} |")

        lines.extend(
            [
                "",
                "## DocumentDomain 详情",
                "",
                "| 域 | 状态 | KEMS | 违规 | 新鲜度 | 最后信号 |",
                "|----|------|------|------|--------|---------|",
            ]
        )
        for domain_id, h in health["document_domains"].items():
            kems_icon = "✅" if h["kems_valid"] else "❌"
            status = h.get("status", "?")
            freshness = f"{h['freshness_score']:.0%}"
            last_sig = h.get("last_signal_ts", "-")[:10] if h.get("last_signal_ts") else "-"
            lines.append(f"| {domain_id} | {status} | {kems_icon} | {h['violations']} | {freshness} | {last_sig} |")

        # 违规详情
        violations = self.get_violations()
        if violations:
            lines.extend(["", "## Schema 违规", ""])
            for domain_id, vlist in violations.items():
                lines.append(f"### {domain_id}")
                for v in vlist:
                    sev = v["severity"]
                    icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(sev, "")
                    lines.append(f"- {icon} [{sev}] {v['message']}")

        return "\n".join(lines) + "\n"

    def get_violations(self) -> dict[str, list[dict]]:
        """获取所有域的 Schema violations。"""
        result = {}
        for d in self.registry.list_document_domains():
            if not d.exists():
                continue
            validator = KemsValidator(d.path)
            vlist = validator.validate_all()
            if vlist:
                result[d.id] = vlist
        return result
