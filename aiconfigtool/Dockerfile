# ============================================================
#  AiConfigTool v2.0 —— 多阶段构建（前端 build → 后端 serve）
#
#    frontend-build  Node 构建 React 产物（tsc 类型检查 + vite build）
#    runtime         Python 3.12 跑 stdlib HTTP 服务，同源托管前端产物
#
#  单容器单端口（8787），不引 nginx：后端自己伺服 frontend/dist，
#  前端 apiClient 用相对路径 /api，同源直连，无需反向代理。
#
#  单独构建：docker build -t aiconfigtool:2.0.0 .
# ============================================================


# ── Stage 1: 前端构建 ────────────────────────────────────────
FROM node:24-alpine AS frontend-build

# 默认走 npmmirror（国内网络）；海外/内网可覆盖：
#   --build-arg NPM_REGISTRY=https://registry.npmjs.org
ARG NPM_REGISTRY=https://registry.npmmirror.com

WORKDIR /build

# 先只拷依赖清单：源码改动时这一层仍命中缓存，不重装 node_modules
COPY frontend/package.json frontend/package-lock.json ./
RUN npm config set registry "${NPM_REGISTRY}" \
 && npm ci --no-audit --no-fund

COPY frontend/ ./

# package.json 的 build = "tsc -b && vite build"，产物落在 /build/dist
RUN npm run build


# ── Stage 2: 运行时（Python 3.12 stdlib，零第三方依赖）────────
FROM python:3.12-slim AS runtime

# ⚠ 目录布局是硬约束，不能随意改：
#   backend/services/install_service.py 用 os.path 向上四级定位 senaite.docker 根：
#     /workspace/aiconfigtool/backend/services/install_service.py  →  _ROOT=/workspace
#   由此推出 output/ 必须在 /workspace/aiconfigtool/output，
#   「直接安装」的目标目录必须在 /workspace/latest/addons/customers。
#   其余模块（audit/log/config 仓库）按 backend/../data 定位，同样依赖此布局。
ARG APP_ROOT=/workspace/aiconfigtool

# 可选功能「直接安装」需要对目标 Senaite 容器执行 docker exec / restart。
# 这里只装 docker CLI（不含 daemon），运行时挂宿主 docker.sock 复用宿主 daemon。
# 不需要该功能（只做摸底 + 生成 + 下载 zip）时可关掉，镜像小 ~50MB：
#   --build-arg WITH_DOCKER_CLI=false
ARG WITH_DOCKER_CLI=true
ARG DOCKER_CLI_VERSION=27.5.1
ARG DOCKER_CLI_BASE_URL=https://mirrors.aliyun.com/docker-ce/linux/static/stable

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai \
    AICONFIG_STATIC_DIR=/workspace/aiconfigtool/frontend/dist

# python:3.12-slim 已自带 tar / ca-certificates / zoneinfo，
# 故全程不需要 apt-get（构建更快，也不依赖 Debian 源可达）。
RUN set -eux; \
    if [ "${WITH_DOCKER_CLI}" = "true" ]; then \
        arch="$(uname -m)"; \
        url="${DOCKER_CLI_BASE_URL}/${arch}/docker-${DOCKER_CLI_VERSION}.tgz"; \
        python -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], '/tmp/docker.tgz')" "$url"; \
        tar -xzf /tmp/docker.tgz -C /tmp docker/docker; \
        install -m 0755 /tmp/docker/docker /usr/local/bin/docker; \
        rm -rf /tmp/docker.tgz /tmp/docker; \
        docker --version; \
    fi; \
    ln -snf "/usr/share/zoneinfo/${TZ}" /etc/localtime; \
    echo "${TZ}" > /etc/timezone

WORKDIR ${APP_ROOT}/backend

COPY backend/   ${APP_ROOT}/backend/
COPY templates/ ${APP_ROOT}/templates/

# 前端产物：由后端 web/server.py 同源托管（AICONFIG_STATIC_DIR）
COPY --from=frontend-build /build/dist ${APP_ROOT}/frontend/dist

# 运行时目录：compose 会用 bind mount 覆盖，这里预建保证不挂卷裸跑也能启动
RUN mkdir -p "${APP_ROOT}/data/logs" \
             "${APP_ROOT}/data/companies" \
             "${APP_ROOT}/data/sites" \
             "${APP_ROOT}/output/projects" \
             "${APP_ROOT}/output/evidence_packs"

EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8787/api/health', timeout=3)" || exit 1

# 容器内必须监听 0.0.0.0，否则宿主访问不到
CMD ["python", "-m", "web.server", "--host", "0.0.0.0", "--port", "8787"]
