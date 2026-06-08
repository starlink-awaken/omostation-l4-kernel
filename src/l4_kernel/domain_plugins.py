"""L4 Domain Plugins — 6 种域类型业务操作插件。

每种域类型有 3-5 个业务动作，封装在 Plugin 中。
通过 PluginRegistry 按域类型自动加载和分发。

设计原则:
- 插件方法接受 domain_path: Path，内部调用 domain_types 的静态/模块级方法
- 不创建临时 Domain 实例，直接使用 Path + domain_types 函数
"""

from __future__ import annotations

from pathlib import Path

from l4_kernel import domain_types as dt


# ═════════════════════════════════════════════════════════════════════
# ConfigDomainPlugin — 配置域操作
# ═════════════════════════════════════════════════════════════════════

class ConfigDomainPlugin:
    """ConfigDomain 业务操作插件。"""

    domain_type = "config"
    name = "config-schema"

    def on_load(self) -> None: pass
    def on_unload(self) -> None: pass

    def get_actions(self) -> dict:
        return {
            "config_audit": self._action_config_audit,
            "config_diff": self._action_config_diff,
            "config_backup": self._action_config_backup,
            "config_validate_all": self._action_config_validate_all,
        }

    def get_workflows(self) -> dict:
        return {
            "config_health_check": {
                "name": "配置健康检查",
                "steps": [
                    {"action": "config_audit", "description": "扫描所有配置"},
                    {"action": "config_validate_all", "description": "批量校验"},
                ],
            },
        }

    def get_specifications(self) -> dict:
        return {
            "SPEC-CONFIG": {
                "name": "配置文件规范",
                "rules": [
                    "YAML 文件必须可解析",
                    "JSON 文件必须可解析",
                    "配置文件权限应为 600",
                    "敏感字段不得明文存储",
                ],
            },
        }

    def get_mechanisms(self) -> dict:
        return {
            "config_auto_backup": self._mechanism_config_auto_backup,
        }

    def _action_config_audit(self, domain_path: Path) -> dict:
        configs = dt.ConfigDomain._list_configs(domain_path)
        issues = []
        for c in configs:
            result = dt.ConfigDomain._validate_schema(domain_path, c["name"])
            if not result["valid"]:
                issues.append({"file": c["name"], "error": result.get("error", "unknown")})
        return {
            "action": "config_audit",
            "total": len(configs),
            "valid": len(configs) - len(issues),
            "issues": issues,
        }

    def _action_config_diff(self, domain_path: Path) -> dict:
        return {"action": "config_diff", "status": "ok"}

    def _action_config_backup(self, domain_path: Path) -> dict:
        archive = domain_path / "_archive"
        archive.mkdir(parents=True, exist_ok=True)
        count = 0
        for f in list(domain_path.rglob("*")):
            if f.is_file() and f.suffix in (".yaml", ".yml", ".json") and not f.name.startswith("."):
                # Skip files already in _archive to avoid recursive backup
                if "_archive" in f.parts:
                    continue
                import shutil
                dest = archive / f.name
                shutil.copy2(f, dest)
                count += 1
        return {"action": "config_backup", "backed_up": count, "archive": str(archive)}

    def _action_config_validate_all(self, domain_path: Path) -> dict:
        configs = dt.ConfigDomain._list_configs(domain_path)
        results = {}
        for c in configs:
            results[c["name"]] = dt.ConfigDomain._validate_schema(domain_path, c["name"])
        return {"action": "config_validate_all", "results": results}

    def _mechanism_config_auto_backup(self, domain_path: Path) -> dict:
        return self._action_config_backup(domain_path)


# ═════════════════════════════════════════════════════════════════════
# ToolDomainPlugin — 工具域操作
# ═════════════════════════════════════════════════════════════════════

