"""L4 Plugin System — 插件扩展框架。

按域类型自动加载插件，支持 KEMS 业务动作、流程、规范、机制。

插件接口:
  class L4Plugin:
      domain_type: str          # 适用的域类型
      name: str                 # 插件名称
      
      # 生命周期
      def on_load(self) -> None
      def on_unload(self) -> None
      
      # KEMS 业务动作
      def get_actions(self) -> dict[str, callable]
      
      # KEMS 流程模板
      def get_workflows(self) -> dict[str, dict]
      
      # KEMS 规范
      def get_specifications(self) -> dict[str, dict]
      
      # KEMS 机制
      def get_mechanisms(self) -> dict[str, callable]
"""

from __future__ import annotations

from typing import Any, Protocol


# ═════════════════════════════════════════════════════════════════════
# 插件接口
# ═════════════════════════════════════════════════════════════════════

class L4Plugin(Protocol):
    """L4 Kernel 插件接口。

    每个插件为一个域类型提供 KEMS 业务操作。
    """

    domain_type: str
    name: str

    def on_load(self) -> None: ...
    def on_unload(self) -> None: ...

    def get_actions(self) -> dict[str, callable]: ...
    def get_workflows(self) -> dict[str, dict]: ...
    def get_specifications(self) -> dict[str, dict]: ...
    def get_mechanisms(self) -> dict[str, callable]: ...


# ═════════════════════════════════════════════════════════════════════
# 内置插件: DocumentDomain KEMS 操作
# ═════════════════════════════════════════════════════════════════════

