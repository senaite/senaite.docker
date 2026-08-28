# labgate —— 实验室仪器采集网关

连接实验室本地仪器（天平 / 串口服务器等），解析读数，**先在本地落盘**，
再通过 **NATS LeafNode** 同步到云端；云端的 `labbridge` 跟着 LIMS 的采集会话
把读数投递给 SENAITE。断网时数据留在本地，网络恢复后自动续传。

Go 单二进制，Windows 双击即可运行，也可以用 Docker 作为边缘节点部署。
这是 `instrument-agent`（Python 版）的重写，本机管理接口保持兼容。

两个可部署程序：

| 程序 | 跑在哪 | 干什么 |
|---|---|---|
| `labgate` | 实验室本地 | 连仪器、解析读数、落盘、经 LeafNode 上云 |
| `labbridge` | 云端 | 跟着 LIMS 会话把读数投递给 SENAITE |

另有两个联调用的替身：`fakebalance`（模拟天平）、`fakelims`（模拟 SENAITE 插件）。

---

## 为什么这么设计

旧版把"缓存 + 重试 + 去重"写在采集端自己的 SQLite 队列里。这类代码最容易在
断网、重启、并发这些边角情况上出问题，而且每加一个下游就要重写一遍。

labgate 把这件事交给 NATS JetStream：

```
实验室                                     云端
─────────────────────────────────         ──────────────────────────────

仪器 ──TCP──► labgate
                 │ ① 解析
                 │ ② 写内嵌 NATS 的 JetStream（拿到 PubAck 才算收下）
                 ▼
        ┌────────────────┐
        │ 本地 READINGS  │  断网期间堆在这里，重启不丢
        └───────┬────────┘
                │ cloud-forward（durable consumer）
                └──── LeafNode（只出站）────►  云端 NATS
                                                  │ LAB_READINGS
                                                  ▼
                                              labbridge
                                                  │ 跟着 LIMS 的采集会话
                                                  ▼ HTTP
                                          SENAITE ingest 接口
```

这样带来几个直接的好处：

- **不丢数据**：TCP 收到一行就同步落盘，拿到 JetStream 的确认才算收下。
- **断网续传**：转发失败就 nak 重投，消息留在本地流里；云端恢复后自动补齐，
  不需要人工干预（见下方"断网演练"）。
- **幂等**：每条读数带 `event_id`，作为 NATS 的 `Nats-Msg-Id`，
  云端在去重窗口内自动丢弃重复投递。
- **多出口互不影响**：NATS 上云和 HTTP 直推 SENAITE 各有各的消费进度，
  一个卡住不会拖住另一个。
- **磁盘有上限**：本地流按 `max_age_hours` / `max_bytes_mb` 滚动淘汰，不会写满磁盘。

内嵌的 NATS **默认不监听任何端口**，采集端以进程内方式连接自己的 NATS
（Windows 下不会弹防火墙）。需要用 `nats` CLI 观察时再在配置里打开 `nats.listen`。

---

## 快速开始

> 现场部署（实施人员照着做，不需要源码、不需要编译）见 **[部署说明.md](部署说明.md)**。
> 下面是开发机上的用法。

### 一、Docker（含一整套可跑通的演示件）

```bash
docker compose up -d --build
```

起来的是完整一条链路：模拟天平 → 采集网关 → 云端 NATS → 桥接 → 替身 LIMS。

| 地址 | 内容 |
|---|---|
| <http://localhost:8090> | 采集网关界面（采集 / 状态 / 调试 / 配置 / 日志） |
| <http://localhost:8080> | 替身 LIMS，在这里点「开始采集」 |
| <http://localhost:8091/api/status> | 桥接层状态（每台仪器投了多少、还欠多少） |
| <http://localhost:8222/jsz?streams=1> | 云端 JetStream |

**试一下"先称量、后开始采集"**：

1. 网关界面「采集」页填 `fake-balance` / `9000`，点「开始采集」——读数开始流。
2. 先**别**在替身 LIMS 上点开始采集。等一两分钟，读数会堆在云端 NATS 里，
   替身 LIMS 那边一条都收不到（注意"因无会话被拒"始终是 0，桥接层根本没去敲它）。
3. 在替身 LIMS 点「开始采集」——刚才那一两分钟的读数会一次性补进来。

接真实环境时：删掉 `fake-balance` / `fake-lims` / `nats-hub` 三个服务，
把 `LABGATE_LEAF_URL` 指向云端 NATS、`LABBRIDGE_LIMS_URL` 指向真的 SENAITE。

