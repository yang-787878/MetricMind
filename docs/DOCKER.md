# Docker 部署

把 MetricMind 打包成两个容器：**web**（Nginx，托管前端静态文件并反代 API）与
**api**（FastAPI + DuckDB/pandas + LangGraph）。浏览器只访问 web 一个端口，前后端同源。

```text
浏览器 ──▶ web:80（Nginx）
             ├─ /            → /usr/share/nginx/html（React 构建产物 + SPA 回退）
             └─ /api/*       → api:8000（FastAPI，SSE 不缓冲）
api ──▶ /app/backend/data（命名卷：SQLite / uploads / exports）
     ──▶ /app/data（只读示例数据，随镜像分发）
```

## 1. 快速开始

前提：Docker Desktop（或 Docker Engine + Compose v2.24+）。

```powershell
# 仓库根目录
Copy-Item .env.example .env        # 可跳过；没有 .env 就是 Demo 模式
docker compose up -d --build
```

打开 **http://localhost:8080**。首次构建要下载 Python/Node 依赖，通常 3–8 分钟；之后改代码重建有层缓存。

常用命令：

| 目的 | 命令 |
|---|---|
| 启动 / 重建 | `docker compose up -d --build` |
| 看状态与健康检查 | `docker compose ps` |
| 跟随日志 | `docker compose logs -f` |
| 只重启 api | `docker compose restart api` |
| 停止（保留数据） | `docker compose down` |
| 停止并清空数据集/报告 | `docker compose down -v` |
| 进容器排查 | `docker compose exec api sh` |
| 在容器里跑后端测试 | `docker compose run --rm --no-deps -e DATA_DIR=/tmp/mmtest/data -e DB_PATH=/tmp/mmtest/data/metricmind.db api python -m pytest -q` |

> 跑测试时务必像上面那样把 `DATA_DIR` / `DB_PATH` 指到 `/tmp`。compose 会挂载持久化卷，
> 而测试夹具在没有环境变量覆盖时会写 `backend/data`，直接跑会把测试数据灌进你的正式数据卷。

## 2. 端口与访问地址

| 地址 | 说明 |
|---|---|
| http://localhost:8080 | 应用入口（前端 + `/api`） |
| http://127.0.0.1:18000/api/health | 后端健康检查（直连，仅供本机调试） |
| http://127.0.0.1:18000/docs | OpenAPI 文档（直连） |

两个端口都可用环境变量改，不必改文件：

```powershell
$env:WEB_PORT=9090; $env:API_PORT=19000; docker compose up -d
# → http://localhost:9090，直连 API 在 127.0.0.1:19000
```

api 的宿主机端口默认是 **18000**，刻意避开 `scripts/dev.cmd` 用的 8000。两个端口默认都只绑
`127.0.0.1`，因此只有本机能访问；要从手机或另一台机器打开前端，显式放开：

```powershell
$env:WEB_BIND='0.0.0.0'; docker compose up -d   # 注意：无鉴权，仅限可信局域网
```

> 应用没有登录鉴权：两个端口默认只绑回环地址。确实要暴露给其他机器时，更稳妥的做法是
> 在前面加一层带认证与 TLS 的反向代理，而不是直接把 8080 开到公网。

## 3. 配置（`.env`）

compose 会把仓库根的 `.env` 注入 api 容器（`env_file`，`required: false`），因此：

- **不填 Key** → `LLM_MODE=auto` 自动落到 Demo 模式，所有工具真实执行，无模型调用；
- **填了 `OPENAI_API_KEY`** → 自动进入 Live 模式（任意 OpenAI 兼容服务，见 `.env.example`）。

修改 `.env` 后**必须重建容器**才会生效——`env_file` 只在创建容器时读取，`restart` 不会重读：

```powershell
docker compose up -d --force-recreate api
```

容器内的路径规则与本地一致：`.env` 里的 `DATA_DIR` / `DB_PATH` 应写**仓库根相对路径**
（默认 `backend/data`），容器里会被解析到 `/app/backend/data`；写 Windows 绝对路径会失败。

`.env` 被 `.dockerignore` 排除，**不会**进入镜像层。同样地，`backend/.env` 也不会进镜像——
容器里只认 compose 注入的根 `.env`，所以本地放在 `backend/.env` 的配置需要挪到根 `.env` 才生效。

## 4. 数据持久化

`metricmind_data` 命名卷挂到 `/app/backend/data`，保存：

- 上传的数据集文件与解析结果；
- SQLite（`metricmind.db`）里的 datasets / runs / events / results / artifacts；
- 导出的 HTML / Markdown 报告。

重建镜像、`docker compose down` 都不会丢数据；只有 `down -v` 或 `docker volume rm metricmind_data` 会清空。
示例数据（`data/sample_*.csv`）是只读的，随镜像分发，不在卷里。

备份：

```powershell
docker run --rm -v metricmind_data:/data -v ${PWD}:/backup alpine `
  tar czf /backup/metricmind-data.tgz -C /data .
