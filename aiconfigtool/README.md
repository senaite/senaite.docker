# AiConfigTool v2.0

> Senaite 实验室 LIMS 系统的 AI 辅助配置工具。
> 自然语言描述变更需求 → 自动生成 Senaite Addon 包（源码 + 文档 + 部署指南）→ 实施人员部署。

本目录为重构后的 AiConfigTool 工具本体，与 `../latest/`（Senaite Docker 环境）平级。

---

## 启动

### 方式一：Docker Compose（推荐）

```bash
cd aiconfigtool
docker compose up -d --build
```

打开 http://localhost:8787 —— **单容器单端口**：后端同源托管前端构建产物，
不引 nginx，也不需要反向代理（前端 `apiClient` 本来就用相对路径 `/api`）。

| 命令 | 作用 |
|------|------|
| `docker compose logs -f` | 跟踪日志 |
| `docker compose restart` | 改完 `templates/` 后重启生效 |
| `docker compose up -d --build` | 改完前端/后端代码后重新构建 |
| `docker compose down` | 停止 |

镜像分两段构建：`node:24-alpine` 跑 `tsc -b && vite build`，产物拷进
`python:3.12-slim` 由 `web/server.py` 托管。后端零第三方依赖，运行时镜像里没有
Node、没有 pip 包。

宿主机挂载 `data/`（运行数据）、`output/`（生成产物）、`templates/`（模板，可直接改），
容器重建不丢。

可选环境变量（都有默认值，不建 `.env` 也能直接跑）：

| 变量 | 默认值 | 作用 |
|------|--------|------|
| `APP_PORT` | `8787` | 对外端口 |
| `NPM_REGISTRY` | npmmirror | 前端依赖源，海外/内网可改 |
| `WITH_DOCKER_CLI` | `true` | 不用「直接安装」设 `false`，镜像小 ~50MB |
| `SENAITE_ADDONS_DIR` | `./data/senaite-addons` | 「直接安装」写入的宿主目录，见下文 |

#### 连远程 Senaite：开箱可用

本服务不依赖任何本地 Senaite 环境即可启动。站点是运行时配置的数据，
在界面上填远程地址（如 `http://121.40.188.203/Maitux`）直接就能摸底、生成、下载。

#### 连本机 Senaite：接入同一 Docker 网络

容器里的 `127.0.0.1` / `localhost` 指容器自己，不是宿主机。本机 Senaite 用
Docker 跑、80/443 由其 nginx 容器发布时，**`host.docker.internal` 走不通**，
实测结果：

| 容器内访问 | 结果 |
|---|---|
| `host.docker.internal:80`（Senaite） | 502，Senaite nginx 的 access.log 里查不到该请求 |
| `host.docker.internal:443`（Senaite） | TLS EOF（握手被重置） |
| 同网络容器名 `maitux-lims-nginx` | **200** ✅ |
| 远程站点 `121.40.188.203` | 200 ✅ |

80 拿到的 502 没有 `Server` 头、响应体为空、固定延迟 ~10.7s，是 Docker Desktop
端口转发器合成的——请求从未到达 Senaite。所以要用容器名：

```bash
cp docker-compose.override.yml.example docker-compose.override.yml
# 按文件内注释改 network name，然后
docker compose up -d
```

compose 会自动合并 `docker-compose.override.yml`，**基础 `docker-compose.yml`
保持零外部依赖**——不需要连本机 Senaite 时删掉该文件即可回到无依赖状态
（该文件已 gitignore，不会影响其他机器）。

然后把 `data/sites/*/config.json` 里本机站点的地址改成容器名：

```
https://localhost/lims   →   https://maitux-lims-nginx/lims      （url）
https://localhost        →   https://maitux-lims-nginx           （connection.baseUrl）
```

> `extra_hosts` 里的 `host.docker.internal` 仍然保留：访问**宿主上的原生进程**
> （如本机直接跑的 Ollama）是可用的，实测走宿主原生端口能通、0.0s 返回。
> 失效只发生在目标是「另一个容器发布的端口」这种回环场景。

#### 「直接安装」的额外前提

这是唯一强依赖本机 Senaite 的功能：`install_service.py` 把生成的源码写进
`<root>/latest/addons/customers`，再对目标容器 `docker exec` 跑 buildout。
用它需要三件事：

1. `.env` 里把 `SENAITE_ADDONS_DIR` 指到你真正在跑的那套 Senaite 挂给 instance 的
   `./addons/customers`（不设则挂到项目下的占位空目录，装了不生效）；
2. 保留 compose 里的 `/var/run/docker.sock` 挂载（容器内只有 docker CLI，复用宿主 daemon）；
3. 目标站点的 `connection.containerName` 显式填 Zope 实例的容器名（如 `maitux-lims`）。
   不填会走端口自动探测，而 Senaite 常把 80/443 发布在 nginx 容器上，探测会命中
   nginx 而不是 Zope，buildout 必然失败。

