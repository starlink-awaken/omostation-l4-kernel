"""Tests for L4 Kernel templates — KEMS 标准模板与 Schema 校验。"""

import errno
import json
import stat
import subprocess
import sys
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

    def test_write_failure_reports_non_destructive_publication_evidence(self, tmp_path, monkeypatch):
        root = tmp_path / "domain"
        original_write = templates._write_contract

        def fail_method(path, content, created):
            if path.name == "Method.md":
                raise PermissionError("denied writing Method")
            return original_write(path, content, created)

        monkeypatch.setattr(templates, "_write_contract", fail_method)

        with pytest.raises(templates.BootstrapWriteError) as raised:
            init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        assert raised.value.residual_paths == (root / "DOMAIN.yaml",)
        assert raised.value.uncertain_paths == (root,)
        assert (root / "DOMAIN.yaml").exists()

    def test_publication_rechecks_parent_after_preflight_without_cleanup(self, tmp_path, monkeypatch):
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

        with pytest.raises(templates.BootstrapWriteError) as raised:
            init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        assert list(external.iterdir()) == []
        assert raised.value.residual_paths == (root / "DOMAIN.yaml", root / "Method.md")
        assert (root / "DOMAIN.yaml").exists()
        assert (root / "Method.md").exists()

    def test_non_destructive_failure_never_deletes_a_concurrently_replaced_contract(self, tmp_path, monkeypatch):
        root = tmp_path / "domain"
        root.mkdir()
        original_write = templates._write_contract

        def replace_manifest_then_fail(path, content, journal):
            if path.name == "Method.md":
                manifest = root / "DOMAIN.yaml"
                manifest.unlink()
                manifest.write_text("replacement must survive\n", encoding="utf-8")
                raise PermissionError("fail after replacement")
            return original_write(path, content, journal)

        monkeypatch.setattr(templates, "_write_contract", replace_manifest_then_fail)

        with pytest.raises(templates.BootstrapWriteError) as raised:
            init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        assert (root / "DOMAIN.yaml").read_text(encoding="utf-8") == "replacement must survive\n"
        assert raised.value.residual_paths == ()

    def test_directory_reopen_failure_reports_directory_uncertainty(self, tmp_path, monkeypatch):
        root = tmp_path / "domain"
        root.mkdir()
        original_open = templates._open_directory_at

        def fail_profiles_reopen(parent_fd, name):
            if name == "profiles" and (root / "profiles").exists():
                raise PermissionError("cannot reopen profiles")
            return original_open(parent_fd, name)

        monkeypatch.setattr(templates, "_open_directory_at", fail_profiles_reopen, raising=False)

        with pytest.raises(templates.BootstrapWriteError) as raised:
            init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        assert raised.value.residual_paths == (root / "DOMAIN.yaml", root / "Method.md")
        assert raised.value.uncertain_paths == (root / "profiles",)
        assert (root / "profiles").is_dir()

    def test_unsupported_secure_publication_platform_fails_closed(self, tmp_path, monkeypatch):
        root = tmp_path / "domain"
        monkeypatch.delattr(templates.os, "O_NOFOLLOW", raising=False)

        with pytest.raises(OSError) as raised:
            init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        assert raised.value.errno == errno.ENOTSUP
        assert not root.exists()

    def test_file_fsync_failure_reports_residual_and_recovery(self, tmp_path, monkeypatch):
        root = tmp_path / "domain"
        original_fsync = templates._fsync_fd

        def fail_file_fsync(fd, operation):
            if operation == "fsync contract file content":
                raise OSError("durability failure")
            return original_fsync(fd, operation)

        monkeypatch.setattr(templates, "_fsync_fd", fail_file_fsync)

        with pytest.raises(templates.BootstrapWriteError) as raised:
            init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        assert raised.value.residual_paths == (root / "DOMAIN.yaml",)
        assert raised.value.uncertain_paths == (root, root / "DOMAIN.yaml")
        assert raised.value.durability_uncertain_paths == (root / "DOMAIN.yaml",)
        assert raised.value.recovery["code"] == "L4-PUBLICATION-RECOVERY-001"
        assert (root / "DOMAIN.yaml").exists()

    def test_platform_not_implemented_error_is_reported_as_enotsup(self, tmp_path, monkeypatch):
        root = tmp_path / "domain"

        def unavailable_fsync(_fd):
            raise NotImplementedError("not supported")

        monkeypatch.setattr(templates.os, "fsync", unavailable_fsync)

        with pytest.raises(templates.BootstrapWriteError) as raised:
            init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        assert raised.value.errno == errno.ENOTSUP
        assert raised.value.residual_paths == ()
        assert raised.value.uncertain_paths == (root,)
        assert raised.value.durability_uncertain_paths == (root,)
        assert root.exists()

    def test_no_failure_path_invokes_destructive_cleanup(self, tmp_path, monkeypatch):
        root = tmp_path / "domain"
        original_write = templates._write_contract

        def fail_method(path, content, journal):
            if path.name == "Method.md":
                raise PermissionError("stop publication")
            return original_write(path, content, journal)

        def destructive_call(*_args, **_kwargs):
            raise AssertionError("bootstrap must never delete during failure handling")

        monkeypatch.setattr(templates, "_write_contract", fail_method)
        monkeypatch.setattr(templates.os, "unlink", destructive_call)
        monkeypatch.setattr(templates.os, "rmdir", destructive_call)

        with pytest.raises(templates.BootstrapWriteError):
            init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        assert (root / "DOMAIN.yaml").exists()

    def test_partial_write_requires_manual_recovery_before_retry(self, tmp_path, monkeypatch):
        root = tmp_path / "domain"
        original_write = templates.os.write

        def short_write(fd, payload):
            if payload.startswith(b"# Method"):
                return 0
            return original_write(fd, payload)

        monkeypatch.setattr(templates.os, "write", short_write)
        with pytest.raises(templates.BootstrapWriteError) as raised:
            init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        method = root / "Method.md"
        assert raised.value.residual_paths == (root / "DOMAIN.yaml", method)
        assert method in raised.value.uncertain_paths
        assert method.stat().st_mode & 0o777 == 0
        assert "uncertain incomplete" in raised.value.recovery["action"]
        monkeypatch.setattr(templates.os, "write", original_write)

        command = [
            sys.executable,
            "-m",
            "l4_kernel.cli",
            "domain",
            "init-content-contracts",
            str(root),
            "--domain-id",
            "registry-id",
            "--name",
            "测试域",
            "--owner",
            "test",
        ]
        retried_process = subprocess.run(command, cwd=Path.cwd(), text=True, capture_output=True, check=False)

        assert retried_process.returncode == 2
        assert json.loads(retried_process.stdout)["error"]["uncertain_paths"] == [str(method)]

        method.unlink()
        recovered = subprocess.run(command, cwd=Path.cwd(), text=True, capture_output=True, check=False)

        assert recovered.returncode == 0
        assert method.read_text(encoding="utf-8").startswith("# Method")

    def test_directory_name_replaced_after_mkdir_is_preserved_as_uncertain(self, tmp_path, monkeypatch):
        root = tmp_path / "domain"
        root.mkdir()
        profiles = root / "profiles"

        def replace_profiles(path):
            if path == profiles:
                profiles.rmdir()
                profiles.write_text("caller replacement\n", encoding="utf-8")

        monkeypatch.setattr(templates, "_after_directory_creation", replace_profiles)

        with pytest.raises(templates.BootstrapWriteError) as raised:
            init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        assert profiles.read_text(encoding="utf-8") == "caller replacement\n"
        assert profiles in raised.value.uncertain_paths

    def test_final_token_verification_rejects_concurrent_file_replacement(self, tmp_path, monkeypatch):
        root = tmp_path / "domain"
        method = root / "Method.md"

        def replace_method(_root):
            replacement = root / "caller-method.tmp"
            replacement.write_text("caller replacement\n", encoding="utf-8")
            replacement.replace(method)

        monkeypatch.setattr(templates, "_before_final_contract_verification", replace_method)

        with pytest.raises(templates.BootstrapWriteError) as raised:
            init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        assert method.read_text(encoding="utf-8") == "caller replacement\n"
        assert method not in raised.value.residual_paths
        assert method in raised.value.uncertain_paths
        assert raised.value.residual_paths == (
            root / "DOMAIN.yaml",
            root / "profiles" / "Profile.md",
            root / "ontology" / "DOMAIN_ONTOLOGY.md",
            root / "rubrics" / "QUALITY_RUBRIC.md",
        )

    @pytest.mark.parametrize("mutation", ["same_size_content", "truncate", "mode_zero", "mode_executable"])
    def test_final_verification_rejects_same_inode_content_and_mode_changes(self, tmp_path, monkeypatch, mutation):
        root = tmp_path / "domain"
        method = root / "Method.md"

        def mutate_method(_root):
            if mutation == "same_size_content":
                method.write_bytes(b"x" * method.stat().st_size)
            elif mutation == "truncate":
                method.write_bytes(b"")
            elif mutation == "mode_zero":
                method.chmod(0)
            else:
                method.chmod(0o755)

        monkeypatch.setattr(templates, "_before_final_contract_verification", mutate_method)

        with pytest.raises(templates.BootstrapWriteError) as raised:
            init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        assert method in raised.value.uncertain_paths
        assert raised.value.residual_paths == (
            root / "DOMAIN.yaml",
            root / "Method.md",
            root / "profiles" / "Profile.md",
            root / "ontology" / "DOMAIN_ONTOLOGY.md",
            root / "rubrics" / "QUALITY_RUBRIC.md",
        )

    def test_read_window_rejects_same_inode_same_size_rewrite_at_eof(self, tmp_path, monkeypatch):
        root = tmp_path / "domain"
        manifest = root / "DOMAIN.yaml"
        original_read = templates.os.read
        rewritten = False

        def rewrite_at_eof(fd, size):
            nonlocal rewritten
            chunk = original_read(fd, size)
            if not chunk and not rewritten:
                rewritten = True
                manifest.write_bytes(b"x" * manifest.stat().st_size)
            return chunk

        monkeypatch.setattr(templates.os, "read", rewrite_at_eof)

        with pytest.raises(templates.BootstrapWriteError) as raised:
            init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        assert manifest in raised.value.residual_paths
        assert manifest in raised.value.uncertain_paths

    @pytest.mark.parametrize("mutation", ["chmod", "replace"])
    def test_read_window_rejects_mode_change_and_path_replacement(self, tmp_path, monkeypatch, mutation):
        root = tmp_path / "domain"
        manifest = root / "DOMAIN.yaml"
        original_read = templates.os.read
        mutated = False

        def mutate_at_eof(fd, size):
            nonlocal mutated
            chunk = original_read(fd, size)
            if not chunk and not mutated:
                mutated = True
                if mutation == "chmod":
                    manifest.chmod(0o755)
                else:
                    replacement = root / "caller-manifest.tmp"
                    replacement.write_text("caller replacement\n", encoding="utf-8")
                    replacement.replace(manifest)
            return chunk

        monkeypatch.setattr(templates.os, "read", mutate_at_eof)

        with pytest.raises(templates.BootstrapWriteError) as raised:
            init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        assert manifest in raised.value.uncertain_paths
        if mutation == "chmod":
            assert manifest in raised.value.residual_paths
        else:
            assert manifest not in raised.value.residual_paths
            assert manifest.read_text(encoding="utf-8") == "caller replacement\n"

    def test_read_eio_keeps_owned_entry_as_residual_and_uncertain(self, tmp_path, monkeypatch):
        root = tmp_path / "domain"
        manifest = root / "DOMAIN.yaml"
        original_read = templates.os.read
        failed = False

        def fail_first_read(fd, size):
            nonlocal failed
            if not failed:
                failed = True
                raise OSError(errno.EIO, "simulated read evidence failure")
            return original_read(fd, size)

        monkeypatch.setattr(templates.os, "read", fail_first_read)

        with pytest.raises(templates.BootstrapWriteError) as raised:
            init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        assert manifest in raised.value.residual_paths
        assert manifest in raised.value.uncertain_paths

    def test_write_time_sentinel_after_preflight_fails_closed_with_prior_residual(self, tmp_path, monkeypatch):
        root = tmp_path / "domain"
        method = root / "Method.md"

        def create_late_sentinel(_root):
            root.mkdir()
            method.touch()
            method.chmod(0)

        monkeypatch.setattr(templates, "_before_contract_publication", create_late_sentinel)

        with pytest.raises(templates.BootstrapWriteError) as raised:
            init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        assert method.stat().st_mode & 0o777 == 0
        assert raised.value.residual_paths == (root / "DOMAIN.yaml",)
        assert method in raised.value.uncertain_paths

    def test_encode_failure_creates_no_artifacts(self, tmp_path):
        root = tmp_path / "domain"

        with pytest.raises(UnicodeEncodeError):
            init_domain_content_contracts(root, domain_id="registry-id", domain_name="\ud800", owner="test")

        assert not root.exists()

        existing_root = tmp_path / "existing-domain"
        existing_root.mkdir()
        with pytest.raises(UnicodeEncodeError):
            init_domain_content_contracts(existing_root, domain_id="existing-id", domain_name="\ud800", owner="test")

        assert list(existing_root.iterdir()) == []

    def test_final_snapshot_samples_each_entry_once(self, tmp_path, monkeypatch):
        root = tmp_path / "domain"
        method = root / "Method.md"
        original_sample = templates._sample_file_entry
        samples = 0

        def count_samples(sample_root, entry):
            nonlocal samples
            samples += 1
            return original_sample(sample_root, entry)

        monkeypatch.setattr(templates, "_sample_file_entry", count_samples)
        monkeypatch.setattr(templates, "_before_final_contract_verification", lambda _root: method.chmod(0o755))

        with pytest.raises(templates.BootstrapWriteError):
            init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        assert samples == 5

    def test_failed_publication_does_not_leak_file_descriptors(self, tmp_path, monkeypatch):
        fd_directory = Path("/dev/fd")
        if not fd_directory.is_dir():
            pytest.skip("platform does not expose process file descriptors")
        root = tmp_path / "domain"
        original_write = templates._write_contract

        def fail_method(path, content, journal):
            if path.name == "Method.md":
                raise PermissionError("stop publication")
            return original_write(path, content, journal)

        monkeypatch.setattr(templates, "_write_contract", fail_method)
        before = len(list(fd_directory.iterdir()))

        with pytest.raises(templates.BootstrapWriteError):
            init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        assert len(list(fd_directory.iterdir())) == before

    def test_incomplete_sentinel_blocks_a_new_cli_process_until_manual_removal(self, tmp_path):
        root = tmp_path / "domain"
        root.mkdir()
        method = root / "Method.md"
        method.write_text("partial", encoding="utf-8")
        method.chmod(0)
        command = [
            sys.executable,
            "-m",
            "l4_kernel.cli",
            "domain",
            "init-content-contracts",
            str(root),
            "--domain-id",
            "registry-id",
            "--name",
            "测试域",
            "--owner",
            "test",
        ]

        failed = subprocess.run(command, cwd=Path.cwd(), text=True, capture_output=True, check=False)

        assert failed.returncode == 2
        payload = json.loads(failed.stdout)
        assert payload["error"]["uncertain_paths"] == [str(method)]
        assert method.stat().st_mode & 0o777 == 0

        method.unlink()
        recovered = subprocess.run(command, cwd=Path.cwd(), text=True, capture_output=True, check=False)

        assert recovered.returncode == 0
        assert (root / "Method.md").read_text(encoding="utf-8").startswith("# Method")

    def test_fstat_failure_leaves_cross_process_recoverable_sentinel(self, tmp_path, monkeypatch):
        root = tmp_path / "domain"
        original_fstat = templates.os.fstat

        def fail_fstat(_fd):
            raise OSError("fstat unavailable")

        monkeypatch.setattr(templates.os, "fstat", fail_fstat)
        with pytest.raises(templates.BootstrapWriteError) as raised:
            init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        target = root / "DOMAIN.yaml"
        assert target in raised.value.uncertain_paths
        assert target in raised.value.durability_uncertain_paths
        assert target.stat().st_mode & 0o777 == 0
        monkeypatch.setattr(templates.os, "fstat", original_fstat)

        with pytest.raises(templates.BootstrapWriteError, match="incomplete content-contract sentinel") as retried:
            init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        assert retried.value.uncertain_paths == (target,)
        assert "uncertain incomplete" in retried.value.recovery["action"]

    def test_incomplete_sentinel_is_scoped_to_its_domain(self, tmp_path):
        failed_root = tmp_path / "failed"
        failed_root.mkdir()
        failed_method = failed_root / "Method.md"
        failed_method.touch()
        failed_method.chmod(0)
        healthy_root = tmp_path / "healthy"

        with pytest.raises(templates.BootstrapWriteError):
            init_domain_content_contracts(failed_root, domain_id="failed", domain_name="失败域", owner="test")

        created = init_domain_content_contracts(healthy_root, domain_id="healthy", domain_name="健康域", owner="test")

        assert healthy_root / "DOMAIN.yaml" in created
        assert failed_method.stat().st_mode & 0o777 == 0

    def test_caller_owned_mode_zero_file_fails_closed_without_mutation(self, tmp_path):
        root = tmp_path / "domain"
        root.mkdir()
        method = root / "Method.md"
        method.write_text("caller content", encoding="utf-8")
        method.chmod(0)

        with pytest.raises(templates.BootstrapWriteError) as raised:
            init_domain_content_contracts(root, domain_id="registry-id", domain_name="测试域", owner="test")

        assert raised.value.residual_paths == ()
        assert raised.value.uncertain_paths == (method,)
        method.chmod(0o644)
        assert method.read_text(encoding="utf-8") == "caller content"


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
