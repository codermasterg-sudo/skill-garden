#!/usr/bin/env python3
"""搜索 BOSS 直聘岗位：在已有浏览器实例中获取岗位列表，输出 JSON。

优先通过页面内 XHR 调用 BOSS 列表接口（返回明文薪资 salaryDesc）；
接口不可用时降级为页面元素抓取 + 薪资字符解码。

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

# 筛选参数映射（实测确认，注意：BOSS 的 URL 参数值与 API 参数值是两套体系！）
# - URL 参数：页面加载时前端过滤（如 URL degree=202 显示"本科"）
# - API 参数：joblist.json 接口过滤（如 API degree=203 才返回"本科"）
# 每项：{中文选项: (URL值, API值)}。API 值为 None 表示该筛选 API 不支持（仅 URL 过滤）。
# API 实测：degree 支持（202大专/203本科/204硕士）、salary 部分支持、
#          experience 仅"经验不限"(101)、jobType/scale/financingStage 不支持（code 37）。
FILTER_MAPS = {
    "jobType": {   # 求职类型（URL 和 API 均支持）
        "全职": ("1901", "1901"), "实习": ("1902", "1902"), "兼职": ("1903", "1903"),
    },
    "experience": {  # 工作经验（API 仅"经验不限"）
        "经验不限": ("101", "101"),
    },
    "degree": {     # 学历
        "大专": ("201", "202"), "本科": ("202", "203"), "硕士": ("203", "204"),
    },
    "salary": {     # 薪资待遇（API 部分支持，区间模糊匹配）
        "3K以下": ("401", "402"), "3-5K": ("402", "403"), "5-10K": ("403", "404"),
    },
    "financingStage": {  # 融资阶段（仅 URL 支持）
        "未融资": ("304", None), "天使轮": ("301", None), "A轮": ("302", None),
        "B轮": ("303", None), "C轮": ("303", None), "D轮及以上": ("305", None), "已上市": ("306", None),
    },
    "scale": {      # 公司规模（仅 URL 支持）
        "0-20人": ("301", None), "20-99人": ("302", None), "100-499人": ("303", None),
        "500-999人": ("304", None), "1000-9999人": ("305", None), "10000人以上": ("306", None),
    },
}

# 中文选项 → URL 参数值（页面展示过滤用）
def _url_filter_value(filter_name: str, option: str):
    pair = FILTER_MAPS[filter_name].get(option)
    return pair[0] if pair else None

# 中文选项 → API 参数值（数据过滤用，None=API 不支持）
def _api_filter_value(filter_name: str, option: str):
    pair = FILTER_MAPS[filter_name].get(option)
    return pair[1] if pair else None

# 列表 API（页面内 XHR 调用，返回明文薪资；页面自身会请求此接口，不触发风控）
API_JOB_LIST_PATH = "/wapi/zpgeek/search/joblist.json"

# 薪资字符映射：专用区字符 → 数字（页面元素降级时转换用；BOSS 更新时需同步）
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
    """把薪资文本里的专用区字符转换为数字（页面元素降级用）。

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


def build_search_url(keyword: str, city: str, filters: dict = None) -> str:
    """构建搜索页 URL。

    Args:
        keyword: 岗位关键词
        city: 城市（中文名）
        filters: 筛选条件 dict，key 为 URL 参数名（jobType/experience/degree/salary/
                 financingStage/scale），value 为参数值。传入的键值直接透传到 URL。

    返回搜索页 URL（BOSS 页面加载时按 URL 参数筛选）。
    """
    from urllib.parse import quote
    city_code = CITY_CODES.get(city, "100010000")  # 全国
    url = f"https://www.zhipin.com/web/geek/job?query={quote(keyword)}&city={city_code}"
    for k, v in (filters or {}).items():
        if v:
            url += f"&{k}={v}"
    return url


