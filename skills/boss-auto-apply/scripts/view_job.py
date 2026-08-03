#!/usr/bin/env python3
"""查看 BOSS 直聘岗位 JD 详情：在已有浏览器实例中获取单个岗位的 JD 信息，输出 JSON。

原子动作：查询 JD → 输出详情。是否要查、查完如何判断，均由 agent 自主决定，
本脚本只负责把详情拿回来。

抓取方式（实测确认，稳定可靠）：
- 直接按 job_id 跳转独立详情页 `https://www.zhipin.com/job_detail/{job_id}.html`。
- 详情页为服务端渲染，各信息块都有带语义的结构化元素，按元素抓取：
  - JD 正文：`.job-sec-text`
  - 岗位名/薪资：`.job-primary .name` 的 `h1` / `.salary`
  - 城市/经验/学历：`.job-primary` 里 `.text-city` / `.text-experiece` / `.text-degree`
  - 福利标签：`.tag-all.job-tags` 下的 `span`（一个个标签，无需切词）
  - 公司基本信息：`.sider-company`（公司名/融资/规模/行业，`p > i[class]` 语义 icon）
  - 公司介绍：`.job-detail-company` 内 `.job-sec-text`
  - 工商信息：`.job-detail-company` 内 `.company-name` 等 `li`
  - 工作地址/经纬度：`.location-address` / `.job-location-map[data-lat]`
  - BOSS 信息：`.job-boss-info`
- 不依赖列表点击（列表动态）、不依赖详情 XHR。
- 不枚举关键词：页面有什么元素就取什么，页面结构变化时报错，人工核对后更新选择器。

输出控制（token 友好）：
- 默认输出**概要**：岗位名/薪资/公司/城市/经验/学历/融资/规模/行业 + JD 正文前 120 字。
- `--full` 输出全部字段（JD 全文、公司介绍全文、工商信息、福利、BOSS、经纬度等）。
- `--fields a,b,c` 精确指定字段（见 `--fields 可选项`），适合只关心某些信息的场景。
- **截断标记**：概要/字段模式下，`description`/`company_intro` 等大文本截断到 120 字，
  截断时输出 `<field>_truncated: true` 标记（如 `description_truncated`），
  并在 `description` 末尾加 `…`，让 agent 明确知道该字段不完整。
  **agent 判断以输出为准，如需完整内容用 `--fields <field>` 或 `--full`。**

流程：跳转详情页 → 等待渲染 → 按元素抓取 → 按参数裁剪输出 JSON。
页面无 JD 正文（岗位已下架等）报错退出。
"""
import argparse
import json
import re
import sys
from pathlib import Path

import config  # 限流/风控配置（可选，缺失时用内置默认）

# 详情页 URL（按 job_id 直接跳转）
JOB_DETAIL_URL = "https://www.zhipin.com/job_detail/{job_id}.html"

RISK_KEYWORDS = ["环境存在异常", "安全验证", "操作过于频繁", "code 37", "您的请求过于频繁"]

# 各信息块的语义选择器（页面改版时核对 references/selectors.md）
DESC_SELECTOR = ".job-sec-text"                        # JD 正文
PRIMARY_SELECTOR = ".job-primary"                      # 岗位主信息容器
SIDER_COMPANY_SELECTOR = ".sider-company"              # 侧边栏公司基本信息
COMPANY_DETAIL_SELECTOR = ".job-detail-company"        # 公司介绍 + 工商信息
TAGS_SELECTOR = ".tag-all.job-tags"                    # 福利标签
BOSS_SELECTOR = ".job-boss-info"                       # BOSS 信息

# 工商信息：li class → 输出字段名（标签在 li 内 span，值在 li 文本尾部）
COMPANY_LI_MAP = {
    "company-name": "company_legal_name",
    "company-user": "company_legal_representative",
    "res-time": "company_founded",
    "company-type": "company_type",
    "manage-state": "company_status",
    "company-fund": "company_capital",
}

# 侧边栏公司信息：icon class → 输出字段名（.sider-company 内 p 带语义 icon）
SIDER_ICON_MAP = {
    "icon-stage": "stage",
    "icon-scale": "scale",
    "icon-industry": "industry",
}

# 概要字段（默认输出，token 友好：不含大文本全文）
SUMMARY_FIELDS = [
    "id", "title", "salary", "company", "city", "experience", "degree",
    "stage", "scale", "industry",
]

