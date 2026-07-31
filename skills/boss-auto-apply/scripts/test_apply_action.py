# test_apply_action.py
import json, os, tempfile, unittest
from unittest.mock import MagicMock, patch

from apply_action import handle_quota_prompt, handle_risk_signal, say_hello
from state_manager import load_state, update_state

class TestApplyAction(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmpdir, "state.md")

    def test_state_init_and_update(self):
        state = load_state(self.state_path)
        self.assertEqual(state["applied_today"], 0)
        update_state(self.state_path, applied_today=5)
        state = load_state(self.state_path)
        self.assertEqual(state["applied_today"], 5)

    def test_handle_quota_prompt_ok(self):
        # 120 弹窗出现 → 点「好」
        page = MagicMock()
        page.query_selector.return_value = MagicMock()  # 弹窗存在
        result = handle_quota_prompt(page)
        self.assertTrue(result)
        page.query_selector.assert_called_once()

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

    def test_say_hello_quota_hard_stop(self):
        # 已达 150 硬顶 → 不执行
        page = MagicMock()
        with patch("apply_action.load_state", return_value={"applied_today": 150}):
            result = say_hello(page, "job123", state_path=self.state_path)
        self.assertFalse(result)

if __name__ == "__main__":
    unittest.main()