### 二、Windows 本机

```powershell
# 本机不用装 Go，用 Docker 交叉编译出 exe
.\build.ps1 -Version 1.0.0
```

产物在 `dist\labgate-windows-amd64.exe`。把它和 `config.json` 放在同一个目录：

```powershell
.\labgate-windows-amd64.exe                      # 前台运行，Ctrl+C 退出
.\labgate-windows-amd64.exe --install-service    # 注册为开机自启的服务（需管理员）
.\labgate-windows-amd64.exe --uninstall-service  # 卸载服务
```

服务会自动开机启动，崩溃后自动重启（10s / 30s / 60s 三级退避），
在「服务」管理器里能看到 **labgate 仪器采集网关**。

### 三、Linux

```bash
./build.sh                       # 有 Go 用 Go，没有就自动走 Docker
sudo cp dist/labgate-linux-amd64 /usr/local/bin/labgate
sudo cp deploy/labgate.service /etc/systemd/system/
sudo systemctl enable --now labgate
```

### 多台仪器 / 多个实例

一个 labgate 实例可以同时连接多台仪器（每台一个独立连接与状态）。
确实需要跑多个实例时，各自指定端口与数据目录：

```bash
labgate --config balance1.json --port 8090 --data-dir data1
labgate --config balance2.json --port 8091 --data-dir data2
```

---

## 配置

配置文件默认是运行目录下的 `config.json`，不存在时会自动生成一份默认配置；
界面「配置」页改动会即时写回文件。完整字段见 [`config.example.json`](config.example.json)。

最少要关心的几项：

| 配置项 | 说明 |
|---|---|
| `agent.site_id` | 站点标识，云端用它区分实验室，会进 NATS 主题 |
| `agent.mode` | `manual` 界面控制 / `auto` 跟随云 LIMS |
| `agent.api_token` | 管理接口鉴权令牌（可选，建议设置），见下方「接口鉴权」 |
| `instruments[]` | 本地仪器清单 `{code, host, port, enabled}`；由 LIMS 下发时可留空 |
| `nats.leaf.url` | 云端 NATS 的 LeafNode 地址，如 `nats-leaf://user:pass@host:7422` |
| `nats.max_age_hours` / `max_bytes_mb` | 本地缓冲保留多久 / 最多占多少磁盘（默认 14 天 / 1 GB） |
| `cloud.lims_url` / `cloud.token` | SENAITE 地址与 Token，**第一阶段可以不填** |

改 `nats.*` 需要重启才生效（界面保存后会提示），其余改完立即生效。

### 环境变量（Docker 用）

首次启动时用环境变量生成 `config.json`，省去手工编辑：

`LABGATE_PORT`、`LABGATE_MODE`、`LABGATE_SITE_ID`、`LABGATE_API_TOKEN`、
`LABGATE_DATA_DIR`、
`LABGATE_LEAF_URL`、`LABGATE_LEAF_USER`、`LABGATE_LEAF_PASSWORD`、
`LABGATE_LEAF_HUB_DOMAIN`、`LABGATE_LEAF_HUB_STREAM`、
`LABGATE_LIMS_URL`、`LABGATE_LIMS_TOKEN`、`LABGATE_LIMS_PUSH`、`LABGATE_LIMS_POLL`

填了 `LABGATE_LEAF_URL` 就默认启用 LeafNode。

---

## 本机接口

路由与响应结构与旧版 Python 采集端保持一致，云 LIMS 侧已有的调用不用改
（`instrument-acquisition` 插件里的 `agent_api_url` 直接填 `http://<本机>:8090`）。

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/state`（可带 `?code=`） | GET | 运行状态；带 `code` 查单台仪器 |
| `/api/readings?limit=N` | GET | 最近读数 |
| `/api/logs` | GET | 运行日志 |
| `/api/stats` | GET | 统计 + 本地 JetStream 流状态 |
| `/api/config` | GET / POST | 读写配置（POST 为深合并） |
| `/api/token/regenerate` | POST | 重新生成 Token |
| `/api/start` | POST | 开始采集 `{code, host, port, push}` |
| `/api/start_sync` | POST | 同步开始：先探测 TCP，探不通立即返回失败（LIMS 点「开始采集」用） |
| `/api/stop` | POST | 停止 `{code}`；`{"all": true}` 停全部。**空 body 返回 400**（防止误停全部） |
| `/api/tcp_test` | POST | TCP 连通测试 |
| `/api/http_test` | POST | 注入一条读数，走完整链路 |
| `/api/parse_test` | POST | 只看解析结果，不产生数据 |
| `/api/pull_now` | POST | 立即拉一次云 LIMS 配置 |
| `/healthz` | GET | 健康检查（Docker HEALTHCHECK 用） |

新增字段（`site_id`、`cloud`、`version`、读数的 `code`）是追加的，旧调用方会忽略。

> `/api/state` 会被 LIMS 反复轮询，其中的 Token 与 LeafNode 密码已脱敏；
> 配置页读的 `/api/config` 才返回原值。

### 界面登录

`agent.admin_password` 非空时，8090 网页要先登录才能用；账号是
`agent.admin_user`（缺省 `admin`）。Docker 部署从 `.env` 注入：

```dotenv
LABGATE_ADMIN_USER=admin
LABGATE_ADMIN_PASSWORD=改成你的密码
```

- 登录成功种一个签名 Cookie（HMAC，服务端不存会话），有效期 12 小时；
  采集端重启或改了密码，旧会话立即失效，重新登录即可。
- 环境变量每次启动都会覆盖 `config.json`，**改密码要改 `.env` 再重启**，
  在配置页上改会被下次启动覆盖回去。
- 密码留空 = 不启用登录，保持旧部署行为（仅建议内网调试用）。

登录只保护网页与界面接口，云 LIMS 联动的三个接口不受影响 —— LIMS 侧不会登录。

### 接口鉴权

`agent.api_token` 是管理接口的可选鉴权令牌（默认空 = 不鉴权，兼容旧部署），
给的是「非浏览器的调用方」，比如脚本或另一套系统直接调管理接口。
已登录的浏览器会话视同已鉴权，界面自己不用再带令牌。

- **受保护**（要求 `Authorization: Bearer <token>`，或 `X-API-Token` 头）：
  除下面豁免项外的全部接口，包括 `GET /api/readings`、`GET /api/logs`、
  `GET /api/stats`、`GET /api/config` 与所有 POST 管理接口
- **豁免**（云 LIMS 联动接口 + 健康检查，LIMS 侧没有本机令牌）：
  `GET /api/state`、`POST /api/start_sync`、`POST /api/stop`、`GET /healthz`

> `GET /api/readings`、`/api/logs`、`/api/stats`、`/api/config` 以前也在豁免里 ——
> 那时没有登录，不豁免界面就没法用。现在有会话 Cookie 了，它们回到保护之下：
> `/api/config` 会原样返回 `cloud.token`，不该是谁都能读的。

配置页可以设置令牌并「记住到本机」（存浏览器 localStorage，界面请求自动带上）。

---

## 数据格式

发到云端的消息体与旧版推送 SENAITE `@@instrument_acquisition_api_ingest`
的请求体一致，云端可以直接复用：

```json
{
  "event_id": "agent-1f0c…",
  "site_id": "lab-shanghai-1",
  "instrument_code": "balance-01",
  "received_at": "2026-08-28T11:09:45",
  "raw_text": "ST,GS,0.9678,mg",
  "parsed": { "value": "0.9678", "unit": "mg", "stable": true }
}
```

主题：`lab.<site_id>.readings.<instrument_code>`，云端流默认叫 `LAB_READINGS`。
云端消费示例：

```bash
nats --server nats://<hub>:4222 sub 'lab.>'
nats --server nats://<hub>:4222 consumer add LAB_READINGS my-app --pull --ack explicit
```

---

## 运维

### 断网演练

```bash
docker compose stop nats-hub                    # 断开云端
# 界面「状态」页：云端链路显示"断开"，"待上传"开始增长
docker compose start nats-hub                   # 恢复
# 十几秒后"待上传"归零，云端 /jsz 里的条数补齐
```

### 常见排查

| 现象 | 处理 |
|---|---|
| 仪器一直「连接失败」 | 仪器/串口服务器的 TCP 通道没开，或 IP、端口不对；用「调试」页的 TCP 连通测试确认 |
| 收到数据但解析不出值 | 用「调试」页的解析预览看这一行会被解析成什么；原始行始终完整上云，可在云端按模板重解析 |
| 「待上传」一直涨 | 云端连不上；看「状态」页的最近错误，以及云端 `http://<hub>:8222/leafz` |
| 界面打不开 | 检查 8090 端口与防火墙；容器部署看 `docker compose logs labgate` |
| 磁盘占用增长 | 调小 `nats.max_age_hours` / `nats.max_bytes_mb`；「状态」页能看到当前占用 |