# 全部可输出字段（--fields 参数可选值；不含 id，id 恒有）
ALL_FIELDS = [
    "title", "salary", "company", "city", "experience", "degree", "job_type",
    "description",       # JD 正文全文
    "welfare",           # 福利标签列表
    "boss",              # BOSS 信息（dict）
    "stage", "scale", "industry",
    "company_intro",     # 公司介绍全文
    "company_legal_name", "company_legal_representative", "company_founded",
    "company_type", "company_status", "company_capital",
    "address", "location_gps",
]

# 概要输出中 JD 正文截断长度
SUMMARY_DESC_LIMIT = 120


def _text(el) -> str:
    """取元素文本，失败返回空串。"""
    try:
        return (el.inner_text() or "").strip()
    except Exception:
        return ""


def extract_company_from_detail_page(page, job: dict) -> None:
    """从详情页抓取公司信息，补充到 job dict。

    来源：
    - `.sider-company`：公司基本信息（公司名 + 阶段/规模/行业），
      公司名在 `a[title]`，阶段/规模/行业在带语义 icon class 的 `p`
    - `.job-detail-company` 内 `.job-sec-text`：公司介绍
    - `.job-detail-company` 内 `li`：工商信息（label 在 span，值在 li 尾部文本）
    - `.company-address`：工作地址

    全部容错：抓不到某字段就跳过，不抛异常。
    """
    # 1. 侧边栏公司基本信息
    try:
        el = page.query_selector(SIDER_COMPANY_SELECTOR)
        if el:
            # 公司名：第一个 a[title]（公司页链接）
            a = el.query_selector("a[title]")
            if a:
                title = a.get_attribute("title") or ""
                if title and not job.get("company"):
                    job["company"] = title
            # 阶段/规模/行业：带语义 icon 的 p（icon class → 字段名）
            for p in el.query_selector_all("p"):
                i = p.query_selector("i")
                if not i:
                    continue
                key = SIDER_ICON_MAP.get(i.get_attribute("class") or "")
                if key and not job.get(key):
                    job[key] = _text(p)
    except Exception:
        pass

    # 2. 公司介绍（.job-detail-company 内第一个 .job-sec-text）
    try:
        el = page.query_selector(COMPANY_DETAIL_SELECTOR)
        if el:
            sec = el.query_selector(".job-sec-text")
            if sec:
                text = _text(sec)
                if text:
                    job["company_intro"] = text
    except Exception:
        pass

    # 3. 工商信息（li，label 在 span，值在 li 尾部文本）
    try:
        el = page.query_selector(COMPANY_DETAIL_SELECTOR)
        if el:
            for li in el.query_selector_all("li"):
                cls = li.get_attribute("class") or ""
                key = COMPANY_LI_MAP.get(cls)
                if not key:
                    continue
                # 值 = li 文本去掉 label span 文本
                label = _text(li.query_selector("span")) if li.query_selector("span") else ""
                value = _text(li)
                if label:
                    value = value.replace(label, "", 1).strip()
                if value:
                    job[key] = value
    except Exception:
        pass

    # 4. 工作地址（.location-address 是纯地址元素；父节点 .job-location-map 带经纬度）
    try:
        el = page.query_selector(".location-address")
        if el:
            address = _text(el)
            if address:
                job["address"] = address
        map_el = page.query_selector(".job-location-map")
        if map_el:
            lat = map_el.get_attribute("data-lat") or ""
            if lat:
                job["location_gps"] = lat
    except Exception:
        pass


def extract_job_extras(page, job: dict) -> None:
    """抓取岗位福利与招聘者（BOSS）信息，补充到 job dict。

    来源：
    - `.tag-all.job-tags` 下的 `span`：福利标签（一个个元素，无需切词）
    - `.job-boss-info`：BOSS 称呼/在线状态/职位
    """
    # 1. 福利（span 元素列表）
    try:
        el = page.query_selector(TAGS_SELECTOR)
        if el:
            tags = [_text(s) for s in el.query_selector_all("span")]
            tags = [t for t in tags if t and t != "..."]
            if tags:
                job["welfare"] = tags
    except Exception:
        pass

    # 2. BOSS 信息
    try:
        el = page.query_selector(BOSS_SELECTOR)
        if el:
            text = _text(el)
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            if lines:
                boss = {"name": lines[0], "title": ""}
                if len(lines) > 1:
                    # 在线状态关键词与职位文本，取最后一行非状态文本为职位
                    status_words = {"在线", "刚刚活跃", "今日活跃", "本周活跃", "本月活跃", "离线"}
                    title_lines = [l for l in lines[1:] if l not in status_words and l != "·"]
                    if title_lines:
                        boss["title"] = title_lines[-1]
                    status = [l for l in lines[1:] if l in status_words]
                    if status:
                        boss["online"] = status[0]
                job["boss"] = boss
    except Exception:
        pass


