import pytest

from l4_kernel.domain_types import clear_wrap_cache


@pytest.fixture(autouse=True)
def _clear_wrap_cache():
    clear_wrap_cache()
