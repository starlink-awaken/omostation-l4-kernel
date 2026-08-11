"""L4 Domain Lifecycle — 域完整生命周期管理。

域状态机:
  proposed → active → frozen → archived → removed
       ↓        ↓
    rejected  degraded

每个状态转换都有对应的操作和校验。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from l4_kernel.content_plane import audit_content_plane
from l4_kernel.contracts import ContractError, load_domain_manifest
from l4_kernel.registry import Domain, DomainRegistry
from l4_kernel.signals import SignalBus
from l4_kernel.templates import BootstrapWriteError, init_domain_content_contracts

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
            domain_type=domain_type,  # type: ignore[reportArgumentType]
            path=path,
            bos_uri=bos,
            kems_planes=kems_planes or [],
            governance_tier=governance_tier,
            capabilities=[],
        )

        # DocumentDomain: 创建 KEMS 骨架
        created_files = []
        if domain_type == "document":
            try:
                created_files = init_domain_content_contracts(
                    path,
                    domain_id=domain_id,
                    domain_name=name,
                    owner=owner,
                    domain_type_desc=description or f"{name} 域",
                )
            except BootstrapWriteError as error:
                return {
                    "status": "error",
                    "message": f"Domain '{domain_id}' content-contract publication failed: {error}",
                    "created_files": [],
                    "residual_paths": [str(item) for item in error.residual_paths],
                    "uncertain_paths": [str(item) for item in error.uncertain_paths],
                    "durability_uncertain_paths": [str(item) for item in error.durability_uncertain_paths],
                    "recovery": error.recovery,
                }
            except (ContractError, OSError, ValueError) as error:
                return {"status": "error", "message": f"Domain '{domain_id}' creation refused: {error}", "created_files": []}

        # 注册
        self.registry.register(domain)

        if domain_type != "document":
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

        # DocumentDomain 仅校验正式 manifest 与 content-plane 边界。
        if domain.domain_type == "document":
            manifest_path = domain.path / "DOMAIN.yaml"
            try:
                manifest = load_domain_manifest(manifest_path)
                if manifest.id != domain.id or manifest.root != domain.path.resolve():
                    raise ContractError("L4-CONTRACT-001", "DOMAIN.yaml does not match registry identity", manifest_path)
                if manifest.display_name != domain.name:
                    raise ContractError("L4-CONTRACT-001", "DOMAIN.yaml display_name does not match registry name", manifest_path)
                result["checks"]["domain_manifest"] = "valid"
            except ContractError as error:
                result["status"] = "error"
                result["checks"]["domain_manifest"] = error.message
                return result
            try:
                report = audit_content_plane(domain.path)
            except (OSError, ValueError) as error:
                result["status"] = "error"
                result["checks"]["content_plane"] = str(error)
                return result
            result["checks"]["content_plane_counts"] = report.counts
            result["checks"]["content_plane_violations"] = [item.to_dict() for item in report.violations]
            if not report.ok:
                result["status"] = "error"

        return result

    # ── 冻结/解冻 ──────────────────────────────────────────────────

    def freeze(self, domain_id: str, reason: str = "") -> dict:
        """冻结域 (暂停操作)。"""
        domain = self.registry.get(domain_id)
        if not domain:
            return {"status": "error", "message": f"Domain '{domain_id}' not found"}

        if domain.domain_type == "document":
            return self._document_lifecycle_deprecated(domain_id, "freeze")

        self.signals.emit(domain_id, "⚠️", f"域已冻结: {reason}" if reason else "域已冻结", source="lifecycle.freeze")
        return {"status": "ok", "message": f"Domain '{domain_id}' frozen"}

    def unfreeze(self, domain_id: str) -> dict:
        """解冻域。"""
        domain = self.registry.get(domain_id)
        if not domain:
            return {"status": "error", "message": f"Domain '{domain_id}' not found"}

        if domain.domain_type == "document":
            return self._document_lifecycle_deprecated(domain_id, "unfreeze")

        self.signals.emit(domain_id, "✅", "域已解冻", source="lifecycle.unfreeze")
        return {"status": "ok", "message": f"Domain '{domain_id}' unfrozen"}

    # ── 归档/恢复 ──────────────────────────────────────────────────

    def archive(self, domain_id: str, reason: str = "") -> dict:
        """归档域 (移动到 _archive/ 或标记)。"""
        domain = self.registry.get(domain_id)
        if not domain:
            return {"status": "error", "message": f"Domain '{domain_id}' not found"}

        if domain.domain_type == "document":
            return self._document_lifecycle_deprecated(domain_id, "archive")

        self.signals.emit(domain_id, "ℹ️", f"域已归档: {reason}" if reason else "域已归档", source="lifecycle.archive")
        return {"status": "ok", "message": f"Domain '{domain_id}' archived"}

    def restore(self, domain_id: str) -> dict:
        """恢复已归档域。"""
        domain = self.registry.get(domain_id)
        if not domain:
            return {"status": "error", "message": f"Domain '{domain_id}' not found"}

        if domain.domain_type == "document":
            return self._document_lifecycle_deprecated(domain_id, "restore")

        self.signals.emit(domain_id, "✅", "域已恢复", source="lifecycle.restore")
        return {"status": "ok", "message": f"Domain '{domain_id}' restored"}

    # ── 迁移 ────────────────────────────────────────────────────────

    def migrate(self, domain_id: str, to_version: str = "v5") -> dict:
        """迁移域至 declarative content contracts, preserving the legacy envelope."""
        domain = self.registry.get(domain_id)
        if not domain or domain.domain_type != "document":
            return {"status": "error", "message": "Only DocumentDomain supports migration"}

        changes: list[str] = []

        if to_version == "v5":
            manifest_path = domain.path / "DOMAIN.yaml"
            try:
                manifest = load_domain_manifest(manifest_path)
            except ContractError as error:
                return self._migration_error(domain_id, error.message)
            if manifest.id != domain.id or manifest.root != domain.path.resolve():
                return self._migration_error(domain_id, "DOMAIN.yaml does not match registry identity")
            if manifest.display_name != domain.name:
                return self._migration_error(domain_id, "DOMAIN.yaml display_name does not match registry name")
            try:
                created_files = init_domain_content_contracts(
                    domain.path,
                    domain_id=domain.id,
                    domain_name=manifest.display_name,
                    owner=manifest.principal_ref,
                )
            except BootstrapWriteError as error:
                return self._migration_error(
                    domain_id,
                    str(error),
                    list(error.residual_paths),
                    list(error.uncertain_paths),
                    list(error.durability_uncertain_paths),
                    error.recovery,
                )
            except (ContractError, OSError, ValueError) as error:
                return self._migration_error(domain_id, str(error))
            changes = [f"created content contract: {path.relative_to(domain.path.resolve()).as_posix()}" for path in created_files]

        return {
            "status": "ok",
            "message": f"Domain '{domain_id}' migrated to {to_version}",
            "changes": changes,
            "deprecation": {
                "code": "L4-DEPRECATION-001",
                "message": "KEMS migration now creates declarative content contracts only",
                "replacement": "l4-kernel domain init-content-contracts",
            },
        }

    @staticmethod
    def _document_lifecycle_deprecated(domain_id: str, action: str) -> dict:
        return {
            "status": "deprecated",
            "message": f"DocumentDomain '{domain_id}' {action} is delegated to OMO/Runtime authority",
            "deprecation": {
                "code": "L4-DEPRECATION-001",
                "replacement": "OMO/Runtime authority",
                "authority": "omo",
            },
        }

    @staticmethod
    def _migration_error(
        domain_id: str,
        message: str,
        residual_paths: list[Path] | None = None,
        uncertain_paths: list[Path] | None = None,
        durability_uncertain_paths: list[Path] | None = None,
        recovery: dict | None = None,
    ) -> dict:
        changes = [f"publication residual: {path}" for path in residual_paths or []]
        return {
            "status": "error",
            "message": f"Domain '{domain_id}' migration publication failed: {message}",
            "changes": changes,
            "residual_paths": [str(path) for path in residual_paths or []],
            "uncertain_paths": [str(path) for path in uncertain_paths or []],
            "durability_uncertain_paths": [str(path) for path in durability_uncertain_paths or []],
            "recovery": recovery,
            "deprecation": {
                "code": "L4-DEPRECATION-001",
                "replacement": "l4-kernel domain init-content-contracts",
            },
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
            mgr = LifecycleManager()  # type: ignore[reportOptionalCall]
            summary = mgr.get_stage_summary(domain_id)
            return summary
        except Exception:  # defensive fallback
            return None

    def _get_md_dashboard(self) -> dict | None:
        """从 model-driven 获取生命周期仪表板"""
        if not _MD_AVAILABLE:
            return None
        try:
            mgr = LifecycleManager()  # type: ignore[reportOptionalCall]
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
            mgr = LifecycleManager()  # type: ignore[reportOptionalCall]
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

            mgr = LifecycleManager()  # type: ignore[reportOptionalCall]
            tracker = mgr.get_tracker(domain_id)
            if not tracker:
                tracker = mgr.create_tracker(domain_id, "domain")

            target = LifecycleStage.from_str(target_stage)  # type: ignore[reportOptionalMemberAccess]
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
            pt = PipelineTracker(entity_id=domain_id, entity_type="domain")  # type: ignore[reportOptionalCall]
            pt.start_phase(PipelinePhase.COLD_START)  # type: ignore[reportOptionalMemberAccess]
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

            engine = DerivationEngine()  # type: ignore[reportOptionalCall]
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

            engine = DerivationEngine()  # type: ignore[reportOptionalCall]
            engine.execute_all(nodes)
            return engine.get_summary()
        except Exception:  # defensive fallback
            return None

    def _get_md_pipeline_summary(self) -> dict | None:
        """获取所有域的 Pipeline 汇总"""
        if not _MD_AVAILABLE:
            return None
        try:
            mgr = LifecycleManager()  # type: ignore[reportOptionalCall]
            pipelines = {}
            for entity_id in mgr.list_entities():
                pt = PipelineTracker(entity_id=entity_id)  # type: ignore[reportOptionalCall]
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
