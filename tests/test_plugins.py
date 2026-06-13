"""Tests for L4 Kernel Plugin System."""


from l4_kernel.plugins import DocumentKemsPlugin, get_plugin_registry


class TestDocumentKemsPlugin:
    def test_domain_type(self):
        plugin = DocumentKemsPlugin()
        assert plugin.domain_type == "document"

    def test_get_actions(self):
        plugin = DocumentKemsPlugin()
        actions = plugin.get_actions()
        assert "state_review" in actions
        assert "signal_respond" in actions
        assert "status_evaluate" in actions
        assert "knowledge_index" in actions
        assert "entity_register" in actions
        assert "storage_archive" in actions
        assert "cross_domain_sync" in actions
        assert len(actions) >= 12

    def test_get_workflows(self):
        plugin = DocumentKemsPlugin()
        workflows = plugin.get_workflows()
        assert "daily_checkin" in workflows
        assert "weekly_review" in workflows
        assert "knowledge_ingest" in workflows

    def test_get_specifications(self):
        plugin = DocumentKemsPlugin()
        specs = plugin.get_specifications()
        assert "SPEC-STATE" in specs
        assert "SPEC-SIGNALS" in specs
        assert "SPEC-STATUS" in specs
        assert "SPEC-CONTROL-RULES" in specs

    def test_get_mechanisms(self):
        plugin = DocumentKemsPlugin()
        mechanisms = plugin.get_mechanisms()
        assert "signal_auto_respond" in mechanisms
        assert "freshness_auto_alert" in mechanisms
        assert "status_auto_evaluate" in mechanisms

    def test_action_state_review(self, tmp_path):
        plugin = DocumentKemsPlugin()
        # Create minimal KEMS
        control = tmp_path / "_control"
        control.mkdir()
        (control / "STATE.md").write_text("---\nstatus: active\n---\n# STATE\n")
        (control / "signals.md").write_text(
            "---\nsignals: []\n---\n| 类型 | 日期 | 信号 |\n| ✅ | 2026-01-01 | ok |\n"
        )
        result = plugin._action_state_review(tmp_path)
        assert result["action"] == "state_review"

    def test_action_status_evaluate(self, tmp_path):
        plugin = DocumentKemsPlugin()
        control = tmp_path / "_control"
        control.mkdir()
        (control / "signals.md").write_text(
            "---\nsignals:\n- {ts: '2026-06-08', type: '⚠️', message: 'test'}\n"
            "- {ts: '2026-06-08', type: '⚠️', message: 'test2'}\n"
            "- {ts: '2026-06-08', type: '⚠️', message: 'test3'}\n"
            "---\n"
        )
        (control / "STATUS.md").write_text("---\nstatus: STABLE\n---\n")
        result = plugin._action_status_evaluate(tmp_path)
        assert result["suggested"] == "ALERT"


class TestPluginRegistry:
    def test_singleton(self):
        reg1 = get_plugin_registry()
        reg2 = get_plugin_registry()
        assert reg1 is reg2

    def test_builtin_plugins_loaded(self):
        reg = get_plugin_registry()
        plugins = reg.get_plugins("document")
        assert len(plugins) >= 1

    def test_get_action(self):
        reg = get_plugin_registry()
        action = reg.get_action("document", "state_review")
        assert action is not None

    def test_get_workflow(self):
        reg = get_plugin_registry()
        wf = reg.get_workflow("document", "daily_checkin")
        assert wf is not None
        assert len(wf["steps"]) == 4

    def test_get_specifications(self):
        reg = get_plugin_registry()
        specs = reg.get_specifications("document")
        assert len(specs) >= 4

    def test_list_actions(self):
        reg = get_plugin_registry()
        actions = reg.list_actions("document")
        assert len(actions) >= 12

    def test_list_workflows(self):
        reg = get_plugin_registry()
        workflows = reg.list_workflows("document")
        assert "daily_checkin" in workflows
        assert "weekly_review" in workflows
