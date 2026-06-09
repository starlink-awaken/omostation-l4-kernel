"""L4 Consistency Check — 三源一致性校验。

对比 registry.py 的内置注册表、vault-paths.yaml、DOMAIN-INDEX.md，
输出差异报告并可选自动修复。

三源 SSOT 归属:
  - 域名/路径:    protocols/vault-paths.yaml（路径唯一 SSOT）
  - 域元数据:     registry.py _BUILTIN_DOMAINS（代码级注册）
  - 人类可读索引: DOMAIN-INDEX.md（驾驶舱聚合视图）
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from l4_kernel.registry import DomainRegistry

# ═════════════════════════════════════════════════════════════════════
# 路径定义
# ═════════════════════════════════════════════════════════════════════

HOME = Path.home()
VAULT_PATHS_YAML = HOME / "Workspace" / "protocols" / "vault-paths.yaml"
DOMAIN_INDEX_MD = HOME / "Documents" / "@驾驶舱" / "_control" / "DOMAIN-INDEX.md"


# ═════════════════════════════════════════════════════════════════════
# 数据加载
# ═════════════════════════════════════════════════════════════════════


def load_vault_paths() -> dict[str, str] | None:
    """加载 vault-paths.yaml。"""
    if not VAULT_PATHS_YAML.exists():
        return None
    try:
        data = yaml.safe_load(VAULT_PATHS_YAML.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "paths" in data:
            return data["paths"]
    except (yaml.YAMLError, OSError):
        pass
    return None


def load_domain_index() -> list[dict[str, str]] | None:
    """解析 DOMAIN-INDEX.md 表格行。"""
    if not DOMAIN_INDEX_MD.exists():
        return None
    try:
        lines = DOMAIN_INDEX_MD.read_text(encoding="utf-8").split("\n")
    except OSError:
        return None

    domains = []
    in_table = False
    for line in lines:
        if line.startswith("|---"):
            in_table = True
            continue
        if not in_table or not line.startswith("|"):
            if in_table and "|" not in line:
                break  # 表格结束
            continue
        cells = [c.strip() for c in line.split("|")]
        if len(cells) >= 5 and cells[1] and cells[2]:
            domains.append({
                "id": cells[1],
                "name": cells[2].replace("@", ""),
                "path": cells[4],
            })
    return domains


# ═════════════════════════════════════════════════════════════════════
# 一致性校验
# ═════════════════════════════════════════════════════════════════════


def check_consistency() -> dict[str, Any]:
    """三源一致性校验。

    Returns:
        {"status": "ok"|"diff", "total": N, "diff_count": N, "differences": [...]}
    """
    registry = DomainRegistry()
    registry_domains = registry.list_all()
    vault_paths = load_vault_paths()
    index_domains = load_domain_index()

    diffs = []
    registry_ids = {d.id for d in registry_domains}
    vault_keys = set(vault_paths.keys()) if vault_paths else set()
    index_ids = {d["id"] for d in index_domains} if index_domains else set()

    # 1. registry 有 → vault 无
    for d in registry_domains:
        expected_key = f"{d.id}_root"
        if vault_paths and expected_key not in vault_keys:
            # 算一下 vault 是否有其他形式
            alt_keys = [k for k in vault_keys if d.id in k]
            if not alt_keys:
                diffs.append({
                    "type": "registry_only",
                    "domain": d.id,
                    "source": "registry.py",
                    "detail": f"已在 registry.py 注册 ({d.name}), 但 vault-paths.yaml 无 {expected_key} 路径",
                    "fix": f"vault-paths.yaml 添加 {expected_key}: {d.path}",
                })

    # 2. registry 有 → DOMAIN-INDEX 无
    for d in registry_domains:
        if index_ids and d.id not in index_ids:
            diffs.append({
                "type": "registry_only",
                "domain": d.id,
                "source": "DOMAIN-INDEX.md",
                "detail": f"已在 registry.py 注册 ({d.name}), 但 DOMAIN-INDEX.md 无此域",
                "fix": "DOMAIN-INDEX.md 添加一行",
            })

    # 3. vault 有 → registry 无 (仅检查 *_root 路径)
    if vault_paths:
        for key in vault_keys:
            if key.endswith("_root"):
                domain_id = key.replace("_root", "")
                if domain_id not in registry_ids:
                    diffs.append({
                        "type": "vault_only",
                        "domain": domain_id,
                        "source": "vault-paths.yaml",
                        "detail": f"vault-paths.yaml 有 {key}, 但 registry.py 未注册 {domain_id}",
                        "fix": f"registry.py _BUILTIN_DOMAINS 添加 Domain(id='{domain_id}', ...)",
                    })

    # 4. vault 路径与 registry 路径不一致
    if vault_paths:
        for d in registry_domains:
            expected_key = f"{d.id}_root"
            if expected_key in vault_paths:
                vault_path = vault_paths[expected_key]
                if vault_path and vault_path != "null" and vault_path != "None":
                    expanded_vault = os.path.expanduser(str(vault_path))
                    registry_path = str(d.path)
                    # 只比较最后两级目录
                    v_parts = expanded_vault.rstrip("/").split("/")[-2:]
                    r_parts = registry_path.rstrip("/").split("/")[-2:]
                    if v_parts != r_parts:
                        diffs.append({
                            "type": "path_mismatch",
                            "domain": d.id,
                            "source": "vault-paths.yaml ↔ registry.py",
                            "detail": f"路径不一致: vault={vault_path} / registry={registry_path}",
                            "fix": f"统一为 {registry_path}",
                        })

    return {
        "total_registry": len(registry_domains),
        "total_vault_paths": len(vault_keys) if vault_paths else 0,
        "total_index": len(index_ids) if index_domains else 0,
        "diff_count": len(diffs),
        "differences": diffs,
        "status": "ok" if len(diffs) == 0 else "diff",
    }
