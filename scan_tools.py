#!/usr/bin/env python3
"""
工具扫描器 — 扫描所有域的工具并注册到 L4 Registry
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from l4_kernel.registry import DomainRegistry, _BUILTIN_DOMAINS


def build_path_overrides() -> dict:
    """从环境变量和默认值构建完整 path_overrides。"""
    overrides = {}
    for d in _BUILTIN_DOMAINS:
        env_key = f"L4_DOMAIN_PATH_{d.id.upper()}"
        env_val = os.environ.get(env_key)
        if env_val:
            overrides[d.id] = Path(env_val)
        else:
            overrides[d.id] = d.path
    return overrides


def main():
    path_overrides = build_path_overrides()
    registry = DomainRegistry(path_overrides=path_overrides)
    
    print("🔍 全域工具扫描")
    print("=" * 50)
    
    all_tools = registry.scan_all_tools()
    
    total_tools = 0
    total_domains = 0
    
    for domain_id, tools in sorted(all_tools.items()):
        d = registry.get(domain_id)
        if not d:
            continue
        
        total_domains += 1
        total_tools += len(tools)
        
        print(f"\n📁 {d.name} ({domain_id}) — {len(tools)} 工具")
        for t in tools:
            print(f"   {t.tool_type:12s} {t.name}")
    
    print(f"\n{'=' * 50}")
    print(f"✅ 扫描完成: {total_domains} 域, {total_tools} 工具")
    
    return registry


if __name__ == "__main__":
    main()
