# test_apply_action.py
"""测试 apply_action.py 的纯逻辑（限额检测、风控检测、投递间隔、投递流程）。
浏览器真实点击需 CloakBrowser 环境，用 mock 验证流程。"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "skills", "boss-auto-apply", "scripts"))

# 测试用独立数据目录（避免污染真实 ~/.boss-auto-apply）
_TEST_DATA = os.path.join(os.path.dirname(__file__), "_test_data")
os.environ["BOSS_SKILL_DATA_DIR"] = _TEST_DATA

import state
from apply_action import handle_quota_prompt, handle_risk_signal, say_hello


class BaseTestCase(unittest.TestCase):
    def setUp(self):
        # 清空测试库，避免用例间数据残留
        import sqlite3
        try:
            conn = sqlite3.connect(state.db_path())
            conn.execute("DELETE FROM applied")
            conn.commit()
            conn.close()
        except Exception:
            pass


def _dialog_el(text, buttons=()):
    """模拟弹窗容器元素（inner_text 返回 text；query_selector_all 返回按钮列表）。

    buttons: 按钮文本列表，如 ("好",) —— 120 弹窗自动点击验证用。
    """
    el = MagicMock()
    el.inner_text.return_value = text
    btn_els = []
    for b_text in buttons:
        b = MagicMock()
        b.inner_text.return_value = b_text
        btn_els.append(b)
    el.query_selector_all.return_value = btn_els
    return el


def _page_with_dialogs(*dialogs):
    """构造 page：query_selector 返回列表中的弹窗（None 表示无该容器）。"""
    page = MagicMock()
    page.query_selector.side_effect = list(dialogs) + [None] * 10
    return page


class TestQuotaPrompt(BaseTestCase):
    def test_no_dialog(self):
        page = _page_with_dialogs(None)
        result = handle_quota_prompt(page)
        self.assertEqual(result, {"quota": None})

    def test_limit_blocked(self):
        # 150 硬顶：弹窗出现"次数已达上限"
        page = _page_with_dialogs(_dialog_el("今日沟通次数已达上限，无法继续投递"))
        result = handle_quota_prompt(page)
        self.assertEqual(result["quota"], "limit_blocked")

    def test_limit_remind(self):
        # 120 提醒：弹窗出现提示文案，自动点击「好」关掉
        btn = MagicMock()
        btn.inner_text.return_value = "好"
        remind = _dialog_el("温馨提示：今日沟通次数已较多", buttons=("好",))
        page = _page_with_dialogs(remind)
        result = handle_quota_prompt(page)
        self.assertEqual(result["quota"], "limit_remind")
        # 弹窗里的「好」按钮被点击（弹窗被关掉）
        self.assertTrue(remind.query_selector_all.return_value[0].click.called)

    def test_irrelevant_dialog(self):
        # 无关弹窗（如活动弹窗）不误判为限额
        page = _page_with_dialogs(_dialog_el("欢迎使用 BOSS 直聘"))
        result = handle_quota_prompt(page)
        self.assertEqual(result["quota"], None)


class TestRiskSignal(BaseTestCase):
    def test_risk_hit(self):
        page = MagicMock()
        page.url = "https://www.zhipin.com/job_detail/x.html"
        page.evaluate.return_value = "您的环境存在异常"
        self.assertTrue(handle_risk_signal(page))

    def test_risk_miss(self):
        page = MagicMock()
        page.url = "https://www.zhipin.com/job_detail/x.html"
        page.evaluate.return_value = "正常页面内容"
        self.assertFalse(handle_risk_signal(page))


def _page_for_apply(btn=True, dialogs=(), chat=True, risk_text="正常内容"):
    """构造 apply 流程 page：按 selector 返回对应元素。

    - btn: 是否返回「立即沟通」按钮
    - dialogs: 弹窗列表（handle_quota_prompt 遍历容器选择器时依次返回）
    - chat: 是否返回聊天输入框
    - risk_text: 风控检测 innerText
    """
    page = MagicMock()
    dialog_iter = iter(list(dialogs) + [None] * 10)

    def qs(sel):
        if sel == ".btn-startchat":
            return MagicMock() if btn else None
        if sel in (".confirm-dialog", ".ant-modal", ".dialog", ".modal", ".toast", ".message"):
            return next(dialog_iter)
        if sel == "input[type=text], .chat-input, textarea, .send-msg, [contenteditable]":
            return MagicMock() if chat else None
        return None

    page.query_selector.side_effect = qs
    page.url = "https://www.zhipin.com/job_detail/x.html"
    page.evaluate.return_value = risk_text
    return page


class TestSayHello(BaseTestCase):
    def test_say_hello_success(self):
        page = _page_for_apply(btn=True, dialogs=(None,), chat=True)
        with patch("apply_action.time.sleep"):
            result = say_hello(page, "job123", delay_range=(0, 0.01))
        self.assertTrue(result["ok"])
        self.assertEqual(result["quota"], {"quota": None})
        page.goto.assert_called_once_with(
            "https://www.zhipin.com/job_detail/job123.html", timeout=60000)

    def test_say_hello_enforce_interval(self):
        # 距上次投递 < 8 秒 → 脚本等待补齐（不拒绝，只是等待）
        import datetime
        now = datetime.datetime.now()
        state.add_applied("prev", ts=now.strftime("%Y-%m-%d %H:%M:%S"))
        page = _page_for_apply(btn=True, dialogs=(None,), chat=True)
        with patch("apply_action.time.sleep") as sleep_mock:
            result = say_hello(page, "job123", delay_range=(0, 0.01))
        self.assertTrue(result["ok"])
        # enforce_min_interval 里 sleep 被调用过（等待补齐），投递照常进行
        self.assertTrue(sleep_mock.called)

    def test_say_hello_limit_blocked(self):
        # BOSS 返回"不允许投递" → ok=False，quota 标记
        blocked = _dialog_el("今日沟通次数已达上限，无法继续投递")
        page = _page_for_apply(btn=True, dialogs=(blocked,), chat=True)
        with patch("apply_action.time.sleep"):
            result = say_hello(page, "job123", delay_range=(0, 0.01))
        self.assertFalse(result["ok"])
        self.assertEqual(result["quota"]["quota"], "limit_blocked")
        self.assertIn("上限", result["reason"])

    def test_say_hello_limit_remind_ok(self):
        # 120 提醒弹窗（还可继续）→ 自动点掉后投递仍成功，quota 带 remind 信息
        remind = _dialog_el("温馨提示：今日沟通次数已较多", buttons=("好",))
        page = _page_for_apply(btn=True, dialogs=(remind,), chat=True)
        with patch("apply_action.time.sleep"):
            result = say_hello(page, "job123", delay_range=(0, 0.01))
        self.assertTrue(result["ok"])
        self.assertEqual(result["quota"]["quota"], "limit_remind")
        # 弹窗按钮被点击（自动关掉，不打断任务）
        self.assertTrue(remind.query_selector_all.called)

    def test_say_hello_risk_signal(self):
        page = _page_for_apply(btn=True, dialogs=(None,), chat=True, risk_text="您的环境存在异常")
        with patch("apply_action.time.sleep"):
            result = say_hello(page, "job123", delay_range=(0, 0.01))
        self.assertFalse(result["ok"])
        self.assertIn("风控", result["reason"])

    def test_say_hello_no_button(self):
        page = _page_for_apply(btn=False)
        with patch("apply_action.time.sleep"):
            result = say_hello(page, "job123", delay_range=(0, 0.01))
        self.assertFalse(result["ok"])
        self.assertIn("未找到", result["reason"])


if __name__ == "__main__":
    unittest.main()
