#!/usr/bin/env python3
"""统一状态模块：所有运行时状态集中存 SQLite（~/.boss-auto-apply/state.db）。

表：
- browser 表：浏览器实例信息（pid + 随机调试端口 + 有头/无头）
- applied 表：投递记录（agent 通过 SQL 读写，见 SKILL.md）
- actions 表：跨进程节流（humanize.CrossProcessThrottle 写入）

数据库文件：~/.boss-auto-apply/state.db（纯标准库 sqlite3，无第三方依赖）。
运行时数据放用户目录而非 skill 目录，保证 skill 可整体复制/只读/升级。

设计：
- 单文件 sqlite，所有脚本共享；写操作带重试（并发进程时 SQLite 可能锁库）
- 所有读写容错：失败打 stderr 不崩溃，保证脚本可运行
- agent 直接改 SQL 维护投递记录（见 SKILL.md）
"""
import os
import sqlite3
import sys
import time
from pathlib import Path

# 运行时数据根目录（可用环境变量覆盖，测试用独立目录）
DATA_DIR = Path(os.environ.get("BOSS_SKILL_DATA_DIR", Path.home() / ".boss-auto-apply"))
DB_NAME = "state.db"


def db_path() -> Path:
    """数据库路径：~/.boss-auto-apply/state.db。"""
    return DATA_DIR / DB_NAME


def _conn() -> sqlite3.Connection:
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(p), timeout=10)


def _init_db() -> None:
    """建表（若不存在）。所有脚本首次调用时自动执行。"""
    try:
        conn = _conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS browser (
                id INTEGER PRIMARY KEY CHECK (id = 1),  -- 单行：始终 id=1
                pid INTEGER NOT NULL DEFAULT 0,
                port INTEGER NOT NULL DEFAULT 0,
                headless INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS applied (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,             -- YYYY-MM-DD HH:MM:SS（含秒，节奏控制用）
                job_id TEXT NOT NULL,
                status TEXT NOT NULL,          -- 成功/失败/风控暂停/达上限
                note TEXT DEFAULT ''
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[state] 初始化数据库失败: {e}", file=sys.stderr)


def _with_retry(fn, retries: int = 3):
    """执行数据库写操作，SQLite 锁冲突时重试（并发进程场景）。"""
    for i in range(retries):
        try:
            return fn()
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and i < retries - 1:
                time.sleep(0.2 * (i + 1))
                continue
            raise


# ============================================================
# browser 表：浏览器实例信息
# ============================================================

def save_browser(pid: int, port: int, headless: bool = False) -> None:
    """记录当前浏览器实例信息（单行 id=1）。"""
    _init_db()
    try:
        def _w():
            conn = _conn()
            conn.execute(
                "INSERT INTO browser (id, pid, port, headless) VALUES (1, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET pid=excluded.pid, port=excluded.port, "
                "headless=excluded.headless",
                (pid, port, 1 if headless else 0),
            )
            conn.commit()
            conn.close()
        _with_retry(_w)
    except Exception as e:
        print(f"[state] 保存浏览器信息失败: {e}", file=sys.stderr)


def get_browser() -> dict:
    """读取当前浏览器实例信息；无记录返回空 dict。"""
    _init_db()
    try:
        conn = _conn()
        row = conn.execute("SELECT pid, port, headless FROM browser WHERE id = 1").fetchone()
        conn.close()
        if not row:
            return {}
        return {"pid": row[0], "port": row[1], "headless": bool(row[2])}
    except Exception as e:
        print(f"[state] 读取浏览器信息失败: {e}", file=sys.stderr)
        return {}


def clear_browser() -> None:
    """清除浏览器实例记录（close 时调用）。"""
    _init_db()
    try:
        def _w():
            conn = _conn()
            conn.execute("DELETE FROM browser WHERE id = 1")
            conn.commit()
            conn.close()
        _with_retry(_w)
    except Exception as e:
        print(f"[state] 清除浏览器信息失败: {e}", file=sys.stderr)


# ============================================================
# applied 表：投递记录
# ============================================================

def add_applied(job_id: str, status: str = "成功", note: str = "", ts: str = None) -> None:
    """新增一条投递记录。

    ts 默认当前时间（YYYY-MM-DD HH:MM:SS）。job_id/status/note 由 agent 传入，
    对应 SKILL.md「投递记录」一节。
    """
    _init_db()
    if ts is None:
        import datetime
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        def _w():
            conn = _conn()
            conn.execute(
                "INSERT INTO applied (ts, job_id, status, note) VALUES (?, ?, ?, ?)",
                (ts, job_id, status, note),
            )
            conn.commit()
            conn.close()
        _with_retry(_w)
    except Exception as e:
        print(f"[state] 写入投递记录失败: {e}", file=sys.stderr)


def count_applied_today() -> int:
    """统计今日投递记录条数（投递上限判断用）。"""
    _init_db()
    import datetime
    today = datetime.date.today().isoformat()
    try:
        conn = _conn()
        row = conn.execute(
            "SELECT COUNT(*) FROM applied WHERE ts >= ? AND ts < ?",
            (today + " 00:00:00", today + " 23:59:59"),
        ).fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception as e:
        print(f"[state] 统计今日投递失败: {e}", file=sys.stderr)
        return 0


def last_applied_time() -> float:
    """最近一次投递的时间戳（秒），无记录返回 0.0（投递最小间隔用）。"""
    _init_db()
    try:
        conn = _conn()
        row = conn.execute("SELECT ts FROM applied ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        if not row:
            return 0.0
        import datetime
        return datetime.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S").timestamp()
    except Exception as e:
        print(f"[state] 读取最近投递时间失败: {e}", file=sys.stderr)
        return 0.0


def list_applied(limit: int = 100) -> list:
    """最近投递记录（agent 查看/汇报用，默认最近 100 条）。"""
    _init_db()
    try:
        conn = _conn()
        rows = conn.execute(
            "SELECT ts, job_id, status, note FROM applied ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [{"ts": r[0], "job_id": r[1], "status": r[2], "note": r[3]} for r in rows]
    except Exception as e:
        print(f"[state] 读取投递记录失败: {e}", file=sys.stderr)
        return []


if __name__ == "__main__":
    # 自检：python3 state.py 打印状态
    import pprint
    print("数据库:", db_path())
    print("浏览器:", get_browser())
    print("最近投递:")
    pprint.pprint(list_applied(5))
