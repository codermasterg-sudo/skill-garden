#!/usr/bin/env python3
"""浏览器窗口管理公共模块。

所有脚本共用的 CDP 连接/开窗/关窗逻辑，集中在这里避免重复。

设计（安全 + 不抢前台）：
- **统一 CDP**：browser.py open 打开一个 Chromium 实例（有头/无头由 --headless 决定），
  带随机 CDP 端口；搜索/投递脚本一律 connect_over_cdp 复用，不各自开浏览器
- **有头**：用户可见窗口（扫码/手动查看）；**无头**：纯后台无窗口（不抢屏幕），
  但同样带 CDP 端口可被脚本连接，登录态共用同一 profile
- 端口仅监听 127.0.0.1、避开常见固定调试端口（9222/9223/9229）、关窗即释放
- 同一时刻只有一个实例（Chromium profile 单例，冲突时明确报错而非静默崩溃）
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import state  # 统一状态模块（SQLite）

DEBUG_HOST = "127.0.0.1"  # 仅本机监听

# 运行时数据统一放用户目录（skill 目录可整体复制/只读/升级，不放运行时数据）
DATA_DIR = Path.home() / ".boss-auto-apply"
PROFILE_DIR = DATA_DIR / "browser_profile"

# BOSS 已知检测的固定端口（避开）
RISK_PORTS = {9222, 9223, 9229}


# 启动 Chromium 的 stealth 参数（与 cloakbrowser 一致，避免被风控识别）
STEALTH_ARGS = [
    "--disable-field-trial-config", "--disable-background-networking",
    "--disable-background-timer-throttling", "--disable-backgrounding-occluded-windows",
    "--disable-breakpad", "--disable-component-update", "--no-default-browser-check",
    "--disable-default-apps", "--disable-dev-shm-usage", "--disable-extensions",
    "--disable-hang-monitor", "--disable-popup-blocking", "--disable-prompt-on-repost",
    "--disable-renderer-backgrounding", "--force-color-profile=srgb",
    "--metrics-recording-only", "--no-first-run", "--password-store=basic",
    "--use-mock-keychain", "--no-service-autorun", "--disable-sync",
    "--no-sandbox", "--ignore-gpu-blocklist",
]


def cdp_alive() -> bool:
    """探测当前窗口的调试端口是否可访问（窗口是否开着）。"""
    info = state.get_browser()
    if not info.get("port"):
        return False
    try:
        with urllib.request.urlopen(
            f"http://{DEBUG_HOST}:{info['port']}/json/version", timeout=2
        ) as r:
            return r.status == 200
    except Exception:
        return False


def connect():
    """连接已有窗口（CDP），返回 playwright Browser。窗口不存在则返回 None。

    只建立连接、不拥有窗口：调用方用完调用 browser.close() 只是断开连接，
    窗口保持打开。
    """
    from playwright.sync_api import sync_playwright
    info = state.get_browser()
    if not info.get("port"):
        raise RuntimeError(
            "没有检测到浏览器窗口。请先运行: python3 scripts/browser.py open"
        )
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(
            f"http://{DEBUG_HOST}:{info['port']}", timeout=10000
        )
    except Exception as e:
        pw.stop()
        raise RuntimeError(
            f"CDP 连接失败（窗口可能已关闭）: {e}\n"
            f"请先运行: python3 scripts/browser.py open"
        ) from e
    # 保存 pw，供 close 时一并释放
    browser._pw = pw
    _orig_close = browser.close

    def _close():
        try:
            _orig_close()
        finally:
            browser._pw.stop()
    browser.close = _close
    return browser


def _free_port() -> int:
    """向系统申请一个空闲随机端口（绑定 127.0.0.1）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((DEBUG_HOST, 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _chromium_args(headless: bool = False, port: int = None) -> list:
    """构建 Chromium 启动参数（传给 cloakbrowser.launch_persistent_context 的 args）。

    注意：
    - 不传 --user-data-dir（playwright 禁止在 args 里传，会抛错），
      profile 目录由 launch_persistent_context 的 user_data_dir 参数指定。
    - 不传 URL（playwright 禁止 args 里出现非 - 开头的参数），
      初始 URL 由 daemon 里 ctx.new_page().goto() 打开。
    """
    args = ["--no-first-run"]
    if headless:
        args.append("--headless")
        # 无头模式需要伪显示（新 headless 支持 --headless=new 但需额外处理，这里用标准 headless）
        args.append("--disable-gpu")
    if port:
        args.append(f"--remote-debugging-port={port}")
    args += STEALTH_ARGS
    return args


def _resolve_pid_by_profile() -> int:
    """按 profile 目录（--user-data-dir）匹配浏览器主进程 pid。

    cloakbrowser.launch_persistent_context 的 Browser 对象没有 .process 属性，
    拿不到直接 pid；改用 ps 匹配 user-data-dir 指向 PROFILE_DIR 的主进程。
    匹配不到返回 0（close 时按端口探测兜底）。
    """
    try:
        r = subprocess.run(
            ["ps", "ax", "-o", "pid=,command="], capture_output=True, text=True, timeout=10
        )
        for line in r.stdout.splitlines():
            if f"--user-data-dir={PROFILE_DIR}" in line and "Chromium Helper" not in line:
                pid = line.split()[0]
                if pid.isdigit():
                    return int(pid)
    except Exception:
        pass
    return 0


# 浏览器常驻 daemon 脚本（browser.py open 用 subprocess 拉起，独立进程持有浏览器，
# browser.py 退出后浏览器仍存活；close 时 kill 该进程组即可连带关闭 Chromium）
_DAEMON_CODE = r"""
import sys, time
sys.path.insert(0, {scripts_dir!r})
import state
from cloakbrowser import launch_persistent_context
ctx = launch_persistent_context(
    user_data_dir={profile_dir!r},
    headless={headless},
    args={args!r},
    stealth_args=True,
    humanize=True,
)
state.save_browser(0, {port!r}, headless={headless})
if {url!r}:
    try:
        page = ctx.new_page()
        page.goto({url!r}, timeout=60000)
    except Exception as e:
        print(f"打开初始 URL 失败（不影响实例启动）: {{e}}", file=sys.stderr)
print("DAEMON_READY", flush=True)
while True:
    time.sleep(60)
"""


def launch_browser(url: str = None, wait_ready: bool = True, headless: bool = False) -> int:
    """打开一个浏览器实例（CloakBrowser Chromium 进程，带随机 CDP 端口），返回进程 pid。

    - headless=False（默认）：有头窗口，用户可见可操作
    - headless=True：无头，纯后台无窗口（不抢屏幕），但带 CDP 端口可被脚本连接
    若已有浏览器在跑（cdp_alive）则直接复用、不再新开，避免 profile 锁冲突。

    浏览器由**独立 daemon 进程**托管（subprocess 拉起 `_DAEMON_CODE`），
    保证 browser.py 退出后实例仍存活（playwright 浏览器生命周期绑定调用进程，
    直接在 browser.py 内 launch 会随进程退出）。daemon 用
    cloakbrowser.launch_persistent_context 启动：自带 stealth 参数
    （--fingerprint 等）、二进制自动发现/下载（首次约 1 分钟）、profile
    持久化（user_data_dir=PROFILE_DIR，登录态 cookie 自动保存）。
    显式传 --remote-debugging-port（随机端口）后，playwright 内部连接与
    搜索/投递脚本的 connect_over_cdp 都走该端口（实测端口可访问），
    端口仅 127.0.0.1。pid 用 ps 匹配 profile 目录获得。
    """
    if cdp_alive():
        return 0  # 已有实例，直接复用

    port = _free_port()
    while port in RISK_PORTS:
        port = _free_port()  # 避开 BOSS 已知检测端口

    args = _chromium_args(headless=headless, port=port)
    daemon_code = _DAEMON_CODE.format(
        scripts_dir=str(Path(__file__).parent),
        profile_dir=str(PROFILE_DIR),
        headless=headless,
        args=args,
        url=url or "",
        port=port,
    )
    # 拉起 daemon：独立进程组（start_new_session），脱离终端，输出到 devnull
    try:
        proc = subprocess.Popen(
            [sys.executable, "-c", daemon_code],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        raise RuntimeError(f"启动浏览器 daemon 失败: {e}") from e

    if wait_ready:
        # 最多等 20 秒直到端口可访问
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://{DEBUG_HOST}:{port}/json/version", timeout=1
                ) as r:
                    if r.status == 200:
                        pid = _resolve_pid_by_profile()
                        state.save_browser(pid, port, headless=headless)
                        return pid
            except Exception:
                pass
            if proc.poll() is not None:
                # daemon 提前退出（如依赖缺失/二进制未下载），报错
                raise RuntimeError(
                    "浏览器 daemon 启动失败（提前退出）。请确认已安装依赖: "
                    "pip install -r scripts/requirements.txt"
                )
            time.sleep(0.5)
        # 启动超时：关闭 daemon 避免残留
        try:
            os.killpg(proc.pid, 15)
        except Exception:
            pass
        raise RuntimeError("Chromium 启动超时，调试端口未就绪")
    pid = _resolve_pid_by_profile()
    state.save_browser(pid, port, headless=headless)
    return pid


def close_window() -> bool:
    """关闭由 browser.py open 打开的窗口。返回是否成功。

    通过状态库找到 daemon 进程组并终止（连带其子进程 Chromium），
    随后清除浏览器记录（端口随之释放）。pid 缺失（=0）时按 profile 匹配兜底。
    """
    info = state.get_browser()
    if not info.get("port"):
        print("未找到窗口信息（窗口可能从未打开）", flush=True)
        return False
    pid = info.get("pid") or _resolve_pid_by_profile()
    if not pid:
        # pid 拿不到（如非本用户启动），报错提示手动关闭
        print("无法确定浏览器进程（pid 未记录且匹配不到），请手动关闭浏览器窗口", flush=True)
        return False
    try:
        os.killpg(pid, 15)  # SIGTERM 整个 daemon 进程组（daemon + Chromium + driver）
        print(f"已向浏览器进程组 {pid} 发送关闭信号", flush=True)
        # 等待进程退出（最多 5 秒）
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
                time.sleep(0.3)
            except ProcessLookupError:
                break
        # 清除浏览器记录（端口随之不可访问）
        state.clear_browser()
        return True
    except ProcessLookupError:
        print(f"浏览器进程组 {pid} 已不存在（可能已自行退出）", flush=True)
        state.clear_browser()
        return False
    except PermissionError:
        print(f"无权限关闭进程组 {pid}", flush=True)
        return False
