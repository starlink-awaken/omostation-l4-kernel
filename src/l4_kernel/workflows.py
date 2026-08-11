"""L4 declarative scenario catalog; execution authority belongs to OMO."""

from __future__ import annotations

from collections.abc import Callable

from l4_kernel import DomainRegistry
from l4_kernel.path_policy import legacy_execution_denied

# ═════════════════════════════════════════════════════════════════════
# 场景定义
# ═════════════════════════════════════════════════════════════════════


class WorkflowStep:
    """工作流步骤。"""

    def __init__(
        self, action: str, description: str, domain: str = "", condition: Callable | None = None, on_error: str = "stop"
    ):
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
    """Compatibility surface that refuses legacy L4 scenario execution."""

    def __init__(self, registry: DomainRegistry | None = None):
        self.registry = registry

    def execute(self, workflow: Workflow, **kwargs) -> dict:
        """Reject direct execution while preserving the legacy API shape."""
        return {**legacy_execution_denied("scenario_engine.execute"), "workflow": workflow.name}

    # ── YAML skill/workflow 直接执行 ─────────────────────────────────

    def run_skill(self, domain_id: str, skill_id: str, **params) -> dict:
        """拒绝 L4 直接执行 YAML skill；执行权归 OMO。"""
        return {**legacy_execution_denied("scenario_engine.run_skill"), "skill_id": skill_id, "domain_id": domain_id}

    def run_workflow(self, domain_id: str, workflow_id: str, **params) -> dict:
        """拒绝 L4 直接执行 YAML workflow；执行权归 OMO。"""
        return {
            **legacy_execution_denied("scenario_engine.run_workflow"),
            "workflow_id": workflow_id,
            "domain_id": domain_id,
        }


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
    """Resolve a predefined scenario, then refuse legacy L4 execution."""
    wf = SCENARIOS.get(name)
    if not wf:
        return {"status": "error", "message": f"Scenario '{name}' not found. Available: {list(SCENARIOS.keys())}"}

    engine = ScenarioEngine(registry)
    return engine.execute(wf, **kwargs)


def list_scenarios() -> dict[str, str]:
    """列出所有可用场景。"""
    return {name: wf.description for name, wf in SCENARIOS.items()}
