#!/usr/bin/env python3
"""点击「立即沟通」自动投递 + 限额处理 + 风控信号检测。"""
import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

from state_manager import load_state, update_state

HARD_LIMIT = 150       # 每日硬顶
PROMPT_LIMIT = 120     # 弹窗提示线
MIN_DELAY = 3          # 每岗位最小延迟（秒）
MAX_DELAY = 10         # 最大延迟
BATCH_SIZE = 20        # 每批岗位数
BATCH_REST_MIN = 60    # 批间休息（秒）
BATCH_REST_MAX = 180

RISK_KEYWORDS = ["环境存在异常", "安全验证", "操作过于频繁", "code 37", "您的请求过于频繁"]


def handle_risk_signal(page) -> bool:
    """检测风控信号，命中返回 True。"""
    try:
        content = page.content()
    except Exception:
        return False
    return any(kw in content for kw in RISK_KEYWORDS)


def handle_quota_prompt(page) -> bool:
    """检测 120 限额弹窗并点击「好/继续沟通」。返回是否处理了弹窗。"""
    for selector in ['text="好"', ".confirm-btn", 'text="继续沟通"']:
        try:
            btn = page.query_selector(selector)
            if btn:
                btn.click()
                time.sleep(1)
                return True
        except Exception:
            continue
    return False


def say_hello(page, job_id: str, state_path: Path, delay_range=(MIN_DELAY, MAX_DELAY)) -> bool:
    """点击「立即沟通」。返回是否执行了投递。"""
    state = load_state(state_path)
    if state["applied_today"] >= HARD_LIMIT:
        print(f"已达每日硬顶 {HARD_LIMIT}，停止投递。", file=sys.stderr)
        return False
    if state.get("risk_paused"):
        print("风控暂停中，不执行投递。", file=sys.stderr)
        return False

    # 拟人化延迟
    time.sleep(random.uniform(*delay_range))

    # 跳转到岗位详情页
    page.goto(f"https://www.zhipin.com/job_detail/{job_id}.html", timeout=60000)
    page.wait_for_load_state("networkidle")

    # 真实点击「立即沟通」
    btn = page.query_selector(".btn-startchat")
    if not btn:
        print(f"未找到「立即沟通」按钮（job {job_id}），可能页面结构变化。", file=sys.stderr)
        return False
    btn.click()
    time.sleep(random.uniform(1, 3))

    # 处理 120 弹窗（出现则确认）
    handle_quota_prompt(page)

    # 投递验证：点击后应出现聊天/沟通界面（如「立即沟通」按钮消失或出现输入框）
    try:
        chat_input = page.query_selector(".chat-input, textarea, .send-msg")
        if not chat_input:
            print(f"点击后未检测到聊天界面（job {job_id}），可能投递未成功。", file=sys.stderr)
            return False
    except Exception:
        pass

    # 风控检测：命中即停并持久化
    if handle_risk_signal(page):
        print("检测到风控信号！停止投递，请人工处理。", file=sys.stderr)
        update_state(state_path, risk_paused=True)
        return False

    # 记录投递
    state = load_state(state_path)
    applied = state["applied_today"] + 1
    batch = state["batch"]
    if applied % BATCH_SIZE == 0:
        batch += 1
        rest = random.uniform(BATCH_REST_MIN, BATCH_REST_MAX)
        print(f"完成一批 {BATCH_SIZE} 个，休息 {int(rest)} 秒。", file=sys.stderr)
        time.sleep(rest)
    update_state(state_path, applied_today=applied, batch=batch)

    if applied == PROMPT_LIMIT:
        print(f"已达 {PROMPT_LIMIT} 次提示线，后续每次都会弹窗确认。", file=sys.stderr)
    return True


def main():
    parser = argparse.ArgumentParser(description="BOSS 点击立即沟通")
    parser.add_argument("--action", choices=["say_hello"], default="say_hello")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--profile", type=Path, default=None)
    parser.add_argument("--state", type=Path, default=None)
    args = parser.parse_args()

    profile_dir = args.profile or Path(__file__).parent.parent / "data" / "browser_profile"
    state_path = args.state or Path(__file__).parent.parent / "data" / "state.md"

    from cloakbrowser import launch
    with launch(user_data_dir=str(profile_dir), headless=False, humanize=True) as browser:
        page = browser.new_page()
        ok = say_hello(page, args.job_id, state_path)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
