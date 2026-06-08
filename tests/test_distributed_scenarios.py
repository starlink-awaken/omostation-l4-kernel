"""Tests for L4 Kernel Distributed Scenarios."""

import tempfile
from pathlib import Path

import pytest

from l4_kernel.federation import FederationHub, PeerNode
from l4_kernel.distributed import DistributedScenarioEngine


@pytest.fixture
def hub():
    config = Path(tempfile.mkdtemp()) / "federation.json"
    return FederationHub(node_id="node-primary", config_path=config)


@pytest.fixture
def engine(hub):
    return DistributedScenarioEngine(hub)


class TestDomainSync:
    def test_sync_all_federated(self, engine, hub):
        hub.register_federated_domain("vault", "node-primary", replica_nodes=["node-2"])
        hub.register_peer(PeerNode(node_id="node-2", hostname="node2.local", role="replica"))
        results = engine.sync_all_federated_domains()
        assert "vault" in results
        assert results["vault"]["status"] == "ok"

    def test_sync_domain_to_replicas(self, engine, hub):
        hub.register_federated_domain("vault", "node-primary", replica_nodes=["node-2"])
        hub.register_peer(PeerNode(node_id="node-2", hostname="node2.local", role="replica"))
        result = engine.sync_domain_to_replicas("vault")
        assert result["domain_id"] == "vault"

    def test_sync_not_primary(self, engine, hub):
        hub.register_federated_domain("personal", "other-node")
        result = engine.sync_domain_to_replicas("personal")
        assert result["status"] == "error"

    def test_pull_domain(self, engine, hub):
        hub.register_federated_domain("vault", "node-primary")
        hub.register_peer(PeerNode(node_id="node-primary", hostname="primary.local", role="primary"))
        result = engine.pull_domain_from_primary("vault")
        assert result["status"] == "ok"


class TestTaskDispatch:
    def test_assign_and_dispatch(self, engine, hub):
        hub.register_federated_domain("vault", "node-primary")
        result = engine.assign_and_dispatch("TASK-001", "vault", "health_check")
        assert result["task_id"] == "TASK-001"
        assert result["assigned_to"] == "node-primary"

    def test_assign_fallback(self, engine, hub):
        # domain not federated → falls back to current node
        result = engine.assign_and_dispatch("TASK-002", "nonexistent", "research")
        assert result["assigned_to"] == "node-primary"  # fallback to self

    def test_get_node_tasks(self, engine, hub):
        hub.register_peer(PeerNode(node_id="node-2", hostname="n2.local", role="worker", domains=["vault"]))
        tasks = engine.get_node_tasks("node-2")
        assert len(tasks) == 1


class TestCollaboration:
    def test_create_collaborative_task(self, engine, hub):
        hub.register_federated_domain("vault", "node-primary")
        result = engine.create_collaborative_task(
            "协同研究",
            [
                {"title": "文献搜索", "domain": "vault", "agent": "agent-1"},
                {"title": "数据分析", "domain": "cockpit", "agent": "agent-2"},
                {"title": "报告撰写", "domain": "vault", "agent": "agent-1", "depends_on": ["协同研究-subtask-1"]},
            ],
        )
        assert result["status"] == "created"
        assert len(result["subtasks"]) == 3

    def test_collaboration_status(self, engine, hub):
        task = engine.create_collaborative_task(
            "测试协同",
            [
                {"title": "步骤1", "domain": "vault"},
                {"title": "步骤2", "domain": "vault", "depends_on": ["测试协同-subtask-1"]},
            ],
        )
        # 标记步骤1完成
        task["subtasks"][0]["status"] = "done"
        status = engine.get_collaboration_status(task)
        assert status["completed"] == 1
        assert status["blocked"] == 0  # 步骤2 依赖已满足

    def test_collaboration_blocked(self, engine, hub):
        task = engine.create_collaborative_task(
            "阻塞测试",
            [
                {"title": "步骤1", "domain": "vault"},
                {"title": "步骤2", "domain": "vault", "depends_on": ["阻塞测试-subtask-1"]},
            ],
        )
        # 步骤1未完成 → 步骤2应阻塞
        status = engine.get_collaboration_status(task)
        assert status["blocked"] == 1


class TestFederationHealth:
    def test_aggregate_federation_health(self, engine, hub):
        hub.register_peer(PeerNode(node_id="node-2", hostname="n2.local", role="replica"))
        hub.register_federated_domain("vault", "node-primary")
        result = engine.aggregate_federation_health()
        assert result["nodes"]["total"] == 1

    def test_generate_federation_dashboard(self, engine, hub):
        hub.register_peer(PeerNode(node_id="node-2", hostname="n2.local", role="replica", domains=["vault"]))
        dashboard = engine.generate_federation_dashboard()
        assert "# L4 联邦 DASHBOARD" in dashboard
        assert "node-2" in dashboard
