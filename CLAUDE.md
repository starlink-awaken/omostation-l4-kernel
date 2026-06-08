# CLAUDE.md — L4 Kernel

> eCOS v5 L4 Self Layer · 管理面 · 19域统一注册 + KEMS六面操作

---

## 项目身份

l4-kernel 是 L4 自我层的**管理面**。它为 19 个域提供统一的注册、读写、校验和健康聚合。

**核心职责**：
1. **DomainRegistry** — 19 域统一注册，与 DOMAIN-INDEX.md 双向同步
2. **KemsPlane** — DocumentDomain 六面文件统一读写
3. **DomainHealth** — 跨域健康聚合 + 全局 DASHBOARD

---

## 架构

```
l4_kernel/
├── registry.py       ← DomainRegistry (19域注册 + 路径解析)
├── domain_types.py   ← 7种域类型 (Document/Config/Tool/...)
├── kems.py           ← KemsPlane (六面读写) + CardsPlane
├── health.py         ← DomainHealth (跨域聚合)
├── schema.py         ← DomainValidator + MigrationEngine
├── templates.py      ← 域骨架生成 + KEMS迁移
├── signals.py        ← 跨域信号总线
└── cli.py            ← CLI入口 (l4-kernel命令)
```

---

## 快速命令

```bash
cd projects/l4-kernel
make test    # 测试
make lint    # 检查
make fmt     # 格式化
make install # 安装
```

---

## GPTCHAS

1. **零外部依赖** — 仅 pyyaml，不依赖任何 eCOS 项目
2. **DomainRegistry 是 SSOT** — DOMAIN-INDEX.md 是唯一真源
3. **KEMS 六面** — _control/_entities/_knowledge/_storage/_archive/_runtime
4. **7 种域类型** — 仅 DocumentDomain 需要 KemsPlane，其他类型各有特化
