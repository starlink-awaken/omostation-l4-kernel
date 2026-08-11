"""Opt-in integration checks against the real Documents registry."""

import os

import pytest

from l4_kernel.config_loader import resolve_registry_path
from l4_kernel.harness import HarnessRunner
from l4_kernel.manifest_registry import ManifestRegistry

pytestmark = pytest.mark.skipif(
    not os.environ.get("L4_DOMAIN_REGISTRY"),
    reason="real Documents contract test requires L4_DOMAIN_REGISTRY",
)


def test_real_documents_registry_compiles() -> None:
    registry = ManifestRegistry.load(resolve_registry_path())
    health = HarnessRunner(registry).run_all()

    assert health.total == 12
    assert health.configuration_errors == 0