def extract_job_from_detail_page(page, job_id: str) -> dict:
    """从独立详情页抓取 JD 详情（服务端渲染，主路径）。

    全部按语义元素抓取，不枚举关键词。字段抓不到则为空，不抛异常。
    """
    job = {"id": job_id}

    # 1. JD 正文
    try:
        el = page.wait_for_selector(DESC_SELECTOR, timeout=15000)
        if el:
            job["description"] = _text(el)
    except Exception:
        pass

    # 2. 岗位名/薪资（.job-primary .name 的 h1 / .salary）
    try:
        el = page.query_selector(PRIMARY_SELECTOR)
        if el:
            name_el = el.query_selector(".name h1")
            if name_el:
                job["title"] = name_el.get_attribute("title") or _text(name_el)
            salary_el = el.query_selector(".name .salary")
            if salary_el:
                job["salary"] = _text(salary_el)
            # 城市/经验/学历（.text-city / .text-experiece / .text-degree）
            for cls, key in [(".text-city", "city"), (".text-experiece", "experience"),
                             (".text-degree", "degree")]:
                sub = el.query_selector(cls)
                if sub:
                    job[key] = _text(sub)
    except Exception:
        pass

    # 3. 内嵌 _jobInfo 变量（精简结构字段，banner/primary 兜底）
    try:
        val = page.evaluate("(typeof _jobInfo !== 'undefined') ? JSON.stringify(_jobInfo) : 'null'")
        if val and val != "null":
            info = json.loads(val)
            job["id"] = job.get("id") or info.get("job_id", "")
            if info.get("job_name"):
                job["title"] = info["job_name"]
            if info.get("job_salary"):
                job["salary"] = info["job_salary"]
            if info.get("company"):
                job["company"] = info["company"]
    except Exception:
        pass

    return job


def _check_risk(page) -> bool:
    """基础风控检测：页面内容命中关键词即认为风控（读操作也做检查）。

    优先检查 URL（风控常跳转 /web/user/ 登录页或验证页，成本低）；
    再查关键区块文本（头部/主体），避免全文 page.content() 序列化整个 DOM
    （慢且 `code 37` 等短串易在正常内容误命中）。
    """
    try:
        url = page.url
        # 风控/验证跳转：URL 特征（登录页、验证码、异常提示）
        if any(mark in url for mark in ("/web/user/", "captcha", "verify", "warn", "risk", "abnormal")):
            return True
    except Exception:
        pass
    keywords = config.get_path(config.load(), "risk.keywords") or RISK_KEYWORDS
    if not isinstance(keywords, list) or not keywords:
        keywords = RISK_KEYWORDS
    try:
        # 只取页面文本（比 page.content() 省内存/快），命中即风控
        text = page.evaluate("document.body ? document.body.innerText : ''")
    except Exception:
        return False
    # 正文匹配只对"中文长短语"（≥4 个中文字符）做，短关键词（如 "code 37"）
    # 只在 URL 匹配，避免正常页面内容误命中
    def _is_body_kw(kw: str) -> bool:
        return sum(1 for ch in kw if "一" <= ch <= "鿿") >= 4
    return any(kw in text for kw in keywords if _is_body_kw(kw))


