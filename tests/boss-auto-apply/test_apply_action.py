# test_apply_action.py
"""测试 apply_action.py 的纯逻辑（投递上限计数、风控检测、弹窗处理、投递流程）。
浏览器真实点击需 CloakBrowser 环境，用 mock 验证流程。"""
import datetime
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "skills", "boss-auto-apply", "scripts"))

from apply_action import count_applied_today, handle_quota_prompt, handle_risk_signal, say_hello


class TestApplyAction(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.applied_path = os.path.join(self.tmpdir, "applied.md")

    def _write_applied(self, today_count, yesterday_count=0):
        today = datetime.date.today().isoformat()
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        lines = ["# 已投递记录\n"]
        for i in range(yesterday_count):
            lines.append(f"{yesterday} 09:{i:02d} job_id=y{i} 状态=成功\n")
        for i in range(today_count):
            lines.append(f"{today} 10:{i:02d} job_id=t{i} 状态=成功\n")
        with open(self.applied_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

    def test_count_applied_today(self):
        self._write_applied(today_count=3, yesterday_count=2)
        self.assertEqual(count_applied_today(self.applied_path), 3)  # 只数今日

    def test_count_applied_missing_file(self):
        self.assertEqual(count_applied_today(os.path.join(self.tmpdir, "none.md")), 0)

    def test_handle_quota_prompt_ok(self):
        page = MagicMock()
        page.query_selector.return_value = MagicMock()  # 弹窗存在
        result = handle_quota_prompt(page)
        self.assertTrue(result)

    def test_handle_quota_prompt_none(self):
        page = MagicMock()
        page.query_selector.return_value = None  # 无弹窗
        result = handle_quota_prompt(page)
        self.assertFalse(result)

    def test_handle_risk_signal(self):
        page = MagicMock()
        page.content.return_value = "您的环境存在异常"
        self.assertTrue(handle_risk_signal(page))
        page.content.return_value = "正常页面内容"
        self.assertFalse(handle_risk_signal(page))

    def test_say_hello_hard_limit_stop(self):
        # 已达 150 投递上限 → 不执行投递
        self._write_applied(today_count=150)
        page = MagicMock()
        result = say_hello(page, "job123", self.applied_path, delay_range=(0, 0.01))
        self.assertFalse(result["ok"])
        self.assertIn("投递上限", result["reason"])
        page.goto.assert_not_called()  # 达上限时不跳转

    def test_say_hello_success(self):
        self._write_applied(today_count=0)
        page = MagicMock()
        # .btn-startchat 存在，聊天输入框存在
        btn = MagicMock()
        chat = MagicMock()
        page.query_selector.side_effect = [btn, chat]  # btn-startchat, chat-input
        page.content.return_value = "正常内容"
        with patch("apply_action.time.sleep"):
            result = say_hello(page, "job123", self.applied_path, delay_range=(0, 0.01))
        self.assertTrue(result["ok"])
        page.goto.assert_called_once_with(
            "https://www.zhipin.com/job_detail/job123.html", timeout=60000)

    def test_say_hello_risk_signal(self):
        self._write_applied(today_count=0)
        page = MagicMock()
        btn = MagicMock()
        chat = MagicMock()
        page.query_selector.side_effect = [btn, chat]
        page.content.return_value = "您的环境存在异常"  # 风控信号
        with patch("apply_action.time.sleep"):
            result = say_hello(page, "job123", self.applied_path, delay_range=(0, 0.01))
        self.assertFalse(result["ok"])
        self.assertIn("风控", result["reason"])

    def test_say_hello_no_button(self):
        self._write_applied(today_count=0)
        page = MagicMock()
        page.query_selector.return_value = None  # 找不到按钮
        with patch("apply_action.time.sleep"):
            result = say_hello(page, "job123", self.applied_path, delay_range=(0, 0.01))
        self.assertFalse(result["ok"])
        self.assertIn("未找到", result["reason"])


if __name__ == "__main__":
    unittest.main()
