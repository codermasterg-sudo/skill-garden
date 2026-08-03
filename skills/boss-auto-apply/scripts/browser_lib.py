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
import json
import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Optional

DEBUG_HOST = "127.0.0.1"  # 仅本机监听

# 浏览器二进制（CloakBrowser 自带 Chromium）
BIN = "/Users/guojin/.cloakbrowser/chromium-145.0.7632.109.2/Chromium.app/Contents/MacOS/Chromium"

PROFILE_DIR = Path(__file__).parent.parent / "data" / "browser_profile"
WINDOW_INFO_FILE = Path(__file__).parent.parent / "data" / "browser_window.json"

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

# BOSS 已知检测的固定端口（避开）
RISK_PORTS = {9222, 9223, 9229}


def _free_port() -> int:
    """向系统申请一个空闲随机端口（绑定 127.0.0.1）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((DEBUG_HOST, 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _window_info() -> Optional[dict]:
    """读取窗口信息（pid + 端口 + 有头/无头）。文件缺失或无效返回 None。"""
    try:
        data = json.loads(WINDOW_INFO_FILE.read_text(encoding="utf-8"))
        if data.get("pid") and data.get("port"):
            return data
    except Exception:
        pass
    return None


def _save_window_info(pid: int, port: int, headless: bool = False) -> None:
    WINDOW_INFO_FILE.write_text(
        json.dumps({"pid": pid, "port": port, "headless": headless}, ensure_ascii=False),
        encoding="utf-8",
    )


def cdp_alive() -> bool:
    """探测当前窗口的调试端口是否可访问（窗口是否开着）。"""
    info = _window_info()
    if not info:
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
    info = _window_info()
    if not info:
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


def _chromium_args(url: str = None, headless: bool = False, port: int = None) -> list:
    """构建 Chromium 启动参数。"""
    args = [BIN, f"--user-data-dir={str(PROFILE_DIR)}", "--no-first-run"]
    if headless:
        args.append("--headless")
        # 无头模式需要伪显示（新 headless 支持 --headless=new 但需额外处理，这里用标准 headless）
        args.append("--disable-gpu")
    if port:
        args.append(f"--remote-debugging-port={port}")
    args += STEALTH_ARGS
    args.append(url or "about:blank")
    return args


def launch_browser(url: str = None, wait_ready: bool = True, headless: bool = False) -> int:
    """打开一个浏览器实例（独立 Chromium 进程，带随机 CDP 端口），返回进程 pid。

    - headless=False（默认）：有头窗口，用户可见可操作
    - headless=True：无头，纯后台无窗口（不抢屏幕），但带 CDP 端口可被脚本连接
    若已有浏览器在跑（cdp_alive）则直接复用、不再新开，避免 profile 锁冲突。
    """
    if cdp_alive():
        return 0  # 已有实例，直接复用

    port = _free_port()
    while port in RISK_PORTS:
        port = _free_port()  # 避开 BOSS 已知检测端口

    args = _chromium_args(url, headless=headless, port=port)
    proc = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if wait_ready:
        # 最多等 15 秒直到端口可访问
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://{DEBUG_HOST}:{port}/json/version", timeout=1
                ) as r:
                    if r.status == 200:
                        _save_window_info(proc.pid, port, headless=headless)
                        return proc.pid
            except Exception:
                pass
            if proc.poll() is not None:
                raise RuntimeError(
                    f"Chromium 启动失败（exit={proc.returncode}）。"
                    "可能是 profile 被其他实例占用，请先关闭其他窗口。"
                )
            time.sleep(0.5)
        raise RuntimeError("Chromium 启动超时，调试端口未就绪")
    _save_window_info(proc.pid, port, headless=headless)
    return proc.pid


def close_window() -> bool:
    """关闭由 browser.py open 打开的窗口。返回是否成功。

    通过窗口信息文件找到进程并终止，随后清理信息文件（端口随之释放）。
    """
    info = _window_info()
    if not info:
        print("未找到窗口信息（窗口可能从未打开）", flush=True)
        return False
    pid = info["pid"]
    try:
        os.kill(pid, 15)  # SIGTERM
        print(f"已向窗口进程 {pid} 发送关闭信号", flush=True)
        # 等待进程退出（最多 5 秒）
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
                time.sleep(0.3)
            except ProcessLookupError:
                break
        # 清理窗口信息文件（端口随之不可访问）
        try:
            WINDOW_INFO_FILE.unlink()
        except FileNotFoundError:
            pass
        return True
    except ProcessLookupError:
        print(f"窗口进程 {pid} 已不存在（可能已自行退出）", flush=True)
        try:
            WINDOW_INFO_FILE.unlink()
        except FileNotFoundError:
            pass
        return False
    except PermissionError:
        print(f"无权限关闭进程 {pid}", flush=True)
        return False
