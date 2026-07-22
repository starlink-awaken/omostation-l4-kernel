"""L4 Domain Registry — 28域统一注册表。

SSOT: ~/Documents/@驾驶舱/_control/DOMAIN-INDEX.md (如果不存在则使用硬编码默认值)
与 L0 MOF M1 domain/DOMAIN-*.yaml 互补: Registry 管理文件系统路径, MOF 管理语义模型。

P52 治本: Domain.path 来源 (3 层优先级)
    1. DomainRegistry(path_overrides={...}) 显式注入 (单测/生产程序化)
    2. 环境变量 L4_<DOMAIN_ID>_PATH (CI/容器/部署配置)
    3. _BUILTIN_DOMAINS 默认 (Path.home() / "Documents" / "@...")

设计原则: path 是运行时环境信息,不是领域语义。
  → 领域语义 (id/name/bos_uri) 来自 L0 MOF,运行时部署路径走 env。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

# ── 域类型枚举 ──────────────────────────────────────────────────────
DomainType = Literal["document", "config", "engine", "tool", "workspace", "storage", "model"]


@dataclass
class Domain:
    """L4 域元数据。"""

    id: str  # "vault", "personal", "cockpit", ...
    name: str  # "@学习进化", "@个人", ...
    domain_type: DomainType
    path: Path  # 文件系统绝对路径
    bos_uri: str  # "bos://vault/**"
    kems_planes: list[str] = field(default_factory=list)  # DocumentDomain 专用
    governance_tier: int = 3  # 1=核心, 2=工作, 3=可选
    capabilities: list[str] = field(default_factory=list)

    def exists(self) -> bool:
        return self.path.is_dir()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.domain_type,
            "path": str(self.path),
            "bos_uri": self.bos_uri,
            "kems_planes": self.kems_planes,
            "governance_tier": self.governance_tier,
            "exists": self.exists(),
        }


# ── 内置 28 域默认注册表 (SSOT 回退) ──────────────────────────────
# ⚠️ 新增域需同时更新三处:
#  1. 此处 _BUILTIN_DOMAINS (l4-kernel 注册表)
#  2. DOMAIN-INDEX.md (L4 域注册表)
#  3. agora POC_SERVICES (BOS 路由)
# 测试: tests/test_registry.py (动态断言自动适配)
# 来源: CLAUDE_COWORK_GLOBAL.md v6.0 + L0 MOF M1 domain/DOMAIN-*.yaml
# 2026-06-10 更新: 新增 opc/family-shared 域, ID 对齐 DOMAIN-INDEX
# 2026-07-02 更新: 移除 family-shared (2026-07-01 已物理并入 family 域, 28→27, 对齐 DOMAIN-INDEX v4.6)
_BUILTIN_DOMAINS: list[Domain] = [
    # ── DocumentDomain (9域) ──
    Domain(
        id="cockpit",
        name="@驾驶舱",
        domain_type="document",
        path=Path.home() / "Documents" / "@驾驶舱",
        bos_uri="bos://cockpit/**",
        kems_planes=["_control", "_knowledge", "_runtime", "_generated", "_meta", "_archive"],
        governance_tier=1,
        capabilities=["knowledge.read", "knowledge.search", "cards.manage", "governance.read", "governance.audit", "signal.emit"],
    ),
    Domain(
        id="vault",
        name="@学习进化",
        domain_type="document",
        path=Path.home() / "Documents" / "@学习进化",
        bos_uri="bos://vault/**",
        kems_planes=["_control", "_entities", "_knowledge", "_storage", "_archive"],
        governance_tier=1,
        capabilities=["knowledge.read", "knowledge.search", "knowledge.archive", "knowledge.create", "knowledge.update", "knowledge.delete"],
    ),
    Domain(
        id="creative",
        name="@创意创作",
        domain_type="document",
        path=Path.home() / "Documents" / "@创意创作",
        bos_uri="bos://creative/**",
        kems_planes=["_control", "_entities", "_knowledge", "_storage", "_archive"],
        governance_tier=1,
        capabilities=["knowledge.read", "knowledge.search", "creative.create", "creative.publish", "creative.archive"],
    ),
    Domain(
        id="personal",
        name="@个人",
        domain_type="document",
        path=Path.home() / "Documents" / "@个人",
        bos_uri="bos://personal/**",
        kems_planes=["_control", "_entities", "_knowledge", "_storage", "_archive"],
        governance_tier=1,
        capabilities=["knowledge.read", "knowledge.search", "personal.read", "personal.write", "personal.search"],
    ),
    Domain(
        id="shared",
        name="@公共",
        domain_type="document",
        path=Path.home() / "Documents" / "@公共",
        bos_uri="bos://shared/**",
        kems_planes=["_control", "_entities", "_knowledge", "_runtime"],
        governance_tier=2,
        capabilities=["knowledge.read", "knowledge.search", "entity.resolve", "shared.read", "shared.write", "shared.search"],
    ),
    Domain(
        id="family",
        name="@家庭生活",
        domain_type="document",
        path=Path.home() / "Documents" / "@家庭生活",
        bos_uri="bos://family/**",
        kems_planes=["_control", "_knowledge", "_storage"],
        governance_tier=2,
        capabilities=["knowledge.read", "task.track", "family.read", "family.write", "family.search"],
    ),
    Domain(
        id="work-weijian",
        name="@工作文档/卫健委",
        domain_type="document",
        path=Path.home() / "Documents" / "@工作文档" / "卫健委",
        bos_uri="bos://work-weijian/**",
        kems_planes=["_control", "_entities", "_knowledge", "_storage", "_archive", "_runtime"],
        governance_tier=1,
        capabilities=["knowledge.read", "document.generate", "task.manage", "document.read", "document.write", "document.search"],
    ),
    Domain(
        id="work-guozhuan",
        name="@工作文档/国转中心",
        domain_type="document",
        path=Path.home() / "Documents" / "@工作文档" / "国转中心",
        bos_uri="bos://work-guozhuan/**",
        kems_planes=["_control", "_entities", "_knowledge", "_storage", "_archive", "_runtime"],
        governance_tier=1,
        capabilities=["knowledge.read", "research.run", "task.manage", "document.read", "document.write", "document.search"],
    ),
    Domain(
        id="work-liyongke",
        name="@工作文档/规自委",
        domain_type="document",
        path=Path.home() / "Documents" / "@工作文档" / "规自委",
        bos_uri="bos://work-liyongke/**",
        kems_planes=["_control", "_entities", "_knowledge", "_storage", "_meta"],
        governance_tier=1,
        capabilities=["knowledge.read", "knowledge.search", "document.read", "document.write", "task.track"],
    ),
    # ── @工作文档 聚合域 (L0 MOF: DOMAIN-work-docs) ──
    Domain(
        id="work-docs",
        name="@工作文档",
        domain_type="document",
        path=Path.home() / "Documents" / "@工作文档",
        bos_uri="bos://work-docs/**",
        kems_planes=["_control", "_entities", "_knowledge", "_storage"],
        governance_tier=1,
        capabilities=["domain.route", "knowledge.read", "knowledge.search", "document.read", "document.write", "document.search"],
    ),
    # ── ConfigDomain (3域) ──
    Domain(
        id="ai-config",
        name="~/.ai",
        domain_type="config",
        path=Path.home() / ".ai",
        bos_uri="bos://ai-config/**",
        governance_tier=2,
        capabilities=["config.read", "config.write", "config.validate", "config.backup"],
    ),
    Domain(
        id="agents-config",
        name="~/.agents",
        domain_type="config",
        path=Path.home() / ".agents",
        bos_uri="bos://agents-config/**",
        governance_tier=2,
        capabilities=["config.read", "config.write", "config.validate", "config.backup"],
    ),
    Domain(
        id="icloud-sharedconf",
        name="SharedConf",
        domain_type="config",
        path=Path.home() / "SharedConf",
        bos_uri="bos://icloud-sharedconf/**",
        governance_tier=3,
        capabilities=["config.read", "config.validate"],
    ),
    # ── ToolDomain (2域) ──
    Domain(
        id="bin",
        name="~/bin",
        domain_type="tool",
        path=Path.home() / "bin",
        bos_uri="bos://bin/**",
        governance_tier=2,
        capabilities=["tool.execute", "tool.list", "tool.install", "tool.uninstall", "tool.update"],
    ),
    Domain(
        id="toolbox-tools",
        name="~/ToolBox",
        domain_type="tool",
        path=Path.home() / "ToolBox",
        bos_uri="bos://toolbox-tools/**",
        governance_tier=2,
        capabilities=["tool.execute", "tool.list", "tool.install", "tool.uninstall", "tool.update"],
    ),
    # ── WorkspaceDomain (5域) ──
    Domain(
        id="sharedwork",
        name="SharedWork",
        domain_type="workspace",
        path=Path("/Users") / "SharedWork",
        bos_uri="bos://sharedwork/**",
        governance_tier=3,
        capabilities=["workspace.read", "workspace.write", "workspace.create", "workspace.delete", "workspace.archive"],
    ),
    # ── StorageDomain (1域) ──
    Domain(
        id="shareddisk",
        name="SharedDisk",
        domain_type="storage",
        path=Path("/Volumes") / "SharedDisk",
        bos_uri="bos://shareddisk/**",
        governance_tier=3,
        capabilities=["storage.read", "storage.write", "storage.create", "storage.delete", "storage.archive"],
    ),
    # ── ModelDomain (2域) ──
    Domain(
        id="model-volume",
        name="Model",
        domain_type="model",
        path=Path("/Volumes") / "Model",
        bos_uri="bos://model-volume/**",
        governance_tier=3,
        capabilities=["model.read", "model.list", "model.create", "model.delete", "model.archive"],
    ),
    Domain(
        id="sharedmodel",
        name="SharedModel",
        domain_type="model",
        path=Path("/Volumes") / "SharedModel",
        bos_uri="bos://sharedmodel/**",
        governance_tier=3,
        capabilities=["model.read", "model.list", "model.create", "model.delete", "model.archive"],
    ),
    # ── EngineDomain (3域) ──
    Domain(
        id="minerva",
        name="Minerva 引擎",
        domain_type="engine",
        path=Path.home() / "minerva",
        bos_uri="bos://minerva/**",
        governance_tier=2,
        capabilities=["engine.start", "engine.stop", "engine.status", "engine.restart", "engine.config", "engine.log"],
    ),
    Domain(
        id="knowledge-engine",
        name="Knowledge 引擎",
        domain_type="engine",
        path=Path.home() / "knowledge",
        bos_uri="bos://knowledge-engine/**",
        governance_tier=2,
        capabilities=["engine.start", "engine.stop", "engine.status", "engine.restart", "engine.config", "engine.log"],
    ),
    # ── Obsidian Vault (DocumentDomain) ──
    Domain(
        id="obsidian-vault",
        name="Obsidian Vault",
        domain_type="document",
        path=Path.home() / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents",
        bos_uri="bos://obsidian-vault/**",
        kems_planes=["_control", "_entities", "_knowledge", "_storage", "_archive"],
        governance_tier=3,
        capabilities=["knowledge.read", "knowledge.search", "knowledge.create", "knowledge.update", "knowledge.delete"],
    ),
    # ── OPC (DocumentDomain, 新增 2026-06-10, 2026-06-13 P5-P7 self-correction 扩展) ──
    Domain(
        id="opc",
        name="@OPC",
        domain_type="document",
        path=Path.home() / "Documents" / "@OPC",
        bos_uri="bos://opc/**",
        kems_planes=["_control", "_entities", "_knowledge", "_storage"],
        governance_tier=1,
        capabilities=[
            "knowledge.read",
            "knowledge.search",
            # 2026-06-13 OPC P5-P7 self-correction 闭环后新增:
            "cadence.cron_wrapper",  # 注入 INVOCATION_ID+OPC_TRIGGER
            "cadence.fcntl_flock",  # 互斥写 *.index.json
            "cadence.opc_mode_env",  # OPC_MODE 透传
            "cadence.semantic_time_env",  # OPC_GENERATED_AT/OPC_TODAY 覆盖
            "drift.self_evolve_planned_only",  # self-evolution 任务仅落 planned/ + approval_required=true
            "audit.5repos_section17",  # .omo/_delivery/audit-rollout/{date}-5repos.json
            "audit.8_field_review_template",  # .omo/standards/opc-review-template.md
            # 2026-06-23 P60 治理方法论内化 — 6 个 governance capability:
            "gov.frontmatter_audit",  # omo lint doc-lifecycle → frontmatter 覆盖率 ≥ 95%
            "gov.drift_monitor",  # bin/mof-drift → LOW 维度 ≤ 5
            "gov.commit_closure",  # git status --short | wc -l → 工作树累积 ≤ 50
            "gov.dimension_saturation",  # linter 维度 ≥ 15 时强制用 bin 工具
            "gov.adr_index_integrity",  # omo audit → ADR INDEX 无 UNLISTED
            "gov.rise_cycle",  # RISE 循环 (R+I+S+E+C) governance-phase-orchestrator
        ],
    ),
    # ── L4 Kernel (EngineDomain) ──
    Domain(
        id="l4-kernel",
        name="L4 Kernel",
        domain_type="engine",
        path=Path.home() / "Workspace" / "projects" / "l4-kernel",
        bos_uri="bos://l4-kernel/**",
        governance_tier=1,
        capabilities=["domain.register", "domain.health", "domain.validate"],
    ),
    # ── eCOS Workbench (WorkspaceDomain) ──
    Domain(
        id="ecos-workbench",
        name="eCOS Workbench",
        domain_type="workspace",
        path=Path.home() / "Workspace",
        bos_uri="bos://ecos/**",
        governance_tier=1,
        capabilities=["workspace.read", "workspace.write", "workspace.search"],
    ),
    # ── OMO Governance (WorkspaceDomain) ──
    Domain(
        id="omo-governance",
        name="OMO Governance",
        domain_type="workspace",
        path=Path.home() / "Workspace" / ".omo",
        bos_uri="bos://omo-governance/**",
        governance_tier=1,
        capabilities=["governance.read", "governance.write", "governance.audit"],
    ),
    # ── Spaces (WorkspaceDomain) ──
    Domain(
        id="spaces",
        name="Spaces",
        domain_type="workspace",
        path=Path.home() / "Workspace" / "spaces",
        bos_uri="bos://spaces/**",
        governance_tier=1,
        capabilities=["space.read", "space.write", "space.admission"],
    ),
    # ── Runtime Data (WorkspaceDomain) ──
    Domain(
        id="runtime",
        name="Runtime Data",
        domain_type="workspace",
        path=Path.home() / "runtime",
        bos_uri="bos://runtime/**",
        governance_tier=1,
        capabilities=["runtime.read", "runtime.write", "runtime.log"],
    ),
]


class DomainRegistry:
    """L4 28 域统一注册表。

    内置默认注册表基于 CLAUDE_COWORK_GLOBAL.md v6.0。

    P52-final 真治本: path 解析
        - 必须显式提供 path_overrides, 缺失抛 ValueError (无默认, 无 env 兜底)
        - 错误前提 Path.home() / "Documents" / "@..." 完全删除
        - 生产入口: l4_kernel.cli.load_overrides_from_config()
        - 测试入口: l4_kernel.testing.default_overrides(tmp_path)

    P52 渐进 (已废弃, 保留 import 兼容):
        - 之前支持 env L4_<ID>_PATH, 已被显式 overrides 取代
        - 之前有 _BUILTIN_DOMAINS 默认, 已被删除 (本类无内部默认)
    """

    def __init__(
        self,
        *,
        path_overrides: dict[str, Path],
    ) -> None:
        if not path_overrides:
            raise ValueError(
                "DomainRegistry requires explicit path_overrides. "
                "Use l4_kernel.cli.load_overrides_from_config() for production, "
                "or l4_kernel.testing.default_overrides(tmp_path) for tests. "
                "P52-final: removed Path.home() default + env fallback."
            )
        self._domains: dict[str, Domain] = {}
        builtin_ids = {d.id for d in _BUILTIN_DOMAINS}
        for d in _BUILTIN_DOMAINS:
            if d.id not in path_overrides:
                raise ValueError(
                    f"Domain {d.id!r} missing from path_overrides. "
                    f"Required keys: {sorted(builtin_ids)}"
                )
            d = replace(d, path=path_overrides[d.id])
            self._domains[d.id] = d

    @staticmethod
    def require_explicit() -> DomainRegistry:
        """失败助手: 用于 class 构造中的 `or DomainRegistry()` 模式。

        P52-final: 没有默认值, 此函数总是抛 RuntimeError, 强制调用方传 registry。
        """
        raise RuntimeError(
            "DomainRegistry requires explicit path_overrides. "
            "P52-final: removed implicit Path.home() default + env fallback. "
            "Pass DomainRegistry(path_overrides=...) explicitly, or use "
            "l4_kernel.testing.default_overrides(tmp_path) for tests."
        )

    # ── 查询 ────────────────────────────────────────────────────────

    def get(self, domain_id: str) -> Domain | None:
        """按 ID 获取域。"""
        return self._domains.get(domain_id)

    def list_all(self) -> list[Domain]:
        """列出所有 28 域。"""
        return list(self._domains.values())

    def list_by_type(self, domain_type: DomainType) -> list[Domain]:
        """按类型筛选。"""
        return [d for d in self._domains.values() if d.domain_type == domain_type]

    def list_document_domains(self) -> list[Domain]:
        """仅 DocumentDomain (有 KEMS 六面的域)。"""
        return self.list_by_type("document")

    # ── 路径解析 (消除硬编码) ───────────────────────────────────────

    def resolve_path(self, domain_id: str) -> Path | None:
        """解析域的文件系统路径。"""
        d = self.get(domain_id)
        return d.path if d else None

    def resolve_bos_uri(self, domain_id: str) -> str | None:
        """解析域的 BOS URI。"""
        d = self.get(domain_id)
        return d.bos_uri if d else None

    # ── 注册 ────────────────────────────────────────────────────────

    def register(self, domain: Domain) -> None:
        """注册或更新一个域。"""
        self._domains[domain.id] = domain

    def unregister(self, domain_id: str) -> bool:
        """移除一个域。返回是否成功。"""
        return self._domains.pop(domain_id, None) is not None

    # ── 健康 ────────────────────────────────────────────────────────

    def health_check(self, domain_id: str) -> dict:
        """检查单个域的磁盘存在性。"""
        d = self.get(domain_id)
        if not d:
            return {"id": domain_id, "status": "not_registered", "exists": False}
        return {
            "id": domain_id,
            "name": d.name,
            "type": d.domain_type,
            "status": "ok" if d.exists() else "missing",
            "exists": d.exists(),
            "path": str(d.path),
        }

    def aggregate_health(self) -> dict:
        """全域健康聚合。"""
        all_domains = self.list_all()
        existing = sum(1 for d in all_domains if d.exists())
        total = len(all_domains)
        return {
            "total": total,
            "existing": existing,
            "missing": total - existing,
            "health_rate": f"{existing / max(total, 1) * 100:.1f}%",
            "by_type": {
                t: {
                    "total": len(self.list_by_type(t)),
                    "existing": sum(1 for d in self.list_by_type(t) if d.exists()),
                    "missing": len(self.list_by_type(t)) - sum(1 for d in self.list_by_type(t) if d.exists()),
                }
                for t in ("document", "config", "engine", "tool", "workspace", "storage", "model")
            },
        }

    def to_dict(self) -> dict:
        """序列化为 dict (用于 JSON/MCP 输出)。"""
        return {
            "domains": [d.to_dict() for d in self.list_all()],
            "health": self.aggregate_health(),
        }