def fetch_jobs_via_api(page, keyword: str, city: str, page_no: int, filters: dict = None) -> tuple:
    """在页面内 XHR 调列表 API，拿明文薪资。

    Args:
        filters: 筛选条件 dict（URL 参数名 → 值），透传到 API。

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
    api_params.update(filters or {})
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


def search_online(url: str, profile_dir: Path, keyword: str, city: str, page_no: int,
                  max_pages: int = 1, filters: dict = None) -> list:
    """在已有浏览器（CDP 复用）中获取岗位列表。

    优先 API（明文薪资，支持翻页），失败降级 DOM。复用 browser.py open 打开的浏览器实例。
    filters 为筛选条件（URL 参数名 → 值），透传到 API。

    频率控制（脚本强制）：
    - 每次 API 请求前随机延迟（humanize.api_request_delay）
    - 单会话请求上限（RequestThrottle，默认 30 次）
    - 失败退避（backoff_wait，指数递增）
    """
    sys.path.insert(0, str(Path(__file__).parent))
    import browser_lib as browser
    from humanize import api_request_delay, page_transition_delay, backoff_wait, RequestThrottle, CrossProcessThrottle

    # 跨进程节流：多次运行 search 脚本也保持间隔（防高频搜索触发风控）
    min_search_interval = 10.0
    try:
        import config as _cfg_mod
        min_search_interval = float(_cfg_mod.get_path(_cfg_mod.load(), "search.min_search_interval", 10.0))
    except Exception:
        pass
    CrossProcessThrottle("search", min_interval=min_search_interval).wait()

    jobs = []
    if not browser.cdp_alive():
        raise RuntimeError(
            "没有检测到浏览器。请先运行: python3 scripts/browser.py open"
        )
    # 单会话 API 请求上限（防高频，可从配置 search.request_throttle_max 覆盖）
    try:
        import config as _cfg_mod
        req_max = int(_cfg_mod.get_path(_cfg_mod.load(), "search.request_throttle_max", 30))
    except Exception:
        req_max = 30
    throttle = RequestThrottle(max_requests=req_max)  # 单会话最多 N 次 API 请求
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
                page_jobs, is_end = fetch_jobs_via_api(page, keyword, city, pg, filters)
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
                max_retries = 3
                try:
                    import config as _cfg_mod
                    max_retries = int(_cfg_mod.get_path(_cfg_mod.load(), "backoff.max_retries", 3))
                except Exception:
                    pass
                if fail_count >= max_retries:
                    print(f"连续 {max_retries} 次 API 失败，停止", file=sys.stderr)
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
    parser.add_argument("--job-type", choices=list(FILTER_MAPS["jobType"]), default=None, help="求职类型: " + "/".join(FILTER_MAPS["jobType"]))
    parser.add_argument("--experience", choices=list(FILTER_MAPS["experience"]), default=None, help="工作经验: " + "/".join(FILTER_MAPS["experience"]))
    parser.add_argument("--degree", choices=list(FILTER_MAPS["degree"]), default=None, help="学历: " + "/".join(FILTER_MAPS["degree"]))
    parser.add_argument("--salary", choices=list(FILTER_MAPS["salary"]), default=None, help="薪资待遇: " + "/".join(FILTER_MAPS["salary"]))
    parser.add_argument("--financing-stage", choices=list(FILTER_MAPS["financingStage"]), default=None, help="融资阶段: " + "/".join(FILTER_MAPS["financingStage"]))
    parser.add_argument("--scale", choices=list(FILTER_MAPS["scale"]), default=None, help="公司规模: " + "/".join(FILTER_MAPS["scale"]))
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

    # 筛选条件：中文选项 → URL 值（页面过滤）和 API 值（数据过滤）
    selected = {   # filter_name → 中文选项
        "jobType": args.job_type, "experience": args.experience,
        "degree": args.degree, "salary": args.salary,
        "financingStage": args.financing_stage, "scale": args.scale,
    }
    url_filters = {}   # URL 参数（页面展示过滤）
    api_filters = {}   # API 参数（数据过滤，仅 API 支持的）
    for name, opt in selected.items():
        if not opt:
            continue
        uv = _url_filter_value(name, opt)
        if uv:
            url_filters[name] = uv
        av = _api_filter_value(name, opt)
        if av:
            api_filters[name] = av

    url = build_search_url(args.keyword, args.city, url_filters)
    profile_dir = args.profile or Path(__file__).parent.parent / "data" / "browser_profile"
    try:
        jobs = search_online(url, profile_dir, args.keyword, args.city, page_no=start_page, max_pages=max_pages, filters=api_filters)
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
