# test_profile_manager.py
import os, tempfile, unittest

from profile_manager import load_profile, update_profile, PROFILE_TEMPLATE

class TestProfileManager(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.profile_path = os.path.join(self.tmpdir, "profile.md")

    def test_load_missing_creates_template(self):
        profile = load_profile(self.profile_path)
        self.assertIn("期望岗位", profile)
        self.assertIn("黑名单", profile)

    def test_update_profile_merges(self):
        load_profile(self.profile_path)
        update_profile(self.profile_path, {
            "期望岗位": ["Python后端开发", "Go开发"],
            "期望城市": "北京",
            "黑名单": ["某外包公司"],
        })
        with open(self.profile_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Python后端开发", content)
        self.assertIn("Go开发", content)
        self.assertIn("某外包公司", content)
        self.assertIn("北京", content)
        # 其他子键不受影响
        self.assertIn("- 期望薪资:", content)

    def test_update_profile_replaces_not_duplicates(self):
        # 重复更新同一子键 → 替换而非追加重复
        load_profile(self.profile_path)
        update_profile(self.profile_path, {"期望城市": "北京"})
        update_profile(self.profile_path, {"期望城市": "上海"})
        with open(self.profile_path, encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content.count("- 期望城市:"), 1)
        self.assertNotIn("北京", content)
        self.assertIn("上海", content)

if __name__ == "__main__":
    unittest.main()
