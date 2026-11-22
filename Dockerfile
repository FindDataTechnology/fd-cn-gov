# fd-cn-gov image — gov.cn 政策库采集（一次性全量 Job / 每日增量 CronJob 共用）。
#
# 发布通道：GitHub Actions -> TCR（.github/workflows/image.yml，公开仓直出）。
#
# 源码直跑（不装 PyPI 版 fd-cn-gov）：gov_cn_library 是本仓新增能力，PyPI 版没有。
# 正文解析复用引擎垂域解析器 fd_text_core.verticals.gov.parser —— 故装 fd-text-core
# （公开仓，从 git 装；本仓公开、无私有依赖）。
#
# 运行形态：
#   全量:  python -m fd_cn_gov.detail.gov_cn_library --all --delay 1.2
#   增量:  python -m fd_cn_gov.detail.gov_cn_library --since <YYYY-MM-DD>
# 产出本地 JSONL（<local-dir>/<bucket>/gov/structured/...），由 Job 再传 S3。
FROM python:3.12-slim

ARG PIP_INDEX_URL=""
ARG FDTEXT_GIT_REF=main

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY . /app/fd-cn-gov

# fd-text-core（正文解析器）：公开仓从 git 装（不 COPY 同级目录 —— 标准 build
# context 不允许 context 外路径）。scrapling 钉 <0.5（0.5 移除 AsyncDynamicSession，
# 本仓 detail/browser 依赖它）；sqlalchemy 是 fd-cn-gov 既有依赖；boto3 供上传 S3。
RUN if [ -n "$PIP_INDEX_URL" ]; then PIPOPT="-i $PIP_INDEX_URL"; else PIPOPT=""; fi \
 && pip install --no-cache-dir $PIPOPT \
      "git+https://github.com/FindDataTechnology/fd-text-core@${FDTEXT_GIT_REF}" \
 && pip install --no-cache-dir $PIPOPT -e /app/fd-cn-gov \
 && pip install --no-cache-dir $PIPOPT 'scrapling[fetchers]>=0.4,<0.5' boto3

RUN useradd -m -u 1000 appuser && chown -R appuser /app
USER appuser

WORKDIR /app/fd-cn-gov
ENTRYPOINT ["python", "-m", "fd_cn_gov.detail.gov_cn_library"]
