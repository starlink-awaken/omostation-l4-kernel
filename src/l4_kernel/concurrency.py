"""L4 Concurrency Manager — 多Agent并发操作管理。

适配自 ECOS L0 分布式锁抽象 (DistributedLock)。
提供基于 fcntl.flock 的文件锁，兼容之前行为。
"""

from __future__ import annotations

import fcntl
import time
from contextlib import contextmanager
from pathlib import Path

# 从 L0 引入基础接口 (假设 ecos 已经可以通过 PYTHONPATH 或 workspace 配置访问)
try:
    from ecos.l0.concurrency import DistributedLock, LockAcquireError
except ImportError:
    # 垫片防腐层: 在还没发布 ecos package 前防止 l4-kernel 本地挂掉
    class LockAcquireError(Exception):
        pass

    class DistributedLock:
        def __init__(self, name: str):
            self.name = name


class L4FileLock(DistributedLock):
    """基于 fcntl.flock 的本地文件锁，向下兼容。"""

    def __init__(self, filepath: Path | str):
        super().__init__(str(filepath))
        self.filepath = Path(filepath)
        self._fd = None

    def acquire(self, timeout: float | None = None) -> bool:
        timeout = timeout or 5.0
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        start = time.time()
        while True:
            try:
                self._fd = open(self.filepath, "a")
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except OSError:
                if self._fd:
                    self._fd.close()
                    self._fd = None
                if time.time() - start > timeout:
                    raise LockAcquireError(f"Failed to acquire lock on {self.filepath} within {timeout}s")
                time.sleep(0.1)

    def release(self) -> None:
        if self._fd:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            self._fd.close()
            self._fd = None

    def check_and_set(self, expected_version: int, new_version: int) -> bool:
        raise NotImplementedError("File lock does not support native atomic check-and-set")

    @contextmanager
    def lock(self, timeout: float | None = None):
        self.acquire(timeout)
        try:
            yield self._fd
        finally:
            self.release()


class ConcurrencyManager:
    """多Agent并发操作管理 (Facade 包装层)。"""

    LOCK_TIMEOUT = 5.0

    @contextmanager
    def lock(self, filepath: Path, timeout: float | None = None):
        """获取文件排他锁。"""
        lock_obj = L4FileLock(filepath)
        with lock_obj.lock(timeout or self.LOCK_TIMEOUT) as fd:
            yield fd

    @contextmanager
    def lock_shared(self, filepath: Path, timeout: float | None = None):
        """获取文件共享锁 (多读)。"""
        timeout = timeout or self.LOCK_TIMEOUT
        filepath.parent.mkdir(parents=True, exist_ok=True)
        f = None
        start = time.time()
        while True:
            try:
                f = open(filepath)
                fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
                break
            except OSError:
                if f:
                    f.close()
                if time.time() - start > timeout:
                    raise TimeoutError(f"Failed to acquire shared lock on {filepath}")
                time.sleep(0.1)
        try:
            yield f
        finally:
            if f:
                fcntl.flock(f, fcntl.LOCK_UN)
                f.close()

    def read_with_version(self, filepath: Path) -> tuple[str, int]:
        if not filepath.exists():
            return ("", 0)
        stat = filepath.stat()
        content = filepath.read_text(encoding="utf-8")
        return (content, int(stat.st_mtime * 1_000_000))

    def write_if_version(self, filepath: Path, content: str, expected_version: int) -> bool:
        with self.lock(filepath):
            if expected_version != 0:
                current = int(filepath.stat().st_mtime * 1_000_000) if filepath.exists() else 0
                if current != expected_version:
                    return False
            filepath.write_text(content, encoding="utf-8")
            return True

    def __init__(self):
        self._held_locks: dict[str, L4FileLock] = {}

    @contextmanager
    def lock_domain_control(self, domain_path: Path, files: list[str] | None = None):
        if files is None:
            files = ["STATE.md", "MEMORY.md", "signals.md", "STATUS.md"]
        control = domain_path / "_control"
        filepaths = sorted(control / f for f in files)
        locks_acquired = []
        try:
            for fp in filepaths:
                key = str(fp)
                if key in self._held_locks:
                    continue
                lock_obj = L4FileLock(fp)
                lock_obj.acquire(self.LOCK_TIMEOUT)
                self._held_locks[key] = lock_obj
                locks_acquired.append(key)
            yield
        finally:
            for key in reversed(locks_acquired):
                lock_obj = self._held_locks.pop(key)
                lock_obj.release()
