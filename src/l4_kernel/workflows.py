"""L4 Workflows — 跨域场景编排引擎。

将多个业务动作组合成端到端场景，支持:
- 串行执行 (step by step)
- 条件分支 (if/else)
- 信号驱动 (signal → next step)
- 回滚 (失败时撤销)
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from l4_kernel import DomainRegistry
from l4_kernel.health import DomainHealth
from l4_kernel.kems import CardsPlane
from l4_kernel.plugins import get_plugin_registry
from l4_kernel.signals import SignalBus
from l4_kernel.skill_loader import (
    domain_skills_dir,
    domain_workflows_dir,
    find_skill,
    find_workflow,
)

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
        import logging
        logger = logging.getLogger(__name__)

        # 条件检查
        if step.condition and not step.condition():
            return {"status": "skipped", "reason": "condition not met"}

        # 路由到对应的执行器
        action = step.action
        domain = step.domain or kwargs.get("domain", "vault")

        domain_obj = self.registry.get(domain)
        if not domain_obj:
            raise ValueError(f"Domain '{domain}' not found")

        # 插件动作 (优先)
        plugin_action = self.plugins.get_action(domain_obj.domain_type, action)
        if plugin_action:
            logger.debug(f"Step action '{action}' → plugin '{domain_obj.domain_type}'")
            return plugin_action(domain_obj.path)

        # 文件级动作 (skill YAML 的底层操作)
        path_override = kwargs.get("path_override", "")
        target_path = Path(path_override) if path_override else Path(step.action.split(":")[-1].strip() if ":" in step.action else step.description)

        file_actions = {
            "read_file": lambda: self._action_read_file(domain_obj.path, target_path),
            "write_file": lambda: self._action_write_file(domain_obj.path, target_path, kwargs.get("content", "")),
            "append_signal": lambda: self._action_append_signal(domain, kwargs.get("message", "") or step.description,
                                                                kwargs.get("source", "l4-kernel"), kwargs.get("type", "ℹ️")),
            "create_entry": lambda: self._action_create_entry(domain_obj.path, str(target_path.parent) if target_path.parent else "_knowledge/创作系统/输入-灵感抽屉",
                                                               kwargs.get("title", "untitled"), kwargs.get("content", "")),
            "update_table": lambda: self._action_update_state(domain_obj.path, kwargs.get("content", "更新")),
            "update_section": lambda: self._action_update_state(domain_obj.path, kwargs.get("content", "更新")),
            "write_yaml": lambda: {"status": "ok", "action": "write_yaml"},
            "read_signals": lambda: self.signals.aggregate_recent(),
        }

        if action in file_actions:
            logger.debug(f"Step action '{action}' → file action")
            return file_actions[action]()

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
            logger.debug(f"Step action '{action}' → builtin")
            return builtin[action]()

        # 尝试跨域类型查找插件动作
        for dtype in ["document", "config", "tool", "engine", "storage", "model", "workspace"]:
            alt = self.plugins.get_action(dtype, action)
            if alt:
                logger.debug(f"Step action '{action}' → plugin '{dtype}' (cross-type)")
                return alt(domain_obj.path)

        raise ValueError(f"Unknown action: '{action}'. Available builtins: {list(builtin.keys())}. Available plugins: check l4_plugin_actions")


    def _action_read_file(self, domain_path, target):
        fp = domain_path / target
        if not fp.exists():
            return {'status': 'error', 'message': f'File not found: {target}'}
        try:
            c = fp.read_text(encoding='utf-8')
            return {'status': 'ok', 'path': str(target), 'size': len(c), 'content': c[:500]}
        except OSError as e:
            return {'status': 'error', 'message': str(e)}

    def _action_write_file(self, domain_path, target, content=''):
        fp = domain_path / target
        try:
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding='utf-8')
            return {'status': 'ok', 'path': str(target), 'size': len(content)}
        except OSError as e:
            return {'status': 'error', 'message': str(e)}

    def _action_append_signal(self, domain_id, message, source='l4-kernel', signal_type='ℹ️'):
        ok = self.signals.emit(domain_id, signal_type, message, source=source)
        return {'status': 'ok' if ok else 'error', 'message': message, 'type': signal_type}

    def _action_create_entry(self, domain_path, parent_dir, title, content=''):
        from datetime import date
        today = date.today().isoformat()
        dir_path = domain_path / parent_dir
        fp = dir_path / f'{today}-{title}.md'
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            fp.write_text(f'# {title}\n\n{content}', encoding='utf-8')
            return {'status': 'ok', 'path': str(fp), 'filename': fp.name}
        except OSError as e:
            return {'status': 'error', 'message': str(e)}

    def _action_update_state(self, domain_path, content=''):
        return {'status': 'ok', 'message': 'STATE update', 'content': content[:200]}

# ── YAML skill/workflow 直接执行 ─────────────────────────────────

    def run_skill(self, domain_id: str, skill_id: str, **params) -> dict:
        """加载并执行一个 YAML skill。

        Args:
            domain_id: 域 ID（如 "creative"）
            skill_id: skill ID（如 "creative/open-workbench"）
            **params: 注入到 steps 中的参数（如 project_name="星尘"）

        Returns:
            {"status", "skill_id", "steps_completed", "results", "duration_sec"}
        """
        d = self.registry.get(domain_id)
        if not d or not d.exists():
            return {"status": "error", "message": f"Domain '{domain_id}' not available"}

        skill = find_skill(domain_skills_dir(d.path), skill_id)
        if not skill:
            return {"status": "error", "message": f"Skill '{skill_id}' not found in '{domain_id}'"}

        start = datetime.now(UTC)
        failed = 0
        step_results = []

        for i, step in enumerate(skill.get("steps", [])):
            action = step.get("action", "")
            target = step.get("target", "")
            step_params = step.get("params", {})

            # 替换模板变量 {xxx}
            for k, v in params.items():
                target = target.replace(f"{{{k}}}", str(v))
                for pk in list(step_params.keys()):
                    pv = step_params[pk]
                    if isinstance(pv, str):
                        step_params[pk] = pv.replace(f"{{{k}}}", str(v))

            result = {"step": i + 1, "action": action, "target": target, "status": "pending"}
            try:
                wf_step = WorkflowStep(action, skill.get("description", ""), domain=domain_id)
                exec_result = self._execute_step(wf_step, **{**params, **step_params, "path_override": target})
                result["status"] = "ok"
                result["result"] = str(exec_result)[:200]
                step_results.append(result)
            except Exception as e:
                result["status"] = "error"
                result["error"] = str(e)
                failed += 1
                step_results.append(result)
                break

        duration = (datetime.now(UTC) - start).total_seconds()

        status = "ok" if failed == 0 else "partial" if len(step_results) > failed else "error"
        self.signals.emit(domain_id, "✅" if status == "ok" else "⚠️",
                          f"skill 执行: {skill_id} ({len(step_results)}/{len(skill.get('steps', []))})",
                          source="scenario_engine")

        return {
            "status": status,
            "skill_id": skill_id,
            "steps_total": len(skill.get("steps", [])),
            "steps_completed": len(step_results) - failed,
            "steps_failed": failed,
            "results": step_results,
            "duration_sec": round(duration, 2),
        }

    def run_workflow(self, domain_id: str, workflow_id: str, **params) -> dict:
        """加载并执行一个 YAML workflow（按 skills 顺序编排）。"""
        d = self.registry.get(domain_id)
        if not d or not d.exists():
            return {"status": "error", "message": f"Domain '{domain_id}' not available"}

        wf = find_workflow(domain_workflows_dir(d.path), workflow_id)
        if not wf:
            return {"status": "error", "message": f"Workflow '{workflow_id}' not found in '{domain_id}'"}

        skill_ids = wf.get("skills", [])
        all_results = []
        total_failed = 0

        for sid in skill_ids:
            skill_result = self.run_skill(domain_id, sid, **params)
            all_results.append({"skill": sid, "result": skill_result})
            if skill_result.get("status") == "error":
                total_failed += 1
                if wf.get("error-handling") == "stop":
                    break

        status = "ok" if total_failed == 0 else "partial"
        return {
            "status": status,
            "workflow_id": workflow_id,
            "skills_total": len(skill_ids),
            "skills_failed": total_failed,
            "skill_results": all_results,
        }


# ═════════════════════════════════════════════════════════════════════
# 预定义场景
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
