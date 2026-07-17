#!/usr/bin/env python3
"""Platform-independent tests for the Codex compatibility driver."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


DRIVER_PATH = Path(__file__).with_name("driver.py")
SPEC = importlib.util.spec_from_file_location("codex_driver", DRIVER_PATH)
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)


class DriverTest(unittest.TestCase):
    def test_normalizes_nested_shell_command(self):
        trace = driver.normalize([{
            "type": "item.completed",
            "item": {
                "type": "command_execution",
                "command": "/bin/bash -lc 'CROSS_TEAM_CONFIG=x cross-team/bin/parallax detect p'",
                "exit_code": 0,
            },
        }])
        self.assertEqual(trace[0]["argv"][-3:], ["cross-team/bin/parallax", "detect", "p"])

    def test_ac8_requires_agent_inbox_inspection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            consumer = root / "consumer"
            consumer.mkdir()
            runtime = consumer / ".parallax-runtime"
            runtime.mkdir()
            (runtime / "_inbox.json").write_text("{}\n")
            self.assertFalse(driver.snapshot_state(consumer, {}, "AC8", [])["scenarios"]["AC8"]["inbox_observed"])
            trace = [{"argv": ["cat", ".parallax-runtime/_inbox.json"], "command": ""}]
            self.assertTrue(driver.snapshot_state(consumer, {}, "AC8", trace)["scenarios"]["AC8"]["inbox_observed"])

    def test_tree_hash_detects_new_submodule_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".keep").write_text("fixture\n")
            before = driver.tree_hash(root)
            (root / "changed.py").write_text("changed\n")
            self.assertNotEqual(before, driver.tree_hash(root))

    def test_opt_in_is_required_before_live_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "profile.json"
            profile.write_text(json.dumps({"id": "codex-cli"}))
            with self.assertRaises(SystemExit) as raised:
                driver.main(["--profile", str(profile), "--out", str(Path(tmp) / "out"), "--codex-bin", "true"])
            self.assertIn("CODEX_AGENT_COMPAT_SMOKE", str(raised.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
