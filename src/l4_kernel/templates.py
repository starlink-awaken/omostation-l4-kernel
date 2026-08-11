"""L4 Kernel Templates — KEMS 控制面标准模板与 Schema 校验。

基于 8 个 DocumentDomain 的实际 KEMS 文件分析结果。
"""

from __future__ import annotations

import errno
import hashlib
import os
import re
import stat
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from l4_kernel.contracts import ContractError, load_domain_manifest

# ═════════════════════════════════════════════════════════════════════
# 标准模板集
# ═════════════════════════════════════════════════════════════════════

MEMORY_TEMPLATE = """---
title: 元事实与指针
description: {domain_name} 跨会话元事实。
status: 已采纳
type: canonical
owner: {owner}
created: {created}
last-reviewed: {created}
tags: [控制面]
---

# MEMORY — 元事实与指针

- **域类型**: {domain_type_desc}
- **核心职责**: {domain_purpose}
- **SSOT 范围**: {ssot_scope}
- **活跃任务**: CARDS 卡片库 (data/cards/cards.db)
- **关键文件**: {key_files}
"""

STATUS_TEMPLATE = """---
title: 系统三态判定
description: {domain_name} 整体健康度三态。
status: 已采纳
type: canonical
owner: {owner}
created: {created}
last-reviewed: {created}
tags: [控制面, 控制器]
---

# STATUS — 系统三态判定

## 当前状态：STABLE 🟢

## 三态定义

| 状态 | 含义 | 判定条件 |
|------|------|---------|
| STABLE 🟢 | 所有维度正常 | 无逾期任务，signals 无 ⚠️🔴 待处理 |
| ALERT 🟡 | 存在风险信号 | 有 ⚠️/🔴 信号未闭环，或有项目逾期 |
| CRITICAL 🔴 | 系统级危机 | 连续 2 次深度门禁失败，或 3+ 逾期任务叠加 |

## 判定依据

| 维度 | 状态 | 权重 | 影响范围 |
|------|------|------|---------|
| CARDS 活跃度 | 正常 | 30% | 任务追踪 |
| signals 健康 | 正常 | 30% | 风险预警 |
| 文件新鲜度 | 正常 | 20% | X2 抗熵 |
| KEMS 结构 | 完整 | 20% | X4 一致性 |

## 状态变更日志

| 日期 | 状态 | 原因 |
|------|------|------|
| {created} | STABLE 🟢 | 初始化 |

## 优先动作

- [ ] 更新 CARDS 卡片
- [ ] 处理 signals 中的 ⚠️🔴 信号
- [ ] 检查 STATE.md 阶段定位
"""

SIGNALS_TEMPLATE = """---
title: 信号日志
description: {domain_name} 传感器信号记录。
status: 已采纳
type: log
owner: {owner}
created: {created}
last-reviewed: {created}
tags: [控制面, 传感器]
---

# signals — 信号日志

> 类型：✅ 正常进展  ⚠️ 关注信号  🔴 紧急信号  ℹ️ 信息性

| 类型 | 日期 | 信号 |
|------|------|------|
| ℹ️ | {created} | {domain_name} 域初始化 |
"""

CONTROL_RULES_TEMPLATE = """---
title: 控制规则
description: {domain_name} 控制面规则表。
status: 已采纳
type: canonical
owner: {owner}
created: {created}
last-reviewed: {created}
tags: [控制面, 控制器]
---

# control-rules — 控制规则

## 内核规则（l4-kernel 强制）

| ID | 输入 | 动作 |
|----|------|------|
| CR01 | signals 出现 🔴 信号 | 触发域内事件响应 + 跨域通知 (@驾驶舱) |
| CR02 | 任务线停滞超过 SLA | 更新 STATE.md 阶段定位 + 检查 CARDS 触发时机 |
| CR03 | STATUS 从 STABLE 变为 ALERT | 通知 @驾驶舱 + 写入 signals |

## 域扩展规则

| ID | 输入 | 动作 |
|----|------|------|
| CR04 | _entities/ 实体 last-reviewed > 30 天 | 触发实体审查 |
"""


# ═════════════════════════════════════════════════════════════════════
# Schema 校验规则
# ═════════════════════════════════════════════════════════════════════


