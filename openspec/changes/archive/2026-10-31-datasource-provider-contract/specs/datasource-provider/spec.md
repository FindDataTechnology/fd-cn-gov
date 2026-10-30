## ADDED Requirements

### Requirement: Provider run() 对登记命令真实取数

`FDcnGovProvider.run(command, params)` SHALL 对 `SCRIPT_NAMES` 定义的 11 个源
执行真实抓取并返回记录列表；`params` SHALL 只消费 `max_pages`（int，`0`=全量，
与 CLI `--all` 同义；缺省取该脚本的 argparse 默认值）。SHALL NOT 存在任何指向
不存在模块属性的 import（修前实测：`from fd_cn_gov.cli import dispatch` 一调即
`ImportError`）。

#### Scenario: 已登记命令返回记录

- **WHEN** `run("mem_tzgg_archive", {"max_pages": 1})` 被调用（抓取层以假件替换）
- **THEN** 返回该源记录列表，且抓取函数收到 `max_pages=1`
- **AND** 不发生任何 `ImportError`

#### Scenario: 多档节源聚合各档结果

- **WHEN** 对 ARCHIVES 型源（如 `mof_gkml_archive`）调用 `run()`
- **THEN** 逐个 archive 调用抓取函数并按 ARCHIVES 顺序聚合返回

#### Scenario: 未知命令显式拒绝

- **WHEN** `run("does_not_exist", {})` 被调用
- **THEN** 抛出 `NotImplementedError`，消息包含替代入口（CLI `fd-cn-gov crawl`）
- **AND** 抛出的是 `NotImplementedError` 而非 `ImportError`/`AttributeError`

### Requirement: CATALOG functions 与脚本面双向一致

`CATALOG["functions"]` SHALL 由各脚本的 `MANIFEST` 派生（单一事实源）：
其 `command` 集合 SHALL 与 `SCRIPT_NAMES` 逐名相等（既无 phantom 命令、
也无漏登源）；每条的 `columns` SHALL 与对应 `MANIFEST.columns` 同名同型。
SHALL NOT 保留任何手写命令字面量。

#### Scenario: 无 phantom 命令

- **WHEN** 加载 `CATALOG`
- **THEN** 每个 `command` 都有对应脚本模块（修前实测 4 个 phantom：
  `mee_tzgg_archive`/`mohrs_wj_gh`/`ndrc_wj`/`miit_wj`）

#### Scenario: 无漏登源

- **WHEN** 加载 `CATALOG`
- **THEN** 11 个脚本源全部在册（修前实测：11 源中 9 源缺失）

#### Scenario: 列 schema 与 MANIFEST 同源

- **WHEN** 比对某命令的 `columns` 与该脚本 `MANIFEST.columns`
- **THEN** 列名集合与类型逐项一致（派生而非手写）

### Requirement: Provider 契约经协议 schema 校验

`CATALOG` SHALL 能被 `fd-open-data-protocol` 的 `load_catalog` 校验为合法
`DatasourceManifest`；`FDcnGovProvider` SHALL 满足 duck-typed 契约
（`name`/`registry()`/`run()`）。

#### Scenario: CATALOG 过协议校验

- **WHEN** 以 `load_catalog(CATALOG)` 加载
- **THEN** 返回合法 `DatasourceManifest`，functions 数与脚本面一致
