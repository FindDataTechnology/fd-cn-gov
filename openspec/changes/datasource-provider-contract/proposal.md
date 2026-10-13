# datasource-provider-contract — provider `run()` 悬空修复 + CATALOG 以 MANIFEST 为唯一事实源

## Why

`gov-documents-vertical` 验收报告 §8.1 记录项（`docs/handoff/fd-cn-gov-dangling-dispatch.md` ④）：
`FDcnGovProvider.run()` 里 `from fd_cn_gov.cli import dispatch`，而 `cli.py` 从未有
`dispatch` 函数——该路径一调即 `ImportError`，`fd-open-data-protocol` 的
`DataProvider.run()` 契约在本源名存实亡（实测复现：`cannot import name 'dispatch'`）。

同一次核验还发现**同文件第二处契约缺陷**：`CATALOG["functions"]` 手写维护、
已与真实脚本面漂移——声明 6 个命令里 4 个（`mee_tzgg_archive` / `mohrs_wj_gh` /
`ndrc_wj` / `miit_wj`）**没有任何脚本实现**（phantom），而真实存在的 11 个源里
9 个不在册。即 `registry()` 与 `run()` 互相矛盾：目录宣传的能力跑不了，
真能跑的能力不在目录里。

根因：`registry.db` 由 `build_registry` 从 11 个脚本的 `MANIFEST` 生成（单一
事实源），而 `CATALOG["functions"]` 是另一份手写字面量——两套事实源必然漂移。
本次把 CATALOG 也改为**从 MANIFEST 派生**，从结构上杜绝再次漂移。

## What Changes

- **`run()` 真派发**（照 `fd-industry-data` 的正确形态，不发明 `cli.dispatch`）：
  按 11 个脚本的四种调用形状显式分派，参数 `max_pages`（0=全量）透传；
  未知命令抛显式 `NotImplementedError`（消息带替代入口），绝不 `ImportError`。
- **CATALOG 从 MANIFEST 派生**：`functions` 列表改为导入时由 11 个 `MANIFEST`
  生成（命令名/描述/列 schema 全部同源）；删掉 4 个 phantom 命令与 2 条指向
  不存在列的 taxonomy 概念的陈旧条目；envelope（concepts/entities/runner）保持。
- **Provider 冒烟测试**（本仓首次 provider 级测试）：目录与脚本面双向一致断言 +
  未知命令抛 `NotImplementedError` + 派遣形状用假件验证（零网络）。

明确不做：
- 不改 11 个脚本与 CLI 的既有行为（纯 provider/CATALOG 面修复）；
- 不为 phantom 命令补实现（证据显示它们从未存在，不是"缺了实现"）；
- 不动 `fd-cn-report`——其同型缺陷在彼仓的 change 里单独修（它是另一条线）。

## Capabilities

### New Capabilities

- `datasource-provider`: fd-cn-gov 作为 `fd-open-data-protocol` DataProvider 的
  可执行契约——`run()` 对登记的 11 源真实取数、对未知命令显式拒绝；
  `registry()` 返回的 CATALOG 与脚本 MANIFEST 集双向一致（单一事实源派生）。

## Impact

- **代码**：`fd_cn_gov/catalog.py`（run() 派发 + functions 派生）、
  新增 `tests/test_provider.py`；不动 `cli.py`、不动 11 个脚本。
- **兼容**：`load_catalog` 路径不变（entry point `fd_cn_gov.catalog:CATALOG` 照旧）；
  `registry()` 消费方（registry.db 读面）不受影响（那是另一份派生件，本就一致）。
  依赖面：catalog 导入将经脚本模块链式导入 `scrapling`——fd-cn-gov 的
  `pyproject.toml` 已声明 `scrapling[fetchers]` 为运行依赖，任何正规安装均在场。
- **无可回滚依赖**：纯代码修复，无迁移、无数据。
