"""l4-kernel 测试 conftest

P52 修复: 健康/federation 测试在 CI (Linux, /home/runner) 上失败,
因为 _BUILTIN_DOMAINS 路径写死为 Path.home() / "Documents" / "@...",
CI 环境下不存在。

策略: 提供 temp_domains fixture,自动用 tmp_path 替换所有域路径,
autouse=True 保证每个测试都干净。
"""
import tempfile
from pathlib import Path

import pytest

from l4_kernel import registry as _registry
from l4_kernel.domain_types import clear_wrap_cache


@pytest.fixture(autouse=True)
def _clear_wrap_cache():
    clear_wrap_cache()


@pytest.fixture(autouse=True)
def temp_domains(monkeypatch):
    """把所有内置域的 path 指向 tmpdir, 让 CI/本地一致。

    P52 修复: _BUILTIN_DOMAINS 路径写死 Path.home() / "Documents" / "@...",
    CI (Linux) 没这些目录,is_dir() 返回 False,health/federation 测试 fail。

    策略: 保留原 path 后缀结构, 但根改为 tmpdir。
    - vault: tmpdir/@学习进化 (path.name = "@学习进化", test_resolve_path 通过)
    - work-weijian: tmpdir/@工作文档/卫健委 (str 含 "工作文档", test_work_weijian_path 通过)
    """
    with tempfile.TemporaryDirectory() as td:
        tmp_root = Path(td)
        for d in _registry._BUILTIN_DOMAINS:
            # 跳过 Path.home() 前缀,保留后缀 (CI/本地一致)
            # vault: 去掉 "~/Documents", 留 "@学习进化"
            # work-weijian: 去掉 "~/Documents", 留 "@工作文档/卫健委"
            suffix_parts = d.path.parts
            # 找 "Documents" 在 parts 中的位置,从其后开始取
            if "Documents" in suffix_parts:
                idx = suffix_parts.index("Documents") + 1
                rel = Path(*suffix_parts[idx:])
            else:
                rel = Path(d.path.name)
            domain_tmp = tmp_root / rel
            domain_tmp.mkdir(parents=True, exist_ok=True)
            monkeypatch.setattr(d, "path", domain_tmp)
        yield tmp_root
