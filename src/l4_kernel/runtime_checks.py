#!/usr/bin/env python3
"""
Runtime Checks — 统一运行时检查
从各域 _runtime/ 下沉，统一 signal_scan / freshness_check / meta_sync 能力。
"""

from datetime import datetime
from pathlib import Path


def signal_scan(domain_root: Path) -> list[dict]:
    """扫描域信号（统一实现）"""
    signals = []
    signals_file = Path(domain_root) / "_control" / "signals.md"
    if signals_file.exists():
        content = signals_file.read_text(encoding="utf-8")
        for line in content.split("\n"):
            if line.startswith("- ") or line.startswith("* "):
                signals.append(
                    {
                        "content": line.strip("- *").strip(),
                        "source": str(signals_file.relative_to(domain_root)),
                        "timestamp": datetime.fromtimestamp(signals_file.stat().st_mtime).isoformat(),
                    }
                )
    return signals


def freshness_check(domain_root: Path, days: int = 90) -> list[dict]:
    """检查过期文档（统一实现）"""
    stale = []
    knowledge_dir = Path(domain_root) / "_knowledge"
    if knowledge_dir.exists():
        now = datetime.now().timestamp()
        threshold = days * 86400
        for md_file in knowledge_dir.rglob("*.md"):
            if md_file.name == "INDEX.md":
                continue
            mtime = md_file.stat().st_mtime
            if now - mtime > threshold:
                stale.append(
                    {
                        "file": str(md_file.relative_to(domain_root)),
                        "days_old": int((now - mtime) / 86400),
                        "last_modified": datetime.fromtimestamp(mtime).isoformat(),
                    }
                )
    stale.sort(key=lambda x: -x["days_old"])
    return stale


def meta_sync_check(domain_root: Path) -> dict:
    """元数据同步状态检查"""
    control_dir = Path(domain_root) / "_control"
    if not control_dir.exists():
        return {"status": "missing", "files": {}}

    required = ["sensors.md", "control-rules.md", "executor-rules.md", "l4-kernel.md"]
    result = {}
    for name in required:
        path = control_dir / name
        result[name] = {"exists": path.exists()}
    return {"status": "ok" if all(r["exists"] for r in result.values()) else "incomplete", "files": result}


def kems_health(domain_root: Path) -> dict:
    """KEMS 健康检查"""
    knowledge_dir = Path(domain_root) / "_knowledge"
    if not knowledge_dir.exists():
        return {"status": "missing"}

    has_extraction = (knowledge_dir / "_kems_extraction_report.json").exists()
    has_fusion = (knowledge_dir / "_kems_fusion_report.json").exists()
    has_graph = (knowledge_dir / "_kems_graph.json").exists()
    has_index = (knowledge_dir / "INDEX.md").exists()

    checks = {
        "extraction": has_extraction,
        "fusion": has_fusion,
        "graph": has_graph,
        "index": has_index,
    }
    passed = sum(checks.values())
    return {
        "status": "healthy" if passed == 4 else "partial" if passed > 0 else "missing",
        "checks": checks,
        "score": f"{passed}/4",
    }


if __name__ == "__main__":
    import sys

    domain = sys.argv[1] if len(sys.argv) > 1 else "卫健委"
    root = Path("/Users/xiamingxing/Documents/@工作文档") / domain

    print(f"Runtime Checks: {domain}")
    print(f"  Signals: {len(signal_scan(root))}")
    print(f"  Stale: {len(freshness_check(root))}")
    print(f"  Meta: {meta_sync_check(root)['status']}")
    print(f"  KEMS: {kems_health(root)['status']}")
