.PHONY: test lint fmt install clean

test:
	uv run pytest tests/ -q --tb=short

lint:
	uv run ruff check src/l4_kernel/ tests/

fmt:
	uv run ruff format src/l4_kernel/ tests/

install:
	uv sync

clean:
	rm -rf .pytest_cache/ src/l4_kernel/__pycache__/ tests/__pycache__/
