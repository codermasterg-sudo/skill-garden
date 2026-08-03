# test_view_job.py
"""测试 view_job.py 的纯逻辑（详情解析、公司信息、福利/BOSS）。浏览器抓取需真实环境，不在此测。"""
import os
import re
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "skills", "boss-auto-apply", "scripts"))

from view_job import (
    extract_job_from_detail_page,
    extract_company_from_detail_page,
    extract_job_extras,
    _trim,
    _check_risk,
)


class _FakeEl:
    """模拟 Playwright 元素：inner_text / get_attribute / query_selector / query_selector_all。

    支持 class 选择器（.foo）、tag 选择器（h1、span、a、p、li）、
    后代选择器（.name h1）、属性选择器（a[title]）。
    """

    def __init__(self, text="", attrs=None, children=None, tag="div"):
        self._text = text
        self._attrs = attrs or {}
        self._children = children or []
        self._tag = tag

    def inner_text(self):
        return self._text

    def get_attribute(self, name):
        return self._attrs.get(name)

    def query_selector(self, sel):
        # 后代选择器（.name h1）或单选择器
        parts = sel.split()
        if len(parts) > 1:
            # 递归：先找父，再在父下找子
            parent = self.query_selector(parts[0])
            return parent.query_selector(" ".join(parts[1:])) if parent else None
        for c in self._children:
            if self._match(c, parts[0]):
                return c
        # 也递归查找后代
        for c in self._children:
            r = c.query_selector(sel)
            if r:
                return r
        return None

    def query_selector_all(self, sel):
        # 只匹配直接子元素（够用）
        return [c for c in self._children if self._match(c, sel)]

    @staticmethod
    def _match(el, sel):
        # a[title] 属性选择器
        m = re.match(r"^([a-z]+)\[([a-z-]+)\]$", sel)
        if m:
            return el._tag == m.group(1) and m.group(2) in el._attrs
        if sel.startswith("."):
            cls = el._attrs.get("class", "")
            return all(part in cls.split() for part in sel.lstrip(".").split("."))
        return el._tag == sel


def _el(text="", cls="", tag="div", attrs=None, children=None):
    a = dict(attrs or {})
    if cls:
        a["class"] = cls
    return _FakeEl(text, a, children=children or [], tag=tag)


def _span(text):
    return _el(text, "span", "span")


def _p(text, cls="", children=None):
    return _el(text, cls, "p", children=children)


def _h1(text):
    return _el(text, attrs={"title": text}, tag="h1")


def _make_page(primary=None, sider=None, company=None, tags=None, boss=None, job_info="null"):
    """构造模拟页面，按选择器返回对应元素。"""
    page = MagicMock()

    def qs(sel):
        if sel == ".job-sec-text" and primary is None and company is None:
            return _FakeEl("岗位职责：\n1、负责核心系统开发")
        if sel == ".job-primary":
            return primary
        if sel == ".sider-company":
            return sider
        if sel == ".job-detail-company":
            return company
        if sel == ".tag-all.job-tags":
            return tags
        if sel == ".job-boss-info":
            return boss
        return None

    def wfs(sel, timeout=0):
        if sel == ".job-sec-text":
            return _FakeEl("岗位职责：\n1、负责核心系统开发")
        return None

    page.query_selector.side_effect = qs
    page.wait_for_selector.side_effect = wfs
    page.evaluate.return_value = job_info
    return page


def _primary_el(title="Python 后端", salary="25-50K", city="北京", exp="3-5年", degree="本科"):
    """构造 .job-primary 结构：.name h1 / .name .salary / .text-city / .text-experiece / .text-degree。"""
    name = _FakeEl("", attrs={"class": "name"}, tag="div", children=[
        _h1(title),
        _el(salary, "salary", "span"),
    ])
    return _FakeEl("", tag="div", children=[
        name,
        _el(city, "text-city", "span"),
        _el(exp, "text-experiece", "span"),
        _el(degree, "text-degree", "span"),
    ])


def _sider_el(company="拾光伴学", stage="天使轮", scale="100-499人", industry="其他行业"):
    """构造 .sider-company 结构：a[title] + 带语义 icon 的 p。"""
    a = _el(company, attrs={"title": company}, tag="a")
    ps = [_p(stage, "", children=[_el("", "icon-stage", "i")]),
          _p(scale, "", children=[_el("", "icon-scale", "i")]),
          _p(industry, "", children=[_el("", "icon-industry", "i")])]
    return _FakeEl("", children=[a] + ps, tag="div")


