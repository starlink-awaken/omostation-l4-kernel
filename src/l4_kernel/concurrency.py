"""L4 Concurrency Manager — 多Agent并发操作管理。

提供:
1. 文件锁 (fcntl.flock) — 单机进程级并发保护
2. 乐观锁 (版本号) — 读写冲突检测
3. 锁上下文管理器 — with 语法
"""

from __future__ import annotations

import fcntl
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class ConcurrencyManager:
    """多Agent并发操作管理。

    使用方式:
        mgr = ConcurrencyManager()
        with mgr.lock(domain_path / "_control" / "STATE.md"):
            # 安全读写 STATE.md
            pass
    """

    LOCK_TIMEOUT = 5.0  # 获取锁超时 (秒)

    @contextmanager
    def lock(self, filepath: Path, timeout: float | None = None):
        """获取文件排他锁。

        Args:
            filepath: 要锁定的文件路径
            timeout: 超时秒数 (默认 LOCK_TIMEOUT)

        Yields:
            锁定的文件对象 (已打开, append模式)

        Raises:
            TimeoutError: 超时未获取到锁
        """
        timeout = timeout or self.LOCK_TIMEOUT
        filepath.parent.mkdir(parents=True, exist_ok=True)

        f = None
        start = time.time()
        while True:
            try:
                f = open(filepath, "a")
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (IOError, OSError):
                if f:
                    f.close()
                if time.time() - start > timeout:
                    raise TimeoutError(f"Failed to acquire lock on {filepath} within {timeout}s")
                time.sleep(0.1)

        try:
            yield f
        finally:
            if f:
                fcntl.flock(f, fcntl.LOCK_UN)
                f.close()

    @contextmanager
    def lock_shared(self, filepath: Path, timeout: float | None = None):
        """获取文件共享锁 (多读)。"""
        timeout = timeout or self.LOCK_TIMEOUT
        filepath.parent.mkdir(parents=True, exist_ok=True)

        f = None
        start = time.time()
        while True:
            try:
                f = open(filepath, "r")
                fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
                break
            except (IOError, OSError):
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

    # ── 乐观锁 ────────────────────────────────────────────────────

    def read_with_version(self, filepath: Path) -> tuple[str, int]:
        """读取文件内容和版本号 (mtime作为版本)。

        Returns:
            (content, version)
        """
        if not filepath.exists():
            return ("", 0)
        stat = filepath.stat()
        content = filepath.read_text(encoding="utf-8")
        return (content, int(stat.st_mtime * 1_000_000))

    def write_if_version(self, filepath: Path, content: str,
                         expected_version: int) -> bool:
        """乐观锁写入: 仅当版本号匹配时才写入。

        expected_version=0 表示无条件写入 (跳过版本检查)。

        Returns:
            True if written, False if version conflict
        """
        with self.lock(filepath):
            if expected_version != 0:
                current = int(filepath.stat().st_mtime * 1_000_000) if filepath.exists() else 0
                if current != expected_version:
                    return False
            filepath.write_text(content, encoding="utf-8")
            return True

    # ── 批量锁 ────────────────────────────────────────────────────

    @contextmanager
    def lock_domain_control(self, domain_path: Path,
                            files: list[str] | None = None):
        """锁定域控制面的多个文件 (按排序加锁避免死锁)。

        Args:
            domain_path: 域根路径
            files: 要锁定的文件列表 (默认: STATE, MEMORY, signals, STATUS)
        """
        if files is None:
            files = ["STATE.md", "MEMORY.md", "signals.md", "STATUS.md"]

        control = domain_path / "_control"
        filepaths = sorted(control / f for f in files)

        locks = []
        try:
            for fp in filepaths:
                lock_ctx = self.lock(fp)
                lock_ctx.__enter__()
                locks.append(lock_ctx)
            yield
        finally:
            for lock_ctx in reversed(locks):
                lock_ctx.__exit__(None, None, None)
