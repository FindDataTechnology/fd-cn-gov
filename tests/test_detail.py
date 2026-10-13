"""`fd_cn_gov.detail` 测试：存储键契约 / 状态水位 / 抓取失败留痕 / 落盘顺序。

不联网：抓取用注入的假 fetcher；S3 用内存替身。
真实站点的行为验证在 reports/acceptance.md（本轮实抓记录）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from fd_cn_gov.detail import fetch as F  # noqa: E402
from fd_cn_gov.detail import pipeline as PL  # noqa: E402
from fd_cn_gov.detail import sources as S  # noqa: E402
from fd_cn_gov.detail import state as ST  # noqa: E402
from fd_cn_gov.detail import storage as STO  # noqa: E402


# ---------- storage：键契约 ----------


def test_key_layout_matches_engine_contract():
    """structured 前缀必须与引擎 iter_structured 读的前缀一致（跨仓唯一接口）。"""
    assert STO.structured_prefix("gov") == "gov/structured/"
    assert STO.state_key("gov") == "gov/state.json"
    assert STO.manifest_prefix("gov") == "gov/manifest/"


def test_part_key_requires_run_id_and_is_immutable_by_design():
    """分片键含 run id：同一天两次运行不会互相覆盖（该仓已产事故的防线）。"""
    k1 = STO.structured_part_key("20261013120000", 1)
    k2 = STO.structured_part_key("20261013130000", 1)
    assert k1 != k2, "不同 run 的分片键必须不同"
    assert k1 == "gov/structured/run-20261013120000-part001.jsonl"
    with pytest.raises(ValueError):
        STO.structured_part_key("2026-10-13", 1)


def test_state_key_not_under_structured_prefix():
    """state/manifest 不得落在 structured 下（否则覆盖度统计会把它们当语料分片）。"""
    assert not STO.state_key("gov").startswith(STO.structured_prefix("gov"))
    assert not STO.manifest_key("20261013120000", "gov").startswith(STO.structured_prefix("gov"))


def test_safe_segment_kills_slashes():
    """URL/source_id 进键位不得引入斜杠（会造出假目录层级）。"""
    seg = STO.safe_segment("http://a.b/c/d.html")
    assert "/" not in seg and seg


def test_illegal_domain_rejected():
    with pytest.raises(ValueError):
        STO.structured_prefix("Gov/../x")


# ---------- sources：列表产物规范化 ----------


def test_load_list_products_normalizes_real_shape():
    """真实列表产物形态：JSON 数组，含 section/title/date/url/doc_type。"""
    raw = json.dumps([
        {"section": "通知公告", "title": "T1", "date": "2026-10-08",
         "url": "http://gi.mnr.gov.cn/202610/t20261008_1.html", "doc_type": "html"},
    ])
    out = S.load_list_products(raw, "mnr_tzgg_archive")
    assert len(out) == 1
    e = out[0]
    assert e.source == "mnr"
    assert e.source_id == "http://gi.mnr.gov.cn/202610/t20261008_1.html"
    assert e.published == "2026-10-08"


def test_load_list_products_dedupes_and_skips_missing_url():
    """同文多栏目重复按 URL 去重；缺 url 的条目跳过而非让整批失败。"""
    raw = json.dumps([
        {"title": "A", "url": "http://x.gov.cn/a.html", "date": "2026-01-01"},
        {"title": "A dup", "url": "http://x.gov.cn/a.html", "date": "2026-01-01"},
        {"title": "no url", "date": "2026-01-01"},
    ])
    out = S.load_list_products(raw, "mnr_tzgg_archive")
    assert len(out) == 1


def test_normalize_url_preserves_case_and_path():
    """规范化只做不改变语义的归一：去 fragment/小写 host，**保留 path 大小写**。

    ndrc 用 `t20260921_1407757.html` 这类大小写敏感路径区分资源，
    擅自小写会造出 404 或把两篇不同文档撞成一个键。
    """
    got = S.normalize_url("HTTP://WWW.NDRC.GOV.CN/Xwdt/Tzgg/t20260921_1407757.html#a")
    assert got == "http://www.ndrc.gov.cn/Xwdt/Tzgg/t20260921_1407757.html"


def test_unknown_script_raises():
    with pytest.raises(KeyError):
        S.script_to_source("not_a_script")


def test_all_eleven_scripts_mapped():
    """11 源都必须有部委标识映射（少一个就会有源悄悄不参与采集）。"""
    assert len(S.SOURCE_BY_SCRIPT) == 11


# ---------- state：水位与失败台账 ----------


def test_state_roundtrip_and_corrupt_degrades_empty():
    s = ST.empty_state("gov")
    ST.remember_success(s, "http://a/1.html", "hash1", published="2026-10-01")
    back = ST.parse_state(ST.dump_state(s), "gov")
    assert back["hashes"]["http://a/1.html"] == "hash1"
    assert back["watermark"] == "2026-10-01"
    # 损坏状态降级为空（绝不臆造成功）
    assert ST.parse_state("{not json", "gov")["hashes"] == {}


def test_failure_does_not_erase_prior_success_hash():
    """失败记录不得抹掉已成功的哈希——否则下轮会重抓本已未变的条目。"""
    s = ST.empty_state("gov")
    ST.remember_success(s, "u1", "h1")
    ST.remember_failure(s, "u1", "timeout")
    assert s["hashes"]["u1"] == "h1"
    assert s["failures"]["u1"]["attempts"] == 1
    ST.remember_failure(s, "u1", "timeout again")
    assert s["failures"]["u1"]["attempts"] == 2


def test_select_targets_skips_unchanged_and_retries_failures_last():
    s = ST.empty_state("gov")
    ST.remember_success(s, "u1", "h1")
    ST.remember_failure(s, "u2", "boom")
    entries = [{"source_id": "u1"}, {"source_id": "u2"}, {"source_id": "u3"}]
    targets, skipped = ST.select_targets(entries, s)
    assert [t["source_id"] for t in targets] == ["u3", "u2"], "新条目在前、历史失败在尾"
    assert skipped[0]["source_id"] == "u1"


def test_select_targets_full_mode_ignores_hash():
    s = ST.empty_state("gov")
    ST.remember_success(s, "u1", "h1")
    targets, _ = ST.select_targets([{"source_id": "u1"}], s, mode="full")
    assert len(targets) == 1


# ---------- fetch：失败如实留痕 ----------


class _Resp:
    def __init__(self, status=200, body="<html>x</html>", url="http://a/1"):
        self.status = status
        self.html_content = body
        self.url = url


class _FakeFetcher:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def get(self, url, **kw):
        self.calls += 1
        nxt = self.outcomes.pop(0) if self.outcomes else _Resp(500, "")
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def _policy():
    return F.FetchPolicy(delay=0, timeout=1, max_attempts=3, backoff=0)


def test_fetch_ok_follows_redirect_and_reports_final_url():
    f = _FakeFetcher([_Resp(200, "<html>ok</html>", url="https://gi.mnr.gov.cn/x.html")])
    res = F.fetch_detail("http://gi.mnr.gov.cn/x.html", _policy(), fetcher=f)
    assert res.ok and res.status == 200
    assert res.final_url == "https://gi.mnr.gov.cn/x.html", "必须记录重定向后的最终 URL"


def test_fetch_404_is_not_retried():
    """404 是确定性缺失：重试无意义，必须立即收手并如实记录。"""
    f = _FakeFetcher([_Resp(404, "")])
    res = F.fetch_detail("http://a/missing.html", _policy(), fetcher=f)
    assert not res.ok and res.status == 404
    assert f.calls == 1, "404 不得重试"
    assert "404" in res.error


def test_fetch_retries_5xx_then_succeeds():
    f = _FakeFetcher([_Resp(503, ""), _Resp(502, ""), _Resp(200, "<html>late</html>")])
    res = F.fetch_detail("http://a/x.html", _policy(), fetcher=f)
    assert res.ok and res.attempts == 3


def test_fetch_exhausted_retries_reports_error_not_silence():
    f = _FakeFetcher([_Resp(500, ""), _Resp(500, ""), _Resp(500, "")])
    res = F.fetch_detail("http://a/x.html", _policy(), fetcher=f)
    assert not res.ok and res.error and f.calls == 3


def test_fetch_empty_200_is_failure_not_success():
    """200 但空体是站点的软失败（维护页/拦截页），不得当成成功。"""
    f = _FakeFetcher([_Resp(200, ""), _Resp(200, ""), _Resp(200, "")])
    res = F.fetch_detail("http://a/x.html", _policy(), fetcher=f)
    assert not res.ok and "空" in res.error


def test_fetch_never_raises_on_network_exception():
    f = _FakeFetcher([TimeoutError("t"), TimeoutError("t"), TimeoutError("t")])
    res = F.fetch_detail("http://a/x.html", _policy(), fetcher=f)
    assert not res.ok and "TimeoutError" in res.error


def test_absolutize_relative_attachment():
    """实测自然资源部附件是 ./P02026...docx 相对链接。"""
    assert F.absolutize("./P0202606306.docx", "http://gi.mnr.gov.cn/202606/t1.html") == \
        "http://gi.mnr.gov.cn/202606/P0202606306.docx"
    assert F.absolutize("http://x/a.pdf", "http://y/") == "http://x/a.pdf"


# ---------- pipeline：落盘顺序与失败计数 ----------


class _FakeS3:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.put_order: list[str] = []
        self.fail_on: str | None = None

    def put_object(self, Bucket, Key, Body, **kw):
        if self.fail_on and self.fail_on in Key:
            raise RuntimeError("simulated S3 failure")
        self.objects[Key] = Body
        self.put_order.append(Key)

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise KeyError(Key)
        return {"Body": type("B", (), {"read": lambda self_: self.objects[Key]})()}


def _entry(i: int, src="mnr"):
    return S.ListEntry(source=src, source_id=f"http://a/{i}.html",
                       url=f"http://a/{i}.html", title=f"T{i}", published="2026-10-01")


def _fake_parser(html):
    class D:
        title = "解析标题"
        doc_number = "X〔2026〕1号"
        issuer = "某部"
        addressee = None
        doc_type = "通知"
        index_no = None
        site_date = None
        date = "2026-09-28"
        body = "正文" * 40
        sections = [("一、", "正文")]
        attachments: list = []
        cited_docs: list = []
    return D()


def test_pipeline_writes_jsonl_manifest_state_and_counts_failures():
    s3 = _FakeS3()
    entries = [_entry(1), _entry(2)]
    # 第 1 条成功；第 2 条 404
    f = _FakeFetcher([_Resp(200, "<html>ok</html>"), _Resp(404, "")])
    stats = PL.run_detail_crawl(entries, s3=s3, bucket="fd-text", policy=_policy(),
                               fetcher=f, parser=_fake_parser, log=lambda *a: None)
    assert stats.listed == 2 and stats.fetched == 1 and stats.written == 1
    assert stats.failed == 1, "404 必须计入失败"
    assert stats.failures[0]["stage"] == "fetch"
    keys = list(s3.objects)
    assert any(k.startswith("gov/structured/run-") for k in keys), "分片键形态"
    assert any(k.startswith("gov/manifest/run-") for k in keys)
    assert "gov/state.json" in keys
    # JSONL 每行一篇，字段含引擎摄取所需
    part = [k for k in keys if "structured" in k][0]
    row = json.loads(s3.objects[part].decode().strip().split("\n")[0])
    assert {"domain", "source", "source_id", "content", "metadata"} <= set(row)
    assert row["domain"] == "gov"


def test_pipeline_writes_manifest_before_state():
    """manifest 先于 state 落盘：反序会让「state 说已抓、分片其实不存在」的窗口出现。"""
    s3 = _FakeS3()
    PL.run_detail_crawl([_entry(1)], s3=s3, bucket="b", policy=_policy(),
                        fetcher=_FakeFetcher([_Resp(200, "<html>ok</html>")]),
                        parser=_fake_parser, log=lambda *a: None)
    order = s3.put_order
    assert any("manifest" in k for k in order) and "gov/state.json" in order
    assert order.index([k for k in order if "manifest" in k][0]) < order.index("gov/state.json")


def test_pipeline_incremental_skips_unchanged_on_second_run():
    s3 = _FakeS3()
    entries = [_entry(1)]
    f1 = _FakeFetcher([_Resp(200, "<html>ok</html>")])
    PL.run_detail_crawl(entries, s3=s3, bucket="b", policy=_policy(),
                        fetcher=f1, parser=_fake_parser, log=lambda *a: None)
    # 第二轮：带上一轮的 state，应全部跳过（不发请求）
    f2 = _FakeFetcher([])
    stats = PL.run_detail_crawl(entries, s3=s3, bucket="b", policy=_policy(),
                                fetcher=f2, parser=_fake_parser,
                                state_raw=s3.objects["gov/state.json"].decode(),
                                log=lambda *a: None)
    assert stats.skipped_unchanged == 1 and stats.fetched == 0
    assert f2.calls == 0, "水位命中时不得发请求"


def test_pipeline_empty_body_is_failure_not_silent_skip():
    """正文为空是数据问题，必须计入失败而非静默写成空文档。"""
    def empty_parser(html):
        return _fake_parser(html) if False else type("D", (), {
            "title": "t", "doc_number": None, "issuer": None, "addressee": None,
            "doc_type": None, "index_no": None, "site_date": None, "date": None,
            "body": "   ", "sections": [], "attachments": [], "cited_docs": [],
        })()

    s3 = _FakeS3()
    stats = PL.run_detail_crawl([_entry(1)], s3=s3, bucket="b", policy=_policy(),
                                fetcher=_FakeFetcher([_Resp(200, "<html>x</html>")]),
                                parser=empty_parser, log=lambda *a: None)
    assert stats.parse_failed == 1 and stats.written == 0
    assert stats.failures[0]["stage"] == "empty"


def test_pipeline_parse_exception_counted_not_swallowed():
    def boom(html):
        raise ValueError("parser exploded")

    s3 = _FakeS3()
    stats = PL.run_detail_crawl([_entry(1)], s3=s3, bucket="b", policy=_policy(),
                                fetcher=_FakeFetcher([_Resp(200, "<html>x</html>")]),
                                parser=boom, log=lambda *a: None)
    assert stats.parse_failed == 1 and stats.written == 0
    assert "ValueError" in stats.failures[0]["reason"]


def test_pipeline_partitions_by_part_size():
    s3 = _FakeS3()
    entries = [_entry(i) for i in range(5)]
    f = _FakeFetcher([_Resp(200, "<html>ok</html>") for _ in range(5)])
    stats = PL.run_detail_crawl(entries, s3=s3, bucket="b", policy=_policy(),
                                fetcher=f, parser=_fake_parser, part_size=2,
                                log=lambda *a: None)
    parts = [k for k in s3.objects if "structured" in k]
    assert len(parts) == 3 and stats.written == 5


def test_build_record_absolutizes_attachment_urls():
    """附件相对链接在采集侧补全（解析器不知道 base URL，属职责分离）。"""
    class A:
        name = "附件1"
        url = "./P02026.docx"
        kind = "docx"

    class D:
        title = "t"
        doc_number = None
        issuer = None
        addressee = None
        doc_type = None
        index_no = None
        site_date = None
        date = None
        body = "正文"
        sections: list = []
        attachments = [A()]
        cited_docs: list = []

    rec = PL.build_record(_entry(1), "<html></html>", parser=lambda h: D())
    assert rec.metadata["attachments"][0]["url"] == "http://a/P02026.docx"
