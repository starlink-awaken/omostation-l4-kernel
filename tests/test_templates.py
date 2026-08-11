"""Tests for L4 Kernel templates — KEMS 标准模板与 Schema 校验。"""

import stat
import tempfile
from pathlib import Path

from l4_kernel.content_plane import audit_content_plane
from l4_kernel.contracts import load_domain_manifest
from l4_kernel.templates import KemsValidator, init_domain_kems


class TestInitDomainKems:
    def test_creates_only_declarative_content_contracts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            created = init_domain_kems(root, domain_name="测试域", owner="test")
            assert set(created) == {
                root / "Method.md",
                root / "profiles" / "Profile.md",
                root / "ontology" / "DOMAIN_ONTOLOGY.md",
                root / "rubrics" / "QUALITY_RUBRIC.md",
                root / "DOMAIN.yaml",
            }
            report = audit_content_plane(root)
            assert report.ok
            assert report.counts.get("runtime", 0) == 0
            assert report.counts.get("cache", 0) == 0
            manifest = load_domain_manifest(root / "DOMAIN.yaml")
            assert manifest.root == root.resolve()
            assert manifest.owners == ("test",)
            assert manifest.principal_ref == "test"

    def test_legacy_api_never_creates_scripts_or_executable_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = init_domain_kems(root, domain_name="测试域", owner="test")

            assert result.deprecation["replacement"] == "l4-kernel domain init-content-contracts"
            assert all(path.suffix not in {".py", ".sh", ".bash", ".zsh"} for path in result)
            assert all(not path.stat().st_mode & stat.S_IXUSR for path in result)

    def test_preserves_existing_content(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            method = root / "Method.md"
            method.write_text("# 已有方法\n", encoding="utf-8")

            created = init_domain_kems(root, domain_name="测试域", owner="test")

            assert method.read_text(encoding="utf-8") == "# 已有方法\n"
            assert method not in created


class TestKemsValidator:
    def setup_domain(self, root: Path, owner: str = "test") -> None:
        """构造旧 KEMS 校验器的最小有效输入。"""
        control = root / "_control"
        control.mkdir(parents=True)
        control.joinpath("MEMORY.md").write_text(
            f"---\ntitle: test\nstatus: 已采纳\ntype: canonical\nowner: {owner}\ncreated: 2026-01-01\n---\n# test\n",
            encoding="utf-8",
        )
        control.joinpath("STATUS.md").write_text(
            f"---\ntitle: test\nstatus: 已采纳\ntype: canonical\nowner: {owner}\ncreated: 2026-01-01\n---\n## 当前状态：STABLE\n",
            encoding="utf-8",
        )
        control.joinpath("signals.md").write_text("# signals\n", encoding="utf-8")
        control.joinpath("control-rules.md").write_text(
            f"---\ntitle: test\nstatus: 已采纳\ntype: canonical\nowner: {owner}\ncreated: 2026-01-01\n---\nCR01\n",
            encoding="utf-8",
        )
        control.joinpath("STATE.md").write_text("# state\n", encoding="utf-8")

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
            assert len(signal_issues) <= 1  # ℹ️ 是合法的信号类型
