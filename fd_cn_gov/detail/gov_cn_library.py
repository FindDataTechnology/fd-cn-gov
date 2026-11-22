"""gov.cn 政策文件库采集：搜索 API 分页 -> 逐条取全文 -> structured JSONL。

与 `detail/__main__.py`（11 部委列表脚本）互补：那条路走各站列表页；这条路走
中国政府网**政策文件库**的搜索 API（`sousuo.www.gov.cn/search-gov/data`），
一次覆盖国务院文件/部委文件/中央文件/公报。

复用的既有能力（**不复制第二份**）：
  · HTTP 礼貌抓取与重试：`detail.fetch.fetch_detail`（UA/限速/退避/如实留痕）
  · 正文解析：`fd_text_core.verticals.gov.parser.parse_gov_doc`（经 `build_record`）
  · JSONL 记录契约与落盘键：`DetailRecord.to_jsonl` + `storage.structured_part_key`
  · 本地降级落盘：`storage.LocalSink`（键布局与桶内同构，可直接上传）

API 实测要点（2026-11-22，见报告）：
  · 一次调用返回 `t` 下所有分类的 `searchVO.catMap.<cat>.listVO[]`
  · `t=zhengcelibrary` 有 gongwen/bumenfile/otherfile/gongbao；
    `t=zhengce` 另有 zhongyangfile（中央文件）
  · **`mintime`/`maxtime` 实测不生效**（totalCount 与首条日期均不变），故增量
    只能按结果天然**日期倒序**翻页 + 日期截断（`--since`）实现，不能靠 API 过滤
  · `n=100/120` 可用，`n=200` 触发 302；结果按 pubtime 严格倒序
  · 响应体外包了一层 `<html><body>…</body></html>`，需剥离再 json 解析

三态如实（不造假）：
  · ok           抓到正文 -> 正常写行
  · unavailable  HTTP/网络失败 -> 写一行 content="" + metadata.status="unavailable"
  · missing      200 但正文为空/二进制 -> 写一行 content="" + metadata.status="missing"
  空正文行会被引擎 `load_gov.py` 跳过并告警（不入库、不占嵌入），但失败事实仍留档。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Iterator
from urllib.parse import urlencode

from .fetch import FetchPolicy, fetch_detail
from .pipeline import DetailRecord, build_record, looks_binary
from .sources import ListEntry, normalize_url
from .storage import LocalSink, manifest_key, run_id_utc, structured_part_key

API_URL = "https://sousuo.www.gov.cn/search-gov/data"

# 分类名 -> (t 参数, catMap 键)。只收「政策文件」类；otherfile 是解读新闻、gongbao 是
# 公报汇编，默认不取（可由 --category 显式加）。
SOURCES: dict[str, tuple[str, str]] = {
    "gongwen": ("zhengcelibrary", "gongwen"),        # 国务院文件
    "bumenfile": ("zhengcelibrary", "bumenfile"),    # 部委文件
    "zhongyangfile": ("zhengce", "zhongyangfile"),   # 中央文件
    "gongbao": ("zhengcelibrary", "gongbao"),        # 国务院公报
    "otherfile": ("zhengcelibrary", "otherfile"),    # 解读/新闻（非政策正文）
}
DEFAULT_CATEGORIES = ("gongwen", "bumenfile", "zhongyangfile")


def pub_date(rec: dict) -> str | None:
    """pubtimeStr（`2026.11.20`）-> `YYYY-MM-DD`；缺失时回退 ptime(ms)。"""
    s = str(rec.get("pubtimeStr") or "").strip()
    m = re.match(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    pt = rec.get("ptime")
    if isinstance(pt, (int, float)) and pt > 0:
        return datetime.fromtimestamp(pt / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    return None


def record_to_entry(rec: dict, category: str) -> ListEntry | None:
    """API 记录 -> ListEntry（无 url 的条目跳过，不让单条脏数据毁整页）。"""
    url = str(rec.get("url") or "").strip()
    if not url:
        return None
    return ListEntry(
        source="govcn",
        source_id=normalize_url(url),
        url=url,
        title=str(rec.get("title") or "").strip(),
        published=pub_date(rec),
        section=category,
        subsection=str(rec.get("childtype") or "").strip(),
        doc_type=str(rec.get("pcode") or "").strip(),
    )


def _api_json(body: str) -> dict | None:
    """剥离 `<html><body>…</body></html>` 外壳后解析 JSON；失败返回 None（如实降级）。"""
    body = body or ""
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(body[start : end + 1])
    except ValueError:
        return None


def fetch_page(
    t: str, page: int, page_size: int, policy: FetchPolicy, fetcher=None
) -> dict | None:
    """取一页搜索 API。失败返回 None（调用方如实记并停这一 t 的翻页）。"""
    qs = urlencode({"t": t, "type": "gwyzcwjk", "q": "", "p": page, "n": page_size})
    res = fetch_detail(f"{API_URL}?{qs}", policy, fetcher=fetcher)
    if not res.ok:
        return None
    return _api_json(res.body)


def iter_entries(
    categories: tuple[str, ...],
    *,
    page_size: int,
    max_pages: int,
    since: str | None,
    all_pages: bool,
    policy: FetchPolicy,
    fetcher=None,
    log=print,
) -> Iterator[tuple[ListEntry, dict]]:
    """按 t 分组翻页，产出 (ListEntry, 原始 API 记录)。按 source_id 全局去重。

    增量：结果天然日期倒序，`since` 之前的一律丢弃；当整页都早于 since 时停该 t 翻页
    （因为 mintime 实测不生效，只能这样截断）。
    """
    by_t: dict[str, list[str]] = {}
    for cat in categories:
        by_t.setdefault(SOURCES[cat][0], []).append(cat)

    seen: set[str] = set()
    for t, cats in by_t.items():
        page = 1
        while True:
            if not all_pages and max_pages and page > max_pages:
                break
            data = fetch_page(t, page, page_size, policy, fetcher)
            if data is None:
                log(f"[warn] API 取页失败 t={t} p={page}，停止该分类组翻页")
                break
            catmap = (data.get("searchVO") or {}).get("catMap") or {}
            got_any = False
            had_recent = False
            for cat in cats:
                recs = (catmap.get(cat) or {}).get("listVO") or []
                if recs:
                    got_any = True
                for rec in recs:
                    pub = pub_date(rec)
                    if since and pub and pub < since:
                        continue
                    entry = record_to_entry(rec, cat)
                    if entry is None or entry.source_id in seen:
                        continue
                    seen.add(entry.source_id)
                    had_recent = True
                    yield entry, rec
            if not got_any:
                break
            if since and not had_recent:
                break
            page += 1


def _enrich(rec: DetailRecord, api: dict, category: str) -> DetailRecord:
    """把 API 侧元数据并入 metadata（pcode/puborg 比详情页解析更干净、更全）。"""
    govcn = {
        "id": api.get("id"),
        "category": category,
        "pcode": api.get("pcode") or None,
        "puborg": api.get("puborg") or None,
        "childtype": api.get("childtype") or None,
        "index_no": api.get("index") or None,
        "summary": api.get("summary") or None,
    }
    rec.metadata["govcn"] = govcn
    # 详情页 <title> 带 `_国务院文件_中国政府网` 站点装饰，解析器尾饰正则不认「网」结尾
    # 去不净；API 的 title 是干净的官方标题，用它覆盖，解析值留档可追溯。
    api_title = str(api.get("title") or "").strip()
    if api_title:
        if rec.title and rec.title != api_title:
            rec.metadata["title_parsed"] = rec.title
        rec.title = api_title
    # 文号：API 的 pcode 是官方干净值（如「国令第848号」）；解析器从正文抽到的常带换行/
    # 机关前缀（实测「中华人民共和国国务院令\n第848号」）。pcode 非空时以它为准，解析值留档。
    if govcn["pcode"]:
        if rec.metadata.get("doc_number") and rec.metadata["doc_number"] != govcn["pcode"]:
            rec.metadata["doc_number_parsed"] = rec.metadata["doc_number"]
        rec.metadata["doc_number"] = govcn["pcode"]
    if not rec.metadata.get("issuer") and govcn["puborg"]:
        rec.metadata["issuer"] = govcn["puborg"]
    return rec


def crawl(
    *,
    sink,
    bucket: str = "fd-text",
    domain: str = "gov",
    categories: tuple[str, ...] = DEFAULT_CATEGORIES,
    page_size: int = 10,
    max_pages: int = 1,
    max_items: int = 0,
    since: str | None = None,
    all_pages: bool = False,
    policy: FetchPolicy | None = None,
    part_size: int = 200,
    fetcher=None,
    parser=None,
    dry_run: bool = False,
    log=print,
) -> dict:
    """列 API -> 逐条取全文 -> 写 structured 分片。返回统计（含逐条失败原因）。"""
    pol = policy or FetchPolicy()
    stats = {"listed": 0, "fetched": 0, "missing": 0, "unavailable": 0,
             "written": 0, "failures": []}

    entries = list(iter_entries(
        categories, page_size=page_size, max_pages=max_pages, since=since,
        all_pages=all_pages, policy=pol, fetcher=fetcher, log=log,
    ))
    if max_items:
        entries = entries[:max_items]
    stats["listed"] = len(entries)
    log(f"[list] 命中 {len(entries)} 条（categories={','.join(categories)} "
        f"pages={'all' if all_pages else max_pages} since={since or '-'}）")

    if dry_run:
        return stats

    rows: list[DetailRecord] = []
    for entry, api in entries:
        res = fetch_detail(entry.url, pol, fetcher=fetcher)
        if not res.ok:
            stats["unavailable"] += 1
            reason = res.error or "抓取失败"
            stats["failures"].append({"url": entry.url, "stage": "fetch", "reason": reason})
            log(f"[fail/fetch] {reason} {entry.url}")
            rows.append(DetailRecord(
                domain=domain, source=entry.source, source_id=entry.source_id,
                url=entry.url, title=entry.title, published=entry.published,
                doc_date=None, content="",
                metadata={"status": "unavailable", "error": reason, "section": entry.section,
                          "category": entry.section, "govcn": {"id": api.get("id")}},
            ))
            continue

        try:
            rec = build_record(entry, res.body, parser=parser)
        except Exception as exc:  # 解析异常如实计入
            stats["missing"] += 1
            reason = f"{type(exc).__name__}: {exc}"
            stats["failures"].append({"url": entry.url, "stage": "parse", "reason": reason})
            log(f"[fail/parse] {reason} {entry.url}")
            rows.append(DetailRecord(
                domain=domain, source=entry.source, source_id=entry.source_id,
                url=entry.url, title=entry.title, published=entry.published,
                doc_date=None, content="",
                metadata={"status": "missing", "error": reason, "category": entry.section,
                          "govcn": {"id": api.get("id")}},
            ))
            continue

        if not rec.content.strip() or looks_binary(rec.content):
            stats["missing"] += 1
            reason = "正文为空或二进制" if not rec.content.strip() else "PDF/二进制正文"
            stats["failures"].append({"url": entry.url, "stage": "empty", "reason": reason})
            log(f"[fail/empty] {reason} {entry.url}")
            _enrich(rec, api, entry.section)
            rec.content = ""
            rec.metadata["status"] = "missing"
            rows.append(rec)
            continue

        stats["fetched"] += 1
        _enrich(rec, api, entry.section)
        rec.metadata["status"] = "ok"
        rec.metadata["content_sha256"] = hashlib.sha256(rec.content.encode("utf-8")).hexdigest()
        rows.append(rec)

    # 落盘：structured 分片（键布局与引擎摄取契约一致）+ manifest
    run_id = run_id_utc()
    parts = 0
    for i in range(0, len(rows), max(1, part_size)):
        chunk = rows[i : i + part_size]
        key = structured_part_key(run_id, parts + 1, domain)
        body = "\n".join(r.to_jsonl() for r in chunk) + "\n"
        sink.put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"),
                        ContentType="application/x-ndjson")
        parts += 1
        stats["written"] += len(chunk)

    manifest = {
        "domain": domain, "run_id": run_id, "bucket": bucket,
        "source": "govcn", "categories": list(categories),
        "parts": parts, "records": stats["written"],
        "stats": {k: v for k, v in stats.items() if k != "failures"},
        "failures": stats["failures"][:200],
    }
    sink.put_object(Bucket=bucket, Key=manifest_key(run_id, domain),
                    Body=json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8"),
                    ContentType="application/json")
    return stats


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m fd_cn_gov.detail.gov_cn_library",
        description="采集 gov.cn 政策文件库（搜索 API -> 全文 -> structured JSONL）。",
    )
    ap.add_argument("--category", action="append", choices=sorted(SOURCES), default=None,
                    help=f"分类，可重复；默认 {','.join(DEFAULT_CATEGORIES)}")
    ap.add_argument("--page-size", type=int, default=10, help="每页条数（100/120 可用，200 会 302）")
    pg = ap.add_mutually_exclusive_group()
    pg.add_argument("--max-pages", type=int, default=1, help="每个分类组翻页上限（默认 1，保守）")
    pg.add_argument("--all", action="store_true", help="全量翻页（低频按需，谨慎）")
    ap.add_argument("--since", default=None, metavar="YYYY-MM-DD",
                    help="只取该日及之后的文件（按结果日期倒序截断；mintime 实测无效）")
    ap.add_argument("--max-items", type=int, default=0, help="本轮最多取几条详情（0=不限）")
    ap.add_argument("--delay", type=float, default=1.5, help="请求间隔秒（默认 1.5，礼貌限速）")
    ap.add_argument("--proxy", default=None, help="显式代理 URL；默认强制直连（不读环境/系统代理）")
    ap.add_argument("--local-dir", default="output/govcn", help="本地落盘根目录（默认 output/govcn）")
    ap.add_argument("--bucket", default=os.environ.get("FDTEXT_S3_BUCKET", "fd-text").strip(),
                    help="桶名（本地布局 <local-dir>/<bucket>/gov/structured/...，可直接上传）")
    ap.add_argument("--domain", default="gov")
    ap.add_argument("--part-size", type=int, default=200)
    ap.add_argument("--dry-run", action="store_true", help="只列不抓、不落盘")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # 默认强制直连：本机 macOS 系统代理/环境代理会劫持回环与外网请求（已知坑）。
    proxies = {"http": args.proxy or "", "https": args.proxy or ""}
    policy = FetchPolicy(delay=args.delay, proxies=proxies)
    sink = LocalSink(args.local_dir)
    try:
        stats = crawl(
            sink=sink, bucket=args.bucket, domain=args.domain,
            categories=tuple(args.category) if args.category else DEFAULT_CATEGORIES,
            page_size=args.page_size, max_pages=args.max_pages, max_items=args.max_items,
            since=args.since, all_pages=args.all, policy=policy,
            part_size=args.part_size, dry_run=args.dry_run,
            log=lambda m: print(m, file=sys.stderr),
        )
    except Exception as exc:
        from .pipeline import ParserUnavailable

        if isinstance(exc, ParserUnavailable):
            print(f"error: {exc}", file=sys.stderr)
            return 3
        raise
    print(json.dumps({k: v for k, v in stats.items() if k != "failures"}, ensure_ascii=False))
    if stats["failures"]:
        print(f"# 失败 {len(stats['failures'])} 条（前 5）：", file=sys.stderr)
        for f in stats["failures"][:5]:
            print(f"#   [{f['stage']}] {f['reason']} {f['url']}", file=sys.stderr)
    return 0 if not stats["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