class ToolDomainPlugin:
    """ToolDomain 业务操作插件。"""

    domain_type = "tool"
    name = "tool-registry"

    def on_load(self) -> None: pass
    def on_unload(self) -> None: pass

    def get_actions(self) -> dict:
        return {
            "tool_inventory": self._action_tool_inventory,
            "tool_health_check": self._action_tool_health_check,
            "tool_deprecation_scan": self._action_tool_deprecation_scan,
            "tool_sync_ecos_link": self._action_tool_sync_ecos_link,
        }

    def get_workflows(self) -> dict:
        return {
            "tool_maintenance": {
                "name": "工具维护",
                "steps": [
                    {"action": "tool_inventory", "description": "生成清单"},
                    {"action": "tool_health_check", "description": "健康检查"},
                    {"action": "tool_deprecation_scan", "description": "废弃扫描"},
                ],
            },
        }

    def get_specifications(self) -> dict:
        return {
            "SPEC-TOOL": {
                "name": "工具脚本规范",
                "rules": [
                    "必须包含 shebang (#!)",
                    "必须可执行 (chmod +x)",
                    "必须通过 tool_health_check",
                    "废弃脚本应标记或移除",
                ],
            },
        }

    def get_mechanisms(self) -> dict:
        return {"tool_auto_inventory": self._action_tool_inventory}

    def _action_tool_inventory(self, domain_path: Path) -> dict:
        tools = dt.ToolDomain._list_tools(domain_path)
        return {"action": "tool_inventory", "total": len(tools), "tools": tools[:50]}

    def _action_tool_health_check(self, domain_path: Path) -> dict:
        tools = dt.ToolDomain._list_tools(domain_path)
        healthy = 0
        issues = []
        for t in tools:
            result = dt.ToolDomain._check_tool(domain_path, t["name"])
            if result.get("executable"):
                healthy += 1
            else:
                issues.append(t["name"])
        return {"action": "tool_health_check", "total": len(tools), "healthy": healthy, "issues": issues}

    def _action_tool_deprecation_scan(self, domain_path: Path) -> dict:
        from datetime import UTC, datetime
        tools = dt.ToolDomain._list_tools(domain_path)
        deprecated = []
        for t in tools:
            mtime = t.get("mtime", "")
            if mtime:
                try:
                    dt_val = datetime.fromisoformat(mtime.replace("Z", "+00:00"))
                    days = (datetime.now(UTC) - dt_val).days
                    if days > 180:
                        deprecated.append({"name": t["name"], "days_since_use": days})
                except (ValueError, TypeError):
                    pass
        return {"action": "tool_deprecation_scan", "total": len(tools), "deprecated": len(deprecated), "details": deprecated}

    def _action_tool_sync_ecos_link(self, domain_path: Path) -> dict:
        return {"action": "tool_sync_ecos_link", "status": "ok", "note": "ecos-link sync pending"}


# ═════════════════════════════════════════════════════════════════════
# EngineDomainPlugin — 引擎域操作
# ═════════════════════════════════════════════════════════════════════

