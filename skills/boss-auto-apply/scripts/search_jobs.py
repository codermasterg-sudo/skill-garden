#!/usr/bin/env python3
"""搜索 BOSS 直聘岗位：在已有浏览器实例中获取岗位列表，输出 JSON。

优先通过页面内 XHR 调用 BOSS 列表 API（返回明文薪资 salaryDesc，绕过字体加密）；
API 失败时降级为 DOM 抓取 + 字体解码。

原子动作：搜索 → 输出岗位列表。筛选、判断、记录均不在本脚本职责内（由 agent 决策）。
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

# 常用城市码（BOSS 直聘）
CITY_CODES = {
    "北京": "101010100", "上海": "101020100", "广州": "101280100",
    "深圳": "101280600", "杭州": "101210100", "成都": "101270100",
    "武汉": "101200100", "南京": "101190100", "西安": "101110100",
}

# 列表 API（页面内 XHR 调用，返回明文薪资；页面自身会请求此接口，不触发风控）
API_JOB_LIST_PATH = "/wapi/zpgeek/search/joblist.json"

# 薪资字体映射：私有区字符 → 数字（DOM 降级时解码用；BOSS 更新字体时需同步）
SALARY_FONT_MAP = {
    0xE031: "0", 0xE032: "1", 0xE033: "2", 0xE034: "3", 0xE035: "4",
    0xE036: "5", 0xE037: "6", 0xE038: "7", 0xE039: "8", 0xE03A: "9",
}

LOGIN_TIMEOUT = 300       # 等待扫码登录的最长时间（秒）
LOGIN_POLL_INTERVAL = 5   # 登录状态轮询间隔（秒）

# 页面内 XHR 调 API 的 JS（在登录后的页面上下文中执行，携带登录态）
FETCH_API_JS_TEMPLATE = """
(function(){
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '__API_URL__', false);
    xhr.send();
    if (xhr.status !== 200) return JSON.stringify({error: xhr.status});
    var data = JSON.parse(xhr.responseText);
    var jobs = (data.zpData || {}).jobList || [];
    var results = jobs.map(function(j) {
        return {
            title: j.jobName || '',
            salary: j.salaryDesc || '',
            company: j.brandName || '',
            salary_min: j.salaryMin || null,
            salary_max: j.salaryMax || null,
            location: (j.cityName || '') + '\\u00b7' + (j.areaDistrict || '') + '\\u00b7' + (j.businessDistrict || ''),
            experience: j.jobExperience || '',
            degree: j.jobDegree || '',
            scale: j.brandScaleName || '',
            stage: j.brandStageName || '',
            industry: j.brandIndustry || '',
            welfare: (j.welfareList || []).join(' | '),
            skills: (j.skills || []).join(' | '),
            id: j.encryptJobId || '',
            href: j.encryptJobId ? '/job_detail/' + j.encryptJobId + '.html' : ''
        };
    });
    return JSON.stringify(results);
})()
"""


def decode_salary(text: str) -> str:
    """把薪资 DOM 里的私有区字符解码为真实数字（DOM 降级用）。

    未识别的字符保留原样并标记 ?，便于发现字体更新。
    """
    out = []
    for ch in text:
        code = ord(ch)
        if 0xE000 <= code <= 0xF8FF:
            out.append(SALARY_FONT_MAP.get(code, "?"))
        else:
            out.append(ch)
    return "".join(out)


def wait_for_login(page) -> bool:
    """检测登录页并等待用户扫码登录。已登录返回 True，超时返回 False。

    登录页出现时（未登录），提示用户扫码；无头实例下无法扫码，
    需用有头实例（browser.py open）登录后复用。
    """
    try:
        page.wait_for_load_state("domcontentloaded")
    except Exception:
        pass
    # 用 URL + 登录页专属元素判断（不调用 content()，避免触发 SPA 重渲染；
    # 也不用「扫码登录」文本，避免详情页字样误判）
    if "/web/user/" not in page.url and not page.query_selector(".qrcode"):
        return True  # 已登录（或无需登录）
    print("检测到登录页，请在浏览器中扫码登录（最长等待 5 分钟）...", file=sys.stderr)
    deadline = time.time() + LOGIN_TIMEOUT
    while time.time() < deadline:
        page.wait_for_timeout(LOGIN_POLL_INTERVAL * 1000)
        try:
            page.wait_for_load_state("domcontentloaded")
        except Exception:
            pass
        if "/web/user/" not in page.url:
            return True  # 登录成功，页面已离开登录页
    print("等待扫码登录超时", file=sys.stderr)
    return False


def build_search_url(keyword: str, city: str) -> str:
    from urllib.parse import quote
    city_code = CITY_CODES.get(city, "100010000")  # 全国
    return f"https://www.zhipin.com/web/geek/job?query={quote(keyword)}&city={city_code}"


def fetch_jobs_via_api(page, keyword: str, city: str, page_no: int) -> tuple:
    """在页面内 XHR 调列表 API，拿明文薪资。

    返回 (jobs, is_end)：
    - jobs: 岗位列表（可能为空）
    - is_end: True 表示已到末尾（空页/不满页，无需继续翻页），False 表示可能还有更多
    网络/解析错误返回 ([]，False) 由调用方退避重试。
    """
    city_code = CITY_CODES.get(city, "100010000")
    api_params = {
        "scene": "1",
        "query": keyword,
        "city": city_code,
        "page": page_no,
        "pageSize": 30,
    }
    api_url = f"{API_JOB_LIST_PATH}?{urlencode(api_params)}"
    api_js = FETCH_API_JS_TEMPLATE.replace("__API_URL__", api_url)
    try:
        val = page.evaluate(api_js)
        data = json.loads(val) if isinstance(val, str) else val
        if isinstance(data, dict) and data.get("error"):
            print(f"API 返回错误: {data['error']}", file=sys.stderr)
            return [], True  # 服务端明确报错，视为到底
        if not isinstance(data, list):
            return [], False
        jobs = [j for j in data if j.get("id")]
        # 不满页（<30）说明到底了
        return jobs, len(jobs) < 30
    except Exception as e:
        print(f"API 抓取失败: {e}", file=sys.stderr)
        return [], False  # 网络异常，调用方退避重试


def fetch_jobs_via_dom(page) -> list:
    """DOM 抓取（降级）：滚动加载全部卡片 + 字体解码。"""
    jobs = []
    try:
        page.wait_for_selector(".job-card-wrap", timeout=15000)
        page.wait_for_timeout(2000)
        # 循环滚动到底，触发懒加载
        last_count = 0
        for _ in range(15):
            cards = page.query_selector_all(".job-card-wrap")
            if len(cards) == last_count:
                break
            last_count = len(cards)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)
        cards = page.query_selector_all(".job-card-wrap")
        for card in cards:
            try:
                job = {}
                el = card.query_selector(".job-name")
                if el:
                    job["title"] = el.inner_text().strip()
                    job["href"] = el.get_attribute("href") or ""
                el = card.query_selector(".boss-name")
                if el:
                    job["company"] = el.inner_text().strip()
                el = card.query_selector(".job-salary")
                if el:
                    job["salary"] = decode_salary(el.inner_text().strip())
                m = re.search(r"job_detail/([a-zA-Z0-9]+)\.html", job.get("href", ""))
                if m:
                    job["id"] = m.group(1)
                if job.get("id"):
                    jobs.append(job)
            except Exception as e:
                print(f"跳过异常岗位卡片: {e}", file=sys.stderr)
                continue
    except Exception as e:
        print(f"DOM 抓取失败: {e}", file=sys.stderr)
    return jobs


def search_online(url: str, profile_dir: Path, keyword: str, city: str, page_no: int, max_pages: int = 1) -> list:
    """在已有浏览器（CDP 复用）中获取岗位列表。

    优先 API（明文薪资，支持翻页），失败降级 DOM。复用 browser.py open 打开的浏览器实例。

    频率控制（脚本强制）：
    - 每次 API 请求前随机延迟（humanize.api_request_delay）
    - 单会话请求上限（RequestThrottle，默认 30 次）
    - 失败退避（backoff_wait，指数递增）
    """
    sys.path.insert(0, str(Path(__file__).parent))
    import browser_lib as browser
    from humanize import api_request_delay, page_transition_delay, backoff_wait, RequestThrottle, CrossProcessThrottle

    # 跨进程节流：多次运行 search 脚本也保持间隔（防高频搜索触发风控）
    CrossProcessThrottle("search", min_interval=10.0).wait()

    jobs = []
    if not browser.cdp_alive():
        raise RuntimeError(
            "没有检测到浏览器。请先运行: python3 scripts/browser.py open"
        )
    throttle = RequestThrottle(max_requests=30)  # 单会话最多 30 次 API 请求
    browser_conn = browser.connect()
    try:
        page = browser_conn.contexts[0].new_page() if browser_conn.contexts else browser_conn.new_page()
        # 首次进入页面：随机延迟
        api_request_delay()
        page.goto(url, timeout=60000)
        if not wait_for_login(page):
            print("等待扫码登录超时，退出", file=sys.stderr)
            return jobs

        # 优先 API 拿明文薪资（支持翻页）
        seen_ids = set()
        fail_count = 0
        for pg in range(page_no, page_no + max_pages):
            try:
                throttle.acquire()  # 请求上限 + 最小间隔
                page_jobs, is_end = fetch_jobs_via_api(page, keyword, city, pg)
            except RuntimeError as e:
                print(str(e), file=sys.stderr)
                break
            if is_end and not page_jobs:
                # 已到末尾（空页），直接停
                print(f"第 {pg} 页无数据，已到末尾，停止翻页", file=sys.stderr)
                break
            if not page_jobs:
                # 网络异常，退避重试
                fail_count += 1
                if fail_count >= 3:
                    print("连续 3 次 API 失败，停止", file=sys.stderr)
                    break
                backoff_wait(fail_count)
                continue
            fail_count = 0
            for j in page_jobs:
                if j["id"] not in seen_ids:
                    seen_ids.add(j["id"])
                    jobs.append(j)
            print(f"API 第 {pg} 页获取 {len(page_jobs)} 个岗位（明文薪资）", file=sys.stderr)
            if is_end:
                print(f"第 {pg} 页不足 30 个，已到末尾，停止翻页", file=sys.stderr)
                break
            if pg < page_no + max_pages - 1:
                page_transition_delay()  # 翻页间隔，拟人化随机

        if not jobs:
            # 降级 DOM 抓取
            print("API 失败，降级 DOM 抓取（薪资字体解码）", file=sys.stderr)
            jobs = fetch_jobs_via_dom(page)

        page.close()
    finally:
        browser_conn.close()  # 只断开 CDP 连接，浏览器保持运行
    return jobs


def main():
    parser = argparse.ArgumentParser(description="搜索 BOSS 直聘岗位")
    parser.add_argument("--keyword", required=True, help="搜索关键词（岗位名）")
    parser.add_argument("--city", default="北京", help="城市")
    parser.add_argument("--pages", default="1,3", help="翻页范围（闭区间，默认 1,3 = 第 1~3 页共 90 个岗位；每页 30 个）")
    parser.add_argument("--profile", type=Path, default=None, help="浏览器 profile 目录")
    parser.add_argument("--output", type=Path, default=None, help="输出 JSON 文件路径")
    args = parser.parse_args()

    # 解析 "start,end" 闭区间
    try:
        start_str, end_str = args.pages.split(",")
        start_page = int(start_str.strip())
        end_page = int(end_str.strip())
    except (ValueError, AttributeError):
        print(f"无效的 --pages 参数: {args.pages!r}，应为 'start,end' 如 1,3", file=sys.stderr)
        sys.exit(1)
    if start_page < 1 or end_page < start_page:
        print(f"无效的 --pages 参数: {args.pages!r}，需 start>=1 且 end>=start", file=sys.stderr)
        sys.exit(1)
    max_pages = end_page - start_page + 1

    url = build_search_url(args.keyword, args.city)
    profile_dir = args.profile or Path(__file__).parent.parent / "data" / "browser_profile"
    try:
        jobs = search_online(url, profile_dir, args.keyword, args.city, page_no=start_page, max_pages=max_pages)
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
