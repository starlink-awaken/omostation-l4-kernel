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
    # The repository token cannot read sibling private repositories. Standalone
    # CI therefore exercises the kernel's documented optional-bridge fallback;
    # cross-repository integration remains covered by the Documents root gate.
    assert _checkout_paths(job) == {".": "self"}


def _assert_core_mode(job: dict) -> None:
    install = next(step for step in job["steps"] if step.get("name") == "Install dependencies")
    command = install["run"]
    assert "uv venv" in command
    assert "uv pip install --no-deps -e ." in command

    commands = "\n".join(step["run"] for step in job["steps"] if "run" in step)
    assert "uv sync" not in commands

    kernel_steps = [
        step
        for step in job["steps"]
        if step.get("name") in {"Ruff check", "Ruff format check", "Run tests", "Run health check"}
    ]
    assert kernel_steps
    assert all("uv run --no-sync" in step["run"] for step in kernel_steps)


def test_ci_jobs_run_standalone_core_mode_without_private_checkouts() -> None:
    workflow = _load_workflow("ci.yml")

    for job in workflow["jobs"].values():
        _assert_standalone_checkout(job)
        _assert_core_mode(job)


def test_health_workflow_uses_standalone_paths_and_optional_slack() -> None:
    path = WORKFLOWS / "health-check.yml"
    raw = path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(raw)
    job = workflow["jobs"]["health-check"]

    assert "projects/l4-kernel" not in raw
    _assert_standalone_checkout(job)
    _assert_core_mode(job)
    assert job["env"]["SLACK_WEBHOOK_URL"]

    notification = next(step for step in job["steps"] if step["name"] == "Send notification on failure")
    assert "env.SLACK_WEBHOOK_URL != ''" in notification["if"]
