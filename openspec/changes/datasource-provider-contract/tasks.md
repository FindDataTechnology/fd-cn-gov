## 1. Provider run() 真派发（catalog.py）

- [x] 1.1 删掉 `from fd_cn_gov.cli import dispatch` 悬空 import；写显式分派：
  按四种形状（D2）调 `crawl_archive`/`crawl`/`crawl_category`；`max_pages`
  从 params 取（缺省=脚本默认值，0=全量）；未知命令抛 `NotImplementedError`
  （消息含 CLI 替代入口）
- [x] 1.2 零网络冒烟：`run("mem_tzgg_archive", {"max_pages": 1})` 不再
  ImportError（抓取层以假件替换，断言参数透传）；未知命令抛 NotImplementedError

## 2. CATALOG 从 MANIFEST 派生（catalog.py）

- [x] 2.1 `functions` 改由 11 个脚本 MANIFEST 生成（command/description/
  columns 三键派生）；删掉 4 个 phantom 命令手写块
- [x] 2.2 concepts 清理：删两条指向不存在列的 taxonomy 概念；保留其余（全指向真实列）
- [x] 2.3 双向一致断言落地测试（目录 ↔ SCRIPT_NAMES 逐名相等 + 列 schema 同源）
- [x] 2.4 `load_catalog(CATALOG)` 过协议 schema 校验（functions=11）

## 3. 测试（新增 tests/test_provider.py）

- [x] 3.1 目录 ↔ 脚本面双向一致（无 phantom、无漏登）
- [x] 3.2 未知命令抛 NotImplementedError 且消息含替代入口
- [x] 3.3 四种派遣形状假件验证（多档节聚合/单档节/单次/分类遍历，零网络）
- [x] 3.4 `pytest tests/ -q` 全绿（含既有 test_detail.py 零回归）

## 4. 提交

- [x] 4.1 提交推送（gitee + github）；commit message 标注
  handoff ④ + CATALOG 漂移两处
