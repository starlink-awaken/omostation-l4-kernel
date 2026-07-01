"""l4-kernel 测试 conftest

P52-final 真治本: 利用 l4_kernel.testing.default_overrides(tmp_path),
传入 DomainRegistry(path_overrides=...)。与生产同款机制 (TOML 注入),
无 env 兜底, 无 Path.home() 默认。
"""
import pytest

from l4_kernel.domain_types import clear_wrap_cache
from l4_kernel.testing import default_overrides


@pytest.fixture(autouse=True)
def _clear_wrap_cache():
    clear_wrap_cache()


@pytest.fixture(autouse=True)
def l4_test_config(tmp_path, monkeypatch):
    """P52-final: 所有测试注入 tmpdir DomainRegistry 路径。

    1. 写 TOML config 到 tmp_path/l4_domain_paths.toml
    2. monkeypatch setattr cli.DEFAULT_CONFIG_PATH 指向 tmpdir
    3. reset mcp_server._globals cache (强制重 init)
    """
    import l4_kernel.cli as cli
    from l4_kernel import mcp_server

    overrides = default_overrides(tmp_path)
    config_path = tmp_path / "l4_domain_paths.toml"
    config_path.write_text(
        "[domain_paths]\n"
        + "\n".join(f'{k} = "{v}"' for k, v in overrides.items())
        + "\n"
    )

    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr(mcp_server, "_globals", None)

    yield overrides

    monkeypatch.setattr(mcp_server, "_globals", None)


@pytest.fixture
def registry(tmp_path, l4_test_config):
    """P52-final: 工厂 fixture, 给所有测试统一 DomainRegistry 实例。

    替代测试里直接 `DomainRegistry()` 无参调用 (现已禁用)。
    """
    from l4_kernel import DomainRegistry
    return DomainRegistry(path_overrides=default_overrides(tmp_path))


# 兼容旧 conftest
@pytest.fixture(autouse=True)
def temp_domains(monkeypatch):
    """P52-final 已废弃, 由 l4_test_config + registry 替代。保留 stub 避免老测试 break。"""
    yield
