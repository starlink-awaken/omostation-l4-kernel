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

L4 Kernel 是 L4 自我层的管理面。它为 19 个域提供统一的 CRUD 接口。

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
| registry.py | DomainRegistry — 19域注册 + DOMAIN-INDEX.md 同步 |
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
