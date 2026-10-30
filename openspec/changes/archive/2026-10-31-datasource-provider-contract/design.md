# Design: datasource-provider-contract

## D1 为什么不是 `cli.dispatch`

handoff 文档已给判词：CLI 的公共面是 argparse（`main`/`build_parser`/四个
`_cmd_*`），没有「命令名 + 参数字典」这个入口；为一行悬空 import 而发明
`cli.dispatch` 会凭空造出第二套命令语义。正确形态 = 照 `fd-industry-data`
的 `provider.py:21` 显式 `if/elif` 分派 + 末尾 `NotImplementedError`。

## D2 四种调用形状（11 源实测归纳）

| 形状 | 脚本 | 调用 |
|---|---|---|
| A. 多档节（ARCHIVES 元组表） | mee_gsgg / mnr_tzgg / mof_gkml / mohurd_xinwen / mot_shuju / ndrc_tzgg / safe_whxw | 逐 `(section, subsection, url)` 调 `crawl_archive(section, subsection, url, max_pages)` |
| B. 单档节 | mem_tzgg / pbc_xinwen | `crawl(max_pages)` |
| C. 全落地单次 | mofcom_xwfb | `crawl()`（无分页参数） |
| D. 分类遍历 | moa_govpublic | `list_categories()` → 逐 `crawl_category(nid, label)` |

派发按其形状传参；`params` 只认 `max_pages`（缺省取该脚本 argparse 默认值，
`0`=全量——与 CLI `--all` 同义）。形状差异封装在派发内部，对调用方是同一个
`run(command, params)` 面。

## D3 CATALOG 从 MANIFEST 派生（单一事实源）

`registry.db` 的生成链已是「MANIFEST → build_registry → registry.db」，
CATALOG 却仍是手写字面量——两套事实源必然漂移（实测：4 phantom + 9 缺失）。
改为导入时派生：

- `functions[i].command` = 脚本名；`description` = `MANIFEST.description`；
  `columns` = `MANIFEST.columns`（name/type/description 三键透传）；
- phantom 命令（`mee_tzgg_archive`/`mohrs_wj_gh`/`ndrc_wj`/`miit_wj`）随
  手写块的删除自然消失；
- 两条 taxonomy 概念（`taxonomy_code`/`document_type_codes`）指向任何
  MANIFEST 都不存在的列——删（保留的 concepts 全部指向真实列）；
- envelope 其他键（`ranking_seed`/`scanner_mode`/`concepts`/`entities`/
  `fetch.runner`）保持不动——它们是声明面不是清单面。

**代价（如实记录）**：`fd_cn_gov.catalog` 导入时会连带导入 11 个脚本模块
（链式 import `scrapling`）。选此形态而非惰性派生的理由：①协议的
`load_catalog` 本来就是「导入即读 CATALOG」；②`pyproject.toml` 已把
`scrapling[fetchers]` 声明为运行依赖，正规安装必在场；③换成惰性函数会
偏离 `CATALOG` dict 契约（entry point `fd_cn_gov.catalog:CATALOG` 是
模块属性不是调用）。

## D4 已知遗留（不在本 change）

`fd-cn-report/catalog.py:201` 同型悬空（`from cnreport_tools import dispatch`）
——**另一条线，另仓另 change**。本仓测试不加跨仓耦合断言。

## D5 验收

- 目录 ↔ 脚本双向一致：`{f["command"]} == set(SCRIPT_NAMES)`（正向断言防
  phantom 复活、反向断言防漏登）；
- `run()` 未知命令抛 `NotImplementedError` 且消息含替代入口（CLI 提示）；
- 派遣形状：以假件替换 `crawl_archive`/`crawl`/`crawl_category`，断言参数
  透传与聚合顺序（零网络零真实抓取）。
