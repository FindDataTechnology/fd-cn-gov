"""`fd_cn_gov.detail.gov_cn_library` 测试：API 分页解析 / 字段映射 / 日期 / 正文抽取 / 三态。

不联网：API 与详情页都由注入的假 fetcher 提供。夹具取自真实抓取（2026-11-22）：
  · api_zhengcelibrary_p1.json —— 真实 search-gov/data 响应（catMap 精简，字段真实）
  · detail_7085110.html —— 真实详情页的元数据表 + UCAP-CONTENT 正文片段
真实站点行为（含 mintime 不生效、html_content 截断）的实测记录见交付报告。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from fd_cn_gov.detail import fetch as F  # noqa: E402
from fd_cn_gov.detail import gov_cn_library as G  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "govcn"


def _api_body() -> str:
    """把真实 API 记录包回 `<html><body>…</body></html>`（线上就是这个外壳）。"""
    return f"<html><body>{FIX.joinpath('api_zhengcelibrary_p1.json').read_text('utf-8')}</body></html>"


def _detail_body() -> str:
    return FIX.joinpath("detail_7085110.html").read_text("utf-8")


class _Resp:
    def __init__(self, status=200, body="", url=""):
        self.status = status
        self.body = body
        self.html_content = body
        self.url = url
        self.encoding = "utf-8"


class _RouteFetcher:
    """按 URL 子串路由：API 返回 API 外壳，详情页返回详情 HTML。"""

    def __init__(self, api_body=None, detail_body=None, api_status=200, detail_status=200):
        self.api_body = _api_body() if api_body is None else api_body
        self.detail_body = _detail_body() if detail_body is None else detail_body
        self.api_status = api_status
        self.detail_status = detail_status
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(url)
        if "search-gov/data" in url:
            return _Resp(self.api_status, self.api_body, url)
        return _Resp(self.detail_status, self.detail_body, url)


def _policy():
    return F.FetchPolicy(delay=0, timeout=1, max_attempts=1, backoff=0)


# ---------- API 解析与字段映射 ----------


def test_api_json_strips_html_wrapper():
    """线上响应用 <html><body> 包了一层，必须先剥壳再 json 解析。"""
    data = G._api_json(_api_body())
    assert data and "searchVO" in data
    assert G._api_json("not json at all") is None


def test_pub_date_dot_and_ptime_fallback():
    assert G.pub_date({"pubtimeStr": "2026.11.20"}) == "2026-11-20"
    assert G.pub_date({"pubtimeStr": "2026.1.5"}) == "2026-01-05"
    # 缺 pubtimeStr 时回退 ptime(ms)
    got = G.pub_date({"ptime": 1791882000000})
    assert got and len(got) == 10 and got[4] == "-"


def test_record_to_entry_maps_fields_and_normalizes_id():
    rec = {
        "id": "26926511", "title": "基金会管理条例", "pcode": "国令第848号",
        "puborg": "国务院", "pubtimeStr": "2026.11.10",
        "url": "https://www.gov.cn/zhengce/zhengceku/202611/content_7085662.htm",
        "childtype": "民政、扶贫、救灾\\其他",
    }
    e = G.record_to_entry(rec, "gongwen")
    assert e.source == "govcn"
    assert e.source_id == e.url == rec["url"]          # 规范化后不变（无查询/大小写差异）
    assert e.published == "2026-11-10"
    assert e.section == "gongwen" and e.doc_type == "国令第848号"
    assert e.title == "基金会管理条例"


def test_record_to_entry_skips_missing_url():
    assert G.record_to_entry({"title": "无链接"}, "gongwen") is None


# ---------- 翻页 / 去重 / since 截断 ----------


def _api_page(records):
    return "<html><body>" + json.dumps(
        {"searchVO": {"catMap": {"gongwen": {"listVO": records}}}}, ensure_ascii=False
    ) + "</body></html>"


def test_iter_entries_paginates_and_dedupes(monkeypatch):
    p1 = [{"id": "a", "url": "https://x/a", "pubtimeStr": "2026.11.10", "title": "A"},
          {"id": "b", "url": "https://x/b", "pubtimeStr": "2026.11.09", "title": "B"}]
    p2 = [{"id": "b", "url": "https://x/b", "pubtimeStr": "2026.11.09", "title": "B"},  # 重复
          {"id": "c", "url": "https://x/c", "pubtimeStr": "2026.11.08", "title": "C"}]
    pages = {1: _api_page(p1), 2: _api_page(p2), 3: "<html><body>{\"searchVO\":{\"catMap\":{}}}</body></html>"}

    def fake_fetch(url, policy, fetcher=None):
        n = int(url.split("p=")[1].split("&")[0])
        return F.FetchResult(url=url, status=200, body=pages[n], error="")

    monkeypatch.setattr(G, "fetch_detail", fake_fetch)
    got = list(G.iter_entries(("gongwen",), page_size=2, max_pages=5, since=None,
                              all_pages=True, policy=_policy()))
    ids = [e.source_id for e, _ in got]
    assert ids == ["https://x/a", "https://x/b", "https://x/c"], "跨页去重后应为 a,b,c"


def test_iter_entries_since_truncates_by_date(monkeypatch):
    """mintime 实测不生效，since 只能靠日期倒序截断：整页都早于 since 时停翻。"""
    p1 = [{"id": "a", "url": "https://x/a", "pubtimeStr": "2026.11.10", "title": "A"},
          {"id": "b", "url": "https://x/b", "pubtimeStr": "2026.11.09", "title": "B"}]
    p2 = [{"id": "c", "url": "https://x/c", "pubtimeStr": "2026.10.01", "title": "C"}]  # 全早于 since
    pages = {1: _api_page(p1), 2: _api_page(p2)}
    calls = []

    def fake_fetch(url, policy, fetcher=None):
        n = int(url.split("p=")[1].split("&")[0])
        calls.append(n)
        return F.FetchResult(url=url, status=200, body=pages.get(n, "<html><body>{}</body></html>"), error="")

    monkeypatch.setattr(G, "fetch_detail", fake_fetch)
    got = list(G.iter_entries(("gongwen",), page_size=2, max_pages=5, since="2026-11-01",
                              all_pages=False, policy=_policy()))
    assert [e.source_id for e, _ in got] == ["https://x/a", "https://x/b"]
    assert calls == [1, 2], "第二页全早于 since，取完即停（不再翻第 3 页）"


def test_iter_entries_max_pages_caps(monkeypatch):
    page = _api_page([{"id": "z", "url": "https://x/z", "pubtimeStr": "2026.11.10", "title": "Z"}])
    calls = []

    def fake_fetch(url, policy, fetcher=None):
        calls.append(url)
        return F.FetchResult(url=url, status=200, body=page, error="")

    monkeypatch.setattr(G, "fetch_detail", fake_fetch)
    list(G.iter_entries(("gongwen",), page_size=1, max_pages=2, since=None,
                        all_pages=False, policy=_policy()))
    assert len(calls) == 2, "max_pages=2 只翻两页"


# ---------- 正文抽取（真实夹具） ----------


def test_detail_body_extracted_from_real_fixture():
    """详情页正文必须从 UCAP 容器抽到（fetch_detail 走 resp.body，避免 html_content 截断）。"""
    res = F.fetch_detail("https://x/detail", _policy(), fetcher=_RouteFetcher())
    assert res.ok and "UCAP-CONTENT" in res.body
    from fd_text_core.verticals.gov.parser import parse_gov_doc
    doc = parse_gov_doc(res.body)
    assert len(doc.body) > 100, "正文非空"


# ---------- 三态：ok / unavailable / missing ----------


class _FakeSink:
    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, **kw):
        self.objects[Key] = Body


def _crawl_one(fetcher):
    sink = _FakeSink()
    stats = G.crawl(sink=sink, bucket="b", categories=("gongwen",), page_size=1,
                    max_pages=1, max_items=1, policy=_policy(), fetcher=fetcher,
                    parser=None, log=lambda *a: None)
    rows = []
    for key, body in sink.objects.items():
        if "structured" in key:
            rows += [json.loads(x) for x in body.decode("utf-8").strip().split("\n")]
    return stats, rows


def test_state_ok_writes_clean_record():
    stats, rows = _crawl_one(_RouteFetcher())
    assert stats["fetched"] == 1 and stats["written"] == 1
    r = rows[0]
    assert {"domain", "source", "source_id", "url", "title", "published",
            "content", "metadata"} <= set(r)
    assert r["source"] == "govcn" and r["content"] and r["metadata"]["status"] == "ok"
    # API 侧干净文号/机关/标题覆盖了详情页的脏值
    assert r["metadata"]["govcn"]["pcode"]
    assert r["title"] and "_中国政府网" not in r["title"]


def test_state_unavailable_on_fetch_failure():
    stats, rows = _crawl_one(_RouteFetcher(detail_status=404))
    assert stats["unavailable"] == 1 and stats["fetched"] == 0
    assert rows and rows[0]["content"] == "" and rows[0]["metadata"]["status"] == "unavailable"


def _empty_parser(html):
    """模拟正文抽不出的页面（容器未命中且解析器无兜底正文）。"""
    class D:
        title = "空壳"
        doc_number = None
        issuer = None
        addressee = None
        doc_type = None
        index_no = None
        site_date = None
        date = None
        body = "   "
        sections: list = []
        attachments: list = []
        cited_docs: list = []
    return D()


def test_state_missing_on_empty_body():
    stats, rows = _crawl_one(_RouteFetcher(detail_body="<html><body>x</body></html>"))
    # 用空正文解析器注入 missing 路径（真实空壳页由解析器兜底成页头，属解析器职责）
    sink = _FakeSink()
    stats = G.crawl(sink=sink, bucket="b", categories=("gongwen",), page_size=1,
                    max_pages=1, max_items=1, policy=_policy(),
                    fetcher=_RouteFetcher(detail_body="<html><body>x</body></html>"),
                    parser=_empty_parser, log=lambda *a: None)
    body = [v for k, v in sink.objects.items() if "structured" in k][0].decode("utf-8")
    row = json.loads(body.strip())
    assert stats["missing"] == 1 and stats["fetched"] == 0
    assert row["content"] == "" and row["metadata"]["status"] == "missing"


def test_api_failure_stops_and_reports(monkeypatch):
    """API 取页失败如实记、停止翻页，不静默当成 0 条。"""
    def boom(url, policy, fetcher=None):
        return F.FetchResult(url=url, status=0, error="HTTP 500")

    monkeypatch.setattr(G, "fetch_detail", boom)
    logs = []
    got = list(G.iter_entries(("gongwen",), page_size=1, max_pages=3, since=None,
                              all_pages=False, policy=_policy(), log=logs.append))
    assert got == []
    assert any("API 取页失败" in m for m in logs)
