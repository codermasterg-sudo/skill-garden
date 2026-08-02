#!/usr/bin/env python3
"""点击「立即沟通」：跳转岗位详情页，真实点击投递。

原子动作：对一个岗位点击「立即沟通」→ 返回结果。
保留的强制约束（安全底线，不依赖 agent 自觉）：
- 每日投递上限：投递前检查 data/applied.md 今日行数，达到则拒绝
- 风控即停：检测到风控信号则停止并返回原因
其余（节奏、去重、记录、批次休息）由 agent 决策，不在本脚本职责内。
"""
import argparse
import datetime
import random
import sys
import time
from pathlib import Path

import config  # 限流/拟人化配置（可选，缺失时用内置默认）

HARD_LIMIT = 150       # 每日投递上限（BOSS 平台限制）
PROMPT_LIMIT = 120     # 弹窗提示线（超过后每次投递会弹确认框）
MIN_DELAY = 3          # 每岗位最小延迟（秒）
MAX_DELAY = 10         # 最大延迟
MIN_APPLY_INTERVAL = 8 # 两次投递最小间隔（秒，脚本强制）

RISK_KEYWORDS = ["环境存在异常", "安全验证", "操作过于频繁", "code 37", "您的请求过于频繁"]

LOGIN_TIMEOUT = 300       # 等待扫码登录的最长时间（秒）
LOGIN_POLL_INTERVAL = 5   # 登录状态轮询间隔（秒）

# 配置加载（失败静默回退到上述默认值）
_cfg = None


def _load_cfg():
    """懒加载配置，失败回退默认值（安全底线：默认值即底线）。"""
    global _cfg
    if _cfg is None:
        import config
        _cfg = config.load()
    return _cfg