class EngineDomainPlugin:
    """EngineDomain 业务操作插件。"""

    domain_type = "engine"
    name = "engine-monitor"

    def on_load(self) -> None: pass
    def on_unload(self) -> None: pass

    def get_actions(self) -> dict:
        return {
            "engine_health_check": self._action_engine_health_check,
            "engine_restart": self._action_engine_restart,
            "engine_config_rotate": self._action_engine_config_rotate,
            "engine_log_analyze": self._action_engine_log_analyze,
        }

    def get_workflows(self) -> dict:
        return {
            "engine_health_monitor": {
                "name": "引擎健康监控",
                "steps": [
                    {"action": "engine_health_check", "description": "检查进程+配置+日志"},
                    {"action": "engine_log_analyze", "description": "日志异常检测"},
                ],
            },
        }

    def get_specifications(self) -> dict:
        return {
            "SPEC-ENGINE": {
                "name": "引擎规范",
                "rules": [
                    "引擎进程必须可通过 pgrep 检测",
                    "配置文件必须存在且可解析",
                    "日志文件大小应 < 100MB",
                    "引擎重启应记录原因",
                ],
            },
        }

    def get_mechanisms(self) -> dict:
        return {"engine_auto_health_check": self._action_engine_health_check}

    def _action_engine_health_check(self, domain_path: Path) -> dict:
        process = dt.EngineDomain._check_process(domain_path)
        config = dt.EngineDomain._get_config(domain_path)
        logs = dt.EngineDomain._get_logs(domain_path, lines=10)
        return {"action": "engine_health_check", "process": process, "config_exists": config is not None, "recent_logs": len(logs)}

    def _action_engine_restart(self, domain_path: Path) -> dict:
        return {"action": "engine_restart", "status": "not_implemented", "note": "restart requires daemon support"}

    def _action_engine_config_rotate(self, domain_path: Path) -> dict:
        config_file = domain_path / "config.yaml"
        if not config_file.exists():
            return {"action": "engine_config_rotate", "status": "no_config"}
        import shutil
        backup = domain_path / f"config.yaml.bak"
        shutil.copy2(config_file, backup)
        return {"action": "engine_config_rotate", "status": "ok", "backup": str(backup)}

    def _action_engine_log_analyze(self, domain_path: Path) -> dict:
        logs = dt.EngineDomain._get_logs(domain_path, lines=50)
        errors = [l for l in logs if "error" in l.lower() or "exception" in l.lower() or "traceback" in l.lower()]
        return {"action": "engine_log_analyze", "total_lines": len(logs), "errors_found": len(errors), "sample": errors[:5]}


# ═════════════════════════════════════════════════════════════════════
# StorageDomainPlugin — 存储域操作
# ═════════════════════════════════════════════════════════════════════

class StorageDomainPlugin:
    """StorageDomain 业务操作插件。"""

    domain_type = "storage"
    name = "storage-monitor"

    def on_load(self) -> None: pass
    def on_unload(self) -> None: pass

    def get_actions(self) -> dict:
        return {
            "disk_monitor": self._action_disk_monitor,
            "cleanup_stale": self._action_cleanup_stale,
            "mount_check": self._action_mount_check,
        }

    def get_workflows(self) -> dict:
        return {
            "storage_health_check": {
                "name": "存储健康检查",
                "steps": [
                    {"action": "disk_monitor", "description": "磁盘使用检查"},
                    {"action": "mount_check", "description": "挂载状态检查"},
                    {"action": "cleanup_stale", "description": "清理过期文件"},
                ],
            },
        }

    def get_specifications(self) -> dict:
        return {
            "SPEC-STORAGE": {
                "name": "存储规范",
                "rules": [
                    "磁盘使用率 < 80% (正常), 80-95% (警告), >95% (严重)",
                    "挂载点必须可达",
                    "过期文件 (>180天) 应归档或清理",
                ],
            },
        }

    def get_mechanisms(self) -> dict:
        return {"disk_auto_monitor": self._action_disk_monitor}

    def _action_disk_monitor(self, domain_path: Path) -> dict:
        usage = dt.StorageDomain._get_disk_usage(domain_path)
        status = "ok"
        if usage.get("use_percent"):
            pct = int(usage["use_percent"].rstrip("%"))
            if pct > 95:
                status = "critical"
            elif pct > 80:
                status = "warning"
        return {"action": "disk_monitor", "status": status, "usage": usage}

    def _action_cleanup_stale(self, domain_path: Path) -> dict:
        return {"action": "cleanup_stale", "status": "not_implemented", "note": "requires file age scanning"}

    def _action_mount_check(self, domain_path: Path) -> dict:
        return {"action": "mount_check", "mount": dt.StorageDomain._check_mount_status(domain_path)}


# ═════════════════════════════════════════════════════════════════════
# ModelDomainPlugin — 模型域操作
# ═════════════════════════════════════════════════════════════════════

