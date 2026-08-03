#!/usr/bin/env python3
"""拟人化行为控制模块（安全底线，脚本强制，不依赖 agent 自觉）。

所有脚本共用的：
- 随机延迟（拟人化，避免规律性触发风控）
- 请求频率控制（单会话请求上限、失败退避）
- 风控信号检测

设计原则：
- 频率/节奏/退避**由脚本内置**，保证执行稳定性
- 所有值带随机抖动，避免固定间隔
"""
import json
import random
import sys
import time
from pathlib import Path

# 延迟/退避参数默认值（可被 config/throttle.json 覆盖）
DELAY_BEFORE_CLICK = (3, 10)   # 投递点击前随机延迟区间 [min, max]
DELAY_AFTER_CLICK = (1, 3)     # 点击后随机延迟区间 [min, max]
DELAY_BEFORE_API = (2, 6)      # API 请求前随机延迟区间 [min, max]
PAGE_TRANSITION_DELAY = (3, 8) # 翻页间随机延迟区间 [min, max]
CLICK_JITTER = 0.2             # 延迟抖动系数（±20%）
BACKOFF_BASE = 5               # 失败退避基数（指数递增）
BACKOFF_MAX = 60               # 退避上限（秒）
BACKOFF_MAX_RETRIES = 3        # 连续失败最大重试次数

_cfg = None  # 懒加载配置


def _get_cfg():
    """读取配置（懒加载，仅首次调用时读文件；config._cache 置 None 可强制重读）。"""
    global _cfg
    if _cfg is None:
        try:
            import config
            _cfg = config.load()
        except Exception as e:
            print(f"[humanize] 加载配置失败，使用默认值: {e}", file=sys.stderr)
            _cfg = {}
    return _cfg


def _range_cfg(key: str, default) -> tuple:
    """从配置取 [min, max] 区间（点路径），非法则用默认。"""
    import config
    val = config.get_path(_get_cfg(), key)
    if isinstance(val, (list, tuple)) and len(val) == 2:
        try:
            a, b = float(val[0]), float(val[1])
            if 0 <= a <= b:
                return (a, b)
        except (TypeError, ValueError):
            pass
    return default

# ============================================================
# 随机延迟（拟人化）
# ============================================================

def random_delay(min_sec: float = 2, max_sec: float = 6, jitter: float = 0.2) -> None:
    """随机延迟 [min, max] 秒，带抖动（±20%），模拟真人操作间隔。"""
    base = random.uniform(min_sec, max_sec)
    jitter_amp = random.uniform(1 - jitter, 1 + jitter)  # ±jitter 抖动
    time.sleep(base * jitter_amp)


def api_request_delay() -> None:
    """API 请求前的拟人化延迟（2-6 秒 + 抖动）。

    每次请求 API 前调用，避免高频请求触发风控。
    """
    random_delay(*_range_cfg("search.delay_before_api", DELAY_BEFORE_API))


def page_transition_delay() -> None:
    """页面跳转/翻页间的拟人化延迟（3-8 秒 + 抖动）。"""
    random_delay(*_range_cfg("search.page_transition_delay", PAGE_TRANSITION_DELAY))


def after_click_delay() -> None:
    """点击后的拟人化延迟（1-3 秒 + 抖动）。"""
    random_delay(*_range_cfg("apply.delay_after_click", DELAY_AFTER_CLICK))


# ============================================================
# 请求频率控制（强制上限）
# ============================================================

class RequestThrottle:
    """单会话 API 请求节流器：强制请求间隔 + 总数上限。

    用法：
        throttle = RequestThrottle(max_requests=30)
        throttle.acquire()  # 每次请求前调用（自动等待间隔 + 检查上限）
    """

    def __init__(self, max_requests: int = 30, min_interval: float = 2.0):
        """
        Args:
            max_requests: 单会话最大 API 请求数（超过抛异常，强制停止）
            min_interval: 请求最小间隔（秒），实际间隔会加随机抖动
        """
        self.max_requests = max_requests
        self.min_interval = min_interval
        self._count = 0
        self._last_ts = 0.0

    def acquire(self) -> None:
        """请求前调用：检查上限 + 等待最小间隔（带抖动）。"""
        if self._count >= self.max_requests:
            raise RuntimeError(
                f"已达单会话请求上限 {self.max_requests}，停止。"
                "如需继续请稍后再运行。"
            )
        # 距上次请求的最小间隔（带抖动）
        elapsed = time.time() - self._last_ts
        wait = self.min_interval * random.uniform(0.8, 1.5) - elapsed
        if wait > 0:
            time.sleep(wait)
        self._count += 1
        self._last_ts = time.time()

    @property
    def count(self) -> int:
        return self._count


