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
