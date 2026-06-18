"""Tests for L4 Kernel consistency checks."""

from unittest.mock import patch

from l4_kernel.consistency import load_domain_index


def test_load_domain_index_multiple_tables(tmp_path):
    """Test that load_domain_index can parse multiple markdown tables separated by empty lines."""
    mock_md_content = """# DOMAIN-INDEX

### 📄 document (2)

| ID | 名称 | 层 | Tier | 路径 |
|---|---|---|---|---|
| cockpit | @驾驶舱 | L4 | 3 | /Documents/@驾驶舱 |
| vault | @学习进化 | L4 | 1 | /Documents/@学习进化 |

### ⚙️ config (1)

| ID | 名称 | 层 | Tier | 路径 |
|---|---|---|---|---|
| ai-config | ~/.ai | L3-L4 | - | /.ai |
"""
    test_file = tmp_path / "DOMAIN-INDEX.md"
    test_file.write_text(mock_md_content, encoding="utf-8")

    with patch("l4_kernel.consistency.DOMAIN_INDEX_MD", test_file):
        domains = load_domain_index()
        assert domains is not None
        assert len(domains) == 3
        assert domains[0]["id"] == "cockpit"
        assert domains[1]["id"] == "vault"
        assert domains[2]["id"] == "ai-config"


def test_load_domain_index_empty_file(tmp_path):
    """Test that load_domain_index handles an empty file gracefully."""
    test_file = tmp_path / "DOMAIN-INDEX.md"
    test_file.write_text("", encoding="utf-8")

    with patch("l4_kernel.consistency.DOMAIN_INDEX_MD", test_file):
        domains = load_domain_index()
        assert domains is not None
        assert len(domains) == 0
