#!/usr/bin/env python3
"""BOSS 岗位搜索 + 双层筛选（规则过滤 + LLM 匹配）。"""
import argparse
import json
import sys
from pathlib import Path

# 常用城市码（BOSS 直聘）
CITY_CODES = {
    "北京": "101010100", "上海": "101020100", "广州": "101280100",
    "深圳": "101280600", "杭州": "101210100", "成都": "101270100",
    "武汉": "101200100", "南京": "101190100", "西安": "101110100",
}


def build_search_url(keyword: str, city: str, page: int = 1) -> str:
    from urllib.parse import quote
    city_code = CITY_CODES.get(city, "100010000")  # 全国
    url = f"https://www.zhipin.com/web/geek/job?query={quote(keyword)}&city={city_code}"
    if page > 1:
        url += f"&page={page}"
    return url


def rule_filter(jobs: list, criteria: dict) -> list:
    """规则过滤第一层：黑名单公司/岗位关键词、岗位类型、薪资范围。"""
    blacklist_companies = criteria.get("blacklist_companies", [])
    blacklist_keywords = criteria.get("blacklist_keywords", [])
    keyword = criteria.get("keyword", "")
    job_type = criteria.get("job_type", "")

    result = []
    for job in jobs:
        title = job.get("title", "")
        company = job.get("company", "")
        jtype = job.get("type", "")

        if any(bc in company for bc in blacklist_companies):
            continue
        if any(bk in title for bk in blacklist_keywords):
            continue
        if keyword and keyword.lower() not in title.lower():
            continue
        if job_type and jtype != job_type:
            continue
        result.append(job)
    return result


def search_online(url: str, profile_dir: Path) -> list:
    """用 CloakBrowser 打开搜索页，抓取岗位列表（真实点击/监听接口）。"""
    from cloakbrowser import launch

    jobs = []
    with launch(user_data_dir=str(profile_dir), headless=False, humanize=True) as browser:
        page = browser.new_page()
        page.goto(url, timeout=60000)
        page.wait_for_load_state("networkidle")
        # 等待岗位卡片
        page.wait_for_selector(".rec-job-list", timeout=15000)
        cards = page.query_selector_all(".card-area")
        for card in cards:
            job = {}
            el = card.query_selector(".job-name")
            if el:
                job["title"] = el.inner_text().strip()
                job["href"] = el.get_attribute("href") or ""
            el = card.query_selector(".company-name")
            if el:
                job["company"] = el.inner_text().strip()
            el = card.query_selector(".salary")
            if el:
                job["salary"] = el.inner_text().strip()
            # 岗位 ID 从 href 提取 /job_detail/{id}.html
            import re
            m = re.search(r"job_detail/(\d+)\.html", job.get("href", ""))
            if m:
                job["id"] = m.group(1)
            if job.get("id"):
                jobs.append(job)
    return jobs


def main():
    parser = argparse.ArgumentParser(description="BOSS 岗位搜索与筛选")
    sub = parser.add_subparsers(dest="mode", required=True)

    p_search = sub.add_parser("search", help="搜索岗位")
    p_search.add_argument("--keyword", required=True)
    p_search.add_argument("--city", default="北京")
    p_search.add_argument("--page", type=int, default=1)
    p_search.add_argument("--profile", type=Path, default=None)
    p_search.add_argument("--output", type=Path, default=None)

    p_filter = sub.add_parser("filter", help="规则过滤")
    p_filter.add_argument("--jobs", type=Path, required=True, help="岗位 JSON 文件")
    p_filter.add_argument("--keyword", default="")
    p_filter.add_argument("--job-type", default="")
    p_filter.add_argument("--blacklist-companies", default="")
    p_filter.add_argument("--blacklist-keywords", default="")
    p_filter.add_argument("--output", type=Path, default=None)

    args = parser.parse_args()

    if args.mode == "search":
        url = build_search_url(args.keyword, args.city, args.page)
        profile_dir = args.profile or Path(__file__).parent.parent / "data" / "browser_profile"
        try:
            jobs = search_online(url, profile_dir)
        except Exception as e:
            print(f"搜索失败: {e}", file=sys.stderr)
            print("提示: 若出现登录页，请先扫码登录；若出现风控信号，请停止人工处理。", file=sys.stderr)
            sys.exit(1)
        if args.output:
            args.output.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            print(json.dumps(jobs, ensure_ascii=False, indent=2))
    elif args.mode == "filter":
        jobs = json.loads(args.jobs.read_text(encoding="utf-8"))
        criteria = {
            "keyword": args.keyword,
            "job_type": args.job_type,
            "blacklist_companies": [c.strip() for c in args.blacklist_companies.split(",") if c.strip()],
            "blacklist_keywords": [c.strip() for c in args.blacklist_keywords.split(",") if c.strip()],
        }
        result = rule_filter(jobs, criteria)
        if args.output:
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
