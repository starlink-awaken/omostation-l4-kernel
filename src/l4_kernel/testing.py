"""P52-final 真治本: 测试助手。

提供 default_overrides(tmp_path) 给单测用, 不依赖 Path.home() 或 env。
"""

from __future__ import annotations

from pathlib import Path

from l4_kernel.registry import _BUILTIN_DOMAINS


def default_overrides(tmp_path: Path) -> dict[str, Path]:
    """为 28 个内置域生成 tmpdir 路径, 注入 DomainRegistry。

    保留原 path 后缀 (如 "Documents/@学习进化"), 保持测试断言
    test_resolve_path/test_work_weijian_path 的中文路径期望通过。

    用法:
        def test_something(tmp_path):
            reg = DomainRegistry(path_overrides=default_overrides(tmp_path))
    """
    overrides: dict[str, Path] = {}
    for d in _BUILTIN_DOMAINS:
        # 保留原 path 后缀结构 (从 "Documents" 后开始)
        suffix_parts = d.path.parts
        if "Documents" in suffix_parts:
            idx = suffix_parts.index("Documents") + 1
            rel = "/".join(suffix_parts[idx:])
        else:
            rel = d.path.name
        domain_tmp = tmp_path / rel
        domain_tmp.mkdir(parents=True, exist_ok=True)
        overrides[d.id] = domain_tmp
    return overrides
