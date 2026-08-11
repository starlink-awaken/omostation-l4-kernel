# L4 Kernel Phase 0 API / Usage Reference

> Quick reference for using **L4 Kernel** programmatically and from the command line.

## Command Line

- `l4-kernel contract validate PATH --json` — 严格校验单个 `DomainManifest`。
- `l4-kernel registry list --registry PATH --json` — 加载显式知识域注册表。
- `l4-kernel harness run DOMAIN_ID --gates T0,T1,T2,T4,T7 --json` — 运行只读确定性门禁。

退出码：`0` 有效，`1` 校验失败，`2` 配置失败。旧 `domain`、`skill`、`workflow` 命令保留为 legacy 兼容入口。

## Programmatic API

稳定入口：

- `l4_kernel.contracts.load_domain_manifest`
- `l4_kernel.manifest_registry.ManifestRegistry`
- `l4_kernel.harness.HarnessRunner`
- `l4_kernel.path_policy.resolve_within`

MCP 只读 Phase 0 工具为 `l4_contract_validate` 与 `l4_harness_run`。它们不创建目录、不写文件，也不调用 `ScenarioEngine`。

## Configuration

- 必需：`L4_DOMAIN_REGISTRY=/path/to/L4-DOMAIN-REGISTRY.yaml`
- 回滚：`L4_REGISTRY_MODE=legacy`
- 旧直接写（仍受路径 containment）：`L4_LEGACY_DIRECT_WRITE=1`

默认没有直接写。关闭旧开关时返回 `L4-MUTATION-011`；路径逃逸返回 `L4-PATH-006`。

Phase 0 不暴露 `ContextPack`；该能力属于 Phase 1。

## Tests

See [`../README.md`](../README.md) for the test command.
