# l4-kernel — System Boundary

> 本文档描述 l4-kernel 与 eCOS 系统其他部分的边界：暴露的接口、依赖的上游、影响的下游。
>
> 系统全景参见：[`../../docs/PANORAMA.md`](../../docs/PANORAMA.md)

---

## 1. 暴露接口

### BOS URI

- `bos://l4-kernel/domains`
- `bos://governance/l4-kernel/domains`

### 入口

- **CLI**: `l4-kernel` status/domain/governance/list
- **MCP stdio**: `l4-kernel mcp` MCP tools (见 project-registry.yaml: l4-kernel)
- **MCP HTTP**: `l4-kernel mcp --http` :7455
- **MCP SSE**: `l4-kernel mcp --sse` 

## 2. 上游依赖

- @驾驶舱/_control/DOMAIN-INDEX.md
- model-driven (M0)

## 3. 下游影响

- cockpit
- omo

## 4. 配置 / SSOT

- 项目源码：`projects/l4-kernel/`
- 入口定义：`projects/l4-kernel/pyproject.toml` 或 `package.json`
- 测试：`cd projects/l4-kernel && make test`

## 架构演进与项目边界索引

参见工作区架构演进与项目边界：[`../../docs/ARCHITECTURE-EVOLUTION.md`](../../docs/ARCHITECTURE-EVOLUTION.md)
