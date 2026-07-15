from pathlib import Path

import pytest

from l4_kernel.config_loader import load_overrides_from_config


def test_missing_config_explains_current_bootstrap_contract(tmp_path: Path):
    missing = tmp_path / "missing" / "l4_domain_paths.toml"

    with pytest.raises(FileNotFoundError, match=r"Create it with a \[domain_paths\] section"):
        load_overrides_from_config(missing)


def test_config_loader_reads_domain_paths(tmp_path: Path):
    config = tmp_path / "custom" / "l4_domain_paths.toml"
    config.parent.mkdir()
    config.write_text('[domain_paths]\ncockpit = "/tmp/cockpit"\n', encoding="utf-8")

    assert load_overrides_from_config(config) == {"cockpit": Path("/tmp/cockpit").resolve()}
