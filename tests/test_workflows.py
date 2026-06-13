"""Tests for L4 Kernel Workflow Scenario Engine."""

from l4_kernel.workflows import (
    SCENARIOS,
    ScenarioEngine,
    Workflow,
    WorkflowStep,
    list_scenarios,
    run_scenario,
)


class TestWorkflowStep:
    def test_create(self):
        step = WorkflowStep("health_check", "检查健康", domain="vault")
        assert step.action == "health_check"
        assert step.domain == "vault"

    def test_on_error_skip(self):
        step = WorkflowStep("risky_action", "可能失败", on_error="skip")
        assert step.on_error == "skip"


class TestWorkflow:
    def test_create(self):
        wf = Workflow("test", "测试工作流", [
            WorkflowStep("step1", "第一步"),
            WorkflowStep("step2", "第二步"),
        ])
        assert len(wf.steps) == 2


class TestScenarioEngine:
    def test_execute_health_check(self):
        engine = ScenarioEngine()
        wf = Workflow("test_health", "测试健康", [
            WorkflowStep("health_check", "健康检查"),
        ])
        result = engine.execute(wf)
        assert result["status"] == "ok"
        assert result["steps_completed"] == 1

    def test_execute_unknown_action(self):
        engine = ScenarioEngine()
        wf = Workflow("test_unknown", "测试未知", [
            WorkflowStep("nonexistent_action", "不存在"),
        ])
        result = engine.execute(wf)
        assert result["status"] == "error"
        assert result["steps_failed"] == 1

    def test_execute_skip_on_error(self):
        engine = ScenarioEngine()
        wf = Workflow("test_skip", "测试跳过", [
            WorkflowStep("nonexistent_action", "会失败", on_error="skip"),
            WorkflowStep("health_check", "会成功"),
        ])
        result = engine.execute(wf)
        assert result["steps_completed"] == 1

    def test_execute_multiple_steps(self):
        engine = ScenarioEngine()
        wf = Workflow("test_multi", "测试多步", [
            WorkflowStep("health_check", "健康"),
            WorkflowStep("aggregate_signals", "信号"),
            WorkflowStep("scan_cards", "CARDS"),
        ])
        result = engine.execute(wf)
        assert result["status"] == "ok"
        assert result["steps_completed"] == 3


class TestPredefinedScenarios:
    def test_all_scenarios_defined(self):
        assert len(SCENARIOS) >= 5

    def test_research_to_archive(self):
        wf = SCENARIOS["research_to_archive"]
        assert wf.name == "research_to_archive"
        assert len(wf.steps) == 5

    def test_signal_to_fix(self):
        wf = SCENARIOS["signal_to_fix"]
        assert len(wf.steps) == 5

    def test_weekly_governance(self):
        wf = SCENARIOS["weekly_governance"]
        assert len(wf.steps) == 8

    def test_agent_session(self):
        wf = SCENARIOS["agent_session"]
        assert len(wf.steps) == 3

    def test_domain_create(self):
        wf = SCENARIOS["domain_create"]
        assert len(wf.steps) == 2

    def test_run_scenario_health(self):
        result = run_scenario("agent_session")
        assert result["status"] == "ok"
        assert result["steps_completed"] == 3

    def test_run_scenario_nonexistent(self):
        result = run_scenario("nonexistent")
        assert result["status"] == "error"

    def test_list_scenarios(self):
        scenarios = list_scenarios()
        assert "research_to_archive" in scenarios
        assert "weekly_governance" in scenarios
        assert "agent_session" in scenarios
