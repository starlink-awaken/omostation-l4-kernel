"""L4 Kernel Templates — KEMS 控制面标准模板与 Schema 校验。

基于 8 个 DocumentDomain 的实际 KEMS 文件分析结果。
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import yaml

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
        except Exception:  # defensive fallback  # noqa: BLE001
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
        except Exception:  # defensive fallback  # noqa: BLE001
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
        except Exception:  # defensive fallback  # noqa: BLE001
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
        except Exception:  # defensive fallback  # noqa: BLE001
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
            except Exception:  # defensive fallback  # noqa: BLE001
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


def init_domain_kems(
    domain_path: Path,
    domain_name: str = "新域",
    owner: str = "未指定",
    domain_type_desc: str = "功能域",
    domain_purpose: str = "待定义",
    ssot_scope: str = "本域 KEMS 文件",
    key_files: str = "CARDS/ · _control/ · _knowledge/ · _storage/",
) -> list[Path]:
    """为 DocumentDomain 创建标准 KEMS 六面骨架。

    Returns:
        创建的文件列表。
    """
    created = []

    # 创建六面目录
    for plane in ["_control", "_entities", "_knowledge", "_storage", "_archive"]:
        p = domain_path / plane
        p.mkdir(parents=True, exist_ok=True)
        created.append(p)

    # 创建决策日志目录
    decisions = domain_path / "_control" / "决策日志"
    decisions.mkdir(parents=True, exist_ok=True)
    created.append(decisions)

    # 生成控制面文件
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    params = {
        "domain_name": domain_name,
        "owner": owner,
        "created": today,
        "domain_type_desc": domain_type_desc,
        "domain_purpose": domain_purpose,
        "ssot_scope": ssot_scope,
        "key_files": key_files,
    }

    files = {
        "MEMORY.md": MEMORY_TEMPLATE.format(**params),
        "STATUS.md": STATUS_TEMPLATE.format(**params),
        "signals.md": SIGNALS_TEMPLATE.format(**params),
        "control-rules.md": CONTROL_RULES_TEMPLATE.format(**params),
        "STATE.md": f"# STATE — {domain_name} 状态\n\n## 当前阶段定位\n\n## 活跃事项\n\n## 子域健康度\n",
        "CLAUDE.md": f"# CLAUDE.md — {domain_name}\n\n域入口协议。\n",
        "PLANE_INDEX.md": f"# PLANE_INDEX — {domain_name}\n\n六平面路由索引。\n",
    }

    for fname, content in files.items():
        fp = domain_path / "_control" / fname
        if not fp.exists():
            fp.write_text(content, encoding="utf-8")
            created.append(fp)

    return created