def _cfg_int(key: str, default: int) -> int:
    try:
        val = config.get_path(_load_cfg(), key)
        return int(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def wait_for_login(page) -> bool:
    """检测登录页并等待用户扫码登录。已登录返回 True，超时返回 False。"""
    try:
        page.wait_for_load_state("domcontentloaded")
    except Exception:
        pass
    # 用 URL + 登录页专属元素判断（不用 content() 全文本扫描，避免详情页
    # 出现「扫码登录」字样时误判为登录页）
    if "/web/user/" not in page.url and not page.query_selector(".qrcode"):
        return True  # 已登录（或无需登录）
    print("检测到登录页，请在浏览器中扫码登录（最长等待 5 分钟）...", file=sys.stderr)
    timeout = _cfg_int("login.timeout_seconds", LOGIN_TIMEOUT)
    poll = _cfg_int("login.poll_interval", LOGIN_POLL_INTERVAL)
    deadline = time.time() + timeout
    while time.time() < deadline:
        page.wait_for_timeout(poll * 1000)
        try:
            page.wait_for_load_state("domcontentloaded")
        except Exception:
            pass
        if "/web/user/" not in page.url:
            return True  # 登录成功，页面已离开登录页
    print("等待扫码登录超时", file=sys.stderr)
    return False


def count_applied_today(applied_path: Path) -> int:
    """统计 data/applied.md 中今日的记录条数（投递上限判断用）。"""
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


def last_apply_time(applied_path: Path) -> float:
    """取最近一次投递的时间戳（从 applied.md 最后一行解析），无记录返回 0。

    兼容 HH:MM 和 HH:MM:SS 两种时间格式（HH:MM 视为该分钟起始）。
    """
    applied_path = Path(applied_path)
    if not applied_path.exists():
        return 0.0
    lines = [l.strip() for l in applied_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        return 0.0
    # 最后一行格式: YYYY-MM-DD HH:MM[:SS] job_id=... 状态=...
    last = lines[-1]
    try:
        parts = last.split()
        if len(parts) >= 2:
            time_part = parts[1]
            if len(time_part) == 8:  # HH:MM:SS
                ts = datetime.datetime.strptime(f"{parts[0]} {time_part}", "%Y-%m-%d %H:%M:%S")
            else:  # HH:MM
                ts = datetime.datetime.strptime(f"{parts[0]} {time_part}", "%Y-%m-%d %H:%M")
            return ts.timestamp()
    except Exception:
        pass
    return 0.0


def enforce_min_interval(applied_path: Path, min_gap: float = 8.0) -> None:
    """强制投递最小间隔：距上次投递不足 min_gap 秒则等待补齐（脚本强制，防连续高频投递）。"""
    import time as _t
    last = last_apply_time(applied_path)
    if not last:
        return
    elapsed = _t.time() - last
    if elapsed < min_gap:
        wait = min_gap - elapsed + 2 * random.random()  # 补齐 + 随机余量
        print(f"距上次投递仅 {elapsed:.0f}s，等待 {wait:.0f}s 保持节奏...", file=sys.stderr)
        _t.sleep(wait)


def handle_risk_signal(page) -> bool:
    """检测风控信号，命中返回 True。关键词可从配置 risk.keywords 覆盖。"""
    try:
        content = page.content()
    except Exception:
        return False
    keywords = config.get_path(_load_cfg(), "risk.keywords") or RISK_KEYWORDS
    if not isinstance(keywords, list) or not keywords:
        keywords = RISK_KEYWORDS
    return any(kw in content for kw in keywords)


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


def handle_handicapped_dialog(page) -> bool:
    """处理「残障人士求职」信息弹窗（BOSS 新版必填弹窗），点「确定」关闭。

    仅当弹窗实际出现时才处理；不出现则立即返回（不浪费时间等待）。
    """
    try:
        # 快速判断弹窗是否出现（最多等 2 秒）
        try:
            page.wait_for_selector(".handicapped-dialog", timeout=2000)
        except Exception:
            return False  # 未出现，无需处理
        # 等确定按钮可见后点击（最多等 5 秒）
        try:
            btn = page.wait_for_selector(".handicapped-dialog .btn-sure", state="visible", timeout=5000)
        except Exception:
            print("残障弹窗确定按钮不可见", file=sys.stderr)
            return False
        btn.click()
        time.sleep(1.5)
        print("已关闭残障人士信息弹窗", file=sys.stderr)
        return True
    except Exception as e:
        print(f"处理残障弹窗异常: {e}", file=sys.stderr)
        return False


def say_hello(page, job_id: str, applied_path: Path, delay_range=(MIN_DELAY, MAX_DELAY)) -> dict:
    """点击「立即沟通」。返回 {'ok': bool, 'reason': str}。"""
    # 拟人化模块（脚本强制频率控制，不依赖 agent）
    sys.path.insert(0, str(Path(__file__).parent))
    from humanize import api_request_delay, after_click_delay, CrossProcessThrottle

    # 跨进程节流：多次投递也保持间隔（配合 enforce_min_interval 双保险）
    CrossProcessThrottle("apply", min_interval=8.0).wait()

    result = {"ok": False, "reason": ""}

    # 投递上限强制检查（安全底线）
    hard_limit = _cfg_int("apply.hard_limit", HARD_LIMIT)
    applied_today = count_applied_today(applied_path)
    if applied_today >= hard_limit:
        result["reason"] = f"已达今日投递上限 {hard_limit} 次，停止投递"
        print(result["reason"], file=sys.stderr)
        return result

    # 强制投递最小间隔（防连续高频投递，脚本强制）
    min_gap = _cfg_int("apply.min_apply_interval", MIN_APPLY_INTERVAL)
    enforce_min_interval(applied_path, min_gap=float(min_gap))

    # 拟人化延迟（投递前随机 3-10 秒 + 抖动）
    api_request_delay()

    # 跳转到岗位详情页
    page.goto(f"https://www.zhipin.com/job_detail/{job_id}.html", timeout=60000)
    try:
        page.wait_for_load_state("domcontentloaded")
    except Exception:
        pass  # SPA 详情页持续有网络请求，networkidle 会死等；DOM 就绪即可继续

    # 登录态过期时等待扫码（未登录则提示用户）
    if not wait_for_login(page):
        result["reason"] = "等待扫码登录超时，投递中止"
        print(result["reason"], file=sys.stderr)
        return result

    # 真实点击「立即沟通」
    btn = page.query_selector(".btn-startchat")
    if not btn:
        result["reason"] = f"未找到「立即沟通」按钮（job {job_id}），可能页面结构变化"
        print(result["reason"], file=sys.stderr)
        return result
    btn.click()
    after_click_delay()

    # 处理 120 弹窗（出现则确认）
    handle_quota_prompt(page)

    # 处理「残障人士求职」信息弹窗（BOSS 新版必填，出现则点确定）
    handle_handicapped_dialog(page)

    # 投递验证：点击后应出现聊天/沟通界面
    try:
        chat_input = page.query_selector("input[type=text], .chat-input, textarea, .send-msg, [contenteditable]")
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
    parser.add_argument("--applied", type=Path, default=None, help="applied.md 路径（投递上限检查用）")
    args = parser.parse_args()

    profile_dir = args.profile or Path(__file__).parent.parent / "data" / "browser_profile"
    applied_path = args.applied or Path(__file__).parent.parent / "data" / "applied.md"

    # 复用 browser.py open 打开的浏览器（有头或无头均可），不新开/不关
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent))
    import browser_lib as browser

    if not browser.cdp_alive():
        print("没有检测到浏览器。请先运行: python3 scripts/browser.py open",
              file=_sys.stderr)
        _sys.exit(1)
    browser_conn = browser.connect()
    try:
        page = browser_conn.contexts[0].new_page() if browser_conn.contexts else browser_conn.new_page()
        result = say_hello(page, args.job_id, applied_path)
        print(result)
        page.close()
        _sys.exit(0 if result["ok"] else 1)
    finally:
            browser_conn.close()  # 只断开 CDP 连接，浏览器实例保持运行


if __name__ == "__main__":
    main()
