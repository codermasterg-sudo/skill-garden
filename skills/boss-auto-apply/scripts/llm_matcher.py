#!/usr/bin/env python3
"""LLM 匹配模块：简历 vs JD 匹配度评分。
后端可插拔：默认用环境变量 ANTHROPIC_API_KEY 调 Claude API；可替换为任意 LLM。"""
import json
import os
import urllib.request


def _call_llm(system: str, user: str) -> str:
    """调用 LLM 返回文本。默认 Claude API，可用环境变量替换后端。"""
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("未设置 ANTHROPIC_API_KEY / LLM_API_KEY")
    model = os.environ.get("LLM_MODEL", "claude-sonnet-4-5")
    payload = {
        "model": model,
        "max_tokens": 300,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode(),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
        return data["content"][0]["text"]


def llm_score(resume_text: str, jd_text: str) -> dict:
    """返回 {'score': 0-100, 'reason': str}。失败时抛异常（由调用方 fail-open）。"""
    system = "你是招聘匹配助手。根据简历与职位描述判断匹配度，只输出 JSON：{\"score\": 0-100, \"reason\": \"一句话理由\"}"
    user = f"简历:\n{resume_text}\n\n职位描述:\n{jd_text}"
    raw = _call_llm(system, user)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 兼容 LLM 输出多余文本
        import re
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise
