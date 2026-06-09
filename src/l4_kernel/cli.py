"""L4 Kernel CLI 入口。"""

from __future__ import annotations

import json
import sys

from l4_kernel import DomainRegistry
from l4_kernel.consistency import check_consistency
from l4_kernel.skill_loader import (
    domain_capabilities_summary,
    domain_skills_dir,
    domain_workflows_dir,
    find_skill,
    find_workflow,
)
from l4_kernel.workflows import ScenarioEngine


def _get_engine() -> ScenarioEngine:
    return ScenarioEngine(DomainRegistry())


def cmd_list(args: list[str]) -> int:
    """列出所有域。"""
    registry = DomainRegistry()
    json_mode = "--json" in args
    domain_type = None
    for a in args:
        if a.startswith("--type="):
            domain_type = a.split("=", 1)[1]

    if domain_type:
        domains = registry.list_by_type(domain_type)
    else:
        domains = registry.list_all()

    if json_mode:
        print(json.dumps([d.to_dict() for d in domains], ensure_ascii=False, indent=2))
    else:
        print(f"\n{'ID':<22} {'名称':<14} {'类型':<12} {'存在':<6} 路径")
        print("-" * 90)
        for d in domains:
            icon = "✅" if d.exists() else "❌"
            print(f"{d.id:<22} {d.name:<14} {d.domain_type:<12} {icon:<6} {d.path}")
        print(f"\n共 {len(domains)} 域\n")

    return 0


def cmd_info(args: list[str]) -> int:
    """显示域详情（含可执行资产摘要）。"""
    if not args:
        print("用法: l4-kernel domain info <domain_id>", file=sys.stderr)
        return 1

    registry = DomainRegistry()
    d = registry.get(args[0])
    if not d:
        print(f"域未找到: {args[0]}", file=sys.stderr)
        return 1

    print(f"\n{d.name} ({d.id})")
    print(f"  类型:     {d.domain_type}")
    print(f"  路径:     {d.path}")
    print(f"  存在:     {'✅' if d.exists() else '❌'}")
    print(f"  BOS URI:  {d.bos_uri}")
    print(f"  治理层:   {d.governance_tier}")
    if d.kems_planes:
        print(f"  KEMS 面:  {', '.join(d.kems_planes)}")
    if d.capabilities:
        print(f"  能力:     {', '.join(d.capabilities)}")
    if d.exists():
        caps = domain_capabilities_summary(d.path)
        if caps["skills"]:
            print(f"  Skills:   {', '.join(caps['skills'])}")
        if caps["workflows"]:
            print(f"  Workflows: {', '.join(caps['workflows'])}")
        if caps["agents"]:
            print(f"  Agents:   {', '.join(caps['agents'])}")
    print()
    return 0


def cmd_skills(args: list[str]) -> int:
    """列出/查看域技能。"""
    if len(args) < 1:
        print("用法: l4-kernel skill list <domain_id> | skill show <domain_id> <skill_id>", file=sys.stderr)
        return 1

    sub = args[0]
    registry = DomainRegistry()

    if sub == "list":
        if len(args) < 2:
            print("用法: l4-kernel skill list <domain_id>", file=sys.stderr)
            return 1
        d = registry.get(args[1])
        if not d or not d.exists():
            print(f"域不可用: {args[1]}", file=sys.stderr)
            return 1
        caps = domain_capabilities_summary(d.path)
        if caps["skills"]:
            print(f"\n{d.name} Skills:")
            for sid in caps["skills"]:
                print(f"  - {sid}")
        else:
            print(f"\n{d.name} 无 registered skills")
        print()
        return 0

    if sub == "show":
        if len(args) < 3:
            print("用法: l4-kernel skill show <domain_id> <skill_id>", file=sys.stderr)
            return 1
        d = registry.get(args[1])
        if not d or not d.exists():
            print(f"域不可用: {args[1]}", file=sys.stderr)
            return 1
        skill = find_skill(domain_skills_dir(d.path), args[2])
        if not skill:
            print(f"Skill 未找到: {args[2]}", file=sys.stderr)
            return 1
        print(json.dumps(skill, ensure_ascii=False, indent=2))
        print()
        return 0

    if sub == "run":
        if len(args) < 3:
            print("用法: l4-kernel skill run <domain_id> <skill_id> [key=val ...]", file=sys.stderr)
            return 1
        engine = _get_engine()
        params = {}
        for a in args[3:]:
            if "=" in a:
                k, v = a.split("=", 1)
                params[k] = v
        result = engine.run_skill(args[1], args[2], **params)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print()
        return 0 if result["status"] == "ok" else 1

    print(f"未知子命令: skill {sub}", file=sys.stderr)
    return 1


