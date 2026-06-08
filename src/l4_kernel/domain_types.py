"""L4 Domain Types — 7 种域类型特化。

每种域类型继承 Domain 基类，添加类型特定的操作。
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import yaml

from l4_kernel.registry import Domain


# ═════════════════════════════════════════════════════════════════════
# DocumentDomain — KEMS 六面域
# ═════════════════════════════════════════════════════════════════════

class DocumentDomain(Domain):
    """DocumentDomain — 有 KEMS 六面结构的域。

    这是 L4 中最复杂的域类型，管理 5-6 个平面。
    """

    def validate_kems_planes(self) -> list[str]:
        """检查 KEMS 面是否存在。"""
        missing = []
        for plane in self.kems_planes:
            p = self.path / plane
            if not p.is_dir():
                missing.append(f"missing plane: {plane}")
        return missing

    def get_control_files(self) -> dict[str, bool]:
        """检查控制面标准文件存在性。"""
        control = self.path / "_control"
        files = {}
        for f in ["STATE.md", "MEMORY.md", "TIMELINE.md", "signals.md",
                   "control-rules.md", "STATUS.md", "PLANE_INDEX.md", "CLAUDE.md"]:
            files[f] = (control / f).exists()
        files["决策日志/"] = (control / "决策日志").is_dir()
        return files

    def get_storage_stats(self) -> dict:
        """获取存储面统计。"""
        storage = self.path / "_storage"
        if not storage.is_dir():
            return {"files": 0, "total_size_mb": 0}
        total_size = 0
        file_count = 0
        for f in storage.rglob("*"):
            if f.is_file() and not f.name.startswith("."):
                try:
                    total_size += f.stat().st_size
                    file_count += 1
                except OSError:
                    pass
        return {"files": file_count, "total_size_mb": round(total_size / (1024 * 1024), 1)}


# ═════════════════════════════════════════════════════════════════════
# ConfigDomain — YAML/JSON 配置域
# ═════════════════════════════════════════════════════════════════════

class ConfigDomain(Domain):
    """ConfigDomain — 配置文件域。

    管理 YAML/JSON 配置文件的读写和校验。
    """

    def list_configs(self) -> list[dict]:
        """列出所有配置文件。"""
        configs = []
        if not self.path.is_dir():
            return configs
        for f in sorted(self.path.rglob("*")):
            if f.is_file() and f.suffix in (".yaml", ".yml", ".json") and not f.name.startswith("."):
                try:
                    stat = f.stat()
                    configs.append({
                        "name": str(f.relative_to(self.path)),
                        "type": f.suffix.lstrip("."),
                        "size": stat.st_size,
                        "mtime": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                    })
                except OSError:
                    pass
        return configs

    def read_config(self, relative_path: str) -> dict | None:
        """读取 YAML/JSON 配置文件。"""
        fp = self.path / relative_path
        if not fp.exists():
            return None
        try:
            text = fp.read_text(encoding="utf-8")
            if fp.suffix == ".json":
                return json.loads(text)
            return yaml.safe_load(text) or {}
        except (json.JSONDecodeError, yaml.YAMLError, OSError):
            return None

    def validate_schema(self, relative_path: str) -> dict:
        """基本 Schema 校验 (检查是否能正确解析)。"""
        data = self.read_config(relative_path)
        if data is None:
            return {"valid": False, "error": "parse_failed", "path": relative_path}
        if isinstance(data, dict):
            return {"valid": True, "type": "object", "keys": list(data.keys())[:20]}
        if isinstance(data, list):
            return {"valid": True, "type": "array", "count": len(data)}
        return {"valid": True, "type": type(data).__name__}


# ═════════════════════════════════════════════════════════════════════
# ToolDomain — 脚本工具域
# ═════════════════════════════════════════════════════════════════════

class ToolDomain(Domain):
    """ToolDomain — 脚本工具域。

    管理 ~/bin 和 ~/ToolBox 下的可执行脚本。
    """

    def list_tools(self) -> list[dict]:
        """列出所有可执行脚本。"""
        tools = []
        if not self.path.is_dir():
            return tools
        for f in sorted(self.path.rglob("*")):
            if f.is_file() and os.access(f, os.X_OK) and not f.name.startswith("."):
                try:
                    stat = f.stat()
                    shebang = ""
                    try:
                        shebang = f.read_text(encoding="utf-8").split("\n")[0]
                        if not shebang.startswith("#!"):
                            shebang = ""
                    except (OSError, UnicodeDecodeError):
                        pass
                    tools.append({
                        "name": f.name,
                        "path": str(f.relative_to(self.path)),
                        "size": stat.st_size,
                        "shebang": shebang[:50],
                        "mtime": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                    })
                except OSError:
                    pass
        return tools

    def check_tool(self, name: str) -> dict:
        """检查单个工具的可执行性和元数据。"""
        fp = self.path / name
        if not fp.exists():
            return {"name": name, "status": "not_found"}
        return {
            "name": name,
            "status": "ok",
            "executable": os.access(fp, os.X_OK),
            "size": fp.stat().st_size if fp.is_file() else 0,
        }


# ═════════════════════════════════════════════════════════════════════
# WorkspaceDomain — 工作空间域
# ═════════════════════════════════════════════════════════════════════

class WorkspaceDomain(Domain):
    """WorkspaceDomain — 共享工作空间域。"""

    def index_files(self, max_depth: int = 3) -> list[dict]:
        """索引工作空间文件。"""
        files = []
        if not self.path.is_dir():
            return files
        for f in self.path.rglob("*"):
            if f.is_file() and not f.name.startswith("."):
                depth = len(f.relative_to(self.path).parts)
                if depth <= max_depth:
                    try:
                        stat = f.stat()
                        files.append({
                            "path": str(f.relative_to(self.path)),
                            "size": stat.st_size,
                            "mtime": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                        })
                    except OSError:
                        pass
        return files

    def search_files(self, pattern: str) -> list[str]:
        """按文件名模式搜索。"""
        results = []
        if not self.path.is_dir():
            return results
        pattern_lower = pattern.lower()
        for f in self.path.rglob("*"):
            if f.is_file() and pattern_lower in f.name.lower() and not f.name.startswith("."):
                results.append(str(f.relative_to(self.path)))
        return results[:20]


# ═════════════════════════════════════════════════════════════════════
# StorageDomain — 存储域
# ═════════════════════════════════════════════════════════════════════

class StorageDomain(Domain):
    """StorageDomain — 存储盘域。"""

    def get_disk_usage(self) -> dict:
        """获取磁盘使用情况 (df -h)。"""
        if not self.path.exists():
            return {"status": "not_mounted", "path": str(self.path)}
        try:
            result = subprocess.run(
                ["df", "-h", str(self.path)],
                capture_output=True, text=True, timeout=5,
            )
            lines = result.stdout.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 5:
                    return {
                        "status": "mounted",
                        "filesystem": parts[0],
                        "size": parts[1],
                        "used": parts[2],
                        "available": parts[3],
                        "use_percent": parts[4],
                    }
        except (subprocess.TimeoutExpired, OSError):
            pass
        return {"status": "mounted", "path": str(self.path)}

    def check_mount_status(self) -> dict:
        """检查挂载状态。"""
        return {
            "path": str(self.path),
            "mounted": self.path.exists(),
            "is_dir": self.path.is_dir() if self.path.exists() else False,
        }


# ═════════════════════════════════════════════════════════════════════
# ModelDomain — 模型域
# ═════════════════════════════════════════════════════════════════════

class ModelDomain(Domain):
    """ModelDomain — 模型文件域。"""

    def list_models(self) -> list[dict]:
        """列出所有模型文件。"""
        models = []
        if not self.path.is_dir():
            return models
        for f in sorted(self.path.rglob("*")):
            if f.is_file() and not f.name.startswith("."):
                try:
                    stat = f.stat()
                    models.append({
                        "name": f.name,
                        "path": str(f.relative_to(self.path)),
                        "size_mb": round(stat.st_size / (1024 * 1024), 1),
                        "mtime": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                    })
                except OSError:
                    pass
        return models

    def get_model_checksum(self, relative_path: str) -> str | None:
        """获取模型文件的 SHA256 校验和。"""
        import hashlib

        fp = self.path / relative_path
        if not fp.is_file():
            return None
        sha = hashlib.sha256()
        with open(fp, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest()


# ═════════════════════════════════════════════════════════════════════
# EngineDomain — 引擎域
# ═════════════════════════════════════════════════════════════════════

class EngineDomain(Domain):
    """EngineDomain — 运行引擎域。"""

    def check_process(self, process_name: str | None = None) -> dict:
        """检查引擎进程是否存活。"""
        name = process_name or self.id
        try:
            result = subprocess.run(
                ["pgrep", "-f", name],
                capture_output=True, text=True, timeout=5,
            )
            pids = [p for p in result.stdout.strip().split("\n") if p]
            return {"name": name, "running": len(pids) > 0, "pids": pids}
        except (subprocess.TimeoutExpired, OSError):
            return {"name": name, "running": False, "error": "pgrep failed"}

    def get_config(self, config_file: str = "config.yaml") -> dict | None:
        """读取引擎配置文件。"""
        fp = self.path / config_file
        if not fp.exists():
            return None
        try:
            return yaml.safe_load(fp.read_text(encoding="utf-8")) or {}
        except (yaml.YAMLError, OSError):
            return None

    def get_logs(self, log_file: str = "daemon.log", lines: int = 20) -> list[str]:
        """读取最近 N 行日志。"""
        fp = self.path / log_file
        if not fp.exists():
            return []
        try:
            content = fp.read_text(encoding="utf-8")
            return content.strip().split("\n")[-lines:]
        except OSError:
            return []


# ═════════════════════════════════════════════════════════════════════
# 工厂函数
# ═════════════════════════════════════════════════════════════════════

def wrap_domain(domain: Domain):
    """将 Domain 包装为对应的特化类型。"""
    mapping = {
        "document": DocumentDomain,
        "config": ConfigDomain,
        "tool": ToolDomain,
        "workspace": WorkspaceDomain,
        "storage": StorageDomain,
        "model": ModelDomain,
        "engine": EngineDomain,
    }
    cls = mapping.get(domain.domain_type, Domain)
    # 创建一个新实例，继承 domain 的属性
    return cls(
        id=domain.id,
        name=domain.name,
        domain_type=domain.domain_type,
        path=domain.path,
        bos_uri=domain.bos_uri,
        kems_planes=domain.kems_planes,
        governance_tier=domain.governance_tier,
        capabilities=domain.capabilities,
    )
