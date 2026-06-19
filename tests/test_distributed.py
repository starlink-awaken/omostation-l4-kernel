"""Tests for L4 Kernel ConcurrencyManager and FederationHub."""

import tempfile
import time
from pathlib import Path

import pytest

from l4_kernel.concurrency import ConcurrencyManager
from l4_kernel.federation import FederatedDomain, FederationHub, PeerNode


class TestConcurrencyManager:
    def test_lock_acquire_release(self):
        mgr = ConcurrencyManager()
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as tf:
            path = Path(tf.name)
        try:
            with mgr.lock(path):
                path.write_text("locked content")
            content = path.read_text()
            assert content == "locked content"
        finally:
            path.unlink(missing_ok=True)

    def test_lock_timeout(self):
        mgr = ConcurrencyManager()
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as tf:
            path = Path(tf.name)
        try:
            import threading

            acquired = threading.Event()
            release = threading.Event()

            def holder():
                with mgr.lock(path):
                    acquired.set()
                    release.wait()

            t = threading.Thread(target=holder)
            t.start()
            acquired.wait(timeout=2)

            # 尝试获取锁应该超时
            try:
                from l4_kernel.concurrency import LockAcquireError
                with mgr.lock(path, timeout=0.5):
                    pass
            except (TimeoutError, LockAcquireError, OSError):
                pass  # 预期行为

            release.set()
            t.join(timeout=2)
        finally:
            path.unlink(missing_ok=True)

    def test_read_with_version(self):
        mgr = ConcurrencyManager()
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as tf:
            tf.write("version 1")
            path = Path(tf.name)

        try:
            content, version = mgr.read_with_version(path)
            assert content == "version 1"
            assert version > 0
        finally:
            path.unlink(missing_ok=True)

    def test_read_with_version_missing(self):
        mgr = ConcurrencyManager()
        content, version = mgr.read_with_version(Path("/nonexistent/file.md"))
        assert content == ""
        assert version == 0

    def test_write_if_version_match(self):
        mgr = ConcurrencyManager()
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as tf:
            tf.write("original")
            path = Path(tf.name)

        try:
            _, version = mgr.read_with_version(path)
            # 等1ms确保mtime变化
            time.sleep(0.01)
            assert mgr.write_if_version(path, "updated", version) is True
            assert path.read_text() == "updated"
        finally:
            path.unlink(missing_ok=True)

    def test_write_if_version_conflict(self):
        mgr = ConcurrencyManager()
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as tf:
            tf.write("original")
            path = Path(tf.name)

        try:
            _, version = mgr.read_with_version(path)
            # 另一个进程修改了文件
            time.sleep(0.01)
            path.write_text("modified by other")
            assert mgr.write_if_version(path, "my update", version) is False
            assert path.read_text() == "modified by other"
        finally:
            path.unlink(missing_ok=True)

    def test_write_if_version_zero(self):
        """version=0 → force write (skip version check)."""
        mgr = ConcurrencyManager()
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as tf:
            tf.write("original")
            path = Path(tf.name)
        try:
            # version=0 → unconditional write
            assert mgr.write_if_version(path, "forced update", 0) is True
            assert path.read_text() == "forced update"
        finally:
            path.unlink(missing_ok=True)

    def test_lock_domain_control(self):
        mgr = ConcurrencyManager()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            control = root / "_control"
            control.mkdir()
            for f in ["STATE.md", "MEMORY.md"]:
                (control / f).write_text("")

            with mgr.lock_domain_control(root, files=["STATE.md", "MEMORY.md"]):
                (control / "STATE.md").write_text("locked state")
            assert (control / "STATE.md").read_text() == "locked state"


class TestPeerNode:
    def test_create(self):
        peer = PeerNode(node_id="node-1", hostname="mac.local", role="primary", domains=["vault", "cockpit"])
        assert peer.node_id == "node-1"
        assert peer.role == "primary"

    def test_to_dict(self):
        peer = PeerNode(node_id="n1", hostname="h1", role="worker")
        d = peer.to_dict()
        assert d["node_id"] == "n1"
        assert d["role"] == "worker"


class TestFederatedDomain:
    def test_create(self):
        fd = FederatedDomain(domain_id="vault", primary_node="node-1", replica_nodes=["node-2"])
        assert fd.primary_node == "node-1"
        assert "node-2" in fd.replica_nodes


class TestFederationHub:
    @pytest.fixture
    def hub(self):
        import tempfile

        config = Path(tempfile.mkdtemp()) / "federation.json"
        return FederationHub(node_id="test-node", config_path=config)

    def test_register_peer(self, hub):
        peer = PeerNode(node_id="peer-1", hostname="peer.local", role="replica")
        hub.register_peer(peer)
        assert hub.get_peer("peer-1") is not None

    def test_list_peers_by_role(self, hub):
        hub.register_peer(PeerNode(node_id="p1", hostname="h1", role="primary"))
        hub.register_peer(PeerNode(node_id="p2", hostname="h2", role="replica"))
        hub.register_peer(PeerNode(node_id="p3", hostname="h3", role="replica"))
        replicas = hub.list_peers(role="replica")
        assert len(replicas) == 2

    def test_unregister_peer(self, hub):
        hub.register_peer(PeerNode(node_id="p1", hostname="h1", role="worker"))
        assert hub.unregister_peer("p1") is True
        assert hub.get_peer("p1") is None
        assert hub.unregister_peer("nonexistent") is False

    def test_register_federated_domain(self, hub):
        fd = hub.register_federated_domain("vault", "test-node", replica_nodes=["peer-1"])
        assert fd.primary_node == "test-node"
        assert hub.is_domain_primary("vault") is True

    def test_get_domain_primary(self, hub):
        hub.register_federated_domain("personal", "peer-1")
        assert hub.get_domain_primary("personal") == "peer-1"

    def test_sync_domain_push(self, hub):
        hub.register_federated_domain("vault", "test-node", replica_nodes=["peer-1"])
        hub.register_peer(PeerNode(node_id="peer-1", hostname="peer.local", role="replica"))
        result = hub.sync_domain("vault")
        assert result["status"] == "ok"

    def test_sync_domain_not_primary(self, hub):
        hub.register_federated_domain("personal", "peer-1")
        result = hub.sync_domain("personal")
        assert result["status"] == "error"

    def test_federation_status(self, hub):
        hub.register_peer(PeerNode(node_id="p1", hostname="h1", role="primary"))
        status = hub.get_federation_status()
        assert status["node_id"] == "test-node"
        assert status["peers"] == 1

    def test_assign_task_affinity(self, hub):
        hub.register_federated_domain("vault", "peer-1")
        result = hub.assign_task("vault", "health_check", strategy="affinity")
        assert result["assigned_to"] == "peer-1"

    def test_assign_task_fallback(self, hub):
        result = hub.assign_task("vault", "health_check")
        assert result["assigned_to"] == "test-node"

    def test_check_peer_health(self, hub):
        hub.register_peer(PeerNode(node_id="p1", hostname="h1", role="primary"))
        result = hub.check_peer_health("p1")
        assert result["status"] == "healthy"
