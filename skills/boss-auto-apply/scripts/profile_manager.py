#!/usr/bin/env python3
"""偏好档案管理：读取/更新 data/profile.md（Markdown 格式，人类可读可手改）。"""
import argparse
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


def update_profile(path: Path, updates: dict) -> str:
    """按 updates（{小节名: 值}）更新档案。值可为 str 或 list。"""
    path = Path(path)
    content = load_profile(path)
    for section, value in updates.items():
        # 在对应小节标题后替换/追加内容
        # 简单实现：查找 "## {section}" 小节，替换其下非注释内容
        lines = content.splitlines()
        in_section = False
        new_lines = []
        for line in lines:
            if line.startswith("## "):
                in_section = (line.strip("## ").strip() == section)
                new_lines.append(line)
                if in_section:
                    # 占位：清掉小节旧内容（保留注释）
                    pass
            elif in_section:
                if not line.strip().startswith(">"):
                    continue  # 跳过旧内容
                new_lines.append(line)
            else:
                new_lines.append(line)
        content = "\n".join(new_lines)

        # 追加新内容
        value_str = value if isinstance(value, str) else "\n".join(f"- {v}" for v in value)
        content += f"\n## {section}\n{value_str}\n"

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
