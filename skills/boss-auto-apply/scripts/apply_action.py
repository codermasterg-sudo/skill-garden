#!/usr/bin/env python3
"""点击「立即沟通」：跳转岗位详情页，真实点击投递。

原子动作：对一个岗位点击「立即沟通」→ 返回结果（含 BOSS 页面的
限额/风控信息，由 agent 据此决策）。
保留的强制约束（安全底线，不依赖 agent 自觉）：
- 风控即停：检测到风控信号则停止并返回原因
- 投递间隔：距上次投递不足最小间隔时等待补齐（防连续高频触发风控）
- 限额感知：检测到 BOSS 的 120 提醒弹窗 / 150 不允许投递时返回信息，
  不自动点击、不本地计数，由 agent 判断
其余（去重、记录、批次休息）由 agent 决策，不在本脚本职责内。
"""
import argparse
import random
import sys
import time
from pathlib import Path

import config  # 限流/拟人化配置（可选，缺失时用内置默认）

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


def last_apply_time() -> float:
    """最近一次投递的时间戳（秒），无记录返回 0.0（读状态库 applied 表）。"""
    import state
    return state.last_applied_time()


def enforce_min_interval(min_gap: float = MIN_APPLY_INTERVAL) -> None:
    """强制投递最小间隔：距上次投递不足 min_gap 秒则等待补齐（脚本强制，防连续高频投递）。

    依赖状态库 applied 表的时间戳——agent 每次投递后往表里写记录
    （SKILL.md「投递记录」），间隔即以此为准。
    """
    import time as _t
    last = last_apply_time()
    if not last:
        return
    elapsed = _t.time() - last
    if elapsed < min_gap:
        wait = min_gap - elapsed + 2 * random.random()  # 补齐 + 随机余量
        print(f"距上次投递仅 {elapsed:.0f}s，等待 {wait:.0f}s 保持节奏...", file=sys.stderr)
        _t.sleep(wait)


def handle_risk_signal(page) -> bool:
    """检测风控信号，命中返回 True。关键词可从配置 risk.keywords 覆盖。

    优先 URL 特征（风控跳转登录/验证页），正文用 innerText（省内存快），
    正文匹配只对中文长短语（≥4 中文字）做，短关键词（如 "code 37"）
    只在 URL 匹配，避免正常页面内容误命中。
    """
    try:
        url = page.url
        if any(mark in url for mark in ("/web/user/", "captcha", "verify", "warn", "risk", "abnormal")):
            return True
    except Exception:
        pass
    try:
        text = page.evaluate("document.body ? document.body.innerText : ''")
    except Exception:
        return False
    keywords = config.get_path(_load_cfg(), "risk.keywords") or RISK_KEYWORDS
    if not isinstance(keywords, list) or not keywords:
        keywords = RISK_KEYWORDS

    def _is_body_kw(kw: str) -> bool:
        return sum(1 for ch in kw if "一" <= ch <= "鿿") >= 4
    return any(kw in text for kw in keywords if _is_body_kw(kw))


def handle_quota_prompt(page) -> dict:
    """检测并处理 BOSS 投递限额提示（120 提醒 / 150 不允许投递）。

    返回 dict：
    - {"quota": None}              未出现限额提示，正常
    - {"quota": "limit_remind"}    出现 120 提醒弹窗，**已自动点击「好/继续沟通」关掉**，投递继续
    - {"quota": "limit_blocked"}   出现 150 不允许投递（已达硬顶），**不点击、停下等用户**

    检测方式：弹窗容器 + 文本关键词。120 只是提醒（还可继续投），自动点掉
    不打断任务；150 是硬顶（继续投会一直报错），必须停下等用户处理。
    """
    # 弹窗容器里找限额文案（避免页面正文误命中）
    for dialog_sel in [".confirm-dialog", ".ant-modal", ".dialog", ".modal", ".toast", ".message"]:
        try:
            dialog = page.query_selector(dialog_sel)
            if not dialog:
                continue
            text = (dialog.inner_text() or "")
            # 150 硬顶 / 不允许投递：不点击，停下等用户
            if any(k in text for k in ("不允许", "无法继续", "次数已达", "不能投递", "已达上限", "次数已用完")):
                return {"quota": "limit_blocked", "text": text.strip()[:200]}
            # 120 提醒（还可继续）：自动点击「好/继续沟通」关掉，投递继续
            if any(k in text for k in ("提示", "提醒", "达到")) and any(k in text for k in ("沟通", "投递", "次数")):
                # 弹窗内找确认按钮并点击
                clicked = False
                for btn in dialog.query_selector_all("button"):
                    btn_text = (btn.inner_text() or "").strip()
                    if btn_text in ("好", "继续沟通", "我知道了", "确定"):
                        try:
                            btn.click()
                            time.sleep(1)
                            clicked = True
                        except Exception:
                            pass
                        break
                if not clicked:
                    # 兜底：.confirm-btn 类
                    try:
                        confirm = dialog.query_selector(".confirm-btn")
                        if confirm:
                            confirm.click()
                            time.sleep(1)
                    except Exception:
                        pass
                return {"quota": "limit_remind", "text": text.strip()[:200]}
        except Exception:
            continue
    return {"quota": None}


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


def say_hello(page, job_id: str, delay_range=(MIN_DELAY, MAX_DELAY)) -> dict:
    """点击「立即沟通」。返回 {'ok': bool, 'reason': str, 'quota': ...}。

    quota 字段为 BOSS 页面的限额信息（handle_quota_prompt 返回值），
    agent 据此判断是否继续投递；本地不计数上限，但强制投递间隔。
    """
    # 拟人化模块（脚本强制频率控制，不依赖 agent）
    sys.path.insert(0, str(Path(__file__).parent))
    from humanize import api_request_delay, after_click_delay, CrossProcessThrottle

    # 跨进程节流：多次投递也保持间隔（防高频触发风控）
    CrossProcessThrottle("apply", min_interval=8.0).wait()

    result = {"ok": False, "reason": "", "quota": None}

    # 强制投递最小间隔（防连续高频投递，脚本强制）
    min_gap = _cfg_int("apply.min_apply_interval", MIN_APPLY_INTERVAL)
    enforce_min_interval(min_gap=float(min_gap))

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

    # 检测 BOSS 限额提示：120 提醒自动点掉（投递继续），150 硬顶停下等用户
    result["quota"] = handle_quota_prompt(page)
    if result["quota"].get("quota") == "limit_blocked":
        result["reason"] = "BOSS 提示投递次数已达上限，不允许继续投递，需人工处理"
        print(result["reason"], file=sys.stderr)
        return result

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
    args = parser.parse_args()

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
        result = say_hello(page, args.job_id)
        print(result)
        page.close()
        _sys.exit(0 if result["ok"] else 1)
    finally:
            browser_conn.close()  # 只断开 CDP 连接，浏览器实例保持运行


if __name__ == "__main__":
    main()
