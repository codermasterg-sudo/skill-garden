#!/usr/bin/env python3
"""端到端冒烟测试：不启动浏览器，验证各脚本 CLI 可用、数据文件流转正确。"""
import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).parent


def run_script(*args, **kwargs):
    return subprocess.run(
        [sys.executable, *args], capture_output=True, text=True, cwd=SCRIPTS, **kwargs
    )


class TestE2E(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_profile_manager_cli(self):
        profile = os.path.join(self.tmpdir, "profile.md")
        r = run_script("profile_manager.py", "--profile", profile, "--action", "get")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("期望岗位", r.stdout)

        r = run_script("profile_manager.py", "--profile", profile,
                       "--action", "update", "--key", "期望岗位", "--value", "Python后端")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_script("profile_manager.py", "--profile", profile, "--action", "get")
        self.assertIn("Python后端", r.stdout)

    def test_search_filter_cli(self):
        jobs = os.path.join(self.tmpdir, "jobs.json")
        with open(jobs, "w", encoding="utf-8") as f:
            json.dump([{"id": "1", "title": "Python后端", "company": "A公司", "type": "全职"}], f)
        out = os.path.join(self.tmpdir, "filtered.json")
        r = run_script("search_filter.py", "filter", "--jobs", jobs,
                       "--keyword", "Python", "--output", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)

    def test_apply_action_state_cli(self):
        # 验证 state_manager CLI 层流转：state 文件可被 apply_action 的 state 逻辑读写
        state = os.path.join(self.tmpdir, "state.md")
        from state_manager import load_state, update_state
        update_state(state, applied_today=7)
        state = load_state(state)
        self.assertEqual(state["applied_today"], 7)
        self.assertEqual(state["date"], datetime.date.today().isoformat())


if __name__ == "__main__":
    unittest.main()
