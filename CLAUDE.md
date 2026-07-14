# CLAUDE.md — L4 Kernel AI Context

    > Session loader for AI work inside `l4-kernel`.
    > Keep durable engineering rules in [`AGENTS.md`](AGENTS.md) and volatile facts in SSOT files.

    ## Load First

    1. [`AGENTS.md`](AGENTS.md)
    2. [`README.md`](README.md) when present
    3. The source files and tests directly related to the task
    4. Workspace context in [`../../CLAUDE.md`](../../CLAUDE.md) when the task crosses project boundaries

    ## Project Role

    - Layer: L4
    - Responsibility: 自我层管理面与域统一注册
    - Stack: Python / uv / pytest

    ## Commands

    ```bash
    uv sync
uv run pytest "tests/" -q
uv run ruff check "src/"
    ```

    ## Safe Editing Rules

    - `域数量和域清单以 registry 与 L0/MOF 模型为准。`
- 不要在项目说明里复制个人目录全量清单。

    - Do not commit, push, reset, or bump submodule pointers unless the user explicitly asks.
    - Preserve unrelated dirty changes in this repository.
    - Keep Markdown pointed at SSOT files instead of copying generated facts.

    ## Closeout

    ```bash
    git status --short
    uv run --with "pyyaml" python "../../bin/ssot/doc-ssot-lint.py" --json
    ```

    Report the checks you actually ran and any pre-existing dirty state that remains.
