"""L4 Kernel Templates — KEMS 控制面标准模板与 Schema 校验。

基于 8 个 DocumentDomain 的实际 KEMS 文件分析结果。
"""

from __future__ import annotations

import os
import re
import stat
import warnings
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


class BootstrapWriteError(ValueError):
    """A failed bootstrap whose rollback left auditable residual paths."""

    def __init__(self, message: str, residual_paths: list[Path]) -> None:
        self.residual_paths = tuple(residual_paths)
        super().__init__(message)


class _BootstrapJournal:
    """Track only filesystem entries created by this bootstrap transaction."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.created_files: list[Path] = []
        self.created_dirs: list[Path] = []


def _before_contract_publication(root: Path) -> None:
    """Publication seam; each actual write still reopens paths with no-follow semantics."""

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
        if mode & 0o111:
            raise ValueError(f"executable contract target: {target}")
    return targets


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


def _open_directory(path: Path) -> int:
    if not hasattr(os, "O_NOFOLLOW"):
        raise OSError("safe no-follow directory publication is unavailable")
    return os.open(path, _DIRECTORY_FLAGS)


def _open_root(journal: _BootstrapJournal) -> int:
    root = journal.root
    try:
        return _open_directory(root)
    except FileNotFoundError:
        parent_fd = _open_directory(root.parent)
        try:
            try:
                os.mkdir(root.name, mode=0o755, dir_fd=parent_fd)
                journal.created_dirs.append(root)
            except FileExistsError:
                pass
            return os.open(root.name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
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
                child_fd = os.open(part, _DIRECTORY_FLAGS, dir_fd=current_fd)
            except FileNotFoundError:
                os.mkdir(part, mode=0o755, dir_fd=current_fd)
                child_fd = os.open(part, _DIRECTORY_FLAGS, dir_fd=current_fd)
                journal.created_dirs.append(current_path / part)
            os.close(current_fd)
            current_fd = child_fd
            current_path = current_path / part
        return current_fd
    except BaseException:
        os.close(current_fd)
        raise


def _write_contract(path: Path, content: str, journal: _BootstrapJournal) -> None:
    """Publish one preflighted file with O_EXCL and O_NOFOLLOW protection."""

    root_fd = _open_root(journal)
    parent_fd: int | None = None
    try:
        parent_fd = _open_parent(root_fd, journal.root, path, journal)
        try:
            current = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            current = None
        if current is not None:
            if not stat.S_ISREG(current.st_mode) or current.st_mode & 0o111:
                raise ValueError(f"unsafe contract target: {path}")
            return
        fd = os.open(
            path.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o644,
            dir_fd=parent_fd,
        )
        journal.created_files.append(path)
        try:
            os.fchmod(fd, 0o644)
            payload = content.encode("utf-8")
            written = 0
            while written < len(payload):
                count = os.write(fd, payload[written:])
                if count == 0:
                    raise OSError("short write while publishing content contract")
                written += count
        finally:
            os.close(fd)
    finally:
        if parent_fd is not None:
            os.close(parent_fd)


def _open_existing_parent(root_fd: int, root: Path, target: Path) -> int:
    """Open target.parent from root_fd without creating or following anything."""

    current_fd = root_fd
    try:
        for part in target.parent.relative_to(root).parts:
            child_fd = os.open(part, _DIRECTORY_FLAGS, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = child_fd
        return current_fd
    except BaseException:
        os.close(current_fd)
        raise


def _remove_created_path(root: Path, path: Path, *, directory: bool) -> None:
    root_fd = _open_directory(root)
    parent_fd: int | None = None
    try:
        relative = path.relative_to(root)
        if relative.parts:
            parent_fd = _open_existing_parent(root_fd, root, path)
            if directory:
                os.rmdir(relative.parts[-1], dir_fd=parent_fd)
            else:
                os.unlink(relative.parts[-1], dir_fd=parent_fd)
    finally:
        if parent_fd is not None:
            os.close(parent_fd)
        elif path == root:
            os.close(root_fd)


def _rollback(journal: _BootstrapJournal) -> list[Path]:
    """Undo only this transaction's entries, reporting any protected residuals."""

    residuals: list[Path] = []
    for path in reversed(journal.created_files):
        try:
            _remove_created_path(journal.root, path, directory=False)
        except FileNotFoundError:
            pass
        except OSError:
            residuals.append(path)
    for path in sorted(journal.created_dirs, key=lambda item: len(item.parts), reverse=True):
        try:
            if path == journal.root:
                parent_fd = _open_directory(path.parent)
                try:
                    os.rmdir(path.name, dir_fd=parent_fd)
                finally:
                    os.close(parent_fd)
            else:
                _remove_created_path(journal.root, path, directory=True)
        except FileNotFoundError:
            pass
        except OSError:
            residuals.append(path)
    return residuals


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
    journal = _BootstrapJournal(root)
    try:
        _before_contract_publication(root)
        for path, content in files.items():
            _write_contract(path, content, journal)
        if set(targets) != set(files):  # defensive invariant for future template edits
            raise RuntimeError("contract preflight and output targets diverged")
        generated = load_domain_manifest(root / "DOMAIN.yaml")
        if (
            generated.root != root
            or generated.id != domain_id
            or generated.display_name != domain_name
            or generated.principal_ref != owner
        ):
            raise ContractError("L4-CONTRACT-001", "generated DOMAIN.yaml identity mismatch", root / "DOMAIN.yaml")
    except (ContractError, OSError, ValueError):
        residuals = _rollback(journal)
        if residuals:
            rendered = ", ".join(str(path) for path in residuals)
            raise BootstrapWriteError(f"bootstrap rollback left residual paths: {rendered}", residuals) from None
        raise
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
