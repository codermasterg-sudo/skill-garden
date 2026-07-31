#!/usr/bin/env python3
"""运行状态管理：data/state.md（当日投递数/批次/风控状态，含日期维度跨天重置）。"""
import datetime
import re
from pathlib import Path

DEFAULTS = {"date": None, "applied_today": 0, "batch": 0, "risk_paused": False}


def _today() -> str:
    return datetime.date.today().isoformat()


def load_state(path) -> dict:
    path = Path(path)
    state = dict(DEFAULTS)
    if path.exists():
        content = path.read_text(encoding="utf-8")
        m = re.search(r"日期:\s*(\d{4}-\d{2}-\d{2})", content)
        if m:
            state["date"] = m.group(1)
        m = re.search(r"当日投递数:\s*(\d+)", content)
        if m:
            state["applied_today"] = int(m.group(1))
        m = re.search(r"批次:\s*(\d+)", content)
        if m:
            state["batch"] = int(m.group(1))
        m = re.search(r"风控暂停:\s*(true|false)", content, re.IGNORECASE)
        if m:
            state["risk_paused"] = m.group(1).lower() == "true"
    # 跨天重置：日期不是今天则清零当日计数
    if state["date"] != _today():
        state["date"] = _today()
        state["applied_today"] = 0
        state["batch"] = 0
    return state


def update_state(path, **kwargs):
    path = Path(path)
    state = load_state(path)
    state.update(kwargs)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# 运行状态\n\n- 日期: {state['date']}\n"
        f"- 当日投递数: {state['applied_today']}\n"
        f"- 批次: {state['batch']}\n- 风控暂停: {str(state['risk_paused']).lower()}\n",
        encoding="utf-8",
    )
    return state
