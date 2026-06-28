"""L4 Kernel MCP Server — 42 tools, 20域全覆盖.

基于 fastmcp，提供标准化 L4 操作接口。
Agent 通过此 MCP Server 操作 L4 数据，无需直接接触文件系统。

启动:
    l4-kernel mcp          # stdio 模式
    l4-kernel mcp --http   # HTTP 模式 (port 7455)
    l4-kernel mcp --sse    # SSE 模式
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from l4_kernel import DomainRegistry
from l4_kernel.claude_injector import ClaudeInjector
from l4_kernel.health import DomainHealth
from l4_kernel.kems import CardsPlane, KemsPlane
from l4_kernel.lifecycle import DomainLifecycle
from l4_kernel.plugins import get_plugin_registry
from l4_kernel.signals import SignalBus
from l4_kernel.skill_loader import (
    domain_capabilities_summary,
    domain_skills_dir,
    domain_workflows_dir,
    find_skill,
    find_workflow,
)
from l4_kernel.templates import KemsValidator

# ── 全局实例 ──────────────────────────────────────────────────────

_registry = DomainRegistry()
_health = DomainHealth(_registry)
_signals = SignalBus(_registry)
_lifecycle = DomainLifecycle(_registry)
_injector = ClaudeInjector(_registry)
_plugins = get_plugin_registry()


def _reload_globals() -> dict:
    """重载所有全局实例 (用于运行时配置更新)。"""
    global _registry, _health, _signals, _lifecycle, _injector
    _registry = DomainRegistry()
    _health = DomainHealth(_registry)
    _signals = SignalBus(_registry)
    _lifecycle = DomainLifecycle(_registry)
    _injector = ClaudeInjector(_registry)
    return {"status": "ok", "message": "Global instances reloaded", "domains": len(_registry.list_all())}


def _ok(data: Any = None) -> str:
    return json.dumps(
        {"status": "ok", "data": data} if data is not None else {"status": "ok"}, ensure_ascii=False, default=str
    )


def _err(msg: str) -> str:
    return json.dumps({"status": "error", "message": msg}, ensure_ascii=False, default=str)


# ═════════════════════════════════════════════════════════════════════
# 域管理 (7 tools)
# ═════════════════════════════════════════════════════════════════════


def l4_domains_list(domain_type: str = "") -> str:
    """列出所有域或按类型筛选。"""
    if domain_type:
        domains = _registry.list_by_type(domain_type)
    else:
        domains = _registry.list_all()
    return json.dumps([d.to_dict() for d in domains], ensure_ascii=False, default=str)


def l4_domain_info(domain_id: str) -> str:
    """获取域详情。"""
    d = _registry.get(domain_id)
    if not d:
        return _err(f"Domain '{domain_id}' not found")
    return json.dumps(d.to_dict(), ensure_ascii=False, default=str)


def l4_domain_create(
    domain_id: str,
    name: str,
    domain_type: str,
    path: str,
    owner: str = "未指定",
    description: str = "",
    dry_run: bool = False,
) -> str:
    """创建新域。"""
    result = _lifecycle.create(
        domain_id,
        name,
        domain_type,
        path,
        owner=owner,
        description=description,
        dry_run=dry_run,
    )
    return json.dumps(result, ensure_ascii=False, default=str)


def l4_domain_validate(domain_id: str = "") -> str:
    """校验域完整性 (不指定=全部)。"""
    if domain_id:
        result = _lifecycle.validate(domain_id)
    else:
        result = _lifecycle.validate_all()
    return json.dumps(result, ensure_ascii=False, default=str)


def l4_domain_freeze(domain_id: str, reason: str = "") -> str:
    """冻结域。"""
    return json.dumps(_lifecycle.freeze(domain_id, reason), ensure_ascii=False, default=str)


def l4_domain_unfreeze(domain_id: str) -> str:
    """解冻域。"""
    return json.dumps(_lifecycle.unfreeze(domain_id), ensure_ascii=False, default=str)


def l4_domain_migrate(domain_id: str = "", to_version: str = "v5") -> str:
    """迁移 KEMS 版本 (不指定=所有 DocumentDomain)。"""
    if domain_id:
        result = _lifecycle.migrate(domain_id, to_version)
    else:
        result = _lifecycle.migrate_all_document_domains(to_version)
    return json.dumps(result, ensure_ascii=False, default=str)


# ═════════════════════════════════════════════════════════════════════
# KEMS 控制面操作 (8 tools)
# ═════════════════════════════════════════════════════════════════════


def _get_kems(domain_id: str):
    d = _registry.get(domain_id)
    if not d or not d.exists():
        return None
    return KemsPlane(d.path)


def l4_state_read(domain_id: str) -> str:
    """读取 STATE.md。"""
    kems = _get_kems(domain_id)
    if not kems:
        return _err(f"Domain '{domain_id}' not available")
    return json.dumps(kems.read_state(), ensure_ascii=False, default=str)


def l4_memory_read(domain_id: str) -> str:
    """读取 MEMORY.md。"""
    kems = _get_kems(domain_id)
    if not kems:
        return _err(f"Domain '{domain_id}' not available")
    return json.dumps(kems.read_memory(), ensure_ascii=False, default=str)


def l4_signals_list(domain_id: str, limit: int = 20) -> str:
    """读取最近 N 条信号。"""
    kems = _get_kems(domain_id)
    if not kems:
        return _err(f"Domain '{domain_id}' not available")
    signals = kems.read_signals()
    return json.dumps(signals[-limit:], ensure_ascii=False, default=str)


def l4_timeline_list(domain_id: str, limit: int = 20) -> str:
    """读取最近 N 条时间线。"""
    kems = _get_kems(domain_id)
    if not kems:
        return _err(f"Domain '{domain_id}' not available")
    events = kems.read_timeline()
    return json.dumps(events[-limit:], ensure_ascii=False, default=str)


def l4_status_read(domain_id: str) -> str:
    """读取 STATUS.md。"""
    kems = _get_kems(domain_id)
    if not kems:
        return _err(f"Domain '{domain_id}' not available")
    return json.dumps(kems.read_status(), ensure_ascii=False, default=str)


def l4_rules_read(domain_id: str) -> str:
    """读取 control-rules.md。"""
    kems = _get_kems(domain_id)
    if not kems:
        return _err(f"Domain '{domain_id}' not available")
    return json.dumps(kems.read_control_rules(), ensure_ascii=False, default=str)


def l4_entrypoint_read(domain_id: str) -> str:
    """读取 CLAUDE.md。"""
    kems = _get_kems(domain_id)
    if not kems:
        return _err(f"Domain '{domain_id}' not available")
    return json.dumps({"content": kems.read_claude_entrypoint()}, ensure_ascii=False, default=str)


def l4_signal_emit(domain_id: str, signal_type: str, message: str, cross_domain: bool = False) -> str:
    """发射信号。signal_type: ✅⚠️🔴ℹ️"""
    ok = _signals.emit(domain_id, signal_type, message, cross_domain=cross_domain)
    return _ok() if ok else _err("Failed to emit signal")


# ═════════════════════════════════════════════════════════════════════
# 搜索/校验 (5 tools)
# ═════════════════════════════════════════════════════════════════════


def l4_search(domain_id: str, keyword: str, max_results: int = 10) -> str:
    """全文搜索。"""
    kems = _get_kems(domain_id)
    if not kems:
        return _err(f"Domain '{domain_id}' not available")
    results = kems.search(keyword, max_results=max_results)
    return json.dumps(results, ensure_ascii=False, default=str)


def l4_cross_search(keyword: str, max_per_domain: int = 5) -> str:
    """跨所有 DocumentDomain 全文搜索。"""
    results = _health.cross_domain_search(keyword, max_per_domain=max_per_domain)
    return json.dumps(results, ensure_ascii=False, default=str)


def l4_kems_validate(domain_id: str) -> str:
    """KEMS 结构校验。"""
    d = _registry.get(domain_id)
    if not d or not d.exists():
        return _err(f"Domain '{domain_id}' not available")
    validator = KemsValidator(d.path)
    return json.dumps(validator.validate_all(), ensure_ascii=False, default=str)


def l4_freshness(domain_id: str = "") -> str:
    """新鲜度检查 (不指定=所有)。"""
    if domain_id:
        result = _health.check_freshness(domain_id)
    else:
        result = _health.check_all_freshness()
    return json.dumps(result, ensure_ascii=False, default=str)


def l4_files_list(domain_id: str, plane: str = "_control", pattern: str = "") -> str:
    """列出域文件。"""
    kems = _get_kems(domain_id)
    if not kems:
        return _err(f"Domain '{domain_id}' not available")
    files = kems.list_files(plane)
    result = [str(f.relative_to(kems.root)) for f in files]
    if pattern:
        result = [f for f in result if pattern.lower() in f.lower()]
    return json.dumps(result, ensure_ascii=False, default=str)


# ═════════════════════════════════════════════════════════════════════
# CARDS 操作 (5 tools)
# ═════════════════════════════════════════════════════════════════════


def _get_cards():
    cockpit = _registry.get("cockpit")
    if not cockpit or not cockpit.exists():
        return None
    return CardsPlane(cockpit.path)


def l4_cards_list(priority: str = "", status: str = "") -> str:
    """列出 CARDS。"""
    cards = _get_cards()
    if not cards:
        return _err("Cockpit domain not available")
    result = cards.scan_cards()
    if priority:
        result = [c for c in result if c["priority"] == priority]
    if status:
        result = [c for c in result if c["status"] == status]
    return json.dumps(result, ensure_ascii=False, default=str)


def l4_cards_get(card_id: str) -> str:
    """获取卡片详情。"""
    cards = _get_cards()
    if not cards:
        return _err("Cockpit domain not available")
    c = cards.get_card(card_id)
    if not c:
        return _err(f"Card '{card_id}' not found")
    return json.dumps(c, ensure_ascii=False, default=str)


def l4_cards_check(card_id: str = "") -> str:
    """CARDS 合规检查。"""
    cards = _get_cards()
    if not cards:
        return _err("Cockpit domain not available")
    return json.dumps(cards.check_compliance(card_id), ensure_ascii=False, default=str)


def l4_cards_search(keyword: str) -> str:
    """全文搜索 CARDS。"""
    cards = _get_cards()
    if not cards:
        return _err("Cockpit domain not available")
    all_cards = cards.scan_cards()
    kw = keyword.lower()
    result = [c for c in all_cards if kw in c.get("title", "").lower() or kw in c.get("id", "").lower()]
    return json.dumps(result, ensure_ascii=False, default=str)


def l4_cards_compliance(card_id: str) -> str:
    """操作前合规检查。"""
    cards = _get_cards()
    if not cards:
        return _err("Cockpit domain not available")
    return json.dumps(cards.check_compliance(card_id), ensure_ascii=False, default=str)


# ═════════════════════════════════════════════════════════════════════
# 健康/仪表板 (4 tools)
# ═════════════════════════════════════════════════════════════════════


def l4_health(domain_id: str = "") -> str:
    """全域/单域健康报告。"""
    result = _lifecycle.health_report(domain_id)
    return json.dumps(result, ensure_ascii=False, default=str)


def l4_dashboard() -> str:
    """生成全域 DASHBOARD。"""
    return json.dumps({"dashboard": _health.generate_dashboard()}, ensure_ascii=False, default=str)


def l4_signal_patterns(window_hours: int = 72) -> str:
    """检测跨域信号模式。"""
    patterns = _signals.detect_patterns(window_hours)
    return json.dumps(patterns, ensure_ascii=False, default=str)


def l4_claude_validate(domain_id: str = "") -> str:
    """CLAUDE.md Schema 注入状态。"""
    if domain_id:
        result = _injector.validate(domain_id)
    else:
        result = _injector.validate_all()
    return json.dumps(result, ensure_ascii=False, default=str)


# ═════════════════════════════════════════════════════════════════════
# 演化系统 (3 tools)
# ═════════════════════════════════════════════════════════════════════

WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", str(Path.home() / "Workspace")))


def l4_evolution_status() -> str:
    """查看全系统演化与 Drift 状态。"""
    try:
        root = WORKSPACE_ROOT
        loop_path = root / ".omo" / "_control" / "evolution" / "loop" / "history.json"

        status = {"loop_history": None, "active_drifts": 0}
        if loop_path.exists():
            status["loop_history"] = json.loads(loop_path.read_text(encoding="utf-8"))

        drift_dir = root / ".omo" / "_control" / "evolution" / "drift"
        if drift_dir.exists():
            status["active_drifts"] = len(list(drift_dir.glob("*.json")))

        return json.dumps(status, ensure_ascii=False, default=str)
    except Exception as e:  # noqa: BLE001  # defensive fallback
        return _err(f"Failed to read evolution status: {e}")


def l4_evolution_trigger(trigger_type: str = "manual") -> str:
    """手动触发全系统 Drift 演化闭环扫描。"""
    import os
    import subprocess

    try:
        script = str(WORKSPACE_ROOT / "scripts" / "opc_p6_self_evolve_cron.sh")
        env = dict(os.environ, OPC_TRIGGER=trigger_type)
        proc = subprocess.run(["bash", script], env=env, capture_output=True, text=True)
        if proc.returncode == 0:
            return _ok("Evolution trigger executed successfully. New tasks may have been planned.")
        else:
            return _err(f"Trigger failed: {proc.stderr}")
    except Exception as e:  # noqa: BLE001  # defensive fallback
        return _err(f"Trigger error: {e}")


def l4_evolution_tasks() -> str:
    """列出当前已自动发现但需人类审批的演进任务 (Planned)。"""
    try:
        import yaml

        root = WORKSPACE_ROOT
        planned_dir = root / ".omo" / "tasks" / "planned"

        tasks = []
        if planned_dir.exists():
            for f in planned_dir.glob("OPC-P6-SELF-EVOLUTION-*.yaml"):
                data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
                tasks.append(
                    {
                        "id": data.get("id"),
                        "title": data.get("title"),
                        "source": data.get("source"),
                        "approval_required": data.get("approval_required", True),
                    }
                )
        return json.dumps(tasks, ensure_ascii=False, default=str)
    except Exception as e:  # noqa: BLE001  # defensive fallback
        return _err(f"Failed to list evolution tasks: {e}")


# ═════════════════════════════════════════════════════════════════════
# 插件/工作流 (5 tools) + 文件操作 + 可执行资产
# ═════════════════════════════════════════════════════════════════════


def l4_plugin_actions(domain_type: str) -> str:
    """列出域类型的可用插件动作。"""
    actions = _plugins.list_actions(domain_type)
    return json.dumps(actions, ensure_ascii=False, default=str)


def l4_plugin_workflows(domain_type: str) -> str:
    """列出域类型的可用工作流。"""
    workflows = _plugins.list_workflows(domain_type)
    return json.dumps(workflows, ensure_ascii=False, default=str)


def l4_plugin_specs(domain_type: str) -> str:
    """获取域类型的规范。"""
    specs = _plugins.get_specifications(domain_type)
    return json.dumps(specs, ensure_ascii=False, default=str)


def l4_plugin_run_action(domain_type: str, action_name: str, domain_id: str) -> str:
    """执行插件动作。"""
    action = _plugins.get_action(domain_type, action_name)
    if not action:
        return _err(f"Action '{action_name}' not found for type '{domain_type}'")
    d = _registry.get(domain_id)
    if not d:
        return _err(f"Domain '{domain_id}' not found")
    result = action(d.path)
    return json.dumps(result, ensure_ascii=False, default=str)


def l4_plugin_run_mechanism(domain_type: str, mechanism_name: str, domain_id: str) -> str:
    """执行插件机制。"""
    mechanism = _plugins.get_mechanism(domain_type, mechanism_name)
    if not mechanism:
        return _err(f"Mechanism '{mechanism_name}' not found for type '{domain_type}'")
    d = _registry.get(domain_id)
    if not d:
        return _err(f"Domain '{domain_id}' not found")
    result = mechanism(d.path)
    return json.dumps(result, ensure_ascii=False, default=str)


# ── 文件操作 (4 tools: skill 的底层执行能力) ──────────────────────


def l4_file_write(domain_id: str, path: str, content: str) -> str:
    """写入文件到域内路径。如果文件存在则覆盖，目录不存在自动创建。"""
    d = _registry.get(domain_id)
    if not d or not d.exists():
        return _err(f"Domain '{domain_id}' not available")
    fp = d.path / path
    try:
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        return _ok({"path": str(fp), "size": len(content)})
    except OSError as e:
        return _err(f"Write failed: {e}")


def l4_file_append(domain_id: str, path: str, content: str) -> str:
    """追加内容到文件末尾。"""
    d = _registry.get(domain_id)
    if not d or not d.exists():
        return _err(f"Domain '{domain_id}' not available")
    fp = d.path / path
    try:
        fp.parent.mkdir(parents=True, exist_ok=True)
        with open(fp, "a", encoding="utf-8") as f:
            f.write(content)
        return _ok({"path": str(fp), "mode": "append"})
    except OSError as e:
        return _err(f"Append failed: {e}")


def l4_file_read(domain_id: str, path: str) -> str:
    """读取域内文件内容。"""
    d = _registry.get(domain_id)
    if not d or not d.exists():
        return _err(f"Domain '{domain_id}' not available")
    fp = d.path / path
    if not fp.exists():
        return _err(f"File not found: {fp}")
    try:
        return _ok({"path": str(fp), "content": fp.read_text(encoding="utf-8")})
    except OSError as e:
        return _err(f"Read failed: {e}")


def l4_entry_create(domain_id: str, parent_dir: str, name: str, content: str) -> str:
    """在域内目录下创建新条目（灵感/项目/日志等）。自动生成日期前缀。"""
    d = _registry.get(domain_id)
    if not d or not d.exists():
        return _err(f"Domain '{domain_id}' not available")
    from datetime import date

    today = date.today().isoformat()
    dir_path = d.path / parent_dir
    fp = dir_path / f"{today}-{name}.md"
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        return _ok({"path": str(fp), "filename": fp.name, "date": today})
    except OSError as e:
        return _err(f"Create entry failed: {e}")


# ── 可执行资产查询 (4 tools) ───────────────────────────────────────


def l4_skill_list(domain_id: str) -> str:
    """列出域的 skills。"""
    d = _registry.get(domain_id)
    if not d or not d.exists():
        return _err(f"Domain '{domain_id}' not available")
    caps = domain_capabilities_summary(d.path)
    return json.dumps({"domain": domain_id, "skills": caps["skills"]}, ensure_ascii=False, default=str)


def l4_skill_show(domain_id: str, skill_id: str) -> str:
    """查看 skill 定义。"""
    d = _registry.get(domain_id)
    if not d or not d.exists():
        return _err(f"Domain '{domain_id}' not available")
    skill = find_skill(domain_skills_dir(d.path), skill_id)
    if not skill:
        return _err(f"Skill '{skill_id}' not found in domain '{domain_id}'")
    return json.dumps(skill, ensure_ascii=False, default=str)


def l4_workflow_list(domain_id: str) -> str:
    """列出域的工作流。"""
    d = _registry.get(domain_id)
    if not d or not d.exists():
        return _err(f"Domain '{domain_id}' not available")
    caps = domain_capabilities_summary(d.path)
    return json.dumps({"domain": domain_id, "workflows": caps["workflows"]}, ensure_ascii=False, default=str)


def l4_workflow_show(domain_id: str, workflow_id: str) -> str:
    """查看工作流定义。"""
    d = _registry.get(domain_id)
    if not d or not d.exists():
        return _err(f"Domain '{domain_id}' not available")
    wf = find_workflow(domain_workflows_dir(d.path), workflow_id)
    if not wf:
        return _err(f"Workflow '{workflow_id}' not found in domain '{domain_id}'")
    return json.dumps(wf, ensure_ascii=False, default=str)


# ── Skill/Workflow 一键执行 (2 tools) ────────────────────────────

from l4_kernel.workflows import ScenarioEngine

_engine = ScenarioEngine(_registry)


def l4_skill_run(domain_id: str, skill_id: str, **params: str) -> str:
    """执行一个 skill。params 传入模板变量如 project_name='星尘'。"""
    result = _engine.run_skill(domain_id, skill_id, **params)
    return json.dumps(result, ensure_ascii=False, default=str)


def l4_workflow_run(domain_id: str, workflow_id: str, **params: str) -> str:
    """执行一个 workflow（按 skills 顺序编排）。"""
    result = _engine.run_workflow(domain_id, workflow_id, **params)
    return json.dumps(result, ensure_ascii=False, default=str)


# ═════════════════════════════════════════════════════════════════════
# 一致性校验 (1 tool)
# ═════════════════════════════════════════════════════════════════════

from l4_kernel.consistency import check_consistency


def l4_check_consistency() -> str:
    """三源一致性校验。"""
    return json.dumps(check_consistency(), ensure_ascii=False, default=str)

    # ═════════════════════════════════════════════════════════════════════
    # Config/Tool/Storage/Model/Engine 域操作 (8 tools)
    # ═════════════════════════════════════════════════════════════════════
    """列出配置域文件。"""
    from l4_kernel.domain_types import wrap_domain

    d = _registry.get(domain_id)  # noqa: F821
    if not d:
        return _err(f"Domain '{domain_id}' not found")  # noqa: F821
    w = wrap_domain(d)
    if hasattr(w, "list_configs"):
        return json.dumps(w.list_configs(), ensure_ascii=False, default=str)
    return _err(f"Domain '{domain_id}' is not a config domain")  # noqa: F821


def l4_config_read(domain_id: str, path: str) -> str:
    """读取配置文件。"""
    from l4_kernel.domain_types import wrap_domain

    d = _registry.get(domain_id)
    if not d:
        return _err(f"Domain '{domain_id}' not found")
    w = wrap_domain(d)
    if hasattr(w, "read_config"):
        data = w.read_config(path)
        return json.dumps(data, ensure_ascii=False, default=str) if data else _err("Config not found")
    return _err(f"Domain '{domain_id}' is not a config domain")


def l4_tools_list(domain_id: str) -> str:
    """列出工具域脚本。"""
    from l4_kernel.domain_types import wrap_domain

    d = _registry.get(domain_id)
    if not d:
        return _err(f"Domain '{domain_id}' not found")
    w = wrap_domain(d)
    if hasattr(w, "list_tools"):
        return json.dumps(w.list_tools(), ensure_ascii=False, default=str)
    return _err(f"Domain '{domain_id}' is not a tool domain")


def l4_storage_usage(domain_id: str) -> str:
    """磁盘使用情况。"""
    from l4_kernel.domain_types import wrap_domain

    d = _registry.get(domain_id)
    if not d:
        return _err(f"Domain '{domain_id}' not found")
    w = wrap_domain(d)
    if hasattr(w, "get_disk_usage"):
        return json.dumps(w.get_disk_usage(), ensure_ascii=False, default=str)
    return _err(f"Domain '{domain_id}' is not a storage domain")


def l4_models_list(domain_id: str) -> str:
    """列出模型文件。"""
    from l4_kernel.domain_types import wrap_domain

    d = _registry.get(domain_id)
    if not d:
        return _err(f"Domain '{domain_id}' not found")
    w = wrap_domain(d)
    if hasattr(w, "list_models"):
        return json.dumps(w.list_models(), ensure_ascii=False, default=str)
    return _err(f"Domain '{domain_id}' is not a model domain")


def l4_engine_check(domain_id: str, process_name: str = "") -> str:
    """检查引擎进程。"""
    from l4_kernel.domain_types import wrap_domain

    d = _registry.get(domain_id)
    if not d:
        return _err(f"Domain '{domain_id}' not found")
    w = wrap_domain(d)
    if hasattr(w, "check_process"):
        return json.dumps(w.check_process(process_name or None), ensure_ascii=False, default=str)
    return _err(f"Domain '{domain_id}' is not an engine domain")


def l4_engine_logs(domain_id: str, log_file: str = "daemon.log", lines: int = 20) -> str:
    """读取引擎日志。"""
    from l4_kernel.domain_types import wrap_domain

    d = _registry.get(domain_id)
    if not d:
        return _err(f"Domain '{domain_id}' not found")
    w = wrap_domain(d)
    if hasattr(w, "get_logs"):
        return json.dumps(w.get_logs(log_file, lines), ensure_ascii=False, default=str)
    return _err(f"Domain '{domain_id}' is not an engine domain")


def l4_workspace_search(domain_id: str, pattern: str) -> str:
    """工作空间文件搜索。"""
    from l4_kernel.domain_types import wrap_domain

    d = _registry.get(domain_id)
    if not d:
        return _err(f"Domain '{domain_id}' not found")
    w = wrap_domain(d)
    if hasattr(w, "search_files"):
        return json.dumps(w.search_files(pattern), ensure_ascii=False, default=str)
    return _err(f"Domain '{domain_id}' is not a workspace domain")


# ═════════════════════════════════════════════════════════════════════
# Tool 注册表 (用于 fastmcp)
# ═════════════════════════════════════════════════════════════════════

TOOLS = {
    # 系统
    "l4_reload": lambda: json.dumps(_reload_globals(), ensure_ascii=False),
    # 域管理 (7)
    "l4_domains_list": l4_domains_list,
    "l4_domain_info": l4_domain_info,
    "l4_domain_create": l4_domain_create,
    "l4_domain_validate": l4_domain_validate,
    "l4_domain_freeze": l4_domain_freeze,
    "l4_domain_unfreeze": l4_domain_unfreeze,
    "l4_domain_migrate": l4_domain_migrate,
    # KEMS 控制面 (8)
    "l4_state_read": l4_state_read,
    "l4_memory_read": l4_memory_read,
    "l4_signals_list": l4_signals_list,
    "l4_timeline_list": l4_timeline_list,
    "l4_status_read": l4_status_read,
    "l4_rules_read": l4_rules_read,
    "l4_entrypoint_read": l4_entrypoint_read,
    "l4_signal_emit": l4_signal_emit,
    # 搜索/校验 (5)
    "l4_search": l4_search,
    "l4_cross_search": l4_cross_search,
    "l4_kems_validate": l4_kems_validate,
    "l4_freshness": l4_freshness,
    "l4_files_list": l4_files_list,
    # CARDS (5)
    "l4_cards_list": l4_cards_list,
    "l4_cards_get": l4_cards_get,
    "l4_cards_check": l4_cards_check,
    "l4_cards_search": l4_cards_search,
    "l4_cards_compliance": l4_cards_compliance,
    # 健康/仪表板 (4)
    "l4_health": l4_health,
    "l4_dashboard": l4_dashboard,
    "l4_signal_patterns": l4_signal_patterns,
    "l4_claude_validate": l4_claude_validate,
    # 插件/工作流 (5)
    "l4_plugin_actions": l4_plugin_actions,
    "l4_plugin_workflows": l4_plugin_workflows,
    "l4_plugin_specs": l4_plugin_specs,
    "l4_plugin_run_action": l4_plugin_run_action,
    "l4_plugin_run_mechanism": l4_plugin_run_mechanism,
    # Config/Tool/Storage/Model/Engine (7)
    "l4_config_read": l4_config_read,
    "l4_tools_list": l4_tools_list,
    "l4_storage_usage": l4_storage_usage,
    "l4_models_list": l4_models_list,
    "l4_engine_check": l4_engine_check,
    "l4_engine_logs": l4_engine_logs,
    "l4_workspace_search": l4_workspace_search,
    # Self-Evolution (3)
    "l4_evolution_status": l4_evolution_status,
    "l4_evolution_trigger": l4_evolution_trigger,
    "l4_evolution_tasks": l4_evolution_tasks,
}


# ── MCP Server 入口 ──────────────────────────────────────────────


def _register_tools(mcp):
    """注册所有 42 个 MCP 工具。"""
    for name, fn in TOOLS.items():
        # 从函数名和 docstring 推断描述
        desc = (fn.__doc__ or name).split("\n")[0].strip()
        mcp.tool(name=name, description=desc)(fn)


def run_stdio():
    """启动 MCP stdio 服务器。"""
    try:
        from fastmcp import FastMCP

        mcp = FastMCP("l4-kernel")
        _register_tools(mcp)
        mcp.run(transport="stdio")
    except ImportError:
        print("fastmcp not installed. Install with: uv sync --extra dev", file=sys.stderr)
        sys.exit(1)


def run_http(port: int = 7455):
    """启动 MCP HTTP 服务器。"""
    try:
        import asyncio

        from fastmcp import FastMCP

        mcp = FastMCP("l4-kernel")
        _register_tools(mcp)
        asyncio.run(mcp.run_http_async(host="0.0.0.0", port=port))  # noqa: S104
    except ImportError:
        print("fastmcp not installed.", file=sys.stderr)
        sys.exit(1)


def run_sse(port: int = 7456):
    """启动 MCP SSE 服务器。"""
    try:
        import asyncio

        from fastmcp import FastMCP

        mcp = FastMCP("l4-kernel")
        _register_tools(mcp)
        asyncio.run(mcp.run_http_async(transport="sse", host="0.0.0.0", port=port))  # noqa: S104  # noqa: S104
    except ImportError:
        print("fastmcp not installed.", file=sys.stderr)
        sys.exit(1)


def main():
    """CLI 入口: l4-kernel mcp [--http|--sse]"""
    args = sys.argv[1:]
    if "--http" in args:
        port = 7455
        for a in args:
            if a.startswith("--port="):
                port = int(a.split("=", 1)[1])
        run_http(port)
    elif "--sse" in args:
        port = 7456
        for a in args:
            if a.startswith("--port="):
                port = int(a.split("=", 1)[1])
        run_sse(port)
    else:
        run_stdio()


if __name__ == "__main__":
    main()