def cmd_workflows(args: list[str]) -> int:
    """列出/查看域工作流。"""
    if len(args) < 1:
        print("用法: l4-kernel workflow list <domain_id> | workflow show <domain_id> <workflow_id>", file=sys.stderr)
        return 1

    sub = args[0]
    registry = DomainRegistry()

    if sub == "list":
        if len(args) < 2:
            print("用法: l4-kernel workflow list <domain_id>", file=sys.stderr)
            return 1
        d = registry.get(args[1])
        if not d or not d.exists():
            print(f"域不可用: {args[1]}", file=sys.stderr)
            return 1
        caps = domain_capabilities_summary(d.path)
        if caps["workflows"]:
            print(f"\n{d.name} Workflows:")
            for wid in caps["workflows"]:
                print(f"  - {wid}")
        else:
            print(f"\n{d.name} 无 registered workflows")
        print()
        return 0

    if sub == "show":
        if len(args) < 3:
            print("用法: l4-kernel workflow show <domain_id> <workflow_id>", file=sys.stderr)
            return 1
        d = registry.get(args[1])
        if not d or not d.exists():
            print(f"域不可用: {args[1]}", file=sys.stderr)
            return 1
        wf = find_workflow(domain_workflows_dir(d.path), args[2])
        if not wf:
            print(f"Workflow 未找到: {args[2]}", file=sys.stderr)
            return 1
        print(json.dumps(wf, ensure_ascii=False, indent=2))
        print()
        return 0

    if sub == "run":
        if len(args) < 3:
            print("用法: l4-kernel workflow run <domain_id> <workflow_id> [key=val ...]", file=sys.stderr)
            return 1
        engine = _get_engine()
        params = {}
        for a in args[3:]:
            if "=" in a:
                k, v = a.split("=", 1)
                params[k] = v
        result = engine.run_workflow(args[1], args[2], **params)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print()
        return 0 if result["status"] == "ok" else 1

    print(f"未知子命令: workflow {sub}", file=sys.stderr)
    return 1


def cmd_consistency(args: list[str]) -> int:
    """三源一致性校验。"""
    json_mode = "--json" in args
    result = check_consistency()
    if json_mode:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print("\nL4 三源一致性校验")
        print(f"  registry.py:  {result['total_registry']} 域")
        print(f"  vault-paths:  {result['total_vault_paths']} 路径")
        print(f"  DOMAIN-INDEX: {result['total_index']} 域")
        print(f"  差异:         {result['diff_count']} 处")
        print()
        if result["diff_count"] == 0:
            print("  ✅ 三源完全一致")
        else:
            for d in result["differences"]:
                print(f"  [{d['type']}] {d['domain']}")
                print(f"    {d['detail']}")
                if "fix" in d:
                    print(f"    建议修复: {d['fix']}")
    print()
    return 0 if result["diff_count"] == 0 else 1


def cmd_health(args: list[str]) -> int:
    """全域健康检查。"""
    registry = DomainRegistry()
    json_mode = "--json" in args

    health = registry.aggregate_health()
    if json_mode:
        print(json.dumps(health, ensure_ascii=False, indent=2))
    else:
        print("\nL4 全域健康")
        print(f"  总计: {health['total']} 域, 存在: {health['existing']}, 缺失: {health['missing']}")
        print(f"  健康率: {health['health_rate']}")
        print("\n  按类型:")
        for t, s in health["by_type"].items():
            icon = "✅" if s["missing"] == 0 else "⚠️"
            print(f"    {icon} {t}: {s['existing']}/{s['total']}")
        print()
    return 0 if health.get("missing", 0) == 0 else 1


def main() -> int:
    """l4-kernel CLI 入口。"""
    args = sys.argv[1:]

    if not args or args[0] in ("--help", "-h"):
        print("l4-kernel — L4 自我层管理面")
        print()
        print("  用法: l4-kernel <命令> [参数]")
        print()
        print("  命令:")
        print("    domain list [--type=<t>] [--json]  列出域")
        print("    domain info <domain_id>             域详情（含技能摘要）")
        print("    skill list <domain_id>              列出域技能")
        print("    skill show <domain_id> <id>         查看技能定义")
        print("    skill run <domain_id> <id> [k=v..]  执行技能")
        print("    workflow list <domain_id>           列出域工作流")
        print("    workflow show <domain_id> <id>      查看工作流定义")
        print("    workflow run <domain_id> <id> [k=v] 执行工作流")
        print("    consistency [--json]                三源一致性校验")
        print("    health [--json]                     全域健康")
        print("    mcp [--http|--sse] [--port=N]       启动 MCP Server")
        return 0

    cmd = args[0]

    if cmd == "domain":
        sub = args[1] if len(args) > 1 else "list"
        if sub == "list":
            return cmd_list(args[2:])
        if sub == "info":
            return cmd_info(args[2:])
        print(f"未知子命令: domain {sub}", file=sys.stderr)
        return 1

    if cmd == "skill":
        return cmd_skills(args[1:])

    if cmd == "workflow":
        return cmd_workflows(args[1:])

    if cmd == "consistency":
        return cmd_consistency(args[1:])

    if cmd == "health":
        return cmd_health(args[1:])

    if cmd == "mcp":
        from l4_kernel.mcp_server import main as mcp_main
        sys.argv = ["l4-kernel"] + args[1:]
        return mcp_main()

    print(f"未知命令: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
