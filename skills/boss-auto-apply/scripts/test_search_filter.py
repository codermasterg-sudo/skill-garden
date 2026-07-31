# test_search_filter.py
import json, os, tempfile, unittest
from unittest.mock import patch

from search_filter import rule_filter, build_search_url
from llm_matcher import llm_score

class TestSearchFilter(unittest.TestCase):
    def setUp(self):
        self.jobs = [
            {"id": "1", "title": "Python后端开发", "company": "字节跳动",
             "salary": "25-40K", "boss_active": "2天内活跃", "type": "全职"},
            {"id": "2", "title": "Python后端开发", "company": "某外包公司",
             "salary": "15-20K", "boss_active": "本周活跃", "type": "全职"},
            {"id": "3", "title": "前端开发", "company": "腾讯",
             "salary": "20-30K", "boss_active": "2天内活跃", "type": "全职"},
            {"id": "4", "title": "Python实习生", "company": "美团",
             "salary": "200-300元/天", "boss_active": "2天内活跃", "type": "实习"},
        ]

    def test_rule_filter_blacklist_company(self):
        result = rule_filter(self.jobs, {
            "blacklist_companies": ["某外包公司"],
            "keyword": "Python",
            "job_type": "全职",
        })
        ids = [j["id"] for j in result]
        self.assertNotIn("2", ids)  # 黑名单公司被排除
        self.assertIn("1", ids)
        self.assertNotIn("3", ids)  # 关键词不匹配排除

    def test_rule_filter_job_type(self):
        result = rule_filter(self.jobs, {
            "blacklist_companies": [],
            "keyword": "Python",
            "job_type": "实习",
        })
        ids = [j["id"] for j in result]
        self.assertIn("4", ids)
        self.assertNotIn("1", ids)

    def test_build_search_url(self):
        url = build_search_url("Python", "北京")
        self.assertIn("query=Python", url)
        self.assertIn("city=101010100", url)  # 北京城市码

    def test_llm_score(self):
        # 用 patch 模拟 LLM 返回
        with patch("llm_matcher._call_llm", return_value=json.dumps({"score": 85, "reason": "技能匹配"})):
            result = llm_score("简历文本", "JD文本")
            self.assertEqual(result["score"], 85)

if __name__ == "__main__":
    unittest.main()
