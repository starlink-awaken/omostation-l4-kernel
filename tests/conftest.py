"""l4-kernel 测试 conftest

P52 治本: 利用 DomainRegistry env var 注入,设 L4_<DOMAIN_ID>_PATH 覆盖默认 path。
与生产部署同一机制 (CI/容器/单测都用 env),不是临时 monkeypatch。
"""
import pytest

from l4_kernel.domain_types import clear_wrap_cache


@pytest.fixture(autouse=True)
def _clear_wrap_cache():
    clear_wrap_cache()


@pytest.fixture(autouse=True)
def temp_domains(tmp_path, monkeypatch):
    """通过 env var 注入 28 个域的 path 到 tmpdir。

    利用 P52 治本: DomainRegistry._load_env_overrides() 会读 L4_<ID>_PATH,
    同一机制单测/生产都可用。CI 可直接 export L4_VAULT_PATH=... 而无需代码改动。
    """
    from l4_kernel import registry as _registry

    for d in _registry._BUILTIN_DOMAINS:
        # 保留原 path 后缀结构 (从 "Documents" 后开始)
        suffix_parts = d.path.parts
        if "Documents" in suffix_parts:
            idx = suffix_parts.index("Documents") + 1
            rel = "/".join(suffix_parts[idx:])
        else:
            rel = d.path.name
        domain_tmp = tmp_path / rel
        domain_tmp.mkdir(parents=True, exist_ok=True)
        env_key = f"L4_{d.id.upper().replace('-', '_')}_PATH"
        monkeypatch.setenv(env_key, str(domain_tmp))
