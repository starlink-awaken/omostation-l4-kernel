"""L4 Skill Loader — 从域 _control/skills/ 和 _control/workflows/ 加载 YAML 声明。

支持:
- 读 skills/*.yaml → 返回 steps 列表（给 ScenarioEngine 执行）
- 读 workflows/*.yaml → 组合多 skill 为完整流程
- 文件不存在时返回空（不报错，静默降级）
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# Declarative actions understood by the current L4 runtime or retained as
# read-only compilation vocabulary during Phase 0. Execution stays separately
# governed; appearing here never grants write authority.
ACTION_CATALOG = frozenset(
    {
        "aggregate",
        "aggregate_signals",
        "analyze",
        "append",
        "append_signal",
        "archive",
        "check",
        "check_constraints",
        "check_contradictions",
        "classify",
        "cli",
        "compare_characters",
        "compare_entries",
        "compute",
        "compute_metrics",
        "create_entry",
        "cross_domain_notify",
        "cross_link",
        "cross_reference",
        "decompose",
        "detect_patterns",
        "diff",
        "exec",
        "execute_pipeline",
        "extract",
        "extract_concepts",
        "extract_meeting_elements",
        "extract_structured",
        "fetch",
        "freshness_check",
        "generate_dashboard",
        "generate_report",
        "grep",
        "health_check",
        "identify_source_type",
        "link_subdomain",
        "log_warning",
        "mcp_call",
        "rank",
        "read",
        "read_all",
        "read_file",
        "read_signals",
        "read_source",
        "recommend",
        "remind",
        "report",
        "resolve_output_path",
        "route",
        "run_check",
        "scan_cards",
        "scan_chapters",
        "scan_files",
        "search",
        "select_work",
        "summarize",
        "sync_todos",
        "todo_write",
        "update",
        "update_file",
        "update_section",
        "update_state",
        "update_table",
        "validate_domain",
        "verify_output",
        "write",
        "write_file",
        "write_md",
        "write_yaml",
    }
)

# ═════════════════════════════════════════════════════════════════════
# Skill 加载
# ═════════════════════════════════════════════════════════════════════


def load_skill(skill_path: Path) -> dict[str, Any] | None:
    """加载单个 skill YAML 文件。

    Args:
        skill_path: _control/skills/{name}.yaml 的绝对路径

    Returns:
        解析后的 skill dict, 文件不存在或格式错误返回 None
    """
    if not skill_path.exists():
        return None

    try:
        data = yaml.safe_load(skill_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "skill" not in data:
            return None
        skill = data["skill"]
        if "id" not in skill or "steps" not in skill:
            return None
        return skill
    except (yaml.YAMLError, OSError):
        return None


def load_all_skills(skills_dir: Path) -> list[dict[str, Any]]:
    """加载指定 skills 目录下的所有 skill。

    Args:
        skills_dir: _control/skills/ 路径

    Returns:
        按文件名排序的 skill dict 列表
    """
    if not skills_dir.is_dir():
        return []

    skills = []
    for yaml_file in sorted(skills_dir.glob("*.yaml")):
        skill = load_skill(yaml_file)
        if skill:
            skills.append(skill)
    return skills


def find_skill(skills_dir: Path, skill_id: str) -> dict[str, Any] | None:
    """按 ID 查找 skill。

    Args:
        skills_dir: _control/skills/ 路径
        skill_id: 如 "creative/append-signal"

    Returns:
        skill dict 或 None
    """
    if not skills_dir.is_dir():
        return None

    for yaml_file in skills_dir.glob("*.yaml"):
        skill = load_skill(yaml_file)
        if skill and skill.get("id") == skill_id:
            return skill
    return None


# ═════════════════════════════════════════════════════════════════════
# Workflow 加载
# ═════════════════════════════════════════════════════════════════════


def load_workflow(workflow_path: Path) -> dict[str, Any] | None:
    """加载单个 workflow YAML 文件。"""
    if not workflow_path.exists():
        return None

    try:
        data = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "workflow" not in data:
            return None
        wf = data["workflow"]
        if "id" not in wf or "skills" not in wf:
            return None
        return wf
    except (yaml.YAMLError, OSError):
        return None


def load_all_workflows(workflows_dir: Path) -> list[dict[str, Any]]:
    """加载指定 workflows 目录下的所有 workflow。"""
    if not workflows_dir.is_dir():
        return []

    workflows = []
    for yaml_file in sorted(workflows_dir.glob("*.yaml")):
        wf = load_workflow(yaml_file)
        if wf:
            workflows.append(wf)
    return workflows


def find_workflow(workflows_dir: Path, workflow_id: str) -> dict[str, Any] | None:
    """按 ID 查找 workflow。"""
    if not workflows_dir.is_dir():
        return None

    for yaml_file in workflows_dir.glob("*.yaml"):
        wf = load_workflow(yaml_file)
        if wf and wf.get("id") == workflow_id:
            return wf
    return None


# ═════════════════════════════════════════════════════════════════════
# 域内资产路径工具
# ═════════════════════════════════════════════════════════════════════


def domain_skills_dir(domain_path: Path) -> Path:
    """获取域的 skills 目录。"""
    return domain_path / "_control" / "skills"


def domain_workflows_dir(domain_path: Path) -> Path:
    """获取域的 workflows 目录。"""
    return domain_path / "_control" / "workflows"


def domain_agents_dir(domain_path: Path) -> Path:
    """获取域的 agents 目录。"""
    return domain_path / "_control" / "agents"


# ═════════════════════════════════════════════════════════════════════
# 列出域可执行资产摘要
# ═════════════════════════════════════════════════════════════════════


def domain_capabilities_summary(domain_path: Path) -> dict[str, list[str]]:
    """返回域的可执行资产摘要。

    Returns:
        {"skills": ["id1", "id2"], "workflows": ["id1"], "agents": ["id1"]}
    """
    skills = [s.get("id", "") for s in load_all_skills(domain_skills_dir(domain_path))]
    workflows = [w.get("id", "") for w in load_all_workflows(domain_workflows_dir(domain_path))]
    agents = []
    agents_dir = domain_agents_dir(domain_path)
    if agents_dir.is_dir():
        for yaml_file in sorted(agents_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "agent" in data:
                    agents.append(data["agent"].get("id", yaml_file.stem))
            except (yaml.YAMLError, OSError):
                pass

    return {
        "skills": skills,
        "workflows": workflows,
        "agents": agents,
    }