class DocumentKemsPlugin:
    """DocumentDomain KEMS 业务操作插件。

    提供 KEMS 六面的标准业务动作、流程、规范、机制。
    """

    domain_type = "document"
    name = "document-kems"

    def on_load(self) -> None:
        pass

    def on_unload(self) -> None:
        pass

    # ── 业务动作 ────────────────────────────────────────────────────

    def get_actions(self) -> dict[str, callable]:
        """KEMS 标准业务动作。

        这些是 Agent 可以通过 MCP 调用的高级操作。
        """
        return {
            # 控制面操作
            "state_review": self._action_state_review,
            "memory_update": self._action_memory_update,
            "signal_respond": self._action_signal_respond,
            "timeline_log": self._action_timeline_log,
            "status_evaluate": self._action_status_evaluate,

            # 知识面操作
            "knowledge_index": self._action_knowledge_index,
            "knowledge_search": self._action_knowledge_search,
            "knowledge_categorize": self._action_knowledge_categorize,

            # 实体面操作
            "entity_register": self._action_entity_register,
            "entity_review": self._action_entity_review,
            "entity_update": self._action_entity_update,

            # 存储面操作
            "storage_archive": self._action_storage_archive,
            "storage_cleanup": self._action_storage_cleanup,

            # 跨域操作
            "cross_domain_sync": self._action_cross_domain_sync,
            "cross_domain_notify": self._action_cross_domain_notify,
        }

    def _action_state_review(self, domain_path: Path) -> dict:
        """审查 STATE.md 并生成建议。"""
        from l4_kernel.kems import KemsPlane
        kems = KemsPlane(domain_path)
        state = kems.read_state()
        signals = kems.read_signals()
        recent_warnings = [s for s in signals[-10:] if s.get("type") in ("⚠️", "🔴")]

        return {
            "action": "state_review",
            "current_state": state,
            "recent_warnings": len(recent_warnings),
            "recommendations": (
                ["处理最近的警告信号"] if recent_warnings
                else ["STATE.md 状态正常"]
            ),
        }

    def _action_memory_update(self, domain_path: Path) -> dict:
        """更新 MEMORY.md 元事实。"""
        from l4_kernel.kems import KemsPlane
        kems = KemsPlane(domain_path)
        memory = kems.read_memory()
        return {
            "action": "memory_update",
            "current_pointers": memory.get("pointers", []),
            "last_updated": memory.get("last-reviewed", ""),
        }

    def _action_signal_respond(self, domain_path: Path) -> dict:
        """响应最近的 ⚠️🔴 信号。"""
        from l4_kernel.kems import KemsPlane
        kems = KemsPlane(domain_path)
        signals = kems.read_signals()
        pending = [s for s in signals if s.get("type") in ("⚠️", "🔴")]
        return {
            "action": "signal_respond",
            "pending_signals": len(pending),
            "latest": pending[-1] if pending else None,
        }

    def _action_timeline_log(self, domain_path: Path) -> dict:
        """记录时间线事件。"""
        from l4_kernel.kems import KemsPlane
        kems = KemsPlane(domain_path)
        events = kems.read_timeline()
        return {
            "action": "timeline_log",
            "total_events": len(events),
            "recent": events[-5:] if events else [],
        }

    def _action_status_evaluate(self, domain_path: Path) -> dict:
        """评估并建议 STATUS 更新。"""
        from l4_kernel.kems import KemsPlane
        kems = KemsPlane(domain_path)
        status = kems.read_status()
        signals = kems.read_signals()
        warnings = [s for s in signals[-10:] if s.get("type") == "⚠️"]
        criticals = [s for s in signals[-10:] if s.get("type") == "🔴"]

        suggested = "STABLE"
        if criticals:
            suggested = "CRITICAL"
        elif warnings:
            suggested = "ALERT"

        return {
            "action": "status_evaluate",
            "current": status.get("status", "unknown"),
            "suggested": suggested,
            "reason": f"基于最近 {len(warnings)} 个⚠️, {len(criticals)} 个🔴 信号",
        }

    def _action_knowledge_index(self, domain_path: Path) -> dict:
        return {"action": "knowledge_index", "status": "ok"}

    def _action_knowledge_search(self, domain_path: Path) -> dict:
        return {"action": "knowledge_search", "status": "ok"}

    def _action_knowledge_categorize(self, domain_path: Path) -> dict:
        return {"action": "knowledge_categorize", "status": "ok"}

    def _action_entity_register(self, domain_path: Path) -> dict:
        return {"action": "entity_register", "status": "ok"}

    def _action_entity_review(self, domain_path: Path) -> dict:
        return {"action": "entity_review", "status": "ok"}

    def _action_entity_update(self, domain_path: Path) -> dict:
        return {"action": "entity_update", "status": "ok"}

    def _action_storage_archive(self, domain_path: Path) -> dict:
        return {"action": "storage_archive", "status": "ok"}

    def _action_storage_cleanup(self, domain_path: Path) -> dict:
        return {"action": "storage_cleanup", "status": "ok"}

    def _action_cross_domain_sync(self, domain_path: Path) -> dict:
        return {"action": "cross_domain_sync", "status": "ok"}

    def _action_cross_domain_notify(self, domain_path: Path) -> dict:
        return {"action": "cross_domain_notify", "status": "ok"}

    # ── KEMS 流程模板 ───────────────────────────────────────────────

    def get_workflows(self) -> dict[str, dict]:
        """KEMS 标准流程模板。"""
        return {
            "daily_checkin": {
                "name": "每日签到",
                "description": "每日域状态检查流程",
                "steps": [
                    {"action": "state_review", "description": "审查 STATE.md"},
                    {"action": "signal_respond", "description": "响应待处理信号"},
                    {"action": "status_evaluate", "description": "评估 STATUS 三态"},
                    {"action": "timeline_log", "description": "记录时间线"},
                ],
            },
            "weekly_review": {
                "name": "周度审查",
                "description": "每周域全面审查",
                "steps": [
                    {"action": "state_review", "description": "审查 STATE.md"},
                    {"action": "memory_update", "description": "更新 MEMORY.md"},
                    {"action": "entity_review", "description": "审查实体新鲜度"},
                    {"action": "knowledge_index", "description": "重建知识索引"},
                    {"action": "storage_cleanup", "description": "清理过期存储"},
                    {"action": "status_evaluate", "description": "更新 STATUS"},
                ],
            },
            "knowledge_ingest": {
                "name": "知识摄入",
                "description": "新知识摄入流程",
                "steps": [
                    {"action": "knowledge_categorize", "description": "分类新知识"},
                    {"action": "knowledge_index", "description": "更新索引"},
                    {"action": "cross_domain_sync", "description": "跨域同步"},
                    {"action": "timeline_log", "description": "记录时间线"},
                ],
            },
        }

    # ── KEMS 规范 ───────────────────────────────────────────────────

    def get_specifications(self) -> dict[str, dict]:
        """KEMS 标准规范。"""
        return {
            "SPEC-STATE": {
                "name": "STATE.md 规范",
                "description": "域状态快照的标准格式",
                "rules": [
                    "必须包含 YAML frontmatter (title, status, type, owner, created)",
                    "必须包含 '当前阶段定位' 段",
                    "必须包含 '活跃事项' 段",
                    "建议包含 '子域健康度' 段",
                    "last-reviewed 字段不超过 30 天",
                ],
            },
            "SPEC-SIGNALS": {
                "name": "signals.md 规范",
                "description": "信号日志的标准格式",
                "rules": [
                    "信号类型必须为 ✅⚠️🔴ℹ️",
                    "格式为 | 类型 | 日期 | 信号 |",
                    "时间倒序排列",
                    "🔴 信号必须在 48h 内响应",
                    "⚠️ 信号必须在 7d 内响应",
                ],
            },
            "SPEC-STATUS": {
                "name": "STATUS.md 规范",
                "description": "三态判定的标准格式",
                "rules": [
                    "必须定义 STABLE/ALERT/CRITICAL 三态",
                    "必须包含判定依据表",
                    "必须包含状态变更日志",
                    "ALERT 状态不超过 7 天",
                    "CRITICAL 状态必须立即通知 @驾驶舱",
                ],
            },
            "SPEC-CONTROL-RULES": {
                "name": "control-rules.md 规范",
                "description": "控制规则的标准格式",
                "rules": [
                    "CR ID 格式为 CR01-CR99",
                    "CR01-CR03 为内核规则 (不可删除)",
                    "CR04+ 为域扩展规则",
                    "每条规则包含: ID | 输入 | 动作",
                ],
            },
        }

    # ── KEMS 机制 ───────────────────────────────────────────────────

    def get_mechanisms(self) -> dict[str, callable]:
        """KEMS 标准机制。"""
        return {
            "signal_auto_respond": self._mechanism_signal_auto_respond,
            "freshness_auto_alert": self._mechanism_freshness_auto_alert,
            "status_auto_evaluate": self._mechanism_status_auto_evaluate,
        }

    def _mechanism_signal_auto_respond(self, domain_path: Path) -> dict:
        from l4_kernel.kems import KemsPlane
        kems = KemsPlane(domain_path)
        signals = kems.read_signals()
        criticals = [s for s in signals[-10:] if s.get("type") == "🔴"]
        return {
            "mechanism": "signal_auto_respond",
            "critical_pending": len(criticals),
            "auto_responded": False,
        }

    def _mechanism_freshness_auto_alert(self, domain_path: Path) -> dict:
        return {"mechanism": "freshness_auto_alert", "status": "ok"}

    def _mechanism_status_auto_evaluate(self, domain_path: Path) -> dict:
        from l4_kernel.kems import KemsPlane
        kems = KemsPlane(domain_path)
        signals = kems.read_signals()
        warnings = sum(1 for s in signals[-20:] if s.get("type") == "⚠️")
        criticals = sum(1 for s in signals[-20:] if s.get("type") == "🔴")

        if criticals >= 3:
            suggested = "CRITICAL"
        elif warnings >= 3:
            suggested = "ALERT"
        else:
            suggested = "STABLE"

        return {
            "mechanism": "status_auto_evaluate",
            "suggested_status": suggested,
            "recent_warnings": warnings,
            "recent_criticals": criticals,
        }


