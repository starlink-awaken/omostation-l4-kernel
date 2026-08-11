"""L4 Kernel CLI 入口。

P52-final 真治本: DomainRegistry 必须显式 path_overrides。
本模块提供 load_overrides_from_config() 从 TOML 配置读 path,
作为唯一生产入口。测试入口: l4_kernel.testing.default_overrides。
"""

from __future__ import annotations

import json
import os
import sys
import warnings
from dataclasses import asdict
from pathlib import Path
from typing import Any

from l4_kernel import DomainRegistry
from l4_kernel.config_loader import load_overrides_from_config, resolve_registry_path
from l4_kernel.consistency import check_consistency
from l4_kernel.content_plane import audit_content_plane
from l4_kernel.contracts import ContractError, load_domain_manifest
from l4_kernel.harness import HarnessRunner
from l4_kernel.harness_profiles import PROFILE_GATES
from l4_kernel.manifest_registry import ManifestRegistry
from l4_kernel.path_policy import legacy_execution_denied
from l4_kernel.skill_loader import (
    domain_capabilities_summary,
    domain_skills_dir,
    domain_workflows_dir,
    find_skill,
    find_workflow,
)
from l4_kernel.templates import BootstrapWriteError, init_domain_content_contracts

# 默认配置文件路径 (与 l4-kernel 同级目录)
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "l4_domain_paths.toml"


def _json_text(payload: Any) -> str:
    """Serialize JSON as strict UTF-8 while preserving normal Unicode text."""

    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    return text.encode("utf-8", errors="backslashreplace").decode("utf-8")


def _json_envelope(*, data: Any = None, error: dict[str, Any] | None = None) -> None:
    payload = {"ok": error is None, "data": data} if error is None else {"ok": False, "error": error}
    print(_json_text(payload))


def _json_data(data: Any, *, ok: bool) -> None:
    print(_json_text({"ok": ok, "data": data}))


def _contract_error(error: ContractError) -> dict[str, Any]:
    return {
        "code": error.code,
        "message": error.message,
        "path": str(error.path) if error.path is not None else None,
    }


def _option(args: list[str], name: str) -> str | None:
    for index, value in enumerate(args):
        if value == name and index + 1 < len(args):
            return args[index + 1]
        if value.startswith(f"{name}="):
            return value.split("=", 1)[1]
    return None


def _manifest_registry(args: list[str]) -> ManifestRegistry:
    explicit = _option(args, "--registry")
    return ManifestRegistry.load(resolve_registry_path(Path(explicit) if explicit else None))


def _get_registry(config_path: Path | None = None) -> DomainRegistry:
    """Load the manifest registry, with explicit legacy compatibility only."""

    registry_env = os.environ.get("L4_DOMAIN_REGISTRY")
    if registry_env:
        return ManifestRegistry.load(resolve_registry_path()).as_legacy_registry()

    path = config_path or DEFAULT_CONFIG_PATH
    if path.exists():
        warnings.warn(
            "legacy TOML domain registry is deprecated; configure L4_DOMAIN_REGISTRY",
            DeprecationWarning,
            stacklevel=2,
        )
        return DomainRegistry(path_overrides=load_overrides_from_config(path))

    if os.environ.get("L4_REGISTRY_MODE") == "legacy":
        warnings.warn(
            "L4_REGISTRY_MODE=legacy uses builtin metadata and is for rollback only",
            DeprecationWarning,
            stacklevel=2,
        )
        from l4_kernel.registry import _BUILTIN_DOMAINS

        return DomainRegistry.from_domains(_BUILTIN_DOMAINS)

    return ManifestRegistry.load(resolve_registry_path()).as_legacy_registry()


def cmd_list(args: list[str]) -> int:
    """列出所有域。"""
    registry = _get_registry()
    json_mode = "--json" in args
    domain_type = None
    for a in args:
        if a.startswith("--type="):
            domain_type = a.split("=", 1)[1]

    if domain_type:
        domains = registry.list_by_type(domain_type)  # type: ignore[reportArgumentType]
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

    registry = _get_registry()
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
    if sub == "run":
        _json_envelope(error=legacy_execution_denied("skill.run")["error"])
        return 1
    registry = _get_registry()

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

    print(f"未知子命令: skill {sub}", file=sys.stderr)
    return 1