### 用 nats CLI 查看本地缓冲

在配置里把 `nats.listen` 设成 `127.0.0.1:4222` 并重启，然后：

```bash
nats --server nats://127.0.0.1:4222 --js-domain edge stream info READINGS
nats --server nats://127.0.0.1:4222 --js-domain edge consumer info READINGS cloud-forward
```

---

## labbridge —— 云端投递给 SENAITE

SENAITE 插件 `maitux.instrument_acquisition` 是个 HTTP 入口，不会从 NATS 取数，
所以云端要有一环把两者接起来。`labbridge` 就是这一环，**addon 一行都不用改**。

它不是"收到就投、投不进就重试"，而是**跟着 LIMS 的采集会话走**：

- 每台仪器一个 durable consumer。某台仪器没有会话，不会占住别人的投递额度。
- 仪器在 LIMS 里有「监听中的会话」（`agent_instruments` 返回 `start: true`）
  才开始投递，并且从**会话开始前 `lookback_minutes`** 那个位置起投。
- 会话关掉就停下来，消费位置留在原地。没有会话的读数原样躺在 JetStream 里，
  既不会灌进 LIMS，也不会丢，到期由流的 `max_age` 自然淘汰。
- 期间**完全不调用** ingest 接口，不会把 SENAITE 的日志刷满。

### 这解决了什么

技术员先在天平上称量、之后才在 LIMS 点「开始采集」——这是真实存在的工作流。
旧架构下这些读数重试 5 次就丢了；现在它们会被补进当前会话。

```bash
# 演示栈里可以直接看到：
docker compose logs -f labbridge
# [balance-01] 会话已开始，从 15m0s 前的读数开始投递
```

### 需要业务上拍板的一个数

`session.lookback_minutes`（默认 15）决定"会话开始前多久的读数还算数"：

| 取值 | 含义 |
|---|---|
| `0` | 不补投，只投会话开始之后的读数（最保守） |
| `15` | 先称量、15 分钟内点开始采集，数据都能归进去 |
| 很大 | 不建议：周一开会话时会把上周末的漂移读数一起灌进 LIMS |

**这个数可能有合规含义**（读数与会话的时间关系会写进 LIMS 记录），
建议按实际工作流和质量体系的要求定，而不是照抄默认值。

### 配置

首次启动生成 `bridge.json`，也可以全用环境变量：

`LABBRIDGE_NATS_URL`、`LABBRIDGE_NATS_USER`、`LABBRIDGE_NATS_PASSWORD`、
`LABBRIDGE_NATS_CREDENTIALS`、`LABBRIDGE_STREAM`、`LABBRIDGE_LIMS_URL`、
`LABBRIDGE_LIMS_TOKEN`、`LABBRIDGE_LOOKBACK_MINUTES`、`LABBRIDGE_POLL_SECONDS`、
`LABBRIDGE_HTTP_LISTEN`

状态接口：`GET /api/status`（每台仪器的会话状态、已投递数、待投递数、最近错误）、
`GET /api/logs`、`GET /healthz`。

### 另一条路：边缘直推（不推荐作为正式路径）

`cloud.lims_push_enabled` 让每个 labgate 直接 HTTP 推 SENAITE。它能用，
但意味着每个实验室都要能访问到 SENAITE——正是 LeafNode 省掉的那件事。
定位是联调和应急兜底。它遇到"无会话"是重投到 `cache.max_retries` 后放弃
（旧采集端行为），**不做补投**；要补投就用 labbridge。

`cloud.poll_enabled` 是另一个可选项：让边缘轮询 LIMS 拿仪器清单与启停指令
（自动模式）。控制面目前仍是 SENAITE 主动 HTTP 调用 labgate，见下。

## 还没做的

- **控制面还是 HTTP 入站**：SENAITE 点「开始采集」是调 `{agent_api_url}/api/start_sync`，
  所以云端仍需能访问到各实验室的 8090。LeafNode 只解决了数据上行。
  把控制面也搬到 NATS request/reply 是自然的下一步，但会改接口。
- **`received_at` 没有时区**：沿用旧格式的本地时间，跨时区部署会有歧义。
- **跨站点同 code 仪器**：NATS 主题 `lab.<site_id>.readings.<code>` 已含站点维度，
  但 HTTP 直推链路按 `instrument_code` 归会话，若同一 LIMS 下两实验室用相同
  仪器 ID 且都直推，会串到同一会话。多站点正式部署建议走 NATS + labbridge。