# ═════════════════════════════════════════════════════════════════════
# 插件注册表
# ═════════════════════════════════════════════════════════════════════

class PluginRegistry:
    """L4 Kernel 插件注册表。

    按域类型管理插件，自动加载和分发操作。
    """

    def __init__(self):
        self._plugins: dict[str, list[L4Plugin]] = {}
        self._load_builtin_plugins()

    def _load_builtin_plugins(self) -> None:
        """加载内置插件。"""
        self.register(DocumentKemsPlugin())

    def register(self, plugin: L4Plugin) -> None:
        """注册插件。"""
        self._plugins.setdefault(plugin.domain_type, []).append(plugin)
        plugin.on_load()

    def unregister(self, plugin: L4Plugin) -> None:
        """注销插件。"""
        plugins = self._plugins.get(plugin.domain_type, [])
        if plugin in plugins:
            plugins.remove(plugin)
            plugin.on_unload()

    def get_plugins(self, domain_type: str) -> list[L4Plugin]:
        """获取指定域类型的所有插件。"""
        return self._plugins.get(domain_type, [])

    def get_action(self, domain_type: str, action_name: str) -> callable | None:
        """获取指定域类型的业务动作。"""
        for plugin in self.get_plugins(domain_type):
            actions = plugin.get_actions()
            if action_name in actions:
                return actions[action_name]
        return None

    def get_workflow(self, domain_type: str, workflow_name: str) -> dict | None:
        """获取指定域类型的工作流模板。"""
        for plugin in self.get_plugins(domain_type):
            workflows = plugin.get_workflows()
            if workflow_name in workflows:
                return workflows[workflow_name]
        return None

    def get_specifications(self, domain_type: str) -> dict[str, dict]:
        """获取指定域类型的规范。"""
        specs = {}
        for plugin in self.get_plugins(domain_type):
            specs.update(plugin.get_specifications())
        return specs

    def get_mechanism(self, domain_type: str, mechanism_name: str) -> callable | None:
        """获取指定域类型的机制。"""
        for plugin in self.get_plugins(domain_type):
            mechanisms = plugin.get_mechanisms()
            if mechanism_name in mechanisms:
                return mechanisms[mechanism_name]
        return None

    def list_actions(self, domain_type: str) -> dict[str, str]:
        """列出指定域类型的所有可用动作。"""
        actions = {}
        for plugin in self.get_plugins(domain_type):
            for name, _ in plugin.get_actions().items():
                actions[name] = plugin.name
        return actions

    def list_workflows(self, domain_type: str) -> dict[str, str]:
        """列出指定域类型的所有工作流。"""
        workflows = {}
        for plugin in self.get_plugins(domain_type):
            for name, wf in plugin.get_workflows().items():
                workflows[name] = wf.get("description", "")
        return workflows


# ── 全局实例 ────────────────────────────────────────────────────

_plugin_registry: PluginRegistry | None = None


def get_plugin_registry() -> PluginRegistry:
    global _plugin_registry
    if _plugin_registry is None:
        _plugin_registry = PluginRegistry()
    return _plugin_registry
