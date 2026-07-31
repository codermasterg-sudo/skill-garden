#!/usr/bin/env python3
"""偏好档案管理：读取/更新 data/profile.md（Markdown 格式，人类可读可手改）。"""
import argparse
import re
import sys
from pathlib import Path

PROFILE_TEMPLATE = """# 用户偏好档案

> 本文件记录用户的求职偏好，由 agent 与用户对话时维护更新。长期复用。
> 修改方式：agent 追加/更新小节内容，保持 Markdown 结构。

## 基本信息
- 姓名:
- 经验年限:
- 技能:

## 期望
- 期望岗位:
- 期望城市:
- 期望薪资:
- 岗位类型: （实习 / 全职 / 兼职）

## 黑名单
- 公司:
- 岗位关键词:

## 备注
（其他长期偏好，如：不接受外包、大小周、加班文化等）
"""


def load_profile(path: Path) -> str:
    """读取档案；不存在则创建模板并返回。"""
    path = Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(PROFILE_TEMPLATE, encoding="utf-8")
    return path.read_text(encoding="utf-8")


def _render_value(value) -> str:
    """把值渲染为 Markdown 文本。str 直接输出；list 转逗号分隔。"""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    return str(value)


def update_profile(path: Path, updates: dict) -> str:
    """按 updates（{子键: 值}）更新档案。值可为 str 或 list。
    语义：在档案中查找 `- 子键:` 行（或 `## 子键` 小节）并替换其值；
    找不到则追加到 `## 备注` 小节。不影响其他子键。"""
    path = Path(path)
    content = load_profile(path)

    for key, value in updates.items():
        rendered = _render_value(value)
        lines = content.splitlines()

        # 1) 匹配小节内子键行：`- 期望岗位:`（可选值）
        replaced = False
        for i, line in enumerate(lines):
            m = re.match(rf"^\s*-\s*{re.escape(key)}:\s*(.*)$", line)
            if m:
                indent = re.match(r"^\s*", line).group(0)
                lines[i] = f"{indent}- {key}: {rendered}"
                replaced = True
                break
        if replaced:
            content = "\n".join(lines)
            continue

        # 2) 匹配独立小节：`## {key}`
        section_idx = None
        for i, line in enumerate(lines):
            if line.startswith("## ") and line.strip("## ").strip() == key:
                section_idx = i
                break
        if section_idx is not None:
            # 替换小节内容（保留 `>` 注释）
            j = section_idx + 1
            while j < len(lines) and not lines[j].startswith("## "):
                j += 1
            comments = [l for l in lines[section_idx + 1:j] if l.strip().startswith(">")]
            new_block = [lines[section_idx]] + comments
            if rendered:
                new_block.append(rendered)
            content = "\n".join(lines[:section_idx] + new_block + lines[j:])
            continue

        # 3) 找不到：追加到「备注」小节
        lines = content.splitlines()
        insert_at = len(lines)
        for i, line in enumerate(lines):
            if line.startswith("## 备注"):
                insert_at = i + 1
                while insert_at < len(lines) and not lines[insert_at].startswith("## "):
                    insert_at += 1
                break
        lines.insert(insert_at, f"- {key}: {rendered}")
        content = "\n".join(lines)

    path.write_text(content, encoding="utf-8")
    return content


def main():
    parser = argparse.ArgumentParser(description="偏好档案管理")
    parser.add_argument("--profile", type=Path, default=None, help="profile.md 路径（默认 data/profile.md）")
    parser.add_argument("--action", choices=["get", "update"], default="get")
    parser.add_argument("--key", help="update: 小节名")
    parser.add_argument("--value", help="update: 值")
    args = parser.parse_args()

    path = args.profile or Path(__file__).parent.parent / "data" / "profile.md"
    if args.action == "get":
        print(load_profile(path))
    else:
        if not args.key or not args.value:
            print("update 需要 --key 和 --value", file=sys.stderr)
            sys.exit(1)
        update_profile(path, {args.key: args.value})
        print(f"已更新 {path}")


if __name__ == "__main__":
    main()