def _company_el(intro="拾光文化是...", lis=None):
    """构造 .job-detail-company 结构：.job-sec-text（公司介绍）+ 若干 li。"""
    lis = lis or [
        ("company-name", "公司名称", "北京拾光书房文化传媒有限公司"),
        ("company-user", "法定代表人", "肖云"),
        ("res-time", "成立日期", "2020-11-27"),
        ("company-type", "企业类型", "有限责任公司"),
        ("manage-state", "经营状态", "存续"),
        ("company-fund", "注册资金", "119.487万元"),
    ]
    children = [_el(intro, "job-sec-text", "div")]
    for cls, label, value in lis:
        children.append(_el(label + "\n" + value, cls, "li", children=[_span(label)]))
    return _FakeEl("", children=children, tag="div")


def _tags_el(*welfare):
    return _FakeEl("", children=[_span(w) for w in welfare])


def _boss_el(name="梁女士", status="在线", title="招聘专员"):
    return _FakeEl(f"{name}\n{status}\n·\n{title}")


class TestExtractJobFromDetailPage(unittest.TestCase):
    def test_full(self):
        page = _make_page(primary=_primary_el())
        job = extract_job_from_detail_page(page, "abc123")
        self.assertEqual(job["id"], "abc123")
        self.assertEqual(job["title"], "Python 后端")
        self.assertEqual(job["salary"], "25-50K")
        self.assertEqual(job["city"], "北京")
        self.assertEqual(job["experience"], "3-5年")
        self.assertEqual(job["degree"], "本科")
        self.assertIn("负责核心系统开发", job["description"])

    def test_job_info_fallback(self):
        # 内嵌 _jobInfo 覆盖 primary
        page = _make_page(
            primary=_primary_el(),
            job_info='{"job_id": "abc123", "job_name": "Python 后端", "job_salary": "25-50K", "company": "某公司"}',
        )
        job = extract_job_from_detail_page(page, "abc123")
        self.assertEqual(job["title"], "Python 后端")
        self.assertEqual(job["salary"], "25-50K")
        self.assertEqual(job["company"], "某公司")

    def test_no_sec_text(self):
        # 无 JD 正文（找不到 .job-sec-text，抛超时异常）→ description 缺失（view_job 会报错）
        page = _make_page(primary=_primary_el())
        page.wait_for_selector.side_effect = Exception("timeout")
        job = extract_job_from_detail_page(page, "abc123")
        self.assertNotIn("description", job)


class TestExtractCompanyFromDetailPage(unittest.TestCase):
    def test_full(self):
        page = _make_page(sider=_sider_el(), company=_company_el())
        job = {}
        extract_company_from_detail_page(page, job)
        self.assertEqual(job["company"], "拾光伴学")
        self.assertEqual(job["stage"], "天使轮")
        self.assertEqual(job["scale"], "100-499人")
        self.assertEqual(job["industry"], "其他行业")
        self.assertEqual(job["company_legal_name"], "北京拾光书房文化传媒有限公司")
        self.assertEqual(job["company_legal_representative"], "肖云")
        self.assertEqual(job["company_founded"], "2020-11-27")
        self.assertEqual(job["company_type"], "有限责任公司")
        self.assertEqual(job["company_status"], "存续")
        self.assertEqual(job["company_capital"], "119.487万元")
        self.assertEqual(job["company_intro"], "拾光文化是...")

    def test_scale_people_above(self):
        # 规模 "10000人以上" 不误判为行业
        page = _make_page(sider=_sider_el(stage="D轮及以上", scale="10000人以上", industry="互联网"))
        job = {}
        extract_company_from_detail_page(page, job)
        self.assertEqual(job["stage"], "D轮及以上")
        self.assertEqual(job["scale"], "10000人以上")
        self.assertEqual(job["industry"], "互联网")

    def test_company_already_set(self):
        # company 已存在（banner 解析）时不覆盖
        page = _make_page(sider=_sider_el())
        job = {"company": "拾光伴学"}
        extract_company_from_detail_page(page, job)
        self.assertEqual(job["company"], "拾光伴学")

    def test_anonymous_no_company_block(self):
        # 匿名公司（无公司详情区块）→ 不抛异常
        page = _make_page(sider=None, company=None)
        job = {"company": "某大型通信公司"}
        extract_company_from_detail_page(page, job)
        self.assertEqual(job["company"], "某大型通信公司")
        self.assertNotIn("stage", job)


