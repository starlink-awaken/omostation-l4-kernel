"""L4 Federation Hub — 多节点联邦中枢。

提供:
1. 联邦域注册表 (合并所有节点的域)
2. 跨节点信号路由
3. 节点健康监控
4. 域同步策略
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from l4_kernel.registry import DomainRegistry

# ═════════════════════════════════════════════════════════════════════
# 数据模型
# ═════════════════════════════════════════════════════════════════════

SyncStrategy = Literal["push", "pull", "merge", "none"]
TaskStrategy = Literal["affinity", "load_balance", "capability"]
NodeRole = Literal["primary", "replica", "observer", "coordinator", "worker"]


@dataclass
class PeerNode:
    """对等节点。"""

    node_id: str
    hostname: str
    role: NodeRole
    domains: list[str] = field(default_factory=list)
    l4_kernel_version: str = "0.1.0"
    health_endpoint: str = ""
    last_seen: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "role": self.role,
            "domains": self.domains,
            "l4_kernel_version": self.l4_kernel_version,
            "last_seen": self.last_seen,
        }


@dataclass
class FederatedDomain:
    """联邦域 — 跨节点的域视图。"""

    domain_id: str
    primary_node: str
    replica_nodes: list[str] = field(default_factory=list)
    observer_nodes: list[str] = field(default_factory=list)
    sync_strategy: SyncStrategy = "push"
    last_sync: str = ""
    conflict_resolution: str = "primary_wins"

    def to_dict(self) -> dict:
        return {
            "domain_id": self.domain_id,
            "primary_node": self.primary_node,
            "replica_nodes": self.replica_nodes,
            "observer_nodes": self.observer_nodes,
            "sync_strategy": self.sync_strategy,
            "last_sync": self.last_sync,
        }


# ═════════════════════════════════════════════════════════════════════
# FederationHub
# ═════════════════════════════════════════════════════════════════════


class FederationHub:
    """L4 联邦中枢。

    管理多节点 L4 域，提供联邦视图和跨节点操作。
    """

    def __init__(self, node_id: str, registry: DomainRegistry | None = None, config_path: Path | None = None):
        self.node_id = node_id
        self.registry = registry or DomainRegistry.require_explicit()
        self.config_path = config_path or Path.home() / ".config" / "l4-kernel" / "federation.json"
        self.peers: dict[str, PeerNode] = {}
        self.federated_domains: dict[str, FederatedDomain] = {}
        self._load_config()

    # ── 配置持久化 ────────────────────────────────────────────────

    def _load_config(self) -> None:
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text())
                for p in data.get("peers", []):
                    peer = PeerNode(**p)
                    self.peers[peer.node_id] = peer
                for d in data.get("federated_domains", []):
                    fd = FederatedDomain(**d)
                    self.federated_domains[fd.domain_id] = fd
            except (json.JSONDecodeError, TypeError):
                pass

    def _save_config(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        # 过滤敏感字段
        safe_peers = []
        for p in self.peers.values():
            d = p.to_dict()
            # 移除可能含 token 的 health_endpoint
            if "health_endpoint" in d and "token" in d.get("health_endpoint", "").lower():
                d["health_endpoint"] = "[REDACTED]"
            safe_peers.append(d)

        data = {
            "node_id": self.node_id,
            "peers": safe_peers,
            "federated_domains": [d.to_dict() for d in self.federated_domains.values()],
            "updated": datetime.now(UTC).isoformat(),
        }
        self.config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        # 设置 600 权限
        self.config_path.chmod(0o600)

    # ── 节点管理 ──────────────────────────────────────────────────

    def register_peer(self, peer: PeerNode) -> None:
        """注册对等节点。"""
        peer.last_seen = datetime.now(UTC).isoformat()
        self.peers[peer.node_id] = peer
        self._save_config()

    def unregister_peer(self, node_id: str) -> bool:
        """注销节点。"""
        if node_id in self.peers:
            del self.peers[node_id]
            self._save_config()
            return True
        return False

    def list_peers(self, role: NodeRole | None = None) -> list[PeerNode]:
        """列出节点 (可按角色筛选)。"""
        peers = list(self.peers.values())
        if role:
            peers = [p for p in peers if p.role == role]
        return peers

    def get_peer(self, node_id: str) -> PeerNode | None:
        return self.peers.get(node_id)

    def check_peer_health(self, node_id: str) -> dict:
        """检查对等节点健康。"""
        peer = self.peers.get(node_id)
        if not peer:
            return {"node_id": node_id, "status": "not_registered"}

        # 检查是否最近有联系
        if peer.last_seen:
            try:
                last = datetime.fromisoformat(peer.last_seen)
                seconds_since = (datetime.now(UTC) - last).total_seconds()
                if seconds_since > 300:  # 5分钟无联系
                    return {"node_id": node_id, "status": "unreachable", "seconds_since": seconds_since}
            except (ValueError, TypeError):
                pass

        return {"node_id": node_id, "status": "healthy"}

    def check_all_peers_health(self) -> dict[str, dict]:
        return {nid: self.check_peer_health(nid) for nid in self.peers}

    # ── 联邦域管理 ────────────────────────────────────────────────

    def register_federated_domain(
        self,
        domain_id: str,
        primary_node: str,
        replica_nodes: list[str] | None = None,
        sync_strategy: SyncStrategy = "push",
    ) -> FederatedDomain:
        """注册联邦域。"""
        fd = FederatedDomain(
            domain_id=domain_id,
            primary_node=primary_node,
            replica_nodes=replica_nodes or [],
            sync_strategy=sync_strategy,
            last_sync=datetime.now(UTC).isoformat(),
        )
        self.federated_domains[domain_id] = fd
        self._save_config()
        return fd

    def get_federated_domains(self) -> dict[str, FederatedDomain]:
        """获取所有联邦域。"""
        return dict(self.federated_domains)

    def get_domain_primary(self, domain_id: str) -> str | None:
        """获取域的主节点。"""
        fd = self.federated_domains.get(domain_id)
        return fd.primary_node if fd else None

    def is_domain_primary(self, domain_id: str) -> bool:
        """当前节点是否为域的主节点。"""
        return self.get_domain_primary(domain_id) == self.node_id

    # ── 域同步 ────────────────────────────────────────────────────

    def sync_domain(self, domain_id: str, strategy: SyncStrategy | None = None) -> dict:
        """同步域数据 (当前仅支持 push 策略)。

        返回同步状态:
        {
            "domain_id": "vault",
            "strategy": "push",
            "status": "ok" | "conflict" | "error",
            "files_synced": 5,
            "conflicts": [...]
        }
        """
        fd = self.federated_domains.get(domain_id)
        if not fd:
            return {"status": "error", "message": f"Domain '{domain_id}' not federated"}

        strategy = strategy or fd.sync_strategy

        if strategy == "push":
            return self._sync_push(domain_id, fd)
        elif strategy == "pull":
            return self._sync_pull(domain_id, fd)
        elif strategy == "merge":
            return self._sync_merge(domain_id, fd)
        else:
            return {"status": "skipped", "message": f"Strategy '{strategy}' not supported"}

    def _sync_push(self, domain_id: str, fd: FederatedDomain) -> dict:
        """推送同步: 主节点 → 副本节点。"""
        if not self.is_domain_primary(domain_id):
            return {"status": "error", "message": f"Node '{self.node_id}' is not primary for '{domain_id}'"}

        results = {"domain_id": domain_id, "strategy": "push", "status": "ok", "files_synced": 0, "replicas": {}}

        domain = self.registry.get(domain_id)
        if not domain or not domain.exists():
            return {"status": "error", "message": f"Domain '{domain_id}' not available"}

        for replica_id in fd.replica_nodes:
            replica = self.peers.get(replica_id)
            if not replica:
                results["replicas"][replica_id] = {"status": "offline"}
                continue

            # 计算需要同步的文件 (基于 mtime)
            files_to_sync = self._compute_sync_diff(domain.path, replica)
            results["replicas"][replica_id] = {
                "status": "pending_sync",
                "files_to_sync": len(files_to_sync),
                "note": "actual sync requires network transport (future Phase)",
            }
            results["files_synced"] += len(files_to_sync)

        fd.last_sync = datetime.now(UTC).isoformat()
        self._save_config()
        return results

    def _sync_pull(self, domain_id: str, fd: FederatedDomain) -> dict:
        """拉取同步: 副本节点 ← 主节点。"""
        return {"domain_id": domain_id, "strategy": "pull", "status": "ok", "note": "pull sync pending implementation"}

    def _sync_merge(self, domain_id: str, fd: FederatedDomain) -> dict:
        """合并同步: 双向 CRDT。"""
        return {
            "domain_id": domain_id,
            "strategy": "merge",
            "status": "ok",
            "note": "merge sync pending implementation",
        }

    def _compute_sync_diff(self, domain_path: Path, peer: PeerNode) -> list[dict]:
        """计算需要同步的文件差异 (基于 mtime)。"""
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
                        "mtime": stat.st_mtime,
                    }
                )
            except OSError:
                pass

        return diff

    # ── 联邦视图 ──────────────────────────────────────────────────

    def get_federation_status(self) -> dict:
        """获取联邦状态总览。"""
        return {
            "node_id": self.node_id,
            "peers": len(self.peers),
            "federated_domains": len(self.federated_domains),
            "peers_healthy": sum(1 for nid in self.peers if self.check_peer_health(nid)["status"] == "healthy"),
            "domains_synced": sum(1 for fd in self.federated_domains.values() if fd.last_sync),
            "timestamp": datetime.now(UTC).isoformat(),
        }

    # ── 任务分配 ──────────────────────────────────────────────────

    def assign_task(self, domain_id: str, task_type: str, strategy: TaskStrategy = "affinity") -> dict:
        """分配任务到最优节点。

        affinity: 分配到域主节点
        load_balance: 分配到负载最低的节点
        capability: 分配到有特定能力的节点
        """
        if strategy == "affinity":
            primary = self.get_domain_primary(domain_id)
            if primary:
                return {"assigned_to": primary, "strategy": "affinity", "reason": f"Primary node for {domain_id}"}

        # 负载均衡: 选域最少的节点
        if strategy == "load_balance":
            candidates = [
                (nid, len(peer.domains)) for nid, peer in self.peers.items() if peer.role in ("primary", "worker")
            ]
            if candidates:
                best = min(candidates, key=lambda x: x[1])
                return {"assigned_to": best[0], "strategy": "load_balance", "domain_count": best[1]}

        return {"assigned_to": self.node_id, "strategy": "fallback", "reason": "No suitable node found"}
