#!/usr/bin/env python3
"""浏览器实例管理 CLI：open / close / port 三个功能。

用法:
    python3 scripts/browser.py open    [--url <初始URL>] [--headless]   # 打开浏览器实例（默认有头，--headless 无头）
    python3 scripts/browser.py close                       # 关闭浏览器实例
    python3 scripts/browser.py port                        # 返回当前实例的调试端口

输出约定（供 agent 读取）：
- 实例信息写入临时文件 `data/browser_window.json`：{"pid": ..., "port": ..., "headless": ...}
- 同时把关键信息打印到 stdout（agent 可直接从返回读取）：
  - open  : "浏览器已打开 pid=... port=...（有头/无头）"
  - close : "浏览器已关闭"
  - port  : 仅打印端口号（如 59004），未打开则打印错误并退出码 1

设计（安全优先）：
- 调试端口为**系统随机端口**（避开 9222/9223/9229 等 BOSS 已知检测点）
- **仅监听 127.0.0.1**，不对局域网/外网开放
- 端口仅在实例运行期间存在，关闭即释放，不常驻暴露
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import browser_lib  # noqa: E402

DEFAULT_URL = "https://www.zhipin.com/web/geek/job?query=Python&city=101010100"


def cmd_open(args):
    if browser_lib.cdp_alive():
        info = browser_lib._window_info()
        mode = "有头" if not info.get("headless") else "无头"
        print(f"浏览器已存在 pid={info['pid']} port={info['port']}（{mode}），直接复用。", flush=True)
        return 0
    print(f"打开浏览器（{'无头' if args.headless else '有头'}）...", flush=True)
    try:
        pid = browser_lib.launch_browser(args.url, headless=args.headless)
    except RuntimeError as e:
        print(f"开窗失败: {e}", file=sys.stderr, flush=True)
        return 1
    info = browser_lib._window_info()
    mode = "无头" if args.headless else "有头"
    print(f"浏览器已打开 pid={pid} port={info['port']}（{mode}）", flush=True)
    print("用完后可运行: python3 scripts/browser.py close 关闭", flush=True)
    return 0


def cmd_close(args):
    if not browser_lib.cdp_alive():
        print("浏览器已关闭（或从未打开）。", flush=True)
        return 0
    if browser_lib.close_window():
        print("浏览器已关闭", flush=True)
        return 0
    return 1


def cmd_port(args):
    info = browser_lib._window_info()
    if not info or not browser_lib.cdp_alive():
        print("浏览器未打开。请先运行: python3 scripts/browser.py open", file=sys.stderr, flush=True)
        return 1
    print(info["port"], flush=True)  # 仅端口号，agent 直接读取
    return 0


def main():
    parser = argparse.ArgumentParser(description="浏览器实例管理（open/close/port）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_open = sub.add_parser("open", help="打开长驻浏览器（默认有头，--headless 无头）")
    p_open.add_argument("--url", default=DEFAULT_URL, help="初始 URL（默认 BOSS Python 搜索页）")
    p_open.add_argument("--headless", action="store_true", default=False, help="无头模式（纯后台，无窗口）")
    p_open.set_defaults(func=cmd_open)
    p_close = sub.add_parser("close", help="关闭浏览器实例")
    p_close.set_defaults(func=cmd_close)

    p_port = sub.add_parser("port", help="返回当前实例调试端口")
    p_port.set_defaults(func=cmd_port)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
