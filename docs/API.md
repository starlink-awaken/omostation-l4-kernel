# L4 Kernel API / Usage Reference

> Quick reference for using **L4 Kernel** programmatically and from the command line.

## Command Line

- `uv run python -m l4_kernel` — L4 Kernel CLI

## Programmatic API

Import `l4_kernel.registry` for domain registration queries.

## Configuration

- Stack: python
- Dependencies: see [`../pyproject.toml`](../pyproject.toml) (Python) or [`../package.json`](../package.json) (TypeScript).
- Environment variables and ports: see workspace `protocols/port-registry.yaml` and root `.env.example`.

## Tests

See [`../README.md`](../README.md) for the test command.
