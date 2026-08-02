# test_search_jobs.py
"""测试 search_jobs.py 的纯逻辑（URL 构建）。浏览器抓取需真实环境，不在此测。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "skills", "boss-auto-apply", "scripts"))

from search_jobs import build_search_url


class TestSearchJobs(unittest.TestCase):
    def test_build_search_url(self):
        url = build_search_url("Python", "北京")
        self.assertIn("query=Python", url)
        self.assertIn("city=101010100", url)  # 北京城市码

    def test_build_search_url_default_city(self):
        url = build_search_url("Python", "未知城市")
        self.assertIn("city=100010000", url)  # 全国码兜底


if __name__ == "__main__":
    unittest.main()
