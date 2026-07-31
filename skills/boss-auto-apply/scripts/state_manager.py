#!/usr/bin/env python3
"""运行状态管理：data/state.md（当日投递数/批次/风控状态）。"""
import re
from pathlib import Path

DEFAULTS = {"applied_today": 0, "batch": 0, "risk_paused": False}


def load_state(path) -> dict:
    path = Path(path)
    state = dict(DEFAULTS)
    if path.exists():
        content = path.read_text(encoding="utf-8")
        m = re.search(r"当日投递数:\s*(\d+)", content)
        if m:
            state["applied_today"] = int(m.group(1))
        m = re.search(r"批次:\s*(\d+)", content)
        if m:
            state["batch"] = int(m.group(1))
        m = re.search(r"风控暂停:\s*(true|false)", content, re.IGNORECASE)
        if m:
            state["risk_paused"] = m.group(1).lower() == "true"
    return state


def update_state(path, **kwargs):
    path = Path(path)
    state = load_state(path)
    state.update(kwargs)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# 运行状态\n\n- 当日投递数: {state['applied_today']}\n"
        f"- 批次: {state['batch']}\n- 风控暂停: {str(state['risk_paused']).lower()}\n",
        encoding="utf-8",
    )
    return state
