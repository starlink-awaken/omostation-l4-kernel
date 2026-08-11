"""Tests for the declarative L4 workflow catalog."""

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
    def test_execute_fails_closed_without_dispatch(self, registry):
        engine = ScenarioEngine(registry)
        workflow = Workflow("blocked", "must use OMO", [WorkflowStep("health_check", "do not run")])

        result = engine.execute(workflow)

        assert result["status"] == "deprecated"
        assert result["error"]["code"] == "L4-EXECUTION-012"
        assert result["error"]["authority"] == "omo"

    def test_run_skill_fails_closed_before_loading_asset(self, registry):
        engine = ScenarioEngine(registry)

        result = engine.run_skill("vault", "test/blocked", content="blocked")

        assert result["status"] == "deprecated"
        assert result["error"]["code"] == "L4-EXECUTION-012"
        assert result["skill_id"] == "test/blocked"

    def test_run_workflow_fails_closed_before_loading_asset(self, registry):
        engine = ScenarioEngine(registry)

        result = engine.run_workflow("vault", "test/workflow")

        assert result["status"] == "deprecated"
        assert result["error"]["code"] == "L4-EXECUTION-012"
        assert result["workflow_id"] == "test/workflow"

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
        assert result["status"] == "deprecated"
        assert result["error"]["code"] == "L4-EXECUTION-012"

    def test_run_scenario_nonexistent(self, registry):
        result = run_scenario("nonexistent")
        assert result["status"] == "error"

    def test_list_scenarios(self, registry):
        scenarios = list_scenarios()
        assert "research_to_archive" in scenarios
        assert "weekly_governance" in scenarios
        assert "agent_session" in scenarios
