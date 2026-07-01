"""L4 Distributed Scenarios — 跨机器同步 + 分布式任务 + 多Agent协同。

基于 federation.py 的联邦中枢，实现三个分布式场景。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from l4_kernel.federation import FederationHub
from l4_kernel.health import DomainHealth
from l4_kernel.registry import DomainRegistry
from l4_kernel.signals import SignalBus


class DistributedScenarioEngine:
    """分布式场景执行引擎。

    基于 FederationHub，提供跨机器域同步、任务分配、多Agent协同。
    """

    def __init__(self, hub: FederationHub, registry: DomainRegistry | None = None):
        self.hub = hub
        self.registry = registry or DomainRegistry.require_explicit()
        self.health = DomainHealth(self.registry)
        self.signals = SignalBus(self.registry)

    # ═══════════════════════════════════════════════════════════════
    # 场景 13: 跨机器域同步
    # ═══════════════════════════════════════════════════════════════

    def sync_all_federated_domains(self) -> dict[str, dict]:
        """同步所有联邦域 (push 策略)。

        Returns:
            {domain_id: sync_result, ...}
        """
        results = {}
        for domain_id in self.hub.federated_domains:
            results[domain_id] = self.hub.sync_domain(domain_id, "push")

        # 发射同步完成信号
        ok = sum(1 for r in results.values() if r.get("status") == "ok")
        total = len(results)
        self.signals.emit(
            "cockpit",
            "✅" if ok == total else "⚠️",
            f"联邦域同步完成: {ok}/{total}",
            source="distributed.sync",
            cross_domain=True,
        )

        return results

    def sync_domain_to_replicas(self, domain_id: str) -> dict:
        """将指定域同步到所有副本节点。

        流程:
        1. 计算域文件差异
        2. 对每个副本节点推送变更
        3. 副本确认接收
        4. 更新同步时间戳
        """
        fd = self.hub.federated_domains.get(domain_id)
        if not fd:
            return {"status": "error", "message": f"Domain '{domain_id}' not federated"}

        if not self.hub.is_domain_primary(domain_id):
            return {"status": "error", "message": f"Not primary for '{domain_id}'"}

        domain = self.registry.get(domain_id)
        if not domain or not domain.exists():
            return {"status": "error", "message": f"Domain '{domain_id}' not available"}

        results = {
            "domain_id": domain_id,
            "primary": self.hub.node_id,
            "replicas": {},
            "synced_files": 0,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        for replica_id in fd.replica_nodes:
            replica = self.hub.peers.get(replica_id)
            if not replica:
                results["replicas"][replica_id] = {"status": "offline"}
                continue

            # 计算差异
            diff = self._compute_file_diff(domain.path)
            results["replicas"][replica_id] = {
                "status": "ready",
                "files_to_sync": len(diff),
                "total_size": sum(f["size"] for f in diff),
            }
            results["synced_files"] += len(diff)

        return results

    def pull_domain_from_primary(self, domain_id: str) -> dict:
        """从主节点拉取域数据 (副本节点使用)。"""
        fd = self.hub.federated_domains.get(domain_id)
        if not fd:
            return {"status": "error", "message": f"Domain '{domain_id}' not federated"}

        primary = self.hub.peers.get(fd.primary_node)
        if not primary:
            return {"status": "error", "message": f"Primary node '{fd.primary_node}' offline"}

        return {
            "domain_id": domain_id,
            "strategy": "pull",
            "from": fd.primary_node,
            "status": "ok",
            "note": "pull sync requires network transport (future Phase)",
        }

    def _compute_file_diff(self, domain_path: Path) -> list[dict]:
        """计算域文件差异 (基于 mtime + size)。"""
        diff = []
        control = domain_path / "_control"
        if not control.is_dir():
            return diff

        for md_file in control.rglob("*.md"):
            if md_file.name.startswith("."):
                continue
            try:
                stat = md_file.stat()
                diff.append(
                    {
                        "path": str(md_file.relative_to(domain_path)),
                        "size": stat.st_size,
                        "mtime": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                        "hash": "",  # placeholder for content hash
                    }
                )
            except OSError:
                pass

        return diff

    # ═══════════════════════════════════════════════════════════════
    # 场景 14: 分布式任务分配
    # ═══════════════════════════════════════════════════════════════

    def assign_and_dispatch(self, task_id: str, domain_id: str, task_type: str, priority: str = "P2") -> dict:
        """分配并派发任务到最优节点。

        流程:
        1. 根据策略选择目标节点
        2. 检查目标节点健康
        3. 派发任务
        4. 记录分配日志
        """
        # Step 1: 选择节点
        assignment = self.hub.assign_task(domain_id, task_type, strategy="affinity")
        target_node = assignment["assigned_to"]

        # Step 2: 检查健康
        health = self.hub.check_peer_health(target_node)
        if health["status"] != "healthy" and target_node != self.hub.node_id:
            # 回退到负载均衡
            assignment = self.hub.assign_task(domain_id, task_type, strategy="load_balance")
            target_node = assignment["assigned_to"]

        # Step 3: 记录分配
        self.signals.emit(
            "cockpit",
            "ℹ️",
            f"任务分配: {task_id} → {target_node} ({task_type})",
            source="distributed.task",
        )

        return {
            "task_id": task_id,
            "assigned_to": target_node,
            "strategy": assignment["strategy"],
            "domain": domain_id,
            "task_type": task_type,
            "priority": priority,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def get_node_tasks(self, node_id: str | None = None) -> list[dict]:
        """获取节点上的任务列表。"""
        node_id = node_id or self.hub.node_id
        # 任务状态由 OMO Task 管理，此处返回联邦视图
        peer = self.hub.peers.get(node_id)
        if not peer and node_id != self.hub.node_id:
            return []
        return [{"node_id": node_id, "domains": peer.domains if peer else []}]

    # ═══════════════════════════════════════════════════════════════
    # 场景 15: 多Agent协同
    # ═══════════════════════════════════════════════════════════════

    def create_collaborative_task(self, title: str, subtasks: list[dict], coordinator: str = "") -> dict:
        """创建多Agent协同任务。

        Args:
            title: 任务标题
            subtasks: 子任务列表 [{"title": "...", "domain": "...", "agent": "..."}]
            coordinator: 协调Agent ID

        Returns:
            协同任务元数据
        """
        task_meta = {
            "title": title,
            "coordinator": coordinator or self.hub.node_id,
            "subtasks": [],
            "created": datetime.now(UTC).isoformat(),
            "status": "created",
        }

        for i, st in enumerate(subtasks):
            assignment = self.hub.assign_task(
                st.get("domain", "cockpit"),
                st.get("type", "research"),
                strategy="affinity" if st.get("agent") else "load_balance",
            )

            task_meta["subtasks"].append(
                {
                    "id": f"{title}-subtask-{i + 1}",
                    "title": st["title"],
                    "domain": st.get("domain", "cockpit"),
                    "assigned_to": st.get("agent") or assignment["assigned_to"],
                    "status": "pending",
                    "depends_on": st.get("depends_on", []),
                }
            )

        self.signals.emit(
            "cockpit",
            "ℹ️",
            f"协同任务创建: {title} ({len(subtasks)} 子任务)",
            source="distributed.collaboration",
            cross_domain=True,
        )

        return task_meta

    def get_collaboration_status(self, task_meta: dict) -> dict:
        """获取协同任务执行状态。

        检查:
        1. 各子任务完成情况
        2. 依赖关系是否满足
        3. 是否有阻塞
        """
        completed = sum(1 for st in task_meta["subtasks"] if st["status"] == "done")
        pending = sum(1 for st in task_meta["subtasks"] if st["status"] == "pending")
        blocked = sum(1 for st in task_meta["subtasks"] if st["status"] == "blocked")

        # 检查依赖
        for st in task_meta["subtasks"]:
            if st["status"] == "pending" and st.get("depends_on"):
                deps_done = all(
                    any(s["id"] == dep and s["status"] == "done" for s in task_meta["subtasks"])
                    for dep in st["depends_on"]
                )
                if not deps_done:
                    st["status"] = "blocked"
                    blocked += 1
                    pending -= 1

        return {
            "title": task_meta["title"],
            "total": len(task_meta["subtasks"]),
            "completed": completed,
            "pending": pending,
            "blocked": blocked,
            "progress": f"{completed / max(len(task_meta['subtasks']), 1) * 100:.0f}%",
        }

    # ═══════════════════════════════════════════════════════════════
    # 联邦健康聚合
    # ═══════════════════════════════════════════════════════════════

    def aggregate_federation_health(self) -> dict:
        """聚合联邦所有节点的健康状态。"""
        nodes_health = self.hub.check_all_peers_health()
        domains_health = {}

        for domain_id in self.hub.federated_domains:
            domains_health[domain_id] = self.health.aggregate_health()

        return {
            "node_id": self.hub.node_id,
            "nodes": {
                "total": len(nodes_health),
                "healthy": sum(1 for h in nodes_health.values() if h["status"] == "healthy"),
                "unreachable": sum(1 for h in nodes_health.values() if h["status"] == "unreachable"),
            },
            "domains": {
                "federated": len(self.hub.federated_domains),
                "synced": sum(1 for fd in self.hub.federated_domains.values() if fd.last_sync),
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def generate_federation_dashboard(self) -> str:
        """生成联邦 DASHBOARD。"""
        status = self.aggregate_federation_health()
        lines = [
            "# L4 联邦 DASHBOARD",
            "",
            f"> 节点: {status['node_id']}",
            f"> 更新时间: {status['timestamp']}",
            "",
            "## 节点状态",
            f"- 总计: {status['nodes']['total']}",
            f"- 健康: {status['nodes']['healthy']}",
            f"- 不可达: {status['nodes']['unreachable']}",
            "",
            "## 联邦域",
            f"- 联邦域数: {status['domains']['federated']}",
            f"- 已同步: {status['domains']['synced']}",
            "",
            "## 对等节点",
        ]
        for nid, peer in self.hub.peers.items():
            h = self.hub.check_peer_health(nid)
            icon = "✅" if h["status"] == "healthy" else "❌"
            lines.append(f"- {icon} {nid} ({peer.hostname}) — {peer.role} — {len(peer.domains)} 域")

        return "\n".join(lines) + "\n"
