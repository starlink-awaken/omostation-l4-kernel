"""Tests for L4 Kernel Workflow Scenario Engine."""

from pathlib import Path

from l4_kernel.workflows import (
    SCENARIOS,
    ScenarioEngine,
    Workflow,
    WorkflowStep,
    list_scenarios,
    run_scenario,
)


class TestWorkflowStep:
    def test_create(self, registry):
        step = WorkflowStep("health_check", "检查健康", domain="vault")
        assert step.action == "health_check"
        assert step.domain == "vault"

    def test_on_error_skip(self, registry):
        step = WorkflowStep("risky_action", "可能失败", on_error="skip")
        assert step.on_error == "skip"


class TestWorkflow:
    def test_create(self, registry):
        wf = Workflow(
            "test",
            "测试工作流",
            [
                WorkflowStep("step1", "第一步"),
                WorkflowStep("step2", "第二步"),
            ],
        )
        assert len(wf.steps) == 2


class TestScenarioEngine:
    def test_execute_health_check(self, registry):
        engine = ScenarioEngine(registry)
        wf = Workflow(
            "test_health",
            "测试健康",
            [
                WorkflowStep("health_check", "健康检查"),
            ],
        )
        result = engine.execute(wf)
        assert result["status"] == "ok"
        assert result["steps_completed"] == 1

    def test_execute_unknown_action(self, registry):
        engine = ScenarioEngine(registry)
        wf = Workflow(
            "test_unknown",
            "测试未知",
            [
                WorkflowStep("nonexistent_action", "不存在"),
            ],
        )
        result = engine.execute(wf)
        assert result["status"] == "error"
        assert result["steps_failed"] == 1

    def test_execute_skip_on_error(self, registry):
        engine = ScenarioEngine(registry)
        wf = Workflow(
            "test_skip",
            "测试跳过",
            [
                WorkflowStep("nonexistent_action", "会失败", on_error="skip"),
                WorkflowStep("health_check", "会成功"),
            ],
        )
        result = engine.execute(wf)
        assert result["steps_completed"] == 1

    def test_execute_multiple_steps(self, registry):
        engine = ScenarioEngine(registry)
        wf = Workflow(
            "test_multi",
            "测试多步",
            [
                WorkflowStep("health_check", "健康"),
                WorkflowStep("aggregate_signals", "信号"),
                WorkflowStep("scan_cards", "CARDS"),
            ],
        )
        result = engine.execute(wf)
        assert result["status"] == "ok"
        assert result["steps_completed"] == 3

    def test_file_read_rejects_traversal(self, registry, tmp_path: Path):
        engine = ScenarioEngine(registry)

        result = engine._action_read_file(tmp_path / "domain", "../../outside.md")

        assert result["ok"] is False
        assert result["error"]["code"] == "L4-PATH-006"

    def test_file_write_is_denied_by_default(self, registry, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("L4_LEGACY_DIRECT_WRITE", raising=False)
        engine = ScenarioEngine(registry)

        result = engine._action_write_file(tmp_path / "domain", "note.md", "blocked")

        assert result["ok"] is False
        assert result["error"]["code"] == "L4-MUTATION-011"

    def test_execute_reports_default_denied_write_as_failure(self, registry, monkeypatch):
        monkeypatch.delenv("L4_LEGACY_DIRECT_WRITE", raising=False)
        engine = ScenarioEngine(registry)
        workflow = Workflow("blocked", "blocked write", [WorkflowStep("write_file", "notes/new.md", domain="vault")])

        result = engine.execute(workflow, content="blocked")

        assert result["status"] == "error"
        assert result["results"][0]["result"]["error"]["code"] == "L4-MUTATION-011"

    def test_run_skill_reports_default_denied_write_as_failure(self, registry, monkeypatch):
        monkeypatch.delenv("L4_LEGACY_DIRECT_WRITE", raising=False)
        vault = registry.get("vault")
        assert vault is not None
        skills = vault.path / "_control" / "skills"
        skills.mkdir(parents=True)
        (skills / "blocked.yaml").write_text(
            "skill:\n  id: test/blocked\n  steps:\n    - action: write_file\n      target: notes/new.md\n",
            encoding="utf-8",
        )
        engine = ScenarioEngine(registry)

        result = engine.run_skill("vault", "test/blocked", content="blocked")

        assert result["status"] == "error"
        assert result["results"][0]["result"]["error"]["code"] == "L4-MUTATION-011"

    def test_legacy_file_write_is_contained(self, registry, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("L4_LEGACY_DIRECT_WRITE", "1")
        root = tmp_path / "domain"
        root.mkdir()
        engine = ScenarioEngine(registry)

        allowed = engine._action_write_file(root, "notes/inside.md", "allowed")
        blocked = engine._action_write_file(root, "../../outside.md", "blocked")

        assert allowed["status"] == "ok"
        assert (root / "notes" / "inside.md").read_text(encoding="utf-8") == "allowed"
        assert blocked["error"]["code"] == "L4-PATH-006"


class TestPredefinedScenarios:
    def test_all_scenarios_defined(self, registry):
        assert len(SCENARIOS) >= 5

    def test_research_to_archive(self, registry):
        wf = SCENARIOS["research_to_archive"]
        assert wf.name == "research_to_archive"
        assert len(wf.steps) == 5

    def test_signal_to_fix(self, registry):
        wf = SCENARIOS["signal_to_fix"]
        assert len(wf.steps) == 5

    def test_weekly_governance(self, registry):
        wf = SCENARIOS["weekly_governance"]
        assert len(wf.steps) == 8

    def test_agent_session(self, registry):
        wf = SCENARIOS["agent_session"]
        assert len(wf.steps) == 3

    def test_domain_create(self, registry):
        wf = SCENARIOS["domain_create"]
        assert len(wf.steps) == 2

    def test_run_scenario_health(self, registry):
        result = run_scenario("agent_session", registry=registry)
        assert result["status"] == "ok"
        assert result["steps_completed"] == 3

    def test_run_scenario_nonexistent(self, registry):
        result = run_scenario("nonexistent")
        assert result["status"] == "error"

    def test_list_scenarios(self, registry):
        scenarios = list_scenarios()
        assert "research_to_archive" in scenarios
        assert "weekly_governance" in scenarios
        assert "agent_session" in scenarios
