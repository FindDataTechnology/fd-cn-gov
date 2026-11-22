"""对象存储契约：公文详情产物的键布局（<bucket>/gov/{raw,structured,manifest}/）。

与引擎摄取契约对齐：引擎 `ingest.iter_structured` 读
`<bucket>/<domain>/structured/*.jsonl`，故本模块只负责把 JSONL 写到该前缀，
不定义第二套消费协议。

键布局照 `fd-law-data/lib/legal-sources/storage.js` 的成熟形态（该仓已在产）：
  · structured 分片键含 run id（UTC 时间戳 YYYYMMDDHHMMSS）——**分片一旦完整即不可变**。
    只带日期会让同一天的第二次运行覆盖第一次的分片，而 state 仍声称旧分片已完成，
    造成永久跳过的集合（该仓 ccdi full5 覆盖 full3 的真实事故）。run id 进键位
    使「新运行的分片排序在后」，折叠时天然 latest-wins。
  · state.json 与 manifest 不在 structured 前缀下——覆盖度统计扫该前缀时
    不会把状态文件误当成语料分片。

本文件只依赖标准库：键构造是纯字符串运算，不引 S3 客户端（调用方注入）。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

ROOT = "gov"
_DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def domain_prefix(domain: str = ROOT) -> str:
    if not _DOMAIN_RE.match(domain):
        raise ValueError(f"非法域标识: {domain!r}")
    return domain


def structured_prefix(domain: str = ROOT) -> str:
    return f"{domain_prefix(domain)}/structured/"


def raw_prefix(domain: str = ROOT) -> str:
    return f"{domain_prefix(domain)}/raw/"


def manifest_prefix(domain: str = ROOT) -> str:
    return f"{domain_prefix(domain)}/manifest/"


def state_key(domain: str = ROOT) -> str:
    return f"{domain_prefix(domain)}/state.json"


def structured_part_key(run_id: str, part: int, domain: str = ROOT) -> str:
    """分片键。run_id 必须是 14 位 UTC 时间戳（校验而非假设）。"""
    stamp = str(run_id or "")
    if not re.fullmatch(r"\d{14}", stamp):
        raise ValueError(f"run id 必须是 14 位 UTC 时间戳(YYYYMMDDHHMMSS)，实得: {run_id!r}")
    return f"{structured_prefix(domain)}run-{stamp}-part{int(part):03d}.jsonl"


def manifest_key(run_id: str, domain: str = ROOT) -> str:
    stamp = str(run_id or "")
    if not re.fullmatch(r"\d{14}", stamp):
        raise ValueError(f"run id 必须是 14 位 UTC 时间戳，实得: {run_id!r}")
    return f"{manifest_prefix(domain)}run-{stamp}.manifest.json"


def safe_segment(value: str, *, max_length: int = 180) -> str:
    """让 URL/source_id 进键时不引入斜杠（键是扁平字符串，斜杠会造出假目录）。"""
    from urllib.parse import quote

    text = str(value or "unnamed")
    encoded = quote(text, safe="")
    if len(encoded) > max_length:
        encoded = encoded[:max_length]
    return encoded or "unnamed"


def raw_key(source_id: str, filename: str, domain: str = ROOT) -> str:
    return f"{raw_prefix(domain)}{safe_segment(source_id)}/{safe_segment(filename)}"


def run_id_utc(when: datetime | None = None) -> str:
    return (when or datetime.now(timezone.utc)).strftime("%Y%m%d%H%M%S")


def local_path(root: str, key: str) -> str:
    """对象键 -> 本地路径（兼容本地落盘；键布局与桶内完全同构，可直接上传）。

    键里没有 `..` 段（键由本模块构造），但仍显式拒绝越界，避免调用方传入的
    可控键把写入引到根目录之外。
    """
    from os.path import normpath, join

    path = normpath(join(root, *key.split("/")))
    if not path.startswith(normpath(root)):
        raise ValueError(f"非法对象键（越界）: {key!r}")
    return path


class LocalSink:
    """`s3` 客户端的最小替身：把对象写进本地目录（无对象存储凭据时的降级路径）。

    只实现管线用到的两个方法，签名与 boto3 对齐（Bucket/Key/Body/ContentType）。
    目录布局与桶内**完全同构**（`<root>/<Bucket>/<Key>`），故本地产物可直接
    同步到 `<bucket>/<domain>/structured/` 供引擎摄取，无需任何转换。
    """

    def __init__(self, root: str):
        self.root = root

    def _path(self, bucket: str, key: str) -> str:
        return local_path(self.root, f"{bucket}/{key}")

    def put_object(self, Bucket: str, Key: str, Body: bytes, **_ignored) -> dict:
        from os import makedirs
        from os.path import dirname

        path = self._path(Bucket, Key)
        makedirs(dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(Body)
        return {"ETag": ""}

    def get_object(self, Bucket: str, Key: str) -> dict:
        from io import BytesIO

        with open(self._path(Bucket, Key), "rb") as fh:
            return {"Body": BytesIO(fh.read())}


def root_summary(domain: str = ROOT) -> dict:
    return {
        "root": domain_prefix(domain),
        "state": state_key(domain),
        "structured": structured_prefix(domain),
        "raw": raw_prefix(domain),
        "manifest": manifest_prefix(domain),
    }
