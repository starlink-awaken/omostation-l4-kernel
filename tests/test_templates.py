"""Tests for L4 Kernel templates — KEMS 标准模板与 Schema 校验。"""

import tempfile
from pathlib import Path

from l4_kernel.templates import KemsValidator, init_domain_kems


class TestInitDomainKems:
    def test_creates_all_planes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            created = init_domain_kems(root, domain_name="测试域", owner="test")
            # 6 个目录 (_control, _entities, _knowledge, _storage, _archive, 决策日志)
            dirs = [p for p in created if p.is_dir()]
            assert len(dirs) >= 6
            # 7 个控制面文件
            files = [p for p in created if p.is_file()]
            assert len(files) >= 7

    def test_control_files_exist(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_domain_kems(root, domain_name="测试域", owner="test")
            for f in ["MEMORY.md", "STATE.md", "signals.md", "control-rules.md", "STATUS.md"]:
                assert (root / "_control" / f).exists(), f"Missing {f}"

    def test_status_contains_three_state_definition(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_domain_kems(root, domain_name="测试域", owner="test")
            content = (root / "_control" / "STATUS.md").read_text()
            assert "STABLE" in content
            assert "ALERT" in content
            assert "CRITICAL" in content

    def test_signals_contains_initial_entry(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_domain_kems(root, domain_name="测试域", owner="test")
            content = (root / "_control" / "signals.md").read_text()
            assert "域初始化" in content

    def test_control_rules_has_cr01(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_domain_kems(root, domain_name="测试域", owner="test")
            content = (root / "_control" / "control-rules.md").read_text()
            assert "CR01" in content
            assert "CR02" in content
            assert "CR03" in content


class TestKemsValidator:
    def setup_domain(self, root: Path, owner: str = "test") -> None:
        """创建标准 KEMS 骨架用于测试。"""
        init_domain_kems(root, domain_name="测试域", owner=owner)

    def test_validate_all_clean(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.setup_domain(root)
            validator = KemsValidator(root)
            issues = validator.validate_all()
            # 新创建的域应该只有 INFO 级别问题（CR04+ 格式）
            errors = [i for i in issues if i["severity"] == "error"]
            assert len(errors) == 0, f"Unexpected errors: {errors}"

    def test_missing_control_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # 不创建骨架，只创建 _control 空目录
            (root / "_control").mkdir(parents=True)
            validator = KemsValidator(root)
            issues = validator.validate_all()
            errors = [i for i in issues if i["rule"] == "V-CONTROL-01"]
            assert len(errors) == 5  # 5 个文件缺失

    def test_invalid_status(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.setup_domain(root)
            # 覆写 STATUS.md 为非法值
            (root / "_control" / "STATUS.md").write_text(
                "---\ntitle: test\nstatus: 已采纳\ntype: canonical\nowner: test\ncreated: 2026-01-01\n---\n"
                "## 当前状态：BROKEN ❌\n"
            )
            validator = KemsValidator(root)
            issues = validator.validate_all()
            status_issues = [i for i in issues if i["rule"] == "V-CONTROL-03"]
            assert len(status_issues) == 1
            assert "BROKEN" in status_issues[0]["message"]

    def test_valid_status(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.setup_domain(root)
            validator = KemsValidator(root)
            issues = validator.validate_all()
            status_issues = [i for i in issues if i["rule"] == "V-CONTROL-03"]
            assert len(status_issues) == 0

    def test_missing_owner(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.setup_domain(root, owner="")  # 空 owner
            validator = KemsValidator(root)
            issues = validator.validate_all()
            owner_issues = [i for i in issues if i["rule"] == "V-CONTROL-07"]
            assert len(owner_issues) >= 1

    def test_frontmatter_required_fields(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.setup_domain(root)
            # 覆写 MEMORY.md 去掉 owner 字段
            (root / "_control" / "MEMORY.md").write_text(
                "---\ntitle: test\nstatus: 已采纳\ntype: canonical\ncreated: 2026-01-01\n---\n# test\n"
            )
            validator = KemsValidator(root)
            issues = validator.validate_all()
            fm_issues = [i for i in issues if i["rule"] == "V-CONTROL-02"]
            assert len(fm_issues) >= 1
            assert "owner" in fm_issues[0]["message"]

    def test_signal_type_valid(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.setup_domain(root)
            validator = KemsValidator(root)
            issues = validator.validate_all()
            signal_issues = [i for i in issues if i["rule"] == "V-CONTROL-04"]
            assert len(signal_issues) == 0  # 模板生成的信号都是合法的
