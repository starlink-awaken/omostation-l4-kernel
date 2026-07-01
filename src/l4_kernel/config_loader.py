"""P52-final 真治本: 配置加载器。

从 TOML 文件读 DomainRegistry.path_overrides, 唯一生产入口。
无 fallback, 无 env 注入 (与 _BUILTIN_DOMAINS 默认一起删除)。

TOML 格式:
    [domain_paths]
    vault = "/Users/x/Documents/@学习进化"
    cockpit = "/Users/x/Documents/@驾驶舱"
    work-weijian = "/Users/x/Documents/@工作文档/卫健委"
    ...

每个 path 必须存在 (is_dir()) 否则抛 FileNotFoundError, fail-fast。
"""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # type: ignore[import-not-found]


def load_overrides_from_config(config_path: Path) -> dict[str, Path]:
    """从 TOML 配置文件读 domain_id -> path 映射。

    Args:
        config_path: TOML 文件路径, 内含 [domain_paths] section

    Returns:
        dict[domain_id, Path] 注入 DomainRegistry

    Raises:
        FileNotFoundError: config_path 不存在
        KeyError: 缺 [domain_paths] section
        ValueError: 某 path 不是目录
    """
    if not config_path.exists():
        raise FileNotFoundError(
            f"l4 domain paths config not found: {config_path}. "
            f"Run scripts/l4_init.py to bootstrap a default config, "
            f"or create one manually with [domain_paths] section."
        )

    with config_path.open("rb") as f:
        data = tomllib.load(f)

    if "domain_paths" not in data:
        raise KeyError(
            f"TOML config {config_path} missing required [domain_paths] section"
        )

    overrides: dict[str, Path] = {}
    for domain_id, path_str in data["domain_paths"].items():
        p = Path(path_str).expanduser().resolve()
        if not p.is_dir():
            raise ValueError(
                f"Domain {domain_id!r} path {p} is not a directory. "
                f"Create the directory or fix the path in {config_path}."
            )
        overrides[domain_id] = p
    return overrides
