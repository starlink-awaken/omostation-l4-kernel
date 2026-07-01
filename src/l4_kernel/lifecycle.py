"""L4 Domain Lifecycle — 域完整生命周期管理。

域状态机:
  proposed → active → frozen → archived → removed
       ↓        ↓
    rejected  degraded

每个状态转换都有对应的操作和校验。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from l4_kernel.kems import KemsPlane
from l4_kernel.registry import Domain, DomainRegistry
from l4_kernel.signals import SignalBus
from l4_kernel.templates import KemsValidator, init_domain_kems

# model-driven 桥接 (可选依赖，导入失败时降级)
try:
    from model_driven.lifecycle import LifecycleManager
    from model_driven.lifecycle.pipeline import PipelinePhase, PipelineTracker
    from model_driven.mof.m3_extended import LifecycleStage
    from model_driven.toolchain.derivation_engine import DerivationEngine

    _MD_AVAILABLE = True
except ImportError:
    LifecycleManager = None  # type: ignore
    LifecycleStage = None  # type: ignore
    PipelineTracker = None  # type: ignore
    PipelinePhase = None  # type: ignore
    DerivationEngine = None  # type: ignore
    _MD_AVAILABLE = False

DomainStatus = Literal["proposed", "active", "degraded", "frozen", "archived", "removed", "rejected"]


class DomainLifecycle:
    """域生命周期管理器。

    管理域从创建到归档的完整生命周期。
    每个操作都有前置校验、执行、后置信号三步。
    """

    def __init__(self, registry: DomainRegistry | None = None):
        self.registry = registry or DomainRegistry.require_explicit()
        self.signals = SignalBus(self.registry)

    # ── 创建域 ──────────────────────────────────────────────────────

    def create(
        self,
        domain_id: str,
        name: str,
        domain_type: str,
        path: str | Path,
        *,
        owner: str = "未指定",
        description: str = "",
        bos_uri: str | None = None,
        kems_planes: list[str] | None = None,
        governance_tier: int = 3,
        dry_run: bool = False,
    ) -> dict:
        """创建新域。

        流程:
        1. 校验域 ID 不重复
        2. 校验路径可用
        3. 创建 KEMS 骨架 (DocumentDomain)
        4. 注册到 DomainRegistry
        5. 注入 CLAUDE.md Schema
        6. 发射创建信号
        """
        # 前置校验
        if self.registry.get(domain_id):
            return {"status": "error", "message": f"Domain '{domain_id}' already exists"}

        path = Path(path)
        if path.exists() and domain_type == "document":
            # 检查是否是空目录或已有 KEMS
            control = path / "_control"
            if control.exists():
                return {
                    "status": "error",
                    "message": f"Path '{path}' already has _control/ directory. Use 'adopt' instead of 'create'.",
                }

        if dry_run:
            return {
                "status": "dry_run",
                "message": f"Would create domain '{domain_id}' at '{path}'",
                "domain_id": domain_id,
                "name": name,
                "domain_type": domain_type,
                "path": str(path),
            }

        # 创建域
        bos = bos_uri or f"bos://{domain_id}/**"
        domain = Domain(
            id=domain_id,
            name=name,
            domain_type=domain_type,
            path=path,
            bos_uri=bos,
            kems_planes=kems_planes or [],
            governance_tier=governance_tier,
            capabilities=[],
        )

        # DocumentDomain: 创建 KEMS 骨架
        created_files = []
        if domain_type == "document":
            created_files = init_domain_kems(
                path,
                domain_name=name,
                owner=owner,
                domain_type_desc=description or f"{name} 域",
            )

        # 注册
        self.registry.register(domain)

        # 发射信号
        self.signals.emit(
            domain_id,
            "ℹ️",
            f"域创建完成: {name} ({domain_type})",
            source="lifecycle.create",
        )

        return {
            "status": "ok",
            "message": f"Domain '{domain_id}' created at '{path}'",
            "domain": domain.to_dict(),
            "created_files": [str(f) for f in created_files],
        }

    def adopt(self, domain_id: str) -> dict:
        """接管已存在的域目录。

        与 create 不同: adopt 不会创建 KEMS 骨架，
        而是将已存在的目录注册到 DomainRegistry。
        """
        domain = self.registry.get(domain_id)
        if not domain:
            return {"status": "error", "message": f"Domain '{domain_id}' not registered"}

        if not domain.path.exists():
            return {"status": "error", "message": f"Domain path '{domain.path}' does not exist"}

        # 检测域类型
        control = domain.path / "_control"
        has_kems = control.is_dir()

        self.signals.emit(
            domain_id,
            "ℹ️",
            f"域已接管: {domain.name} (has_kems={has_kems})",
            source="lifecycle.adopt",
        )

        return {
            "status": "ok",
            "message": f"Domain '{domain_id}' adopted",
            "has_kems": has_kems,
        }

    # ── 校验域 ──────────────────────────────────────────────────────

    def validate(self, domain_id: str) -> dict:
        """校验域完整性。

        检查:
        1. 域路径是否存在
        2. KEMS 面是否完整 (DocumentDomain)
        3. Schema 是否合规
        4. 新鲜度是否正常
        """
        domain = self.registry.get(domain_id)
        if not domain:
            return {"status": "error", "message": f"Domain '{domain_id}' not found"}

        result = {
            "domain_id": domain_id,
            "name": domain.name,
            "status": "ok",
            "checks": {},
        }

        # 路径检查
        result["checks"]["path_exists"] = domain.exists()
        if not domain.exists():
            result["status"] = "error"
            result["checks"]["path_error"] = f"Path '{domain.path}' does not exist"
            return result

        # KEMS 校验 (仅 DocumentDomain)
        if domain.domain_type == "document":
            validator = KemsValidator(domain.path)
            violations = validator.validate_all()
            errors = [v for v in violations if v["severity"] == "error"]
            result["checks"]["kems_violations"] = len(violations)
            result["checks"]["kems_errors"] = len(errors)
            if errors:
                result["status"] = "error"
                result["checks"]["kems_error_details"] = errors[:5]

        return result

    # ── 冻结/解冻 ──────────────────────────────────────────────────

    def freeze(self, domain_id: str, reason: str = "") -> dict:
        """冻结域 (暂停操作)。"""
        domain = self.registry.get(domain_id)
        if not domain:
            return {"status": "error", "message": f"Domain '{domain_id}' not found"}

        # 更新 STATUS
        if domain.domain_type == "document":
            kems = KemsPlane(domain.path)
            kems.write_status({"status": "frozen", "frozen_reason": reason, "frozen_at": datetime.now(UTC).isoformat()})

        self.signals.emit(domain_id, "⚠️", f"域已冻结: {reason}" if reason else "域已冻结", source="lifecycle.freeze")
        return {"status": "ok", "message": f"Domain '{domain_id}' frozen"}

    def unfreeze(self, domain_id: str) -> dict:
        """解冻域。"""
        domain = self.registry.get(domain_id)
        if not domain:
            return {"status": "error", "message": f"Domain '{domain_id}' not found"}

        if domain.domain_type == "document":
            kems = KemsPlane(domain.path)
            kems.write_status({"status": "active", "unfrozen_at": datetime.now(UTC).isoformat()})

        self.signals.emit(domain_id, "✅", "域已解冻", source="lifecycle.unfreeze")
        return {"status": "ok", "message": f"Domain '{domain_id}' unfrozen"}

    # ── 归档/恢复 ──────────────────────────────────────────────────

    def archive(self, domain_id: str, reason: str = "") -> dict:
        """归档域 (移动到 _archive/ 或标记)。"""
        domain = self.registry.get(domain_id)
        if not domain:
            return {"status": "error", "message": f"Domain '{domain_id}' not found"}

        if domain.domain_type == "document":
            kems = KemsPlane(domain.path)
            kems.write_status(
                {
                    "status": "archived",
                    "archived_reason": reason,
                    "archived_at": datetime.now(UTC).isoformat(),
                }
            )

        self.signals.emit(domain_id, "ℹ️", f"域已归档: {reason}" if reason else "域已归档", source="lifecycle.archive")
        return {"status": "ok", "message": f"Domain '{domain_id}' archived"}

    def restore(self, domain_id: str) -> dict:
        """恢复已归档域。"""
        domain = self.registry.get(domain_id)
        if not domain:
            return {"status": "error", "message": f"Domain '{domain_id}' not found"}

        if domain.domain_type == "document":
            kems = KemsPlane(domain.path)
            kems.write_status({"status": "active", "restored_at": datetime.now(UTC).isoformat()})

        self.signals.emit(domain_id, "✅", "域已恢复", source="lifecycle.restore")
        return {"status": "ok", "message": f"Domain '{domain_id}' restored"}

    # ── 迁移 ────────────────────────────────────────────────────────

    def migrate(self, domain_id: str, to_version: str = "v5") -> dict:
        """迁移域 KEMS 版本。

        当前支持: v4 → v5 (KEMS 六面标准化)
        """
        domain = self.registry.get(domain_id)
        if not domain or domain.domain_type != "document":
            return {"status": "error", "message": "Only DocumentDomain supports migration"}

        changes = []

        # v4 → v5: 确保 KEMS 六面目录存在
        if to_version == "v5":
            required_planes = ["_control", "_entities", "_knowledge", "_storage", "_archive"]
            for plane in required_planes:
                p = domain.path / plane
                if not p.is_dir():
                    p.mkdir(parents=True, exist_ok=True)
                    changes.append(f"created plane: {plane}")

            # 确保 5 核心文件存在 (按需创建, 不覆盖已有)
            control = domain.path / "_control"
            from l4_kernel.templates import (
                CONTROL_RULES_TEMPLATE,
                MEMORY_TEMPLATE,
                SIGNALS_TEMPLATE,
                STATUS_TEMPLATE,
            )

            today = datetime.now(UTC).strftime("%Y-%m-%d")
            params = {
                "domain_name": domain.name,
                "owner": "migrated",
                "created": today,
                "domain_type_desc": "",
                "domain_purpose": "",
                "ssot_scope": "",
                "key_files": "",
            }
            file_templates = {
                "STATE.md": f"# STATE — {domain.name} 状态\n\n## 当前阶段定位\n\n## 活跃事项\n",
                "MEMORY.md": MEMORY_TEMPLATE.format(**params),
                "signals.md": SIGNALS_TEMPLATE.format(**params),
                "control-rules.md": CONTROL_RULES_TEMPLATE.format(**params),
                "STATUS.md": STATUS_TEMPLATE.format(**params),
            }
            for f, template in file_templates.items():
                if not (control / f).exists():
                    (control / f).write_text(template, encoding="utf-8")
                    changes.append(f"created control file: {f}")

        self.signals.emit(
            domain_id,
            "ℹ️",
            f"KEMS 迁移 {to_version}: {len(changes)} changes",
            source="lifecycle.migrate",
        )

        return {
            "status": "ok",
            "message": f"Domain '{domain_id}' migrated to {to_version}",
            "changes": changes,
        }

    # ── 健康报告 ────────────────────────────────────────────────────

    def health_report(self, domain_id: str | None = None) -> dict:
        """生成域健康报告。

        如果 domain_id 为空，返回所有域的聚合报告。
        如果 model-driven 可用，额外包含生命周期追踪 + 推导结果 + Pipeline 进度。
        """
        if domain_id:
            result = self.validate(domain_id)
            if _MD_AVAILABLE:
                result["lifecycle_tracking"] = self._get_md_lifecycle_status(domain_id)
                result["derivation"] = self._run_derivation_for_domain(domain_id)
            return result

        from l4_kernel.health import DomainHealth

        health = DomainHealth(self.registry)
        report = health.aggregate_health()

        # model-driven 桥接: 生命周期仪表板 + 推导 + Pipeline
        if _MD_AVAILABLE:
            report["lifecycle_dashboard"] = self._get_md_dashboard()
            report["derivation"] = self._run_derivation_all()
            report["pipeline"] = self._get_md_pipeline_summary()

        return report

    # ── model-driven 桥接方法 ────────────────────────────────────────

    def _get_md_lifecycle_status(self, domain_id: str) -> dict | None:
        """从 model-driven 获取域的生命周期状态"""
        if not _MD_AVAILABLE:
            return None
        try:
            mgr = LifecycleManager()
            summary = mgr.get_stage_summary(domain_id)
            return summary
        except Exception:  # defensive fallback
            return None

    def _get_md_dashboard(self) -> dict | None:
        """从 model-driven 获取生命周期仪表板"""
        if not _MD_AVAILABLE:
            return None
        try:
            mgr = LifecycleManager()
            dashboard = mgr.generate_dashboard()
            return {
                "total_entities": dashboard.total_entities,
                "by_stage": dashboard.entities_by_stage,
                "blockers": dashboard.blockers,
                "avg_progress": dashboard.avg_progress,
            }
        except Exception:  # defensive fallback
            return None

    def track_domain_lifecycle(self, domain_id: str, entity_type: str = "domain") -> dict:
        """在 model-driven 中创建域的完整生命周期追踪"""
        if not _MD_AVAILABLE:
            return {"status": "error", "message": "model-driven 不可用"}

        try:
            mgr = LifecycleManager()
            mgr.create_tracker(domain_id, entity_type)
            return {"status": "ok", "message": f"已为 {domain_id} 创建生命周期追踪"}
        except Exception as e:  # defensive fallback
            return {"status": "error", "message": str(e)}

    def advance_domain_stage(self, domain_id: str, target_stage: str) -> dict:
        """推进域的生命周期阶段"""
        if not _MD_AVAILABLE:
            return {"status": "error", "message": "model-driven 不可用"}

        try:
            from model_driven.lifecycle.transitions import TransitionEngine

            mgr = LifecycleManager()
            tracker = mgr.get_tracker(domain_id)
            if not tracker:
                tracker = mgr.create_tracker(domain_id, "domain")

            target = LifecycleStage.from_str(target_stage)
            engine = TransitionEngine()
            success, msg, _ = engine.try_transition(tracker, target)

            return {
                "status": "ok" if success else "error",
                "message": msg,
                "current_stage": tracker.current_stage.value if tracker.current_stage else None,
            }
        except Exception as e:  # defensive fallback
            return {"status": "error", "message": str(e)}

    def create_domain_pipeline(self, domain_id: str) -> dict:
        """为域创建三阶段宏观流水线追踪"""
        if not _MD_AVAILABLE:
            return {"status": "error", "message": "model-driven 不可用"}

        try:
            pt = PipelineTracker(entity_id=domain_id, entity_type="domain")
            pt.start_phase(PipelinePhase.COLD_START)
            return {
                "status": "ok",
                "message": f"已为 {domain_id} 创建三阶段流水线 (当前: ColdStart)",
                "pipeline": pt.get_progress(),
            }
        except Exception as e:  # defensive fallback
            return {"status": "error", "message": str(e)}

    def _run_derivation_for_domain(self, domain_id: str) -> dict | None:
        """对单个域运行推导规则"""
        if not _MD_AVAILABLE:
            return None
        try:
            # 加载该域的 M1 节点
            from pathlib import Path

            import yaml

            domain = self.registry.get(domain_id)
            if not domain:
                return {"error": f"域 {domain_id} 不存在"}

            # 从 L0 M1 加载相关节点
            m1_dir = Path.home() / "Workspace" / "projects" / "ecos" / "src" / "ecos" / "ssot" / "mof" / "m1"
            nodes = []
            for d in sorted(m1_dir.iterdir()):
                if d.is_dir():
                    for f in sorted(d.glob("*.yaml")):
                        try:
                            data = yaml.safe_load(open(f))
                            if data and "type" in data:
                                nodes.append(data)
                        except Exception:  # defensive fallback
                            pass

            engine = DerivationEngine()
            engine.execute_all(nodes)
            summary = engine.get_summary()
            return summary
        except Exception:  # defensive fallback
            return None

    def _run_derivation_all(self) -> dict | None:
        """对所有域运行推导规则"""
        if not _MD_AVAILABLE:
            return None
        try:
            from pathlib import Path

            import yaml

            m1_dir = Path.home() / "Workspace" / "projects" / "ecos" / "src" / "ecos" / "ssot" / "mof" / "m1"
            nodes = []
            for d in sorted(m1_dir.iterdir()):
                if d.is_dir():
                    for f in sorted(d.glob("*.yaml")):
                        try:
                            data = yaml.safe_load(open(f))
                            if data and "type" in data:
                                nodes.append(data)
                        except Exception:  # defensive fallback
                            pass

            engine = DerivationEngine()
            engine.execute_all(nodes)
            return engine.get_summary()
        except Exception:  # defensive fallback
            return None

    def _get_md_pipeline_summary(self) -> dict | None:
        """获取所有域的 Pipeline 汇总"""
        if not _MD_AVAILABLE:
            return None
        try:
            mgr = LifecycleManager()
            pipelines = {}
            for entity_id in mgr.list_entities():
                pt = PipelineTracker(entity_id=entity_id)
                pipelines[entity_id] = pt.get_progress()
            return {
                "total": len(pipelines),
                "by_phase": {
                    "cold_start": sum(1 for p in pipelines.values() if p["current_phase"] == "cold_start"),
                    "evolution": sum(1 for p in pipelines.values() if p["current_phase"] == "evolution"),
                    "hardening": sum(1 for p in pipelines.values() if p["current_phase"] == "hardening"),
                },
                "pipelines": pipelines,
            }
        except Exception:  # defensive fallback
            return None

    # ── 批量操作 ────────────────────────────────────────────────────

    def migrate_all_document_domains(self, to_version: str = "v5") -> dict[str, dict]:
        """批量迁移所有 DocumentDomain。"""
        results = {}
        for d in self.registry.list_document_domains():
            results[d.id] = self.migrate(d.id, to_version)
        return results

    def validate_all(self) -> dict[str, dict]:
        """批量校验所有域。"""
        results = {}
        for d in self.registry.list_all():
            results[d.id] = self.validate(d.id)
        return results