class TestExtractJobExtras(unittest.TestCase):
    def test_welfare_elements(self):
        # 福利是 span 元素列表，无需切词
        page = _make_page(tags=_tags_el("生日福利", "五险一金", "带薪年假", "底薪加提成"), boss=_boss_el())
        job = {}
        extract_job_extras(page, job)
        self.assertEqual(job["welfare"], ["生日福利", "五险一金", "带薪年假", "底薪加提成"])
        self.assertEqual(job["boss"]["name"], "梁女士")
        self.assertEqual(job["boss"]["title"], "招聘专员")
        self.assertEqual(job["boss"]["online"], "在线")

    def test_boss_various_status(self):
        page = _make_page(tags=_tags_el("五险一金"), boss=_boss_el(name="王先生", status="刚刚活跃", title="HR"))
        job = {}
        extract_job_extras(page, job)
        self.assertEqual(job["boss"]["online"], "刚刚活跃")
        self.assertEqual(job["boss"]["title"], "HR")

    def test_no_welfare(self):
        page = _make_page()
        job = {}
        extract_job_extras(page, job)
        self.assertNotIn("welfare", job)
        self.assertNotIn("boss", job)


class TestTrim(unittest.TestCase):
    """测试 _trim 输出裁剪（token 友好）。"""

    def setUp(self):
        self.job = {
            "id": "abc123",
            "title": "Python 后端",
            "salary": "25-50K",
            "company": "某公司",
            "city": "北京",
            "experience": "3-5年",
            "degree": "本科",
            "stage": "天使轮",
            "scale": "100-499人",
            "industry": "互联网",
            "description": "岗位职责：\n1、负责核心系统开发\n2、" + "长" * 200,
            "welfare": ["五险一金", "带薪年假"],
            "boss": {"name": "梁女士", "title": "招聘专员"},
            "company_intro": "公司介绍" + "长" * 300,
            "company_legal_name": "北京某公司",
            "address": "北京海淀",
            "location_gps": "116.3,39.9",
        }

    def test_summary_default(self):
        # 默认：概要字段 + JD 正文截断（带截断标记），不含大文本全文
        out = _trim(self.job, None)
        self.assertEqual(out["id"], "abc123")
        self.assertEqual(out["title"], "Python 后端")
        self.assertIn("description", out)
        self.assertLess(len(out["description"]), 200)  # 截断了
        self.assertTrue(out.get("description_truncated"))  # 截断标记
        self.assertNotIn("welfare", out)
        self.assertNotIn("boss", out)
        self.assertNotIn("company_intro", out)
        self.assertNotIn("company_legal_name", out)
        self.assertNotIn("address", out)
        self.assertNotIn("location_gps", out)

    def test_full(self):
        # --full：全部字段，不截断
        out = _trim(self.job, None, full=True)
        self.assertEqual(out["description"], self.job["description"])
        self.assertEqual(out["company_intro"], self.job["company_intro"])
        self.assertEqual(out["welfare"], ["五险一金", "带薪年假"])
        self.assertEqual(out["boss"]["name"], "梁女士")
        self.assertEqual(out["location_gps"], "116.3,39.9")

    def test_fields(self):
        # --fields：只输出指定字段（+id），大文本截断并带标记
        out = _trim(self.job, ["description", "address"])
        self.assertEqual(set(out.keys()), {"id", "description", "address", "description_truncated"})
        self.assertLess(len(out["description"]), 200)
        self.assertTrue(out["description_truncated"])

    def test_fields_short_text_no_mark(self):
        # 短文本（不截断）不输出标记
        job = dict(self.job)
        job["company_intro"] = "短介绍"
        out = _trim(job, ["company_intro"])
        self.assertEqual(out["company_intro"], "短介绍")
        self.assertNotIn("company_intro_truncated", out)

    def test_fields_welfare(self):
        out = _trim(self.job, ["welfare"])
        self.assertEqual(out["welfare"], ["五险一金", "带薪年假"])

    def test_fields_missing(self):
        # 请求不存在的字段：不报错，忽略
        out = _trim(self.job, ["title", "not_exist"])
        self.assertNotIn("not_exist", out)
        self.assertEqual(out["title"], "Python 后端")


class TestCheckRisk(unittest.TestCase):
    def test_risk_hit(self):
        page = MagicMock()
        page.content.return_value = "您的环境存在异常"
        self.assertTrue(_check_risk(page))

    def test_risk_miss(self):
        page = MagicMock()
        page.content.return_value = "正常页面内容"
        self.assertFalse(_check_risk(page))


if __name__ == "__main__":
    unittest.main()
