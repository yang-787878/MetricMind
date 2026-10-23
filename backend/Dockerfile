# syntax=docker/dockerfile:1.7
# MetricMind 后端镜像：FastAPI + uvicorn + DuckDB/pandas + LangGraph。
#
# 关键点（不要随意改）：
# 1. 工作目录保持 /app + backend/ 两层，与仓库结构一致。app/config.py 用
#    Path(__file__).parents[2] 定位 ROOT_DIR，扁平化成 /app/app 会让 ROOT_DIR 变成 /，
#    .env 与 data/samples.json 都会找不到。
# 2. 运行期只跑 1 个 uvicorn worker：EventBus、RunManager 信号量、SQLite 都在进程内，
#    多 worker 会让 SSE 事件与并发限制失真。
# 3. 以非 root 用户运行；/app/backend/data 由 compose 的命名卷覆盖，需保持可写。

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /app

# 依赖层单独一层：只改业务代码时不必重装 pandas/duckdb/langgraph。
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# 业务代码与示例数据；.dockerignore 已排除 .venv、backend/data、__pycache__ 等。
COPY backend/ /app/backend/
COPY data/ /app/data/

# 10001 是容器内的固定 UID，便于挂载卷时排查权限问题。
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --no-create-home \
       --shell /usr/sbin/nologin app \
    && mkdir -p /app/backend/data/uploads /app/backend/data/exports \
    && chown -R app:app /app

USER app
WORKDIR /app/backend

EXPOSE 8000

# 不装 curl：直接用解释器请求 /api/health，镜像更小且无额外 CVE 面。
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"]

# --proxy-headers：部署在 nginx 后面时，让 request.client 取 X-Forwarded-For，
# 否则按 IP 的限流会把所有请求算成 nginx 容器的 IP。
CMD ["python", "-m", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