def cmd_workflows(args: list[str]) -> int:
    """列出/查看域工作流。"""
    if len(args) < 1:
        print("用法: l4-kernel workflow list <domain_id> | workflow show <domain_id> <workflow_id>", file=sys.stderr)
        return 1

    sub = args[0]
    if sub == "run":
        _json_envelope(error=legacy_execution_denied("workflow.run")["error"])
        return 1
    registry = _get_registry()

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

    print(f"未知子命令: workflow {sub}", file=sys.stderr)
    return 1


def cmd_consistency(args: list[str]) -> int:
    """三源一致性校验。"""
    json_mode = "--json" in args
    result = check_consistency(_get_registry())
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
    registry = _get_registry()
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


def cmd_contract(args: list[str]) -> int:
    """Validate one DomainManifest and return a stable envelope."""

    if not args or args[0] != "validate" or len(args) < 2:
        _json_envelope(error={"code": "L4-CONFIG-002", "message": "usage: contract validate PATH", "path": None})
        return 2
    path = Path(args[1]).expanduser()
    try:
        manifest = load_domain_manifest(path)
    except ContractError as error:
        _json_envelope(error=_contract_error(error))
        return 1
    _json_envelope(data=asdict(manifest))
    return 0


def cmd_registry(args: list[str]) -> int:
    """List the explicit Phase 0 manifest registry."""

    if not args or args[0] != "list":
        _json_envelope(error={"code": "L4-CONFIG-002", "message": "usage: registry list", "path": None})
        return 2
    try:
        registry = _manifest_registry(args)
    except FileNotFoundError as error:
        _json_envelope(error={"code": "L4-CONFIG-002", "message": str(error), "path": None})
        return 2
    except ContractError as error:
        _json_envelope(error=_contract_error(error))
        return 2
    _json_envelope(data=registry.to_dict())
    return 0


def cmd_harness(args: list[str]) -> int:
    """Run read-only deterministic gates for one registered domain."""

    if not args or args[0] != "run" or len(args) < 2:
        _json_envelope(error={"code": "L4-CONFIG-002", "message": "usage: harness run DOMAIN_ID", "path": None})
        return 2
    try:
        registry = _manifest_registry(args)
    except FileNotFoundError as error:
        _json_envelope(error={"code": "L4-CONFIG-002", "message": str(error), "path": None})
        return 2
    except ContractError as error:
        _json_envelope(error=_contract_error(error))
        return 2

    manifest = registry.get(args[1])
    if manifest is None:
        _json_envelope(
            error={
                "code": "L4-HARNESS-003",
                "message": f"domain not found: {args[1]}",
                "path": str(registry.index_path),
            }
        )
        return 1
    raw_gates = _option(args, "--gates")
    gates = (
        tuple(item.strip() for item in raw_gates.split(",") if item.strip())
        if raw_gates
        else PROFILE_GATES[manifest.archetype]
    )
    health = HarnessRunner().run(manifest, gates)
    _json_envelope(data=health.to_dict())
    return 0 if health.ok else 1


def cmd_content(args: list[str]) -> int:
    """Audit one Documents root as a declarative content plane."""

    if not args or args[0] != "audit" or len(args) < 2:
        _json_envelope(error={"code": "L4-CONFIG-002", "message": "usage: content audit ROOT --json", "path": None})
        return 2
    root = Path(args[1]).expanduser()
    try:
        report = audit_content_plane(root)
    except ValueError as error:
        _json_envelope(error={"code": "L4-CONFIG-002", "message": str(error), "path": str(root)})
        return 2
    _json_data(report.to_dict(), ok=report.ok)
    return 0 if report.ok else 1