class KemsValidator:
    """KEMS 控制面 Schema 校验器。

    校验 8 类规则，覆盖 5 个核心文件。
    """

    # 控制面 5 核心文件（必须存在）
    REQUIRED_CONTROL_FILES = [
        "MEMORY.md",
        "STATE.md",
        "signals.md",
        "control-rules.md",
        "STATUS.md",
    ]

    # 信号类型枚举
    SIGNAL_TYPES = {"✅", "⚠️", "🔴", "ℹ️"}

    # STATUS 枚举
    STATUS_VALUES = {"STABLE", "ALERT", "CRITICAL"}

    # Frontmatter 必选字段
    REQUIRED_FRONTMATTER = ["title", "status", "type", "owner", "created"]

    def __init__(self, domain_path: Path):
        self._root = domain_path
        self._control = domain_path / "_control"

    def validate_all(self) -> list[dict]:
        """运行所有校验规则，返回问题列表。"""
        issues = []
        for rule in [
            self.check_control_files_exist,
            self.check_memory_frontmatter,
            self.check_status_enum,
            self.check_signal_types,
            self.check_control_rule_ids,
            self.check_owner_field,
            self.check_memory_frontmatter,  # MEMORY.md frontmatter
        ]:
            issues.extend(rule())
        return issues

    def check_control_files_exist(self) -> list[dict]:
        """V-CONTROL-01: 检查控制面 5 核心文件是否存在。"""
        issues = []
        for f in self.REQUIRED_CONTROL_FILES:
            if not (self._control / f).exists():
                issues.append(
                    {
                        "rule": "V-CONTROL-01",
                        "severity": "error",
                        "message": f"missing required file: _control/{f}",
                    }
                )
        return issues

    def check_memory_frontmatter(self) -> list[dict]:
        """V-CONTROL-02: 检查 MEMORY.md frontmatter 必选字段。"""
        issues = []
        fp = self._control / "MEMORY.md"
        if not fp.exists():
            return issues
        try:
            fm = self._parse_frontmatter(fp)
            if fm is None:
                issues.append(
                    {
                        "rule": "V-CONTROL-02",
                        "severity": "warning",
                        "message": "MEMORY.md: no YAML frontmatter found",
                    }
                )
            else:
                for field in self.REQUIRED_FRONTMATTER:
                    if field not in fm:
                        issues.append(
                            {
                                "rule": "V-CONTROL-02",
                                "severity": "warning",
                                "message": f"MEMORY.md: missing required frontmatter field '{field}'",
                            }
                        )
        except Exception:  # defensive fallback
            pass
        return issues

    def check_status_enum(self) -> list[dict]:
        """V-CONTROL-03: 检查 STATUS.md 当前状态是否在三态枚举中。"""
        issues = []
        fp = self._control / "STATUS.md"
        if not fp.exists():
            return issues
        try:
            text = fp.read_text(encoding="utf-8")
            # 匹配 "## 当前状态：<STATUS> <emoji>"
            m = re.search(r"当前状态[：:]\s*(\w+)", text)
            if m:
                status = m.group(1)
                if status not in self.STATUS_VALUES:
                    issues.append(
                        {
                            "rule": "V-CONTROL-03",
                            "severity": "error",
                            "message": f"STATUS.md: unknown status '{status}', must be one of {self.STATUS_VALUES}",
                        }
                    )
        except Exception:  # defensive fallback
            pass
        return issues

    def check_signal_types(self) -> list[dict]:
        """V-CONTROL-04: 检查 signals.md 信号类型是否在枚举中。"""
        issues = []
        fp = self._control / "signals.md"
        if not fp.exists():
            return issues
        try:
            text = fp.read_text(encoding="utf-8")
            for line in text.split("\n"):
                if line.startswith("|") and "---" not in line and "类型" not in line:
                    parts = [p.strip() for p in line.split("|")]
                    # parts[0]="" (leading |), parts[1]=type, parts[2]=date, parts[3]=signal
                    if len(parts) >= 4:
                        sig_type = parts[1]
                        # 检查是否包含已知信号 emoji
                        has_known = any(ch in self.SIGNAL_TYPES for ch in sig_type)
                        if sig_type and not has_known:
                            issues.append(
                                {
                                    "rule": "V-CONTROL-04",
                                    "severity": "warning",
                                    "message": f"signals.md: unknown signal type in row: {line[:60]}",
                                }
                            )
        except Exception:  # defensive fallback
            pass
        return issues

    def check_control_rule_ids(self) -> list[dict]:
        """V-CONTROL-05: 检查 control-rules CR ID 格式。"""
        issues = []
        fp = self._control / "control-rules.md"
        if not fp.exists():
            return issues
        try:
            text = fp.read_text(encoding="utf-8")
            ids = set(re.findall(r"\b(CR\d{2,})\b", text))
            for crid in ids:
                if not re.match(r"^CR\d{2}$", crid):
                    issues.append(
                        {
                            "rule": "V-CONTROL-05",
                            "severity": "info",
                            "message": f"control-rules.md: non-standard CR ID format: {crid}",
                        }
                    )
        except Exception:  # defensive fallback
            pass
        return issues

    def check_owner_field(self) -> list[dict]:
        """V-CONTROL-07: 检查域 owner 字段非空。"""
        issues = []
        for fname in ["MEMORY.md", "STATUS.md", "control-rules.md"]:
            fp = self._control / fname
            if not fp.exists():
                continue
            try:
                fm = self._parse_frontmatter(fp)
                if fm and not fm.get("owner"):
                    issues.append(
                        {
                            "rule": "V-CONTROL-07",
                            "severity": "error",
                            "message": f"{fname}: owner field is empty",
                        }
                    )
            except Exception:  # defensive fallback
                pass
        return issues

    # ── helpers ────────────────────────────────────────────────────

    @staticmethod
    def _parse_frontmatter(filepath: Path) -> dict | None:
        """解析 YAML frontmatter。"""
        text = filepath.read_text(encoding="utf-8")
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 2:
                try:
                    return yaml.safe_load(parts[1]) or {}
                except yaml.YAMLError:
                    return None
        return None


