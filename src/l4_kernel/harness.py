"""Deterministic read-only Harness for L4 Phase 0 contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from yaml.nodes import MappingNode, ScalarNode

from l4_kernel.contracts import DomainHealth, DomainManifest, ValidationIssue, ValidationResult
from l4_kernel.harness_profiles import GATES, PROFILE_GATES
from l4_kernel.path_policy import PathPolicyError, resolve_within
from l4_kernel.skill_loader import ACTION_CATALOG

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass(frozen=True, slots=True)
class HarnessSummary:
    """Aggregate result for one explicit registry run."""

    domains: tuple[DomainHealth, ...]

    @property
    def total(self) -> int:
        return len(self.domains)

    @property
    def configuration_errors(self) -> int:
        return sum(not health.ok for health in self.domains)

    @property
    def ok(self) -> bool:
        return self.configuration_errors == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "total": self.total,
            "configuration_errors": self.configuration_errors,
            "domains": [health.to_dict() for health in self.domains],
        }


@dataclass(frozen=True, slots=True)
class _Asset:
    kind: str
    asset_id: str
    path: Path
    body: dict[str, Any]


class HarnessRunner:
    """Run stable, read-only gates over validated domain manifests."""

    def __init__(self, registry: Any | None = None, *, action_catalog: Iterable[str] = ACTION_CATALOG) -> None:
        self.registry = registry
        self.action_catalog = frozenset(action_catalog)

    def compile_assets(self, root: Path) -> ValidationResult:
        """Compile declarative skill/workflow assets without executing them."""

        issues: list[ValidationIssue] = []
        assets: list[_Asset] = []
        for kind, directory in (
            ("skill", root / "_control" / "skills"),
            ("workflow", root / "_control" / "workflows"),
        ):
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.yaml")):
                assets.extend(self._load_assets(path, kind, issues))

        by_id: dict[str, _Asset] = {}
        for asset in assets:
            if asset.asset_id in by_id:
                issues.append(
                    self._compile_issue(
                        asset.path,
                        f"duplicate asset id: {asset.asset_id}; first declared in {by_id[asset.asset_id].path}",
                    )
                )
            else:
                by_id[asset.asset_id] = asset

        skill_ids = {asset.asset_id for asset in assets if asset.kind == "skill"}
        workflow_ids = {asset.asset_id for asset in assets if asset.kind == "workflow"}
        for asset in assets:
            self._validate_actions(asset, issues)
            skill_refs = self._refs(asset, "skill_refs")
            if asset.kind == "workflow":
                skill_refs += self._refs(asset, "skills")
            for ref in skill_refs:
                if ref not in skill_ids:
                    issues.append(self._compile_issue(asset.path, f"unresolved skill reference: {ref}"))
            for ref in self._refs(asset, "workflow_refs"):
                if ref not in workflow_ids:
                    issues.append(self._compile_issue(asset.path, f"unresolved workflow reference: {ref}"))

        return ValidationResult(tuple(issues))

    def run(self, manifest: DomainManifest, gates: tuple[str, ...]) -> DomainHealth:
        """Run an explicit ordered gate set over one manifest."""

        issues: list[ValidationIssue] = []
        for gate in gates:
            if gate not in GATES:
                issues.append(
                    ValidationIssue(
                        code="L4-HARNESS-002",
                        severity="error",
                        message=f"unsupported gate: {gate}",
                        path=manifest.root,
                        gate=gate,
                    )
                )
                continue
            issues.extend(getattr(self, f"_gate_{gate.lower()}")(manifest))

        return DomainHealth(
            domain_id=manifest.id,
            profile_id=manifest.harness_profile_ref,
            checked_at=datetime.now(UTC).isoformat(),
            issues=tuple(issues),
        )

    def run_profile(self, manifest: DomainManifest) -> DomainHealth:
        """Run the built-in profile selected by the manifest archetype."""

        return self.run(manifest, PROFILE_GATES[manifest.archetype])

    def run_all(self, gates: tuple[str, ...] | None = None) -> HarnessSummary:
        """Run all manifests from the registry supplied to the constructor."""

        if self.registry is None:
            raise ValueError("HarnessRunner.run_all requires an explicit registry")
        manifests = self.registry.list_all()
        health = tuple(self.run(manifest, gates or PROFILE_GATES[manifest.archetype]) for manifest in manifests)
        return HarnessSummary(health)

    def _load_assets(self, path: Path, kind: str, issues: list[ValidationIssue]) -> list[_Asset]:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            issues.append(self._compile_issue(path, str(exc)))
            return []

        fenced = re.findall(r"```ya?ml\s*\n(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            return self._load_fenced_assets(path, kind, fenced, issues)

        try:
            root_node = yaml.compose(text)
        except yaml.YAMLError as exc:
            line = exc.problem_mark.line + 1 if isinstance(exc, yaml.MarkedYAMLError) and exc.problem_mark else None
            issues.append(self._compile_issue(path, str(exc), line=line))
            return []
        if root_node is None:
            return []
        if not isinstance(root_node, MappingNode):
            issues.append(self._compile_issue(path, f"{kind} document must be a mapping"))
            return []

        wrapped_nodes = [
            value_node
            for key_node, value_node in root_node.value
            if isinstance(key_node, ScalarNode) and key_node.value == kind
        ]
        if wrapped_nodes:
            bodies = [yaml.safe_load(yaml.serialize(node)) for node in wrapped_nodes]
        else:
            bodies = [yaml.safe_load(text)]
        return [
            asset
            for body in bodies
            if (asset := self._asset_from_body(path, kind, body, issues)) is not None
        ]

    def _load_fenced_assets(
        self,
        path: Path,
        kind: str,
        fenced: list[str],
        issues: list[ValidationIssue],
    ) -> list[_Asset]:
        assets: list[_Asset] = []
        for block in fenced:
            try:
                body = yaml.safe_load(block)
            except yaml.YAMLError as exc:
                line = exc.problem_mark.line + 1 if isinstance(exc, yaml.MarkedYAMLError) and exc.problem_mark else None
                issues.append(self._compile_issue(path, str(exc), line=line))
                continue
            asset = self._asset_from_body(path, kind, body, issues)
            if asset is not None:
                assets.append(asset)
        return assets

    def _asset_from_body(
        self,
        path: Path,
        kind: str,
        body: Any,
        issues: list[ValidationIssue],
    ) -> _Asset | None:
        if not isinstance(body, dict):
            issues.append(self._compile_issue(path, f"{kind} body must be a mapping"))
            return None
        asset_id = body.get("id")
        if not isinstance(asset_id, str) or not asset_id.strip():
            issues.append(self._compile_issue(path, f"{kind} id must be a non-empty string"))
            return None
        return _Asset(kind=kind, asset_id=asset_id.strip(), path=path, body=body)

    def _validate_actions(self, asset: _Asset, issues: list[ValidationIssue]) -> None:
        steps = asset.body.get("steps", [])
        if steps is None:
            return
        if not isinstance(steps, list):
            issues.append(self._compile_issue(asset.path, "steps must be a list"))
            return
        for step in steps:
            if not isinstance(step, dict):
                issues.append(self._compile_issue(asset.path, "each step must be a mapping"))
                continue
            action = step.get("action")
            if action is None:
                continue
            if not isinstance(action, str) or action not in self.action_catalog:
                issues.append(self._compile_issue(asset.path, f"unregistered action: {action}"))

    @staticmethod
    def _refs(asset: _Asset, field: str) -> list[str]:
        value = asset.body.get(field, [])
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, str) and item]

    @staticmethod
    def _compile_issue(path: Path, message: str, *, line: int | None = None) -> ValidationIssue:
        return ValidationIssue(
            code="L4-COMPILE-004",
            severity="error",
            message=message,
            path=path,
            line=line,
            gate="T4",
        )

    @staticmethod
    def _gate_t0(manifest: DomainManifest) -> tuple[ValidationIssue, ...]:
        if manifest.root.is_dir():
            return ()
        return (
            ValidationIssue(
                code="L4-ROOT-000",
                severity="error",
                message="domain root does not exist or is not a directory",
                path=manifest.root,
                gate="T0",
            ),
        )

    @staticmethod
    def _gate_t1(manifest: DomainManifest) -> tuple[ValidationIssue, ...]:
        expected = f"harness://{manifest.archetype}/v1"
        if manifest.harness_profile_ref == expected:
            return ()
        return (
            ValidationIssue(
                code="L4-PROFILE-001",
                severity="error",
                message=f"harness profile mismatch: expected {expected}",
                path=manifest.root,
                gate="T1",
            ),
        )

    @staticmethod
    def _gate_t2(manifest: DomainManifest) -> tuple[ValidationIssue, ...]:
        if manifest.policy_refs:
            return ()
        return (
            ValidationIssue(
                code="L4-REFERENCE-002",
                severity="warning",
                message="domain has no policy references",
                path=manifest.root,
                gate="T2",
            ),
        )

    def _gate_t4(self, manifest: DomainManifest) -> tuple[ValidationIssue, ...]:
        return self.compile_assets(manifest.root).issues

    @staticmethod
    def _gate_t7(manifest: DomainManifest) -> tuple[ValidationIssue, ...]:
        issues: list[ValidationIssue] = []
        try:
            resolve_within(manifest.root, ".")
        except PathPolicyError as exc:
            issues.append(
                ValidationIssue(exc.code, "error", exc.message, manifest.root, gate="T7")
            )
        if not manifest.space_ref:
            issues.append(HarnessRunner._policy_issue(manifest, "space_ref is required"))
        if not manifest.principal_ref:
            issues.append(HarnessRunner._policy_issue(manifest, "principal_ref is required"))
        elif manifest.principal_ref not in manifest.owners:
            issues.append(HarnessRunner._policy_issue(manifest, "principal_ref must reference an owner"))
        sensitivity_rank = {"internal": 0, "private": 1, "confidential": 2, "restricted": 3}
        if manifest.archetype == "private-core" and sensitivity_rank.get(manifest.default_sensitivity, -1) < 1:
            issues.append(HarnessRunner._policy_issue(manifest, "private-core sensitivity must be private or stronger"))
        if manifest.archetype in {"projection", "federation"} and manifest.authority_policy == "canonical_write":
            issues.append(HarnessRunner._policy_issue(manifest, f"{manifest.archetype} forbids canonical_write"))
        return tuple(issues)

    @staticmethod
    def _policy_issue(manifest: DomainManifest, message: str) -> ValidationIssue:
        return ValidationIssue(
            code="L4-POLICY-007",
            severity="error",
            message=message,
            path=manifest.root,
            gate="T7",
        )
