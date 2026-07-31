#!/usr/bin/env python3
"""点击「立即沟通」：跳转岗位详情页，真实点击投递。

原子动作：对一个岗位点击「立即沟通」→ 返回结果。
保留的强制约束（安全底线，不依赖 agent 自觉）：
- 每日 150 硬顶：投递前检查 data/applied.md 今日行数，达到则拒绝
- 风控即停：检测到风控信号则停止并返回原因
其余（节奏、去重、记录、批次休息）由 agent 决策，不在本脚本职责内。
"""
import argparse
import datetime
import random
import sys
import time
from pathlib import Path

HARD_LIMIT = 150       # 每日硬顶（BOSS 平台限制）
PROMPT_LIMIT = 120     # 弹窗提示线（超过后每次投递会弹确认框）
MIN_DELAY = 3          # 每岗位最小延迟（秒）
MAX_DELAY = 10         # 最大延迟

RISK_KEYWORDS = ["环境存在异常", "安全验证", "操作过于频繁", "code 37", "您的请求过于频繁"]


def count_applied_today(applied_path: Path) -> int:
    """统计 data/applied.md 中今日的记录条数（硬顶判断用）。"""
    applied_path = Path(applied_path)
    today = datetime.date.today().isoformat()
    if not applied_path.exists():
        return 0
    count = 0
    for line in applied_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(today):
            count += 1
    return count


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


def say_hello(page, job_id: str, applied_path: Path, delay_range=(MIN_DELAY, MAX_DELAY)) -> dict:
    """点击「立即沟通」。返回 {'ok': bool, 'reason': str}。"""
    result = {"ok": False, "reason": ""}

    # 硬顶强制检查（安全底线）
    applied_today = count_applied_today(applied_path)
    if applied_today >= HARD_LIMIT:
        result["reason"] = f"已达每日硬顶 {HARD_LIMIT}，停止投递"
        print(result["reason"], file=sys.stderr)
        return result

    # 拟人化延迟
    time.sleep(random.uniform(*delay_range))

    # 跳转到岗位详情页
    page.goto(f"https://www.zhipin.com/job_detail/{job_id}.html", timeout=60000)
    page.wait_for_load_state("networkidle")

    # 真实点击「立即沟通」
    btn = page.query_selector(".btn-startchat")
    if not btn:
        result["reason"] = f"未找到「立即沟通」按钮（job {job_id}），可能页面结构变化"
        print(result["reason"], file=sys.stderr)
        return result
    btn.click()
    time.sleep(random.uniform(1, 3))

    # 处理 120 弹窗（出现则确认）
    handle_quota_prompt(page)

    # 投递验证：点击后应出现聊天/沟通界面
    try:
        chat_input = page.query_selector(".chat-input, textarea, .send-msg")
        if not chat_input:
            result["reason"] = f"点击后未检测到聊天界面（job {job_id}），可能投递未成功"
            print(result["reason"], file=sys.stderr)
            return result
    except Exception:
        pass

    # 风控即停（安全底线）：命中则停止
    if handle_risk_signal(page):
        result["reason"] = "检测到风控信号，停止投递，请人工处理"
        print(result["reason"], file=sys.stderr)
        return result

    result["ok"] = True
    result["reason"] = "投递成功"
    return result


def main():
    parser = argparse.ArgumentParser(description="BOSS 点击立即沟通")
    parser.add_argument("--job-id", required=True, help="岗位 ID")
    parser.add_argument("--profile", type=Path, default=None, help="浏览器 profile 目录")
    parser.add_argument("--applied", type=Path, default=None, help="applied.md 路径（硬顶检查用）")
    args = parser.parse_args()

    profile_dir = args.profile or Path(__file__).parent.parent / "data" / "browser_profile"
    applied_path = args.applied or Path(__file__).parent.parent / "data" / "applied.md"

    from cloakbrowser import launch
    with launch(user_data_dir=str(profile_dir), headless=False, humanize=True) as browser:
        page = browser.new_page()
        result = say_hello(page, args.job_id, applied_path)
        print(result)
        sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
