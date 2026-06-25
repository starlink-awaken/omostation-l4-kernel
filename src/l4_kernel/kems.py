"""L4 KEMS Plane — DocumentDomain 六面统一读写接口。

KEMS 六面:
  _control/   — STATE, MEMORY, TIMELINE, signals, control-rules, STATUS, PLANE_INDEX, 决策日志
  _entities/  — 实体定义
  _knowledge/ — 方法论/经验/概念
  _storage/   — 资料库/订阅/灵感
  _archive/   — 历史归档
  _runtime/   — 运行时产物 (仅 cockpit 域)
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml


class KemsPlane:
    """DocumentDomain KEMS 六面操作抽象。

    为每个 DocumentDomain 提供统一的文件读写接口。
    """

    # 控制面标准文件列表
    CONTROL_FILES = [
        "STATE.md",
        "MEMORY.md",
        "TIMELINE.md",
        "signals.md",
        "control-rules.md",
        "STATUS.md",
        "PLANE_INDEX.md",
        "CLAUDE.md",
    ]

    def __init__(self, domain_path: Path) -> None:
        self._root = domain_path

    @property
    def root(self) -> Path:
        return self._root

    # ── 基础路径 ────────────────────────────────────────────────────

    def plane_path(self, plane: str) -> Path:
        """获取指定面的路径。"""
        return self._root / plane

    def control_path(self) -> Path:
        return self.plane_path("_control")

    def entities_path(self) -> Path:
        return self.plane_path("_entities")

    def knowledge_path(self) -> Path:
        return self.plane_path("_knowledge")

    def storage_path(self) -> Path:
        return self.plane_path("_storage")

    def archive_path(self) -> Path:
        return self.plane_path("_archive")

    # ── 控制面读写 ─────────────────────────────────────────────────

    def _read_yaml_md(self, filename: str, plane: str = "_control") -> dict:
        """读取带 YAML frontmatter 的 Markdown 文件。"""
        fp = self.plane_path(plane) / filename
        if not fp.exists():
            return {}
        text = fp.read_text(encoding="utf-8")
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 2:
                try:
                    return yaml.safe_load(parts[1]) or {}
                except yaml.YAMLError:
                    return {}
        # 无 frontmatter → 尝试纯 YAML
        try:
            return yaml.safe_load(text) or {}
        except yaml.YAMLError:
            return {}

    def _write_yaml_md(self, filename: str, data: dict, plane: str = "_control") -> None:
        """写入带 YAML frontmatter 的 Markdown 文件。"""
        fp = self.plane_path(plane) / filename
        fp.parent.mkdir(parents=True, exist_ok=True)
        frontmatter = yaml.dump(data, allow_unicode=True, default_flow_style=False).strip()
        content = f"---\n{frontmatter}\n---\n"
        fp.write_text(content, encoding="utf-8")

    def read_state(self) -> dict:
        """读取 STATE.md。"""
        return self._read_yaml_md("STATE.md")

    def write_state(self, data: dict) -> None:
        """写入 STATE.md。"""
        self._write_yaml_md("STATE.md", data)

    def read_memory(self) -> dict:
        """读取 MEMORY.md。"""
        return self._read_yaml_md("MEMORY.md")

    def write_memory(self, data: dict) -> None:
        """写入 MEMORY.md。"""
        self._write_yaml_md("MEMORY.md", data)

    def read_signals(self) -> list[dict]:
        """读取 signals.md 信号列表。"""
        data = self._read_yaml_md("signals.md")
        if isinstance(data, dict):
            signals = data.get("signals", [])
            return signals if isinstance(signals, list) else []
        if isinstance(data, list):
            return data
        return []

    def append_signal(self, event: dict) -> None:
        """追加信号到 signals.md。"""
        signals = self.read_signals()
        event.setdefault("ts", datetime.now(UTC).isoformat())
        signals.append(event)
        self._write_yaml_md("signals.md", {"signals": signals})

    def read_timeline(self) -> list[dict]:
        """读取 TIMELINE.md 事件列表。"""
        data = self._read_yaml_md("TIMELINE.md")
        if isinstance(data, dict):
            return data.get("events", [])
        if isinstance(data, list):
            return data
        return []

    def append_timeline(self, event: dict) -> None:
        """追加事件到 TIMELINE.md。"""
        events = self.read_timeline()
        event.setdefault("ts", datetime.now(UTC).isoformat())
        events.append(event)
        self._write_yaml_md("TIMELINE.md", {"events": events})

    def read_status(self) -> dict:
        """读取 STATUS.md 三态判定。"""
        return self._read_yaml_md("STATUS.md")

    def write_status(self, status: dict) -> None:
        """写入 STATUS.md。"""
        self._write_yaml_md("STATUS.md", status)

    def read_control_rules(self) -> dict:
        """读取 control-rules.md。"""
        return self._read_yaml_md("control-rules.md")

    def read_plane_index(self) -> dict:
        """读取 PLANE_INDEX.md 六面路由索引。"""
        return self._read_yaml_md("PLANE_INDEX.md")

    def read_claude_entrypoint(self) -> str:
        """读取 CLAUDE.md 入口协议。"""
        fp = self.control_path() / "CLAUDE.md"
        if fp.exists():
            return fp.read_text(encoding="utf-8")
        return ""

    # ── 全文搜索 ────────────────────────────────────────────────────

    def search(self, keyword: str, max_results: int = 10) -> list[dict]:
        """在当前域全文搜索。"""
        results = []
        if not keyword or not self._root.is_dir():
            return results
        kw = keyword.lower()
        for md_file in self._root.rglob("*.md"):
            if md_file.name.startswith("."):
                continue
            try:
                text = md_file.read_text(encoding="utf-8")
                if kw in text.lower():
                    lines = text.split("\n")
                    title = lines[0].replace("# ", "").strip() if lines else md_file.stem
                    idx = text.lower().index(kw)
                    snippet_start = max(0, idx - 40)
                    snippet_end = min(len(text), idx + 120)
                    results.append(
                        {
                            "path": str(md_file.relative_to(self._root)),
                            "title": title,
                            "snippet": "..." + text[snippet_start:snippet_end].replace("\n", " ").strip() + "...",
                        }
                    )
                    if len(results) >= max_results:
                        break
            except (OSError, ValueError):
                continue
        return results

    # ── 结构校验 ────────────────────────────────────────────────────

    def validate_structure(self) -> list[str]:
        """检查控制面标准文件完整性。"""
        missing = []
        ctrl = self.control_path()
        for f in self.CONTROL_FILES:
            if not (ctrl / f).exists():
                missing.append(f"missing: _control/{f}")
        # 检查决策日志目录
        decisions_dir = ctrl / "决策日志"
        if not decisions_dir.is_dir():
            missing.append("missing: _control/决策日志/")
        return missing

    def list_files(self, plane: str) -> list[Path]:
        """列出指定面的所有文件。"""
        p = self.plane_path(plane)
        if not p.is_dir():
            return []
        return sorted(p.rglob("*"))


class CardsPlane(KemsPlane):
    """CARDS 特化 — cockpit 域的卡片操作。

    基于 KemsPlane，额外提供 CARDS 系统的扫描/获取/合规检查。
    """

    @property
    def cards_dir(self) -> Path:
        return self._root / "CARDS"

    def scan_cards(self) -> list[dict]:
        """扫描 CARDS 目录下所有带 frontmatter 的 Markdown 文件。

        替代 cockpit_mcp.py 中的 _scan_cards()。
        """
        cards = []
        if not self.cards_dir.is_dir():
            return cards

        for md_file in sorted(self.cards_dir.rglob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8")
                if text.startswith("---"):
                    _, fm, __ = text.split("---", 2)
                    meta = yaml.safe_load(fm) or {}
                    if isinstance(meta, dict) and meta.get("id") and meta.get("type"):
                        cards.append(
                            {
                                "id": str(meta.get("id", "")),
                                "type": str(meta.get("type", "")),
                                "status": str(meta.get("status", "")),
                                "title": str(meta.get("title", "")),
                                "priority": str(meta.get("priority", "")),
                                "domain": str(meta.get("domain", "")),
                                "created": str(meta.get("created", "")),
                                "parent": str(meta.get("parent", "")),
                                "tags": str(meta.get("tags", "[]")),
                            }
                        )
            except (OSError, ValueError, yaml.YAMLError):
                continue

        cards.sort(
            key=lambda c: ({"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(c["priority"], 9), c["created"]),
            reverse=True,
        )
        return cards

    def get_card(self, card_id: str) -> dict | None:
        """按 ID 获取单个卡片。"""
        for c in self.scan_cards():
            if c["id"] == card_id:
                return c
        return None

    def check_compliance(self, card_id: str = "") -> dict:
        """操作前合规检查。"""
        violations = []

        # 检查卡片状态
        if card_id:
            card = self.get_card(card_id)
            if not card:
                violations.append(f"卡片 {card_id} 不存在")
            elif card["status"] in ("closed", "cancelled"):
                violations.append(f"卡片 {card_id} 已{card['status']}")

        # 检查 OMO 约束
        state = self._read_yaml_md("STATE.md")
        if state.get("code_freeze"):
            violations.append("代码冻结中: 禁止非紧急修改")

        return {
            "compliant": len(violations) == 0,
            "violations": violations,
            "guidance": "合规, 可以执行" if not violations else f"需要解决 {len(violations)} 个违规项",
        }