# ============================================================
# 跨进程频率控制（SQLite 持久化，多次运行脚本共享）
# ============================================================

class CrossProcessThrottle:
    """跨进程请求节流：SQLite 记录时间戳，多次运行脚本共享。

    无论 agent 调用多少次脚本，强制保证两次操作之间有时间间隔。
    用于搜索/投递等会触达 BOSS 服务器的动作。

    用法：
        throttle = CrossProcessThrottle("search", min_interval=10)
        throttle.wait()  # 每次操作前调用
    """

    DB_NAME = "throttle.db"

    def __init__(self, name: str, min_interval: float = 10.0, max_interval: float = 20.0,
                 data_dir=None):
        """
        Args:
            name: 节流器名称（如 "search"/"apply"），不同动作独立节流
            min_interval: 最小间隔（秒），实际会加随机抖动
            max_interval: 间隔上限（秒）
            data_dir: 数据库目录（默认 skill 的 data/ 目录）
        """
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data"
        self.name = name
        self.min_interval = min_interval
        self.max_interval = max_interval
        self._db = Path(data_dir) / self.DB_NAME
        self._db.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """建表（若不存在）：action=动作名, last_ts=上次时间戳, count=当日次数。"""
        import sqlite3
        try:
            conn = sqlite3.connect(str(self._db))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS actions (
                    action TEXT PRIMARY KEY,
                    last_ts REAL NOT NULL DEFAULT 0,
                    count INTEGER NOT NULL DEFAULT 0,
                    date TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"SQLite 初始化失败: {e}", file=sys.stderr)

    def wait(self) -> None:
        """操作前调用：检查距上次操作的间隔，不足则等待（带随机抖动）。"""
        import sqlite3
        import datetime

        today = datetime.date.today().isoformat()
        conn = sqlite3.connect(str(self._db))
        try:
            row = conn.execute(
                "SELECT last_ts, count, date FROM actions WHERE action = ?",
                (self.name,),
            ).fetchone()

            now = time.time()
            last_ts = row[0] if row else 0
            count = row[1] if row else 0
            date = row[2] if row else ""

            # 跨天重置计数
            if date and date != today:
                count = 0

            # 间隔控制
            if last_ts and now - last_ts < self.min_interval:
                wait = (self.min_interval - (now - last_ts)) + random.uniform(0, 3)
                print(f"距上次操作仅 {now - last_ts:.0f}s，等待 {wait:.0f}s 保持节奏...", flush=True)
                time.sleep(wait)

            # 记录本次操作
            conn.execute(
                """INSERT INTO actions (action, last_ts, count, date) VALUES (?, ?, ?, ?)
                   ON CONFLICT(action) DO UPDATE SET
                       last_ts = excluded.last_ts,
                       count = excluded.count,
                       date = excluded.date""",
                (self.name, time.time(), count + 1, today),
            )
            conn.commit()
        except Exception as e:
            print(f"SQLite 节流失败: {e}", file=sys.stderr)
        finally:
            conn.close()

    def get_daily_count(self) -> int:
        """查询当日已执行次数（供投递上限检查）。"""
        import sqlite3
        import datetime

        today = datetime.date.today().isoformat()
        try:
            conn = sqlite3.connect(str(self._db))
            row = conn.execute(
                "SELECT count, date FROM actions WHERE action = ?", (self.name,)
            ).fetchone()
            conn.close()
            if row and row[1] == today:
                return row[0]
            return 0
        except Exception:
            return 0


# ============================================================
# 失败退避（防止快速重试触发风控）
# ============================================================

def backoff_wait(fail_count: int) -> None:
    """失败退避：失败次数越多，等待越久（指数 + 抖动）。

    首次失败等 5-10 秒，之后 10-20、20-40 秒递增，避免快速重试。
    """
    base = BACKOFF_BASE * (2 ** fail_count)  # 5, 10, 20, 40...
    jitter = random.uniform(0.8, 1.3)
    wait = min(base * jitter, BACKOFF_MAX)  # 上限 60 秒
    print(f"等待 {wait:.0f} 秒后重试（失败 {fail_count} 次）...", flush=True)
    time.sleep(wait)


# ============================================================
# 每日/会话投递上限（供投递等动作复用）
# ============================================================

def daily_limit_check(applied_path, limit: int) -> int:
    """检查当日已执行次数，达到上限返回 True。文件不存在视为 0。"""
    import datetime
    from pathlib import Path

    applied_path = Path(applied_path)
    today = datetime.date.today().isoformat()
    if not applied_path.exists():
        return 0
    count = 0
    for line in applied_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(today):
            count += 1
    return count >= limit