# ═════════════════════════════════════════════════════════════════════
# 域骨架生成
# ═════════════════════════════════════════════════════════════════════


class DeclarativeBootstrapResult(list[Path]):
    """List-compatible legacy result with machine-readable migration evidence."""

    def __init__(self, paths: list[Path]) -> None:
        super().__init__(paths)
        self.deprecation: dict[str, str] = {
            "code": "L4-DEPRECATION-001",
            "message": "init_domain_kems now creates declarative content contracts only",
            "replacement": "l4-kernel domain init-content-contracts",
        }

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-ready compatibility evidence without changing list semantics."""

        return {"created_files": [str(path) for path in self], "deprecation": dict(self.deprecation)}


_CONTRACT_FILES = (
    "DOMAIN.yaml",
    "Method.md",
    "profiles/Profile.md",
    "ontology/DOMAIN_ONTOLOGY.md",
    "rubrics/QUALITY_RUBRIC.md",
)
_DEFAULT_KEY_FILES = "DOMAIN.yaml · Method.md · profiles/ · ontology/ · rubrics/"
_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_INCOMPLETE_MODE = 0o000
_PUBLISHED_MODE = 0o644


class BootstrapWriteError(OSError):
    """A non-destructive failed publication with machine-readable evidence."""

    def __init__(
        self,
        message: str,
        residual_paths: list[Path],
        *,
        uncertain_paths: list[Path] | None = None,
        durability_uncertain_paths: list[Path] | None = None,
        error_number: int | None = None,
    ) -> None:
        self.residual_paths = tuple(dict.fromkeys(residual_paths))
        self.uncertain_paths = tuple(dict.fromkeys(uncertain_paths or []))
        self.durability_uncertain_paths = tuple(dict.fromkeys(durability_uncertain_paths or []))
        self.recovery = {
            "code": "L4-PUBLICATION-RECOVERY-001",
            "action": "inspect confirmed residual paths and uncertain incomplete targets; manually remove only files confirmed incomplete before retrying",
        }
        super().__init__(error_number or errno.EIO, message)


@dataclass(frozen=True)
class _JournalEntry:
    """A created path together with the inode identity owned by this invocation."""

    path: Path
    st_dev: int
    st_ino: int
    expected_size: int
    expected_sha256: str


@dataclass(frozen=True)
class _FileSample:
    """Read-window evidence for one published contract path."""

    owned: bool
    published: bool
    inspect_error: str | None = None


@dataclass(frozen=True)
class _FilePartition:
    """One-pass classification of published, owned, and non-published entries."""

    published: tuple[Path, ...]
    owned: tuple[Path, ...]
    nonpublished: tuple[Path, ...]


class _BootstrapJournal:
    """Track file tokens plus non-claiming directory/durability observations."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.file_entries: list[_JournalEntry] = []
        self.uncertain_file_paths: list[Path] = []
        self.uncertain_directory_paths: list[Path] = []
        self.durability_uncertain_file_paths: list[Path] = []
        self.durability_uncertain_directory_paths: list[Path] = []
        self._uncertain_paths: list[Path] = []
        self._durability_uncertain_paths: list[Path] = []

    @property
    def created_files(self) -> list[Path]:
        return [entry.path for entry in self.file_entries]

    @staticmethod
    def _record(paths: list[Path], path: Path) -> None:
        if path not in paths:
            paths.append(path)

    @property
    def uncertain_paths(self) -> tuple[Path, ...]:
        return tuple(self._uncertain_paths)

    @property
    def durability_uncertain_paths(self) -> tuple[Path, ...]:
        return tuple(self._durability_uncertain_paths)

    def record_uncertain_file(self, path: Path) -> None:
        self._record(self.uncertain_file_paths, path)
        self._record(self._uncertain_paths, path)

    def record_uncertain_directory(self, path: Path) -> None:
        self._record(self.uncertain_directory_paths, path)
        self._record(self._uncertain_paths, path)

    def record_file_durability_uncertain(self, path: Path) -> None:
        self._record(self.durability_uncertain_file_paths, path)
        self._record(self._durability_uncertain_paths, path)

    def record_directory_durability_uncertain(self, path: Path) -> None:
        self._record(self.durability_uncertain_directory_paths, path)
        self._record(self._durability_uncertain_paths, path)


