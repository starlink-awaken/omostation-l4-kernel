"""L4 Domain Registry — 19域统一注册表。

SSOT: ~/Documents/驾驶舱/CARDS/DOMAIN-INDEX.md (如果不存在则使用硬编码默认值)
与 L0 MOF M1 domain/DOMAIN-*.yaml 互补: Registry 管理文件系统路径, MOF 管理语义模型。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# ── 域类型枚举 ──────────────────────────────────────────────────────
DomainType = Literal[
    "document", "config", "engine", "tool", "workspace", "storage", "model"
]


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


# ── 内置 20 域默认注册表 (SSOT 回退) ──────────────────────────────
# 来源: CLAUDE_COWORK_GLOBAL.md v6.0 + L0 MOF M1 domain/DOMAIN-*.yaml
# 2026-06-09 更新: 新增 creative 域, vault 描述修正
_BUILTIN_DOMAINS: list[Domain] = [
    # ── DocumentDomain (8域) ──
    Domain(
        id="cockpit", name="@驾驶舱", domain_type="document",
        path=Path.home() / "Documents" / "@驾驶舱",
        bos_uri="bos://cockpit/**",
        kems_planes=["_control", "_knowledge", "_runtime", "_generated", "_meta", "_archive"],
        governance_tier=1,
        capabilities=["knowledge.read", "knowledge.search", "cards.manage"],
    ),
    Domain(
        id="vault", name="@学习进化", domain_type="document",
        path=Path.home() / "Documents" / "@学习进化",
        bos_uri="bos://vault/**",
        kems_planes=["_control", "_entities", "_knowledge", "_storage", "_archive"],
        governance_tier=1,
        capabilities=["knowledge.read", "knowledge.search", "knowledge.archive"],
    ),
    Domain(
        id="creative", name="@创意创作", domain_type="document",
        path=Path.home() / "Documents" / "@创意创作",
        bos_uri="bos://creative/**",
        kems_planes=["_control", "_entities", "_knowledge", "_storage", "_archive"],
        governance_tier=1,
        capabilities=["knowledge.read", "knowledge.search"],
    ),
    Domain(
        id="personal", name="@个人", domain_type="document",
        path=Path.home() / "Documents" / "@个人",
        bos_uri="bos://personal/**",
        kems_planes=["_control", "_entities", "_knowledge", "_storage", "_archive"],
        governance_tier=1,
        capabilities=["knowledge.read", "knowledge.search"],
    ),
    Domain(
        id="shared", name="@公共", domain_type="document",
        path=Path.home() / "Documents" / "@公共",
        bos_uri="bos://shared/**",
        kems_planes=["_control", "_entities", "_knowledge", "_runtime"],
        governance_tier=2,
    ),
    Domain(
        id="family", name="@家庭生活", domain_type="document",
        path=Path.home() / "Documents" / "@家庭生活",
        bos_uri="bos://family/**",
        kems_planes=["_control", "_knowledge", "_storage"],
        governance_tier=2,
    ),
    Domain(
        id="work-weijian", name="@工作文档/卫健委", domain_type="document",
        path=Path.home() / "Documents" / "@工作文档" / "卫健委",
        bos_uri="bos://work-weijian/**",
        kems_planes=["_control", "_entities", "_knowledge", "_storage", "_archive", "_runtime"],
        governance_tier=2,
    ),
    Domain(
        id="work-guozhuan", name="@工作文档/国转中心", domain_type="document",
        path=Path.home() / "Documents" / "@工作文档" / "国转中心",
        bos_uri="bos://work-guozhuan/**",
        kems_planes=["_control", "_entities", "_knowledge", "_storage", "_archive", "_runtime"],
        governance_tier=2,
    ),
    # ── ConfigDomain (3域) ──
    Domain(
        id="ai-config", name="~/.ai", domain_type="config",
        path=Path.home() / ".ai",
        bos_uri="bos://ai-config/**",
    ),
    Domain(
        id="agents-config", name="~/.agents", domain_type="config",
        path=Path.home() / ".agents",
        bos_uri="bos://agents-config/**",
    ),
    Domain(
        id="icloud-sharedconf", name="SharedConf", domain_type="config",
        path=Path.home() / "SharedConf",
        bos_uri="bos://icloud-sharedconf/**",
    ),
    # ── ToolDomain (2域) ──
    Domain(
        id="bin", name="~/bin", domain_type="tool",
        path=Path.home() / "bin",
        bos_uri="bos://bin/**",
    ),
    Domain(
        id="toolbox", name="~/ToolBox", domain_type="tool",
        path=Path.home() / "ToolBox",
        bos_uri="bos://toolbox/**",
    ),
    # ── WorkspaceDomain (1域) ──
    Domain(
        id="sharedwork", name="SharedWork", domain_type="workspace",
        path=Path("/Users") / "SharedWork",
        bos_uri="bos://sharedwork/**",
    ),
    # ── StorageDomain (1域) ──
    Domain(
        id="shareddisk", name="SharedDisk", domain_type="storage",
        path=Path("/Volumes") / "SharedDisk",
        bos_uri="bos://shareddisk/**",
    ),
    # ── ModelDomain (2域) ──
    Domain(
        id="model-volume", name="Model", domain_type="model",
        path=Path("/Volumes") / "Model",
        bos_uri="bos://model-volume/**",
    ),
    Domain(
        id="sharedmodel", name="SharedModel", domain_type="model",
        path=Path("/Volumes") / "SharedModel",
        bos_uri="bos://sharedmodel/**",
    ),
    # ── EngineDomain (2域) ──
    Domain(
        id="minerva", name="Minerva 引擎", domain_type="engine",
        path=Path.home() / "minerva",
        bos_uri="bos://minerva/**",
    ),
    Domain(
        id="knowledge", name="Knowledge 引擎", domain_type="engine",
        path=Path.home() / "knowledge",
        bos_uri="bos://knowledge/**",
    ),
    # ── Obsidian Vault (DocumentDomain) ──
    Domain(
        id="obsidian-vault", name="Obsidian Vault", domain_type="document",
        path=Path.home() / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents",
        bos_uri="bos://obsidian-vault/**",
        kems_planes=["_control", "_entities", "_knowledge", "_storage", "_archive"],
        governance_tier=3,
    ),
    # ── L4 Kernel (EngineDomain) ──
    Domain(
        id="l4-kernel", name="L4 Kernel", domain_type="engine",
        path=Path.home() / "Workspace" / "projects" / "l4-kernel",
        bos_uri="bos://l4-kernel/**",
        governance_tier=1,
    ),
    # ── eCOS Workbench (WorkspaceDomain) ──
    Domain(
        id="ecos-workbench", name="eCOS Workbench", domain_type="workspace",
        path=Path.home() / "Workspace",
        bos_uri="bos://ecos/**",
        governance_tier=1,
    ),
]


class DomainRegistry:
    """L4 21 域统一注册表。

    内置默认注册表基于 CLAUDE_COWORK_GLOBAL.md v6.0。
    可通过 load_from_index() 从 DOMAIN-INDEX.md 加载覆盖。
    """

    def __init__(self) -> None:
        self._domains: dict[str, Domain] = {}
        for d in _BUILTIN_DOMAINS:
            self._domains[d.id] = d

    # ── 查询 ────────────────────────────────────────────────────────

    def get(self, domain_id: str) -> Domain | None:
        """按 ID 获取域。"""
        return self._domains.get(domain_id)

    def list_all(self) -> list[Domain]:
        """列出所有 19 域。"""
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
