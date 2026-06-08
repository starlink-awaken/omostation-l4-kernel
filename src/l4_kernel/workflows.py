"""L4 Workflows — 跨域场景编排引擎。

将多个业务动作组合成端到端场景，支持:
- 串行执行 (step by step)
- 条件分支 (if/else)
- 信号驱动 (signal → next step)
- 回滚 (失败时撤销)
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from l4_kernel import DomainRegistry
from l4_kernel.kems import KemsPlane, CardsPlane
from l4_kernel.health import DomainHealth
from l4_kernel.signals import SignalBus
from l4_kernel.plugins import get_plugin_registry


# ═════════════════════════════════════════════════════════════════════
# 场景定义
# ═════════════════════════════════════════════════════════════════════

class WorkflowStep:
    """工作流步骤。"""

    def __init__(self, action: str, description: str, domain: str = "",
                 condition: Callable | None = None, on_error: str = "stop"):
        self.action = action
        self.description = description
        self.domain = domain
        self.condition = condition
        self.on_error = on_error  # "stop" | "skip" | "continue"


class Workflow:
    """工作流定义。"""

    def __init__(self, name: str, description: str, steps: list[WorkflowStep]):
        self.name = name
        self.description = description
        self.steps = steps


# ═════════════════════════════════════════════════════════════════════
# 场景编排引擎
# ═════════════════════════════════════════════════════════════════════

class ScenarioEngine:
    """跨域场景编排引擎。

    执行预定义的跨域场景，记录每步结果，发射完成信号。
    """

    def __init__(self, registry: DomainRegistry | None = None):
        self.registry = registry or DomainRegistry()
        self.health = DomainHealth(self.registry)
        self.signals = SignalBus(self.registry)
        self.plugins = get_plugin_registry()

    def execute(self, workflow: Workflow, **kwargs) -> dict:
        """执行工作流。

        Returns:
            {status, workflow, steps_completed, steps_failed, results, duration_sec}
        """
        start = datetime.now(UTC)
        results = []
        completed = 0
        failed = 0

        for i, step in enumerate(workflow.steps):
            step_result = {
                "step": i + 1,
                "action": step.action,
                "description": step.description,
                "status": "pending",
            }

            try:
                result = self._execute_step(step, **kwargs)
                step_result["status"] = "ok"
                step_result["result"] = result
                completed += 1
            except Exception as e:
                step_result["status"] = "error"
                step_result["error"] = str(e)
                failed += 1
                if step.on_error == "stop":
                    results.append(step_result)
                    break
                elif step.on_error == "skip":
                    results.append(step_result)
                    continue

            results.append(step_result)

        duration = (datetime.now(UTC) - start).total_seconds()

        status = "ok" if failed == 0 else "partial" if completed > 0 else "error"

        # 发射完成信号
        self.signals.emit(
            "cockpit", "✅" if status == "ok" else "⚠️",
            f"场景完成: {workflow.name} ({completed}/{len(workflow.steps)})",
            source="scenario_engine",
        )

        return {
            "status": status,
            "workflow": workflow.name,
            "steps_completed": completed,
            "steps_failed": failed,
            "total_steps": len(workflow.steps),
            "results": results,
            "duration_sec": round(duration, 2),
        }

    def _execute_step(self, step: WorkflowStep, **kwargs) -> dict:
        """执行单个步骤。"""
        # 条件检查
        if step.condition and not step.condition():
            return {"status": "skipped", "reason": "condition not met"}

        # 路由到对应的执行器
        action = step.action
        domain = step.domain or kwargs.get("domain", "vault")

        domain_obj = self.registry.get(domain)
        if not domain_obj:
            raise ValueError(f"Domain '{domain}' not found")

        # 插件动作
        plugin_action = self.plugins.get_action(domain_obj.domain_type, action)
        if plugin_action:
            return plugin_action(domain_obj.path)

        # 内置动作
        builtin = {
            "health_check": lambda: self.health.aggregate_health(),
            "freshness_check": lambda: self.health.check_freshness(domain),
            "validate_domain": lambda: self._validate_domain(domain),
            "scan_cards": lambda: self._scan_cards(),
            "generate_dashboard": lambda: self.health.generate_dashboard(),
            "aggregate_signals": lambda: self.signals.aggregate_recent(),
            "detect_patterns": lambda: self.signals.detect_patterns(),
            "cross_domain_notify": lambda: self._cross_notify(kwargs.get("message", "")),
        }

        if action in builtin:
            return builtin[action]()

        raise ValueError(f"Unknown action: {action}")

    def _validate_domain(self, domain_id: str) -> dict:
        from l4_kernel.templates import KemsValidator
        d = self.registry.get(domain_id)
        if not d:
            raise ValueError(f"Domain '{domain_id}' not found")
        validator = KemsValidator(d.path)
        return {"violations": validator.validate_all()}

    def _scan_cards(self) -> list:
        cockpit = self.registry.get("cockpit")
        if not cockpit:
            return []
        cards = CardsPlane(cockpit.path)
        return cards.scan_cards()

    def _cross_notify(self, message: str) -> dict:
        for d in self.registry.list_document_domains():
            self.signals.emit(d.id, "ℹ️", message, source="scenario_engine")
        return {"notified_domains": len(self.registry.list_document_domains())}


# ═════════════════════════════════════════════════════════════════════
# 预定义场景
# ═════════════════════════════════════════════════════════════════════

SCENARIOS: dict[str, Workflow] = {
    # ── 场景 1: 研究→归档→CARDS ──
    "research_to_archive": Workflow(
        name="research_to_archive",
        description="研究完成 → Vault归档 → CARDS更新 → 信号发射",
        steps=[
            WorkflowStep("knowledge_categorize", "分类研究结果", domain="vault"),
            WorkflowStep("knowledge_index", "更新知识索引", domain="vault"),
            WorkflowStep("scan_cards", "检查相关 CARDS", domain="cockpit"),
            WorkflowStep("health_check", "更新全域健康", domain="cockpit"),
            WorkflowStep("cross_domain_notify", "通知相关域"),
        ],
    ),

    # ── 场景 2: 信号→诊断→修复 ──
    "signal_to_fix": Workflow(
        name="signal_to_fix",
        description="Schema violation → 诊断 → 修复 → 验证",
        steps=[
            WorkflowStep("validate_domain", "Schema 校验"),
            WorkflowStep("detect_patterns", "检测跨域模式"),
            WorkflowStep("freshness_check", "新鲜度检查"),
            WorkflowStep("health_check", "更新健康度"),
            WorkflowStep("cross_domain_notify", "通知相关域"),
        ],
    ),

    # ── 场景 3: 周度全局治理 ──
    "weekly_governance": Workflow(
        name="weekly_governance",
        description="全域周度审查 + DASHBOARD 生成",
        steps=[
            WorkflowStep("state_review", "审查 STATE", domain="vault"),
            WorkflowStep("state_review", "审查 STATE", domain="personal"),
            WorkflowStep("state_review", "审查 STATE", domain="cockpit"),
            WorkflowStep("aggregate_signals", "聚合跨域信号"),
            WorkflowStep("detect_patterns", "检测跨域模式"),
            WorkflowStep("scan_cards", "扫描 CARDS"),
            WorkflowStep("generate_dashboard", "生成 DASHBOARD"),
            WorkflowStep("cross_domain_notify", "周报通知"),
        ],
    ),

    # ── 场景 4: 域创建→初始化→注册 ──
    "domain_create": Workflow(
        name="domain_create",
        description="创建新域 → KEMS 骨架 → Schema 注入 → 信号",
        steps=[
            WorkflowStep("validate_domain", "检查域不存在"),
            WorkflowStep("cross_domain_notify", "通知新域创建"),
        ],
    ),

    # ── 场景 11: Agent 会话 ──
    "agent_session": Workflow(
        name="agent_session",
        description="Agent 会话 → 上下文注入 → 执行 → 归档",
        steps=[
            WorkflowStep("scan_cards", "获取 P0 CARDS", domain="cockpit"),
            WorkflowStep("aggregate_signals", "获取最近信号"),
            WorkflowStep("health_check", "全域健康检查"),
        ],
    ),
}


# ── 便捷函数 ────────────────────────────────────────────────────

def run_scenario(name: str, registry: DomainRegistry | None = None, **kwargs) -> dict:
    """执行预定义场景。"""
    wf = SCENARIOS.get(name)
    if not wf:
        return {"status": "error", "message": f"Scenario '{name}' not found. Available: {list(SCENARIOS.keys())}"}

    engine = ScenarioEngine(registry)
    return engine.execute(wf, **kwargs)


def list_scenarios() -> dict[str, str]:
    """列出所有可用场景。"""
    return {name: wf.description for name, wf in SCENARIOS.items()}