---

## 更新记录

### 2026-08-28 与真 LIMS 联动修复（诺诚项目联调）

本次改动让 labgate 与真实 SENAITE 插件 `maitux.instrument_acquisition`
（Linux 192.168.1.18）完整联动，并修复联调中发现的问题：

**LIMS 插件侧（`maitux.instrument_acquisition/services/session_store.py`）**

- 「开始采集」通知采集端时携带 `code: instrument_code`（此前只发 host/port，
  labgate 无法反查真实仪器 code，会建一个 code=`instrument` 的错误连接，
  读数推不进 LIMS —— 表现为 `Invalid token`）。
- 「停止采集」通知携带 `{"code": instrument_code}`（此前空 body，labgate
  收到会停掉该站全部仪器 —— 多仪器场景会误停其他仪器）。

**labgate 侧**

| 文件 | 改动 | 解决 |
|---|---|---|
| `internal/httpapi/api.go` | `resolveCode` 不再硬编码 `instrument`：按本地清单 → 最近轮询结果反查真实 code → 查不到返回空并拒绝 `start_sync` | start_sync 不带 code 时错误归集 / 重复连接 |
| `internal/httpapi/api.go` | `/api/stop` 空 body 返回 400，停全部须显式 `{"all": true}` | 误停全部仪器 |
| `internal/httpapi/api.go` | `/api/state?code=` 对已在轮询清单但未开始采集的仪器返回「已登记，等待 LIMS 开始采集」 | 「该仪器未在本采集端登记」误导 |
| `internal/limsapi/client.go` | HTTP 401 从 Transient 改为 Rejected（有界重试 5 次后放弃） | 一条永远推不进的消息（如 code 已被删）无限刷屏 |
| `internal/limspoll/poller.go` | 轮询对比上一轮清单，LIMS 中已消失的仪器自动停止采集 | 删除/停用模板后残留僵尸连接 |
| `internal/config/config.go` | 新增 `agent.api_token`（env `LABGATE_API_TOKEN`） | 管理接口鉴权 |
| `internal/httpapi/server.go` | 管理接口鉴权中间件（Bearer token，LIMS 联动接口豁免） | 局域网内任意改配置 / 注入读数 |
| `internal/httpapi/web/*` | 配置页 api_token 输入与「记住到本机」；「全部停止」改传 `all:true`；`app.js` 请求自动带令牌 | 配合鉴权与 stop 防御 |

**验证结果（联调实测）**

- `agent_instruments` 返回 `{"instruments": [{"start": false, "code": "instrument-3"}]}`
- 点「开始采集」→ `同步开始采集 [instrument-3]` → 立即连接，徽章不再先显示「已停止采集」
- 读数经 HTTP 直推进入 LIMS 采集页（event_id 前缀 `agent-…`）
- NetAssist 手动发送不带换行且间隔 <500ms 的数据会被拼成一条（与旧 Python
  采集端行为一致）；真实天平协议一般每帧带 `\r\n` 或足够间隔，不受影响

---

## 开发

```bash
make test          # 全部测试
make race          # 带竞态检测
make build         # 编译当前平台
make cross         # 交叉编译三平台
make up / down     # 起停本机演示栈
```

本机没装 Go 也可以：`./build.sh` 和 `build.ps1` 会自动改用 Docker 里的 Go。

### 代码结构

```
cmd/labgate/          边缘网关入口、Windows 服务托管
cmd/labbridge/        云端桥接入口
cmd/fakebalance/      模拟天平（联调用）
cmd/fakelims/         模拟 SENAITE 插件（联调用）
internal/
  app/                边缘侧组件装配与生命周期
  config/             配置加载、深合并、热更新、环境变量覆盖
  bus/                内嵌 NATS 服务器（LeafNode + JetStream）与流管理
  acquire/            每台仪器一个 TCP 连接：分行、空闲成行、断线重连
  parse/              读数解析（值 + 单位）
  ingest/             读数落盘到本地 JetStream
  forward/            cloud.go 上云 / lims.go 边缘直推 SENAITE（可选）
  limsapi/            SENAITE HTTP 契约（边缘与云端共用的唯一定义）
  limspoll/           轮询云 LIMS 的仪器清单与启停指令
  bridge/             云端桥接：跟着会话投递、按会话开始时间回溯
  state/              运行时统计、最近读数、云端状态
  logx/               日志（标准输出 + 界面用的环形缓冲）
  httpapi/            管理界面与 JSON API（含内嵌的页面资源）
```