```

## 5. 镜像说明

| 项 | 实现 |
|---|---|
| backend | `python:3.12-slim-bookworm`，先装 `requirements.txt` 再拷代码（依赖层可缓存），非 root（UID 10001） |
| frontend | 多阶段：`node:24-alpine` + pnpm 11 装依赖并 `vite build`，`nginx:1.27-alpine` 托管产物 |
| 健康检查 | api 请求 `/api/health`（用 Python urllib，不额外装 curl）；web 请求 `/healthz` |
| 启动顺序 | `web` 等 api 健康后再启动 |
| 构建上下文 | 两个镜像都用仓库根，`.dockerignore` 排除 `node_modules`、`.venv`、`backend/data`、`.env`、`.tmp` 等 |

> 依赖版本：`backend/requirements.txt` 给的是区间（与本地开发一致），所以镜像解析到的补丁版本可能随上游更新；
> 需要「半年后重建仍然一模一样」时应加 `constraints.txt` 锁定版本。前端有 `pnpm-lock.yaml` + `--frozen-lockfile`，本身是确定的。

### 为什么只有一个 uvicorn worker

事件总线、运行队列信号量（`MAX_CONCURRENT_RUNS`）、取消标志都在**进程内**，SQLite 也以单进程写入为假设。
多 worker 会导致：SSE 连到没产事件的 worker、并发上限按 worker 数翻倍、限流各自计数。
需要横向扩展时应先把 EventBus 换成 Redis/Postgres 通知、运行状态外置，而不是简单调大 `--workers`。

### SSE 为什么必须关缓冲

Nginx 默认会把上游响应缓冲后整块发出。`/api/runs/{id}/stream` 是长连接事件流，
`deploy/nginx.conf` 里对 `/api/` 设置了 `proxy_buffering off`、`proxy_read_timeout 3600s`，
否则工作区会「运行结束后一次性刷出所有事件」。验证：

```powershell
curl.exe -N http://localhost:8080/api/runs/<run_id>/stream?after_seq=0
```

## 6. 冒烟验证

```powershell
# 1) 健康检查
curl.exe -s http://localhost:8080/api/health

# 2) 前端入口（应返回 index.html）
curl.exe -s -o NUL -w "%{http_code}`n" http://localhost:8080/

# 3) 深链接回退（SPA）
curl.exe -s -o NUL -w "%{http_code}`n" http://localhost:8080/workspace

# 4) 载入示例数据 → 发起 Demo 运行 → 取报告
curl.exe -s -X POST http://localhost:8080/api/datasets/samples/sales
# 用返回的 dataset_id：
curl.exe -s -X POST http://localhost:8080/api/runs -H "Content-Type: application/json" `
  -d "{\"dataset_id\":\"ds_xxx\",\"question\":\"为什么 2025 年 9 月销售额相比 6-8 月下降了？\",\"mode\":\"demo\"}"

# 5) 报告与导出
curl.exe -s http://localhost:8080/api/runs/<run_id>/report
curl.exe -OJ "http://localhost:8080/api/runs/<run_id>/export?format=html"
```

## 7. 故障排查

| 现象 | 原因 / 处理 |
|---|---|
| `bind: address already in use` | 8080 被占就 `$env:WEB_PORT=9090; docker compose up -d`；18000 被占则设 `API_PORT`。默认端口已避开本地 dev 的 8000/5173 |
| web 容器一直 `unhealthy` | 看 `docker compose logs web`；确认构建时 `dist/` 有产物，Nginx 配置通过 `docker compose exec web nginx -t` |
| 页面能开、接口 502 | api 还没健康或启动失败：`docker compose logs api`；常见是 `.env` 里路径/Key 写错导致启动自检失败 |
| 改了 `.env` 不生效 | 见第 3 节，需要 `up -d --force-recreate api` |
| 工作区事件一次性刷出 | 反向代理缓冲被打开，检查 `deploy/nginx.conf` 的 `proxy_buffering off` |
| `permission denied` 写数据 | 数据卷属主是 UID 10001；不要用 root 往里写文件。必要时 `docker compose down -v` 重建卷 |
| 拉取基础镜像超时 | 配置 Docker Desktop 的 registry mirror / 代理，或预先 `docker pull python:3.12-slim-bookworm nginx:1.27-alpine node:24-alpine` |
| 上传大文件 413 | Nginx `client_max_body_size 32m` 与后端 `MAX_UPLOAD_MB=25` 是两道限制，按需同时调整 |

## 8. 这只是「可运行」而不是「可公开运营」

镜像解决的是环境一致性，不解决产品化问题。真正对外部署前至少还需要：

- 认证与租户隔离（当前 API 无鉴权，按 IP 限流 6 次/分钟）；
- HTTPS（在 web 前加一层 TLS 终止，或给 Nginx 配证书）；
- SQLite → Postgres、进程内 EventBus → 外部消息/通知机制，才谈得上多副本；
- 资源限制与可观测性：`docker compose` 里的 `deploy.resources`、集中日志、指标；
- 运行容器的用户、只读根文件系统、镜像漏洞扫描（当前已是非 root，但 Nginx 容器仍是默认配置）。
