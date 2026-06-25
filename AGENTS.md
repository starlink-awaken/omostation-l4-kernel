# AGENTS.md — L4 Kernel Development Guide

> eCOS v5 L4 Self Layer · Domain Management Kernel

## Quick Commands

```bash
cd projects/l4-kernel
make test     # 测试
make lint     # ruff check
make fmt      # ruff format
make install  # uv sync
```

## Architecture

L4 Kernel 是 L4 自我层的管理面。它为 25 个域提供统一的 CRUD 接口。

### 调用关系

```
l4-kernel (L4 管理面)
    ↑ import
    ├── cockpit (L3) → MCP tools 调用
    ├── metaos (L2)  → cards_context
    ├── minerva (L2) → VaultSink
    └── omo (L2)     → 域审计

l4-kernel 不依赖任何 eCOS 项目
```

### 模块职责

| 模块 | 职责 |
|------|------|
| registry.py | DomainRegistry — 25域注册 + DOMAIN-INDEX.md 同步 |
| domain_types.py | 7种域类型特化 (Document/Config/Tool/...) |
| kems.py | KemsPlane — DocumentDomain 六面读写 + CardsPlane |
| health.py | DomainHealth — 跨域健康聚合 |
| schema.py | DomainValidator — 与 M1 Schema 对比校验 |
| templates.py | 域骨架生成 + KEMS 版本迁移 |
| signals.py | 跨域信号总线 |
| cli.py | CLI 入口 |

## Key Dependencies

- **pyyaml** — 唯一外部依赖
- 无 eCOS 项目依赖

## Testing Pattern

```bash
uv run pytest tests/ -q
```

## File Organization

- `src/l4_kernel/` — 19 个源文件
- `tests/` — 测试文件

## Workspace-Wide Governance (2026-06-24)

This project follows the workspace-level governance conventions documented in the root `AGENTS.md`:

- **Agent Mutation Protocol**: Any autonomous agent/cron/daemon that modifies workspace state must emit `agent_mutation_intent`, avoid direct file I/O to `.omo/`/`spaces/`, and commit immediately. See `.omo/standards/agent-mutation-protocol.md` for the full protocol.
- **SSOT Guardian**: Run `python3 bin/ssot-guardian.py` from the workspace root before committing to detect task-count, current-wave, submodule-pointer, or direct-omo-io drift.
- **direct-omo-io**: Scripts must route writes to `.omo/` through `omo CLI`, `projects/omo` core, or `projects/c2g` ingress — never via raw `open()/mkdir()/write_text()`.
- **Submodule Governance**: Commit changes inside the submodule first, then bump the root-repo pointer; `git submodule status` with a `+` prefix indicates pending drift.
