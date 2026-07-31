#!/usr/bin/env python3
"""解析 Word/PDF 简历，提取结构化字段。"""
import argparse
import json
import re
import sys
from pathlib import Path


def parse_docx(path: Path) -> str:
    from docx import Document
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def parse_pdf(path: Path) -> str:
    import fitz  # PyMuPDF
    doc = fitz.open(str(path))
    return "\n".join(page.get_text() for page in doc)


def parse_resume(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return parse_docx(path)
    elif suffix == ".pdf":
        return parse_pdf(path)
    else:
        raise ValueError(f"不支持的简历格式: {suffix}（仅支持 .docx / .pdf）")


def extract_fields(text: str) -> dict:
    """从简历文本提取结构化字段（基于规则的启发式提取）。"""
    fields = {
        "name": "",
        "skills": [],
        "experience_years": None,
        "expected_job": "",
        "city": "",
        "expected_salary": "",
    }

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # 姓名：第一行（非空非标题），只取姓名部分（截断手机号/邮箱等）
    for line in lines:
        if not line.startswith(("#", "简历", "个人")):
            name = re.split(r"[\s|，,]+", line)[0]
            name = re.sub(r"(手机|电话|邮箱|微信).*", "", name)
            fields["name"] = name
            break

    # 技能：匹配「熟悉/掌握/精通/熟练」开头的关键词（技术栈常见词）
    tech_keywords = [
        "Python", "Java", "Go", "C++", "C#", "JavaScript", "TypeScript", "Node",
        "React", "Vue", "Django", "Flask", "FastAPI", "Spring", "Docker", "K8s",
        "MySQL", "Redis", "MongoDB", "PostgreSQL", "Kafka", "RabbitMQ", "Git",
        "Linux", "TensorFlow", "PyTorch", "爬虫", "数据分析", "自动化测试",
        "机器学习", "深度学习", "分布式", "微服务",
    ]
    for line in lines:
        for kw in tech_keywords:
            if kw in line and kw not in fields["skills"]:
                fields["skills"].append(kw)

    # 经验年限
    m = re.search(r"(\d+)\s*年.*?经验", text)
    if m:
        fields["experience_years"] = int(m.group(1))

    # 期望岗位
    m = re.search(r"期望(?:岗位|职位)[：:]\s*(.+)", text)
    if m:
        fields["expected_job"] = m.group(1).strip()

    # 期望城市
    m = re.search(r"期望(?:城市|地点)[：:]\s*(.+)", text)
    if m:
        fields["city"] = m.group(1).strip()

    # 期望薪资
    m = re.search(r"期望(?:薪资|薪酬)[：:]\s*(.+)", text)
    if m:
        fields["expected_salary"] = m.group(1).strip()

    return fields


def main():
    parser = argparse.ArgumentParser(description="解析 Word/PDF 简历")
    parser.add_argument("resume", type=Path, help="简历文件路径 (.docx / .pdf)")
    parser.add_argument("--output", type=Path, default=None, help="输出 Markdown 路径")
    args = parser.parse_args()

    if not args.resume.exists():
        print(f"错误: 文件不存在 {args.resume}", file=sys.stderr)
        sys.exit(1)

    try:
        text = parse_resume(args.resume)
        fields = extract_fields(text)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

    md = f"""# 简历解析结果

- 姓名: {fields['name'] or '(未识别)'}
- 经验: {fields['experience_years'] or '(未识别)'} 年
- 技能: {', '.join(fields['skills']) or '(未识别)'}
- 期望岗位: {fields['expected_job'] or '(未识别)'}
- 期望城市: {fields['city'] or '(未识别)'}
- 期望薪资: {fields['expected_salary'] or '(未识别)'}

## 原始文本

{text}
"""
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(md, encoding="utf-8")
    else:
        print(md)


if __name__ == "__main__":
    main()
