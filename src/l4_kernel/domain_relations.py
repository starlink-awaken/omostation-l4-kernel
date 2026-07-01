"""L4 Domain 关系建模。

定义域之间的关系，支持层次结构、依赖关系等。

使用方式:
    from l4_kernel.domain_relations import DomainRelations

    relations = DomainRelations()
    relations.get_children("work-docs")  # 获取子域
    relations.get_parent("work-weijian")  # 获取父域
    relations.get_dependencies("cockpit")  # 获取依赖域
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from l4_kernel.registry import DomainRegistry


@dataclass
class DomainRelation:
    """域关系定义。"""

    source: str  # 源域 ID
    target: str  # 目标域 ID
    relation_type: Literal["contains", "depends_on", "provides", "uses", "related"]
    description: str = ""


class DomainRelations:
    """域关系管理器。"""

    def __init__(self, registry: DomainRegistry | None = None):
        self.registry = registry or DomainRegistry.require_explicit()
        self._relations: list[DomainRelation] = []
        self._init_default_relations()

    def _init_default_relations(self) -> None:
        """初始化默认关系。"""
        # 层次关系（contains）
        self._relations.extend([
            DomainRelation("work-docs", "work-weijian", "contains", "@工作文档 包含 卫健委"),
            DomainRelation("work-docs", "work-guozhuan", "contains", "@工作文档 包含 国转中心"),
        ])

        # 依赖关系（depends_on）
        self._relations.extend([
            DomainRelation("cockpit", "vault", "depends_on", "@驾驶舱 依赖 @学习进化 的知识"),
            DomainRelation("cockpit", "omo-governance", "depends_on", "@驾驶舱 依赖 OMO 治理数据"),
            DomainRelation("cockpit", "ecos-workbench", "depends_on", "@驾驶舱 依赖 eCOS 工作台"),
            DomainRelation("metaos", "agora", "depends_on", "MetaOS 依赖 Agora 路由"),
            DomainRelation("metaos", "l4-kernel", "depends_on", "MetaOS 依赖 L4 Kernel 域管理"),
            DomainRelation("runtime", "agora", "depends_on", "Runtime 依赖 Agora 路由"),
            DomainRelation("runtime", "omo-governance", "depends_on", "Runtime 依赖 OMO 治理"),
        ])

        # 提供关系（provides）
        self._relations.extend([
            DomainRelation("vault", "cockpit", "provides", "@学习进化 提供知识给 @驾驶舱"),
            DomainRelation("omo-governance", "cockpit", "provides", "OMO 提供治理数据给 @驾驶舱"),
            DomainRelation("ecos-workbench", "cockpit", "provides", "eCOS 提供工作台给 @驾驶舱"),
            DomainRelation("agora", "metaos", "provides", "Agora 提供路由给 MetaOS"),
            DomainRelation("l4-kernel", "metaos", "provides", "L4 Kernel 提供域管理给 MetaOS"),
            DomainRelation("agora", "runtime", "provides", "Agora 提供路由给 Runtime"),
            DomainRelation("omo-governance", "runtime", "provides", "OMO 提供治理给 Runtime"),
        ])

        # 使用关系（uses）
        self._relations.extend([
            DomainRelation("creative", "vault", "uses", "@创意创作 使用 @学习进化 的知识"),
            DomainRelation("personal", "vault", "uses", "@个人 使用 @学习进化 的知识"),
            DomainRelation("family", "vault", "uses", "@家庭生活 使用 @学习进化 的知识"),
            DomainRelation("work-weijian", "vault", "uses", "卫健委 使用 @学习进化 的知识"),
            DomainRelation("work-guozhuan", "vault", "uses", "国转中心 使用 @学习进化 的知识"),
        ])

        # 相关关系（related）
        self._relations.extend([
            DomainRelation("family", "family-shared", "related", "@家庭生活 与 FamilyShared 相关"),
            DomainRelation("ai-config", "agents-config", "related", "AI 配置 与 Agent 配置 相关"),
            DomainRelation("model-volume", "sharedmodel", "related", "Model 与 SharedModel 相关"),
        ])

    def add_relation(self, relation: DomainRelation) -> None:
        """添加关系。"""
        self._relations.append(relation)

    def get_relations(
        self,
        source: str | None = None,
        target: str | None = None,
        relation_type: str | None = None,
    ) -> list[DomainRelation]:
        """获取关系列表。"""
        result = self._relations

        if source:
            result = [r for r in result if r.source == source]
        if target:
            result = [r for r in result if r.target == target]
        if relation_type:
            result = [r for r in result if r.relation_type == relation_type]

        return result

    def get_children(self, domain_id: str) -> list[str]:
        """获取子域列表。"""
        return [r.target for r in self._relations
                if r.source == domain_id and r.relation_type == "contains"]

    def get_parent(self, domain_id: str) -> str | None:
        """获取父域。"""
        for r in self._relations:
            if r.target == domain_id and r.relation_type == "contains":
                return r.source
        return None

    def get_dependencies(self, domain_id: str) -> list[str]:
        """获取依赖域列表。"""
        return [r.target for r in self._relations
                if r.source == domain_id and r.relation_type == "depends_on"]

    def get_dependents(self, domain_id: str) -> list[str]:
        """获取依赖于当前域的域列表。"""
        return [r.source for r in self._relations
                if r.target == domain_id and r.relation_type == "depends_on"]

    def get_providers(self, domain_id: str) -> list[str]:
        """获取提供者列表。"""
        return [r.source for r in self._relations
                if r.target == domain_id and r.relation_type == "provides"]

    def get_consumers(self, domain_id: str) -> list[str]:
        """获取消费者列表。"""
        return [r.target for r in self._relations
                if r.source == domain_id and r.relation_type == "provides"]

    def get_related(self, domain_id: str) -> list[str]:
        """获取相关域列表。"""
        related = set()
        for r in self._relations:
            if r.relation_type == "related":
                if r.source == domain_id:
                    related.add(r.target)
                elif r.target == domain_id:
                    related.add(r.source)
        return list(related)

    def get_relation_graph(self) -> dict:
        """获取关系图。"""
        graph = {}

        for domain in self.registry.list_all():
            domain_id = domain.id
            graph[domain_id] = {
                "children": self.get_children(domain_id),
                "parent": self.get_parent(domain_id),
                "dependencies": self.get_dependencies(domain_id),
                "dependents": self.get_dependents(domain_id),
                "providers": self.get_providers(domain_id),
                "consumers": self.get_consumers(domain_id),
                "related": self.get_related(domain_id),
            }

        return graph

    def to_dict(self) -> list[dict]:
        """序列化为 dict 列表。"""
        return [
            {
                "source": r.source,
                "target": r.target,
                "relation_type": r.relation_type,
                "description": r.description,
            }
            for r in self._relations
        ]
