"""P52-final 真治本: 配置加载器。

从 TOML 文件读 DomainRegistry.path_overrides, 唯一生产入口。
无 fallback, 无 env 注入 (与 _BUILTIN_DOMAINS 默认一起删除)。

TOML 格式:
    [domain_paths]
    vault = "/Users/x/Documents/@学习进化"
    cockpit = "/Users/x/Documents/@驾驶舱"
    work-weijian = "/Users/x/Documents/@工作文档/卫健委"
    ...

路径存在性: 目录不存在时保留条目并告警 (stderr), 由 Domain.exists /
aggregate_health 如实测量 — 未挂载卷/尚未创建的域是被测量的信号, 不是加载错误。
(2026-07-15 软化: 原 fail-fast 设计在外接卷 /Volumes/* 未挂载时会拖垮整个
域注册表加载, 与 aggregate_health 的 existing/total 语义冲突。)
"""

from __future__ import annotations

import sys
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
    """
    if not config_path.exists():
        raise FileNotFoundError(
            f"l4 domain paths config not found: {config_path}. "
            f"Create it with a [domain_paths] section before running production commands. "
            f"See src/l4_kernel/config_loader.py for the TOML contract."
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
            print(
                f"⚠ l4 domain {domain_id!r} path {p} not a directory "
                f"(unmounted volume / not yet created) — kept, health will report it",
                file=sys.stderr,
            )
        overrides[domain_id] = p
    return overrides
