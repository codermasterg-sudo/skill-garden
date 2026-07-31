#!/usr/bin/env python3
"""搜索 BOSS 直聘岗位：用 CloakBrowser 打开搜索页，抓取岗位卡片，输出 JSON 列表。

原子动作：搜索 → 输出岗位列表。筛选、判断、记录均不在本脚本职责内（由 agent 决策）。
"""
import argparse
import json
import re
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


def search_online(url: str, profile_dir: Path) -> list:
    """用 CloakBrowser 打开搜索页，抓取岗位卡片。返回岗位字典列表。"""
    from cloakbrowser import launch

    jobs = []
    with launch(user_data_dir=str(profile_dir), headless=False, humanize=True) as browser:
        page = browser.new_page()
        page.goto(url, timeout=60000)
        page.wait_for_load_state("networkidle")
        # 等待岗位列表
        page.wait_for_selector(".rec-job-list", timeout=15000)
        cards = page.query_selector_all(".card-area")
        for card in cards:
            try:
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
                m = re.search(r"job_detail/(\d+)\.html", job.get("href", ""))
                if m:
                    job["id"] = m.group(1)
                if job.get("id"):
                    jobs.append(job)
            except Exception as e:
                # 单卡异常不中断整个列表抓取
                print(f"跳过异常岗位卡片: {e}", file=sys.stderr)
                continue
    return jobs


def main():
    parser = argparse.ArgumentParser(description="搜索 BOSS 直聘岗位")
    parser.add_argument("--keyword", required=True, help="搜索关键词（岗位名）")
    parser.add_argument("--city", default="北京", help="城市")
    parser.add_argument("--page", type=int, default=1, help="页码")
    parser.add_argument("--profile", type=Path, default=None, help="浏览器 profile 目录")
    parser.add_argument("--output", type=Path, default=None, help="输出 JSON 文件路径")
    args = parser.parse_args()

    url = build_search_url(args.keyword, args.city, args.page)
    profile_dir = args.profile or Path(__file__).parent.parent / "data" / "browser_profile"
    try:
        jobs = search_online(url, profile_dir)
    except Exception as e:
        print(f"搜索失败: {e}", file=sys.stderr)
        print("提示: 若出现登录页，请先扫码登录；若出现风控信号，请停止人工处理。", file=sys.stderr)
        sys.exit(1)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(json.dumps(jobs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
