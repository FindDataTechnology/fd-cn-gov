"""`fd_cn_gov.catalog` provider 测试（change datasource-provider-contract）。

覆盖：
- 目录 ↔ 脚本面双向一致（无 phantom 命令、无漏登源）——修前实测：CATALOG
  声明 6 命令中 4 个无脚本实现、11 个真实源中 9 个缺失；
- `run()` 未知命令抛**显式 NotImplementedError**（修前实测：悬空 import
  `from fd_cn_gov.cli import dispatch` 一调即 ImportError）；
- 四种派遣形状（多档节聚合/单档节/单次/分类遍历）以假件验证参数透传与
  聚合行为（零网络零真实抓取）；
- CATALOG 过 fd-open-data-protocol schema 校验、列 schema 与 MANIFEST 同源。

不联网：抓取入口全部以 monkeypatch 替换为记录参数的假件。
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from fd_cn_gov.catalog import (  # noqa: E402
    CATALOG,
    SCRIPT_NAMES,
    FDcnGovProvider,
    _DEFAULT_MAX_PAGES,
    _SHAPES,
)


# ---------- 目录 ↔ 脚本面双向一致 ----------


def test_catalog_functions_match_scripts_both_ways():
    """目录命令集与脚本面逐名相等：既无 phantom 命令、也无漏登源。"""
    catalog_commands = {f["command"] for f in CATALOG["functions"]}
    assert catalog_commands == set(SCRIPT_NAMES)
    assert len(CATALOG["functions"]) == len(SCRIPT_NAMES) == 11


def test_no_phantom_commands_from_handwritten_era():
    """修前的 4 个 phantom 命令不得回归（它们从未有过脚本实现）。"""
    catalog_commands = {f["command"] for f in CATALOG["functions"]}
    for phantom in ("mee_tzgg_archive", "mohrs_wj_gh", "ndrc_wj", "miit_wj"):
        assert phantom not in catalog_commands


def test_function_columns_derive_from_manifest():
    """每条 functions 的列 schema 与对应 MANIFEST 同名同型（派生非手写）。"""
    for entry in CATALOG["functions"]:
        mod = importlib.import_module(f"fd_cn_gov.scripts.{entry['command']}")
        manifest = mod.MANIFEST
        catalog_cols = {(c["name"], c["type"]) for c in entry["columns"]}
        manifest_cols = {(c.name, c.type) for c in manifest.columns}
        assert catalog_cols == manifest_cols, entry["command"]


def test_concepts_reference_real_columns():
    """概念提示只指向真实存在的列（修前两条 taxonomy_* 指向不存在列，已删）。"""
    real_columns = set()
    for entry in CATALOG["functions"]:
        real_columns.update(c["name"] for c in entry["columns"])
    for concept in CATALOG["concepts"]:
        assert concept["column"] in real_columns, concept


def test_shape_and_defaults_cover_exactly_script_names():
    """派发表的键集与脚本面相等（新增脚本漏登即红）。"""
    assert set(_SHAPES) == set(SCRIPT_NAMES)
    assert set(_DEFAULT_MAX_PAGES) == set(SCRIPT_NAMES)


# ---------- run() 契约 ----------


def test_unknown_command_raises_not_implemented_with_cli_hint():
    """未知命令抛显式 NotImplementedError（不是 ImportError），消息含 CLI 替代入口。"""
    provider = FDcnGovProvider()
    with pytest.raises(NotImplementedError) as excinfo:
        provider.run("does_not_exist", {})
    message = str(excinfo.value)
    assert "does_not_exist" in message
    assert "fd-cn-gov crawl" in message


def test_no_dangling_cli_dispatch_import():
    """cli 模块不得被 catalog 依赖 dispatch 属性（修前的悬空面）。"""
    from fd_cn_gov import cli

    assert not hasattr(cli, "dispatch"), (
        "cli.dispatch 不存在；provider 必须自行显式分派（不得复活悬空 import）"
    )


def test_run_returns_records_and_forwards_max_pages(monkeypatch):
    """形状 B（单档节）：run() 返回记录列表且 max_pages 透传。"""
    mod = importlib.import_module("fd_cn_gov.scripts.mem_tzgg_archive")
    calls: list[dict] = []

    def fake_crawl(max_pages):
        calls.append({"max_pages": max_pages})
        return [{"title": "假件记录", "url": "https://example.invalid/a"}]

    monkeypatch.setattr(mod, "crawl", fake_crawl)
    records = FDcnGovProvider().run("mem_tzgg_archive", {"max_pages": 2})

    assert calls == [{"max_pages": 2}]
    assert [r["title"] for r in records] == ["假件记录"]


def test_run_shape_a_aggregates_archives_in_order(monkeypatch):
    """形状 A（多档节）：按 ARCHIVES 顺序逐档调用并聚合。"""
    mod = importlib.import_module("fd_cn_gov.scripts.mof_gkml_archive")
    calls: list[tuple] = []

    def fake_crawl_archive(section, subsection, base_index, max_pages):
        calls.append((section, subsection, base_index, max_pages))
        return [{"section": section, "subsection": subsection, "url": base_index}]

    monkeypatch.setattr(mod, "crawl_archive", fake_crawl_archive)
    records = FDcnGovProvider().run("mof_gkml_archive", {"max_pages": 3})

    assert calls == [(s, sub, url, 3) for s, sub, url in mod.ARCHIVES]
    assert len(records) == len(mod.ARCHIVES)
    # 聚合顺序 = ARCHIVES 顺序（首末逐字对账）
    assert records[0]["subsection"] == mod.ARCHIVES[0][1]
    assert records[-1]["subsection"] == mod.ARCHIVES[-1][1]


def test_run_shape_c_single_landing(monkeypatch):
    """形状 C（单次落地）：crawl() 无参调用（max_pages 不参与）。"""
    mod = importlib.import_module("fd_cn_gov.scripts.mofcom_xwfb_archive")
    called: list[bool] = []

    def fake_crawl():
        called.append(True)
        return [{"section": "新闻发布", "url": "https://example.invalid/x"}]

    monkeypatch.setattr(mod, "crawl", fake_crawl)
    records = FDcnGovProvider().run("mofcom_xwfb_archive", {"max_pages": 9})

    assert called == [True]
    assert len(records) == 1


def test_run_shape_d_category_walk(monkeypatch):
    """形状 D（分类遍历）：list_categories() → 逐类 crawl_category(nid, label)。"""
    mod = importlib.import_module("fd_cn_gov.scripts.moa_govpublic_archive")
    calls: list[tuple] = []

    monkeypatch.setattr(mod, "list_categories", lambda: [("001", "办公厅"), ("002", "种植业司")])

    def fake_crawl_category(nid, label):
        calls.append((nid, label))
        return [{"department": label, "department_id": nid}]

    monkeypatch.setattr(mod, "crawl_category", fake_crawl_category)
    records = FDcnGovProvider().run("moa_govpublic_archive", {})

    assert calls == [("001", "办公厅"), ("002", "种植业司")]
    assert [r["department"] for r in records] == ["办公厅", "种植业司"]


def test_run_uses_script_default_when_max_pages_omitted(monkeypatch):
    """缺省 max_pages 取脚本默认值（与 CLI argparse 默认同源）。"""
    mod = importlib.import_module("fd_cn_gov.scripts.mot_shuju_archive")
    seen: list[int] = []

    def fake_crawl_archive(section, subsection, base_index, max_pages):
        seen.append(max_pages)
        return []

    monkeypatch.setattr(mod, "crawl_archive", fake_crawl_archive)
    FDcnGovProvider().run("mot_shuju_archive", {})

    assert seen and all(p == _DEFAULT_MAX_PAGES["mot_shuju_archive"] for p in seen)


# ---------- 协议 schema ----------


def test_catalog_validates_against_protocol_schema():
    """CATALOG 可被 fd-open-data-protocol load_catalog 校验；functions=11。"""
    protocol_root = REPO.parent / "fd-open-data-protocol"
    if not protocol_root.exists():
        pytest.skip("fd-open-data-protocol 不在同级（monorepo 外安装形态）")
    sys.path.insert(0, str(protocol_root))
    from fd_open_data_protocol.loader import load_catalog

    manifest = load_catalog(CATALOG)
    assert len(manifest.functions) == len(SCRIPT_NAMES)