def cmd_domain_init_content_contracts(args: list[str]) -> int:
    """Initialize one path with the validated declarative content contracts."""

    if not args or args[0].startswith("-") or not args[0].strip():
        _json_envelope(
            error={
                "code": "L4-CONFIG-002",
                "message": "usage: domain init-content-contracts ROOT --domain-id ID [--name NAME] [--owner OWNER]",
                "path": None,
            }
        )
        return 2

    root = Path(args[0]).expanduser()
    options = {"--domain-id": None, "--name": root.name, "--owner": "未指定"}
    seen: set[str] = set()
    index = 1
    while index < len(args):
        option = args[index]
        if option not in options or option in seen or index + 1 >= len(args):
            _json_envelope(
                error={
                    "code": "L4-CONFIG-002",
                    "message": "usage: domain init-content-contracts ROOT --domain-id ID [--name NAME] [--owner OWNER]",
                    "path": str(root),
                }
            )
            return 2
        value = args[index + 1]
        if value.startswith("--") or not value.strip():
            _json_envelope(
                error={
                    "code": "L4-CONFIG-002",
                    "message": f"{option} must be provided once and be non-empty",
                    "path": str(root),
                }
            )
            return 2
        options[option] = value
        seen.add(option)
        index += 2

    try:
        if options["--domain-id"] is None:
            raise ValueError("--domain-id is required")
        created = init_domain_content_contracts(
            root,
            domain_id=options["--domain-id"],
            domain_name=options["--name"],
            owner=options["--owner"],
        )
        manifest = load_domain_manifest(root / "DOMAIN.yaml")
        audit = audit_content_plane(root)
    except ContractError as error:
        _json_envelope(error=_contract_error(error))
        return 1
    except BootstrapWriteError as error:
        _json_envelope(
            error={
                "code": "L4-CONFIG-002",
                "message": str(error),
                "path": str(root),
                "residual_paths": [str(path) for path in error.residual_paths],
                "uncertain_paths": [str(path) for path in error.uncertain_paths],
                "durability_uncertain_paths": [str(path) for path in error.durability_uncertain_paths],
                "directory_entry_durability_uncertain_paths": [
                    str(path) for path in error.directory_entry_durability_uncertain_paths
                ],
                "recovery": error.recovery,
            }
        )
        return 2
    except (OSError, ValueError) as error:
        _json_envelope(error={"code": "L4-CONFIG-002", "message": str(error), "path": str(root)})
        return 2
    _json_data(
        {"created_files": [str(path) for path in created], "manifest": asdict(manifest), "audit": audit.to_dict()},
        ok=audit.ok,
    )
    return 0 if audit.ok else 1


def main() -> int:
    """l4-kernel CLI 入口。"""
    args = sys.argv[1:]

    if (
        args
        and args[0] in {"domain", "skill", "workflow", "consistency", "health"}
        and args[1:2] != ["init-content-contracts"]
    ):
        print("⚠️ 该 L4 legacy 命令已弃用，请迁移到 contract/registry/harness 或 cockpit", file=sys.stderr)

    if not args or args[0] in ("--help", "-h"):
        print("l4-kernel — L4 自我层管理面")
        print()
        print("  用法: l4-kernel <命令> [参数]")
        print()
        print("  命令:")
        print("    contract validate PATH --json       校验 DomainManifest")
        print("    registry list --registry PATH --json 列出显式知识域")
        print("    harness run DOMAIN_ID --gates ...   运行只读确定性门禁")
        print("    content audit ROOT --json           审计 Documents 内容面边界")
        print("    domain init-content-contracts ROOT --domain-id ID  初始化声明式内容契约")
        print("    domain list/info ...                legacy 域视图")
        print("    skill list/show/run ...             legacy 技能入口")
        print("    workflow list/show/run ...          legacy 工作流入口")
        print("    consistency [--json]                三源一致性校验")
        print("    health [--json]                     全域健康")
        print("    mcp [--http|--sse] [--port=N]       启动 MCP Server")
        return 0

    cmd = args[0]

    if cmd == "contract":
        return cmd_contract(args[1:])

    if cmd == "registry":
        return cmd_registry(args[1:])

    if cmd == "harness":
        return cmd_harness(args[1:])

    if cmd == "content":
        return cmd_content(args[1:])

    if cmd == "domain":
        sub = args[1] if len(args) > 1 else "list"
        if sub == "init-content-contracts":
            return cmd_domain_init_content_contracts(args[2:])
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
        return mcp_main()  # type: ignore[reportReturnType]

    print(f"未知命令: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