def view_job(job_id: str) -> dict:
    """查询单个岗位的 JD 详情，返回完整抓取的 dict（未裁剪）。

    按 job_id 直接跳转独立详情页，按语义元素抓取（服务端渲染，零额外请求）。
    返回全部字段；裁剪由 main() 按参数处理。
    """
    sys.path.insert(0, str(Path(__file__).parent))
    import browser_lib as browser
    from humanize import api_request_delay, CrossProcessThrottle
    from search_jobs import wait_for_login

    # 跨进程节流：连续查看详情也保持间隔（防高频触发风控）
    min_view_interval = 5.0
    try:
        min_view_interval = float(config.get_path(config.load(), "view.min_view_interval", 5.0))
    except Exception:
        pass
    CrossProcessThrottle("view", min_interval=min_view_interval).wait()

    if not browser.cdp_alive():
        raise RuntimeError("没有检测到浏览器。请先运行: python3 scripts/browser.py open")

    browser_conn = browser.connect()
    try:
        page = browser_conn.contexts[0].new_page() if browser_conn.contexts else browser_conn.new_page()
        # 按 job_id 直接跳转详情页
        api_request_delay()
        page.goto(JOB_DETAIL_URL.format(job_id=job_id), timeout=60000)
        try:
            page.wait_for_load_state("domcontentloaded")
        except Exception:
            pass  # SPA 持续有网络请求，DOM 就绪即可继续

        # 登录态过期时等待扫码
        if not wait_for_login(page):
            raise RuntimeError("等待扫码登录超时，退出")

        # 风控检测
        if _check_risk(page):
            raise RuntimeError("检测到风控信号，停止，请人工处理")

        # DOM 抓取（服务端渲染，主路径）
        job = extract_job_from_detail_page(page, job_id)
        if not job.get("description"):
            raise RuntimeError(
                f"获取 JD 详情失败（页面无 JD 正文，岗位 {job_id} 可能已下架或页面结构变化），请人工确认"
            )

        # 公司信息补充（规模/融资/注册资金/地址等）
        extract_company_from_detail_page(page, job)
        # 福利与 BOSS 信息补充
        extract_job_extras(page, job)

        page.close()
        return job
    finally:
        browser_conn.close()  # 只断开 CDP 连接，浏览器保持运行


def _trim(job: dict, fields: list, full: bool = False, desc_limit: int = SUMMARY_DESC_LIMIT) -> dict:
    """按参数裁剪输出，token 友好。

    - full=True：输出全部字段（不过滤、不截断）。
    - full=False 且 fields 为空：输出概要字段 + JD 正文前 desc_limit 字。
    - full=False 且 fields 指定：只输出指定字段（+id）。
    概要/字段模式下，大文本（description/company_intro）截断到 desc_limit 字，
    被截断的字段值为 `前 desc_limit 字 + …`，并额外提供 `<field>_truncated` 布尔标记，
    让 agent 明确知道该字段不完整（长度 N 字、已截断）。（agent 判断以输出为准）
    """
    out = {"id": job.get("id", "")}
    if full:
        for k, v in job.items():
            if k != "id":
                out[k] = v
        return out

    def _put(k, v):
        # 大文本截断 + 标记
        if isinstance(v, str) and len(v) > desc_limit and k in ("description", "company_intro"):
            out[k] = v[:desc_limit] + "…"
            out[f"{k}_truncated"] = True  # 标记：该字段被截断
        else:
            out[k] = v

    if fields:
        for k in fields:
            if k in job:
                _put(k, job[k])
        return out
    # 概要：SUMMARY_FIELDS + JD 正文截断
    for k in SUMMARY_FIELDS:
        if k in job:
            out[k] = job[k]
    if job.get("description"):
        _put("description", job["description"])
    return out


def main():
    parser = argparse.ArgumentParser(description="查看 BOSS 直聘岗位 JD 详情")
    parser.add_argument("--job-id", required=True, help="岗位 ID（search_jobs.py 列表输出中的 id 字段）")
    parser.add_argument("--full", action="store_true", help="输出全部字段（JD 全文/公司介绍全文/工商信息/经纬度等）")
    parser.add_argument("--fields", default=None,
                        help="只输出指定字段，逗号分隔。可选项: " + ", ".join(ALL_FIELDS) +
                             "。示例: --fields description 或 --fields welfare,address")
    args = parser.parse_args()

    try:
        job = view_job(args.job_id)
    except Exception as e:
        print(f"查看 JD 失败: {e}", file=sys.stderr)
        sys.exit(1)

    # 参数校验：--fields 只接受 ALL_FIELDS 内的字段
    fields = None
    if args.fields:
        fields = [f.strip() for f in args.fields.split(",") if f.strip()]
        unknown = [f for f in fields if f not in ALL_FIELDS]
        if unknown:
            print(f"未知字段: {', '.join(unknown)}。可选: {', '.join(ALL_FIELDS)}", file=sys.stderr)
            sys.exit(1)

    print(json.dumps(_trim(job, fields, full=args.full), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
