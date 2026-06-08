"""L4 Kernel CLI 入口。"""

from __future__ import annotations

import json
import sys

from l4_kernel import DomainRegistry


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
    """显示域详情。"""
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
    print()
    return 0


def cmd_health(args: list[str]) -> int:
    """全域健康检查。"""
    registry = DomainRegistry()
    json_mode = "--json" in args

    health = registry.aggregate_health()
    if json_mode:
        print(json.dumps(health, ensure_ascii=False, indent=2))
    else:
        print(f"\nL4 全域健康")
        print(f"  总计: {health['total']} 域, 存在: {health['existing']}, 缺失: {health['missing']}")
        print(f"  健康率: {health['health_rate']}")
        print(f"\n  按类型:")
        for t, s in health["by_type"].items():
            icon = "✅" if s["missing"] == 0 else "⚠️"
            print(f"    {icon} {t}: {s['existing']}/{s['total']}")
        print()
    # Exit code: 0 = 全存在, 1 = 有 missing。X-Plane 探针用此判定。
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
        print("    domain info <domain_id>             域详情")
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
