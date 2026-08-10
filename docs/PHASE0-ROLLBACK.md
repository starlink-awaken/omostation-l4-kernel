# L4 Knowledge Sovereignty Phase 0 Rollback

Phase 0 adds a read-only contract and Harness surface. Rollback must preserve Documents canonical content and path containment.

## Runtime rollback

1. Set `L4_REGISTRY_MODE=legacy` only if the explicit `L4_DOMAIN_REGISTRY` path cannot be restored immediately.
2. Keep `L4_DOMAIN_REGISTRY` unset while the legacy registry is active.
3. If an old workflow absolutely requires direct file writes, set `L4_LEGACY_DIRECT_WRITE=1` for that process only. Remove it immediately after the compatibility run.
4. Never disable `resolve_within`; legacy writes remain constrained to their registered domain root.

## Code rollback

- Remove the new CLI/MCP registrations while retaining `contracts/`, `manifest_registry.py`, `harness.py`, and `path_policy.py` until callers are migrated.
- Restore the previous Space registry entries only; do not delete or move Documents content.
- Revert ECOS L4 M2 schemas only together with their consumer contract tests.
- Do not remove `DOMAIN.yaml` files until the old registry adapter is verified against all 12 knowledge domains.

## Verification

After rollback:

```bash
uv run pytest tests/test_path_policy.py tests/test_manifest_registry.py -q
L4_REGISTRY_MODE=legacy uv run l4-kernel domain list --json
```

Expected invariants:

- external sentinel hashes are unchanged;
- traversal, absolute paths, and symlink escapes still return `L4-PATH-006`;
- no process retains `L4_LEGACY_DIRECT_WRITE=1` after the rollback window;
- Documents canonical files are untouched.