只做摸底 + 生成 + 下载 zip 的话，这三条都不用管，还可以
`WITH_DOCKER_CLI=false` 让镜像小 ~50MB。

### 方式二：本地直跑（开发调试）

```bash
# 后端（零依赖，Python 3.12）
cd aiconfigtool/backend
py -m web.server --host 127.0.0.1 --port 8787

# 前端（新终端）
cd aiconfigtool/frontend
npm install
npm run dev
```

打开 http://localhost:5173，vite 自动代理 `/api` 到后端 8787。
此方式下站点地址用 `127.0.0.1` / `localhost` 即可，无需改动。

> 后端的静态托管只在 `frontend/dist` 存在时生效，不影响 vite dev 流程。
> 跑过 `npm run build` 后，也可以直接访问 8787 预览生产产物。

---

## 目录结构

```
aiconfigtool/
├── frontend/                     # React + TypeScript 前端
│   └── src/
│       ├── features/             # 按业务领域拆分的 Feature 模块
│       │   ├── workspace/        # 🏠 工作台（公司/站点管理）
│       │   ├── addon-studio/     # 🤖 Addon 工坊（一站式生成）★ 核心
│       │   ├── delivery/         # 📦 交付管理
│       │   ├── permissions/      # 🔐 权限工具
│       │   └── settings/         # ⚙️ 设置
│       ├── core/                 # 跨 Feature 共享（组件/hooks/types/utils）
│       ├── routes/               # 路由配置
│       └── mocks/                # 开发用 Mock 数据
│
├── backend/                      # Python 后端（零第三方运行时依赖）
│   ├── web/                      # HTTP 层（server/router/response）
│   ├── api/                      # 各资源 handler
│   ├── domain/                   # 领域模型层（纯数据 + 基本验证）
│   ├── services/                 # 服务层（业务逻辑编排）
│   ├── engines/                  # 引擎层（核心算法，可替换）
│   │   ├── ai/                   #   AI 引擎（deterministic/ollama/cloud）
│   │   ├── generator/            #   代码生成引擎（field/listing/permission...）
│   │   ├── delivery/             #   交付引擎（package_export/direct_install）
│   │   └── document/             #   文档生成引擎（deploy/readme/checklist）
│   ├── infrastructure/           # 基础设施层（config/audit/log/runner）
│   ├── schemas/                  # JSON Schema 验证
│   └── shared/                   # 共享工具（errors/result/logger）
│
├── templates/                    # 代码生成与文档模板（非开发人员可改）
│   ├── addon/                    #   Addon 固定骨架模板（.tmpl）
│   └── document/                 #   部署文档模板（.tmpl）
│
├── tests/                        # 测试（unit/integration/e2e）
│
├── output/                       # 生成产物（gitignore，volume 挂载）
│   ├── projects/                 #   生成的 Addon 项目源码
│   └── evidence_packs/           #   证据包
│
├── data/                         # 运行时数据（gitignore，volume 挂载）
│   ├── config.json               #   全局配置
│   ├── audit.db                  #   SQLite 操作记录
│   ├── logs/                     #   JSONL 运行日志
│   ├── companies/                #   公司配置
│   └── sites/                    #   站点配置 + Inventory 快照
│
├── Dockerfile                    # 多阶段构建（前端 build → 后端 serve），单容器
├── docker-compose.yml            # 一键启动（单服务，不依赖本地 Senaite）
├── docker-compose.override.yml.example  # 可选：接入本机 Senaite 的 Docker 网络
├── .dockerignore
├── .gitignore
└── README.md
```

## 分层依赖规则

| 层 | 允许依赖 |
|------|----------|
| `domain/` | 不依赖任何其他模块（纯净领域模型） |
| `engines/` | 仅 `domain/` + `shared/` |
| `services/` | `domain/` + `engines/` + `infrastructure/`（依赖注入） |
| `web` | 仅 `services/`（依赖注入） |
| `shared/` | 被任何模块使用 |

## 设计约束

- **后端零第三方运行时依赖**：仅使用 Python stdlib + `jsonschema`（离线/气隙环境要求）。
- **配置外部化**：所有可配置项存 JSON 文件，不硬编码。
- **命名空间规范**：通用包 `maitux.*`，客户定制包 `{公司简称}.*`。

## 预置 Senaite Addon 说明

工具运行所依赖的预置 Addon（如 `maitux.capabilityinventory` 能力扫描器、
`maitux.permissionsapply` 权限变更目标）位于 `../latest/addons/`，
随 Senaite Docker 环境一起构建，不在本工具源码树内维护。

---

> 详细设计见 `../docs/重构设计/` 下的三份文档：
> `00_项目理解与现状分析.md`、`01_面向用户的重构设计文档.md`、`02_技术设计文档.md`。
