"""Tests for L4 Kernel templates — KEMS 标准模板与 Schema 校验。"""

import json
import stat
import tempfile
from pathlib import Path

import pytest

import l4_kernel.templates as templates
from l4_kernel.content_plane import audit_content_plane
from l4_kernel.contracts import load_domain_manifest
from l4_kernel.templates import KemsValidator, init_domain_content_contracts, init_domain_kems


class TestInitDomainKems:
    def test_creates_only_declarative_content_contracts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canonical_root = root.resolve()
            created = init_domain_kems(root, domain_name="测试域", owner="test")
            assert set(created) == {
                canonical_root / "Method.md",
                canonical_root / "profiles" / "Profile.md",
                canonical_root / "ontology" / "DOMAIN_ONTOLOGY.md",
                canonical_root / "rubrics" / "QUALITY_RUBRIC.md",
                canonical_root / "DOMAIN.yaml",
            }
            report = audit_content_plane(root)
            assert report.ok
            assert report.counts.get("runtime", 0) == 0
            assert report.counts.get("cache", 0) == 0
            assert not (root / "_control").exists()
            manifest = load_domain_manifest(root / "DOMAIN.yaml")
            assert manifest.root == root.resolve()
            assert manifest.owners == ("test",)
            assert manifest.principal_ref == "test"

    def test_legacy_api_never_creates_scripts_or_executable_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = init_domain_kems(root, domain_name="测试域", owner="test")

            assert result.deprecation["replacement"] == "l4-kernel domain init-content-contracts"
            assert json.loads(json.dumps(result.to_dict()))["deprecation"] == result.deprecation
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

    def test_explicit_domain_id_wins_over_path_basename(self, tmp_path):
        root = tmp_path / "path-basename"

        init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        assert load_domain_manifest(root / "DOMAIN.yaml").id == "registry-id"

    def test_default_ontology_key_files_describe_only_declarative_artifacts(self, tmp_path):
        root = tmp_path / "domain"

        init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        ontology = (root / "ontology" / "DOMAIN_ONTOLOGY.md").read_text(encoding="utf-8")
        assert "_control" not in ontology
        assert "_knowledge" not in ontology
        assert "_storage" not in ontology
        assert "DOMAIN.yaml" in ontology

    def test_write_failure_rolls_back_all_new_contract_files_and_directories(self, tmp_path, monkeypatch):
        root = tmp_path / "domain"
        original_write = templates._write_contract

        def fail_method(path, content, created):
            if path.name == "Method.md":
                raise PermissionError("denied writing Method")
            return original_write(path, content, created)

        monkeypatch.setattr(templates, "_write_contract", fail_method)

        with pytest.raises(PermissionError):
            init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        assert not root.exists()

    def test_publication_rechecks_parent_after_preflight_and_rolls_back(self, tmp_path, monkeypatch):
        root = tmp_path / "domain"
        profiles = root / "profiles"
        external = tmp_path / "external"
        root.mkdir()
        profiles.mkdir()
        external.mkdir()

        def swap_profiles_after_preflight(_root):
            profiles.rmdir()
            profiles.symlink_to(external, target_is_directory=True)

        monkeypatch.setattr(templates, "_before_contract_publication", swap_profiles_after_preflight, raising=False)

        with pytest.raises(OSError):
            init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        assert list(external.iterdir()) == []
        assert not (root / "DOMAIN.yaml").exists()
        assert not (root / "Method.md").exists()


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