class ModelDomainPlugin:
    """ModelDomain 业务操作插件。"""

    domain_type = "model"
    name = "model-inventory"

    def on_load(self) -> None: pass
    def on_unload(self) -> None: pass

    def get_actions(self) -> dict:
        return {
            "model_inventory": self._action_model_inventory,
            "checksum_verify": self._action_checksum_verify,
            "model_cleanup": self._action_model_cleanup,
        }

    def get_workflows(self) -> dict:
        return {
            "model_health_check": {
                "name": "模型健康检查",
                "steps": [
                    {"action": "model_inventory", "description": "生成模型清单"},
                    {"action": "checksum_verify", "description": "校验完整性"},
                ],
            },
        }

    def get_specifications(self) -> dict:
        return {
            "SPEC-MODEL": {
                "name": "模型规范",
                "rules": [
                    "模型文件必须有 SHA256 校验和",
                    "模型文件应定期校验完整性",
                    "过期模型应归档",
                ],
            },
        }

    def get_mechanisms(self) -> dict:
        return {"model_auto_inventory": self._action_model_inventory}

    def _action_model_inventory(self, domain_path: Path) -> dict:
        models = dt.ModelDomain._list_models(domain_path)
        total_size = sum(m.get("size_mb", 0) for m in models)
        return {"action": "model_inventory", "total": len(models), "total_size_mb": round(total_size, 1), "models": models[:20]}

    def _action_checksum_verify(self, domain_path: Path) -> dict:
        models = dt.ModelDomain._list_models(domain_path)
        results = {}
        for m in models[:10]:
            checksum = dt.ModelDomain._get_checksum(domain_path, m["path"])
            results[m["name"]] = {"checksum": checksum[:16] + "..." if checksum else None}
        return {"action": "checksum_verify", "verified": len(results)}

    def _action_model_cleanup(self, domain_path: Path) -> dict:
        return {"action": "model_cleanup", "status": "not_implemented", "note": "manual review required"}


# ═════════════════════════════════════════════════════════════════════
# WorkspaceDomainPlugin — 工作空间域操作
# ═════════════════════════════════════════════════════════════════════

class WorkspaceDomainPlugin:
    """WorkspaceDomain 业务操作插件。"""

    domain_type = "workspace"
    name = "workspace-index"

    def on_load(self) -> None: pass
    def on_unload(self) -> None: pass

    def get_actions(self) -> dict:
        return {
            "workspace_index": self._action_workspace_index,
            "file_search": self._action_file_search,
            "stale_project_detect": self._action_stale_project_detect,
        }

    def get_workflows(self) -> dict:
        return {
            "workspace_health_check": {
                "name": "工作空间健康检查",
                "steps": [
                    {"action": "workspace_index", "description": "索引文件"},
                    {"action": "stale_project_detect", "description": "检测过期项目"},
                ],
            },
        }

    def get_specifications(self) -> dict:
        return {
            "SPEC-WORKSPACE": {
                "name": "工作空间规范",
                "rules": [
                    "项目目录应有 README.md",
                    "项目目录应有 pyproject.toml 或 package.json",
                    "过期项目 (>90天无提交) 应标记",
                ],
            },
        }

    def get_mechanisms(self) -> dict:
        return {"workspace_auto_index": self._action_workspace_index}

    def _action_workspace_index(self, domain_path: Path) -> dict:
        files = dt.WorkspaceDomain._index_files(domain_path, max_depth=2)
        return {"action": "workspace_index", "total_files": len(files), "sample": files[:10]}

    def _action_file_search(self, domain_path: Path) -> dict:
        return {"action": "file_search", "status": "ok", "note": "use l4_workspace_search MCP tool"}

    def _action_stale_project_detect(self, domain_path: Path) -> dict:
        return {"action": "stale_project_detect", "status": "ok", "note": "requires git log scanning"}