def _before_contract_publication(root: Path) -> None:
    """Publication seam; each actual write still reopens paths with no-follow semantics."""

    del root


def _before_final_contract_verification(root: Path) -> None:
    """Test seam; success still depends on the following read-only token verification."""

    del root


def _validate_text(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    normalized = value.strip()
    if not normalized or "\x00" in normalized:
        raise ValueError(f"{label} must not be empty")
    if label == "domain id" and ("/" in normalized or "\\" in normalized or normalized in {".", ".."}):
        raise ValueError("domain id must not contain path traversal")
    return normalized


def _contract_root(domain_path: Path) -> Path:
    requested = Path(domain_path).expanduser()
    if not requested.is_absolute() or ".." in requested.parts:
        raise ValueError("domain path must be an absolute path without traversal")
    if requested.is_symlink():
        raise ValueError(f"domain path must not be a symlink: {requested}")
    root = requested.resolve(strict=False)
    if root.exists():
        mode = root.lstat().st_mode
        if not stat.S_ISDIR(mode):
            raise ValueError(f"domain path is not a directory: {root}")
    return root


def _preflight_contract_paths(root: Path) -> tuple[Path, ...]:
    """Reject every unsafe destination before the first bootstrap write."""

    targets = tuple(root / relative for relative in _CONTRACT_FILES)
    parents = {root}
    for target in targets:
        parent = target.parent
        while parent != root:
            parents.add(parent)
            parent = parent.parent

    for parent in sorted(parents, key=lambda path: len(path.parts)):
        if not parent.exists() and not parent.is_symlink():
            continue
        if parent.is_symlink() or not stat.S_ISDIR(parent.lstat().st_mode):
            raise ValueError(f"unsafe contract parent: {parent}")
    for target in targets:
        if not target.exists() and not target.is_symlink():
            continue
        mode = target.lstat().st_mode
        if target.is_symlink() or not stat.S_ISREG(mode):
            raise ValueError(f"unsafe contract target: {target}")
        _reject_incomplete_target(target, mode)
        if mode & 0o111:
            raise ValueError(f"executable contract target: {target}")
    return targets


def _reject_incomplete_target(path: Path, mode: int) -> None:
    if stat.S_IMODE(mode) == _INCOMPLETE_MODE:
        raise BootstrapWriteError(
            "incomplete content-contract sentinel requires manual recovery before retry",
            [],
            uncertain_paths=[path],
        )


def _verify_existing_manifest(root: Path, domain_id: str, domain_name: str, owner: str) -> None:
    manifest_path = root / "DOMAIN.yaml"
    if not manifest_path.exists():
        return
    manifest = load_domain_manifest(manifest_path)
    if (
        manifest.root != root
        or manifest.id != domain_id
        or manifest.display_name != domain_name
        or manifest.principal_ref != owner
    ):
        raise ValueError(f"conflicting existing DOMAIN.yaml: {manifest_path}")


def _unsupported_platform(operation: str, cause: BaseException | None = None) -> OSError:
    error = OSError(errno.ENOTSUP, f"secure contract publication unsupported: {operation}")
    if cause is not None:
        error.__cause__ = cause
    return error


def _secure_call(operation: str, function: Any, /, *args: Any, **kwargs: Any) -> Any:
    """Convert platform stubs into one stable, fail-closed publication error."""

    try:
        return function(*args, **kwargs)
    except NotImplementedError as error:
        raise _unsupported_platform(operation, error) from error


def _require_secure_publication_platform() -> None:
    required_flags = ("O_NOFOLLOW", "O_DIRECTORY", "O_EXCL")
    required_functions = ("open", "mkdir", "stat", "fsync", "fstat", "fchmod", "read", "write")
    if any(not hasattr(os, flag) for flag in required_flags) or any(not hasattr(os, name) for name in required_functions):
        raise _unsupported_platform("required flags or filesystem functions")

    supports_dir_fd = getattr(os, "supports_dir_fd", set())
    required_dir_fd = (os.open, os.mkdir, os.stat)
    if any(function not in supports_dir_fd for function in required_dir_fd):
        raise _unsupported_platform("dir_fd filesystem operations")
    if os.stat not in getattr(os, "supports_follow_symlinks", set()):
        raise _unsupported_platform("nofollow lstat operation")


def _open_directory(path: Path) -> int:
    return _secure_call("open directory", os.open, path, _DIRECTORY_FLAGS)


def _open_directory_at(parent_fd: int, name: str) -> int:
    return _secure_call("open directory at", os.open, name, _DIRECTORY_FLAGS, dir_fd=parent_fd)


def _stat_at(parent_fd: int, name: str) -> os.stat_result:
    return _secure_call("lstat at", os.stat, name, dir_fd=parent_fd, follow_symlinks=False)


def _fsync_fd(fd: int, operation: str) -> None:
    _secure_call(operation, os.fsync, fd)


def _record_created_file(journal: _BootstrapJournal, fd: int, path: Path, payload: bytes) -> None:
    try:
        info = _secure_call("fstat created file", os.fstat, fd)
    except OSError:
        journal.record_uncertain_file(path)
        journal.record_file_durability_uncertain(path)
        raise
    if not stat.S_ISREG(info.st_mode):
        journal.record_uncertain_file(path)
        journal.record_file_durability_uncertain(path)
        raise OSError(errno.EIO, f"created file changed before ownership could be recorded: {path}")
    journal.file_entries.append(_JournalEntry(path, info.st_dev, info.st_ino, len(payload), hashlib.sha256(payload).hexdigest()))


def _after_directory_creation(path: Path) -> None:
    """Test seam: directory names are deliberately never treated as deletable ownership."""

    del path


def _create_directory(journal: _BootstrapJournal, parent_fd: int, parent: Path, name: str) -> None:
    """Create a directory and retain only non-claiming evidence of that action."""

    path = parent / name
    _secure_call("mkdir at", os.mkdir, name, mode=0o755, dir_fd=parent_fd)
    journal.record_uncertain_directory(path)
    try:
        _fsync_fd(parent_fd, "fsync directory creation")
    except OSError:
        journal.record_directory_durability_uncertain(path)
        raise
    _after_directory_creation(path)


def _open_root(journal: _BootstrapJournal) -> int:
    root = journal.root
    try:
        return _open_directory(root)
    except FileNotFoundError:
        parent_fd = _open_directory(root.parent)
        try:
            try:
                _create_directory(journal, parent_fd, root.parent, root.name)
            except FileExistsError:
                pass
            return _open_directory_at(parent_fd, root.name)
        finally:
            os.close(parent_fd)


def _open_parent(root_fd: int, root: Path, target: Path, journal: _BootstrapJournal) -> int:
    """Open/create target.parent from root_fd without following a symlink."""

    relative_parts = target.parent.relative_to(root).parts
    current_fd = root_fd
    current_path = root
    try:
        for part in relative_parts:
            try:
                child_fd = _open_directory_at(current_fd, part)
            except FileNotFoundError:
                try:
                    _create_directory(journal, current_fd, current_path, part)
                except FileExistsError:
                    pass
                child_fd = _open_directory_at(current_fd, part)
            os.close(current_fd)
            current_fd = child_fd
            current_path = current_path / part
        return current_fd
    except BaseException:
        os.close(current_fd)
        raise


def _write_contract(path: Path, payload: bytes, journal: _BootstrapJournal) -> None:
    """Publish one preflighted file with O_EXCL and O_NOFOLLOW protection."""

    root_fd = _open_root(journal)
    parent_fd: int | None = None
    try:
        parent_fd = _open_parent(root_fd, journal.root, path, journal)
        try:
            current = _stat_at(parent_fd, path.name)
        except FileNotFoundError:
            current = None
        if current is not None:
            if not stat.S_ISREG(current.st_mode) or current.st_mode & 0o111:
                raise ValueError(f"unsafe contract target: {path}")
            try:
                _reject_incomplete_target(path, current.st_mode)
            except BootstrapWriteError:
                journal.record_uncertain_file(path)
                raise
            return
        fd = _secure_call(
            "create contract file",
            os.open,
            path.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            _INCOMPLETE_MODE,
            dir_fd=parent_fd,
        )
        try:
            _record_created_file(journal, fd, path, payload)
            try:
                written = 0
                while written < len(payload):
                    count = _secure_call("write contract file", os.write, fd, payload[written:])
                    if count == 0:
                        raise OSError("short write while publishing content contract")
                    written += count
                _fsync_fd(fd, "fsync contract file content")
                _secure_call("publish contract mode", os.fchmod, fd, _PUBLISHED_MODE)
                _fsync_fd(fd, "fsync contract file metadata")
            except OSError:
                journal.record_uncertain_file(path)
                journal.record_file_durability_uncertain(path)
                raise
        finally:
            os.close(fd)
        try:
            _fsync_fd(parent_fd, "fsync contract directory entry")
        except OSError:
            journal.record_file_durability_uncertain(path)
            raise
    finally:
        if parent_fd is not None:
            os.close(parent_fd)


def _open_existing_parent(root_fd: int, root: Path, target: Path) -> int:
    """Open target.parent from root_fd without creating or following anything."""

    current_fd = root_fd
    try:
        for part in target.parent.relative_to(root).parts:
            child_fd = _open_directory_at(current_fd, part)
            os.close(current_fd)
            current_fd = child_fd
        return current_fd
    except BaseException:
        os.close(current_fd)
        raise


def _open_file_parent(root: Path, path: Path) -> int:
    root_fd = _open_directory(root)
    return _open_existing_parent(root_fd, root, path)


def _identity_matches(entry: _JournalEntry, info: os.stat_result | None) -> bool:
    return bool(info and stat.S_ISREG(info.st_mode) and info.st_dev == entry.st_dev and info.st_ino == entry.st_ino)


def _published_signature(info: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        stat.S_IFMT(info.st_mode),
        stat.S_IMODE(info.st_mode),
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _sample_file_entry(root: Path, entry: _JournalEntry) -> _FileSample:
    """Close the no-follow read window before declaring a contract published."""

    parent_fd: int | None = None
    file_fd: int | None = None
    path_pre: os.stat_result | None = None
    fd_pre: os.stat_result | None = None
    fd_post: os.stat_result | None = None
    path_post: os.stat_result | None = None
    digest = hashlib.sha256()
    inspect_errors: list[str] = []

    def record_inspect_error(error: OSError) -> None:
        inspect_errors.append(str(error))

    try:
        parent_fd = _open_file_parent(root, entry.path)
        try:
            path_pre = _stat_at(parent_fd, entry.path.name)
            file_fd = _secure_call(
                "open published contract for verification",
                os.open,
                entry.path.name,
                os.O_RDONLY | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
            fd_pre = _secure_call("fstat published contract before read", os.fstat, file_fd)
            while True:
                chunk = _secure_call("read published contract", os.read, file_fd, 65536)
                if not chunk:
                    break
                digest.update(chunk)
        except OSError as error:
            record_inspect_error(error)
        try:
            if file_fd is not None:
                fd_post = _secure_call("fstat published contract after read", os.fstat, file_fd)
        except OSError as error:
            record_inspect_error(error)
        try:
            path_post = _stat_at(parent_fd, entry.path.name)
        except OSError as error:
            record_inspect_error(error)
        owned = (
            _identity_matches(entry, path_post)
            if path_post is not None
            else any(_identity_matches(entry, info) for info in (path_pre, fd_pre))
        )
        infos = (path_pre, fd_pre, fd_post, path_post)
        published = (
            not inspect_errors
            and all(_identity_matches(entry, info) for info in infos)
            and all(
                stat.S_IMODE(info.st_mode) == _PUBLISHED_MODE and info.st_size == entry.expected_size
                for info in infos
                if info is not None
            )
            and len({_published_signature(info) for info in infos if info is not None}) == 1
            and digest.hexdigest() == entry.expected_sha256
        )
        return _FileSample(owned, published, "; ".join(inspect_errors) or None)
    except OSError as error:
        return _FileSample(False, False, str(error))
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if parent_fd is not None:
            os.close(parent_fd)


def _partition_file_entries(root: Path, entries: list[_JournalEntry]) -> _FilePartition:
    """Sample each entry once and retain evidence needed by both error envelopes."""

    published: list[Path] = []
    owned: list[Path] = []
    nonpublished: list[Path] = []
    for entry in entries:
        sample = _sample_file_entry(root, entry)
        if sample.owned:
            owned.append(entry.path)
        if sample.published:
            published.append(entry.path)
        else:
            nonpublished.append(entry.path)
    return _FilePartition(tuple(published), tuple(owned), tuple(nonpublished))


def _is_incomplete_sentinel(root: Path, path: Path) -> bool:
    """Return true only for a currently observable regular mode-000 path."""

    parent_fd: int | None = None
    try:
        parent_fd = _open_file_parent(root, path)
        info = _stat_at(parent_fd, path.name)
        return stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == _INCOMPLETE_MODE
    except OSError:
        return False
    finally:
        if parent_fd is not None:
            os.close(parent_fd)


def _durability_paths(journal: _BootstrapJournal, partition: _FilePartition) -> list[Path]:
    """Retain durability evidence only where its original subject is still truthful."""

    tokenized_paths = {entry.path for entry in journal.file_entries}
    paths: list[Path] = []
    for path in journal.durability_uncertain_file_paths:
        if path in tokenized_paths:
            if path in partition.owned:
                paths.append(path)
        elif path in journal.uncertain_file_paths and _is_incomplete_sentinel(journal.root, path):
            paths.append(path)
    paths.extend(journal.durability_uncertain_directory_paths)
    return list(dict.fromkeys(paths))


def _publication_failure(error: BaseException, journal: _BootstrapJournal) -> BootstrapWriteError:
    """Sample evidence without mutating any path after a failed publication."""

    partition = _partition_file_entries(journal.root, journal.file_entries)
    durability_paths = _durability_paths(journal, partition)
    error_number = error.errno if isinstance(error, OSError) else None
    return BootstrapWriteError(
        "content-contract publication failed; no cleanup was attempted",
        list(partition.owned),
        uncertain_paths=[*journal.uncertain_paths, *partition.nonpublished],
        durability_uncertain_paths=durability_paths,
        error_number=error_number,
    )


def init_domain_content_contracts(
    domain_path: Path,
    *,
    domain_id: str,
    domain_name: str = "新域",
    owner: str = "未指定",
    domain_type_desc: str = "功能域",
    domain_purpose: str = "待定义",
    ssot_scope: str = "本域 KEMS 文件",
    key_files: str = _DEFAULT_KEY_FILES,
) -> list[Path]:
    """Create only the declarative content contracts for one DocumentDomain."""

    root = _contract_root(domain_path)
    domain_id = _validate_text(domain_id, "domain id")
    domain_name = _validate_text(domain_name, "domain name")
    owner = _validate_text(owner, "owner")
    _require_secure_publication_platform()
    targets = _preflight_contract_paths(root)
    _verify_existing_manifest(root, domain_id, domain_name, owner)

    manifest: dict[str, Any] = {
        "apiVersion": "l4/v1",
        "kind": "DomainManifest",
        "id": domain_id,
        "display_name": domain_name,
        "archetype": "library",
        "space_ref": "personal-space",
        "root": ".",
        "owners": [owner],
        "principal_ref": owner,
        "default_sensitivity": "private",
        "default_visibility": "private",
        "sharing_policy": "deny",
        "retention": "permanent",
        "authority_policy": "reference_library",
        "harness_profile_ref": "harness://library/v1",
        "lifecycle": "active",
        "policy_refs": ["policy://personal-space"],
    }
    files: dict[Path, str] = {
        root / "DOMAIN.yaml": yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        root / "Method.md": f"# Method — {domain_name}\n\n{domain_purpose}\n",
        root / "profiles" / "Profile.md": f"# Profile — {domain_name}\n\n- Owner: {owner}\n- Type: {domain_type_desc}\n",
        root / "ontology" / "DOMAIN_ONTOLOGY.md": f"# Domain ontology — {domain_name}\n\n- Scope: {ssot_scope}\n- Key files: {key_files}\n",
        root / "rubrics" / "QUALITY_RUBRIC.md": f"# Quality rubric — {domain_name}\n\n- Content remains declarative and canonical.\n",
    }
    payloads = {path: content.encode("utf-8") for path, content in files.items()}
    journal = _BootstrapJournal(root)
    try:
        _before_contract_publication(root)
        for path, payload in payloads.items():
            _write_contract(path, payload, journal)
        if set(targets) != set(payloads):  # defensive invariant for future template edits
            raise RuntimeError("contract preflight and output targets diverged")
        generated = load_domain_manifest(root / "DOMAIN.yaml")
        if (
            generated.root != root
            or generated.id != domain_id
            or generated.display_name != domain_name
            or generated.principal_ref != owner
        ):
            raise ContractError("L4-CONTRACT-001", "generated DOMAIN.yaml identity mismatch", root / "DOMAIN.yaml")
    except (ContractError, OSError, ValueError) as error:
        if journal.file_entries or journal.uncertain_paths:
            raise _publication_failure(error, journal) from None
        raise
    _before_final_contract_verification(root)
    partition = _partition_file_entries(root, journal.file_entries)
    if partition.nonpublished:
        durability_paths = _durability_paths(journal, partition)
        raise BootstrapWriteError(
            "content-contract publication failed final token verification; no cleanup was attempted",
            list(partition.owned),
            uncertain_paths=[*journal.uncertain_paths, *partition.nonpublished],
            durability_uncertain_paths=durability_paths,
        )
    return journal.created_files


def init_domain_kems(
    domain_path: Path,
    domain_name: str = "新域",
    owner: str = "未指定",
    domain_type_desc: str = "功能域",
    domain_purpose: str = "待定义",
    ssot_scope: str = "本域 KEMS 文件",
    key_files: str = _DEFAULT_KEY_FILES,
    *,
    domain_id: str | None = None,
) -> DeclarativeBootstrapResult:
    """Deprecated compatibility API; creates declarative contracts only."""

    warnings.warn(
        "init_domain_kems is deprecated; use l4-kernel domain init-content-contracts",
        DeprecationWarning,
        stacklevel=2,
    )
    return DeclarativeBootstrapResult(
        init_domain_content_contracts(
            domain_path,
            domain_id=domain_id or Path(domain_path).expanduser().resolve(strict=False).name,
            domain_name=domain_name,
            owner=owner,
            domain_type_desc=domain_type_desc,
            domain_purpose=domain_purpose,
            ssot_scope=ssot_scope,
            key_files=key_files,
        )
    )
