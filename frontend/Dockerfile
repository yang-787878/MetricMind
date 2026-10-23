# syntax=docker/dockerfile:1.7
# MetricMind 前端镜像：Node 里执行 vite build，产物交给 Nginx 静态托管。
#
# 只产出静态文件，不跑 Vite dev server：容器里不需要 HMR，Nginx 同时负责
# SPA 回退与 /api 反向代理，浏览器只面对一个来源，天然没有跨域问题。

FROM node:24-alpine AS build

ENV CI=true \
    PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH

# 版本与 package.json 的 packageManager 保持一致，避免 lockfile 解析差异。
RUN npm install --global pnpm@11.28.5

WORKDIR /app

# 先只拷贝依赖清单：源码改动不会击穿 pnpm install 的缓存层。
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./

# 前端固定走相对路径 /api，由同容器内的 Nginx 转发给 api 服务。
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=${VITE_API_BASE}
RUN pnpm build


FROM nginx:1.27-alpine AS runtime

# 用完整 nginx.conf 替换默认主配置，并去掉自带的 default.conf 站点。
COPY deploy/nginx.conf /etc/nginx/nginx.conf
RUN rm -f /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1
