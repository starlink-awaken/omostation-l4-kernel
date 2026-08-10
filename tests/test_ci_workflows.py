from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def _load_workflow(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _checkout_paths(job: dict) -> dict[str, str]:
    paths: dict[str, str] = {}
    for step in job["steps"]:
        if step.get("uses") != "actions/checkout@v4":
            continue
        options = step.get("with", {})
        paths[options.get("path", ".")] = options.get("repository", "self")
    return paths


def _assert_standalone_checkout(job: dict) -> None:
    assert _checkout_paths(job) == {
        "l4-kernel": "self",
        "bus-foundation": "starlink-awaken/omostation-bus-foundation",
        "model-driven": "starlink-awaken/omostation-model-driven",
    }


def test_ci_jobs_checkout_local_dependencies_as_siblings() -> None:
    workflow = _load_workflow("ci.yml")

    for job in workflow["jobs"].values():
        _assert_standalone_checkout(job)
        run_steps = [step for step in job["steps"] if "run" in step]
        assert run_steps
        assert all(step.get("working-directory") == "l4-kernel" for step in run_steps)


def test_health_workflow_uses_standalone_paths_and_optional_slack() -> None:
    path = WORKFLOWS / "health-check.yml"
    raw = path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(raw)
    job = workflow["jobs"]["health-check"]

    assert "projects/l4-kernel" not in raw
    _assert_standalone_checkout(job)
    run_steps = [step for step in job["steps"] if "run" in step]
    assert run_steps
    assert all(step.get("working-directory") == "l4-kernel" for step in run_steps)
    assert job["env"]["SLACK_WEBHOOK_URL"]

    notification = next(step for step in job["steps"] if step["name"] == "Send notification on failure")
    assert "env.SLACK_WEBHOOK_URL != ''" in notification["if"]
