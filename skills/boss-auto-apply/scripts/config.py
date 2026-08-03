#!/usr/bin/env python3
"""限流/拟人化行为配置加载（纯标准库，无第三方依赖）。

优先级（高 → 低）：
1. skill 目录下 config/throttle.json   —— 用户自定义（推荐修改点，git 入库可选）
2. skill 目录下 config/config.default.json —— 内置默认（git 入库，兜底）
3. 代码内硬编码默认值                  —— 最终兜底（配置缺失/损坏时保证脚本可运行）

用法：
    import config
    cfg = config.load()           # 读取配置（dict，自动合并）
    cfg["apply"]["hard_limit"]     # 150
    cfg.get_path("apply.min_apply_interval")  # 8.0（点路径取值，缺省返回 None）

设计：任何解析失败都只打 stderr 警告并回退下一级，绝不让配置问题阻塞投递。
"""
import json
import sys
from pathlib import Path

# 内置兜底（最终一级，与 config.default.json 同构）
_BUILTIN_DEFAULTS = {
    "apply": {
        "min_apply_interval": 8,
        "delay_after_click": [1, 3],
    },
    "search": {
        "min_search_interval": 10,
        "request_throttle_max": 30,
        "delay_before_api": [2, 6],
        "page_transition_delay": [3, 8],
    },
    "backoff": {
        "max_retries": 3,
    },
    "login": {
        "timeout_seconds": 300,
        "poll_interval": 5,
    },
    "risk": {
        "keywords": ["环境存在异常", "安全验证", "操作过于频繁", "code 37", "您的请求过于频繁"],
    },
}

_config_path = Path(__file__).resolve().parent.parent / "config" / "throttle.json"
_default_path = Path(__file__).resolve().parent.parent / "config" / "config.default.json"

_cache = None  # 配置缓存（进程内只读一次；改配置后置 None 重读）


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并：override 的值覆盖 base，两者都是 dict 时逐层合并。"""
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load() -> dict:
    """加载配置：用户自定义 throttle.json > 内置默认 config.default.json > 代码硬编码。

    注意：本函数有模块级缓存（_cache），修改 config 文件后同一进程内
    重复调用返回旧值。测试/调试时可用 config._cache = None 强制重读。
    """
    global _cache
    if _cache is not None:
        return _cache
    cfg = _BUILTIN_DEFAULTS

    # 1. 内置默认文件（config.default.json）
    try:
        if _default_path.exists():
            with open(_default_path, encoding="utf-8") as f:
                cfg = _deep_merge(cfg, json.load(f))
    except Exception as e:
        print(f"[config] 读取内置默认配置失败，使用代码硬编码: {e}", file=sys.stderr)

    # 2. 用户自定义文件（config/throttle.json）
    try:
        if _config_path.exists():
            with open(_config_path, encoding="utf-8") as f:
                cfg = _deep_merge(cfg, json.load(f))
    except Exception as e:
        print(f"[config] 读取用户配置失败，使用内置默认: {e}", file=sys.stderr)

    _cache = cfg
    return cfg


def get_path(cfg: dict, dotted: str, default=None):
    """点路径取值：get_path(cfg, "apply.min_apply_interval")。"""
    cur = cfg
    for key in dotted.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


if __name__ == "__main__":
    # 自检：python3 config.py 打印合并后的配置
    import pprint
    pprint.pprint(load())
