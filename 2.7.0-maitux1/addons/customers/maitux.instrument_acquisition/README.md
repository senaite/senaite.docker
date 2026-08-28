# maitux.instrument_acquisition —— 仪器采集插件说明

SENAITE（LIMS）仪器数据采集插件：采集页绑定解析模板 → 按模板连接仪器 /
对接本地采集端（labgate）→ 接收读数 → 解析 → 分配/回写到 Worksheet 的
Interim Field（`T_name` / `T_weight`）→ 可选 HTTP 转发到第三方系统。

> 适用版本：SENAITE core 2.x / Plone 5 / Zope 4（Python 2.7）
> 采集端：`labgate`（Go，边缘网关，见 labgate 项目 README）

---

## 一、功能说明

### 1. 总体流程

```
仪器（天平/串口服务器，TCP）
   │  (a) 进程内 relay 模式：LIMS 直接连仪器收数
   │  (b) 远端采集端模式（默认）：labgate 连仪器，读数 HTTP 推回 LIMS
   ▼
LIMS 采集页（Worksheet）
   │  按 event_id 幂等去重、按 instrument_code 归入当前监听会话
   ▼
读数列表（pending / assigned / saved / discarded）
   │  手动分配或自动回写
   ▼
Worksheet Interim Field：T_name（名称）、T_weight（重量）
```

默认模式是 **远端采集端模式**（`PHASE1_AGENT_MODE = True`）：LIMS 与仪器
不在同一网络，由实验室本地的 labgate 采集端连接仪器，读数推回 LIMS；
LIMS 点「开始采集」只是标记会话监听并通知采集端连接仪器。

### 2. 采集会话状态机

- 会话状态：`active`（活动）→ `closed`（关闭）
- 监听状态：`listening=True`（采集中）/ `listening=False`（未监听）
- 读数状态：`pending`（待分配）→ `assigned`（已分配）→ `saved`（已保存写回）；
  也可 `discarded`（废弃）
- 同一仪器同时只允许一个监听会话；其他用户点「开始采集」会弹确认框，
  确认后 `force=1` 挤占（自动停掉对方会话并通知其采集端断开）

### 3. 核心接口（HTTP，全部 `zope.Public`）

请求头统一用 `X-Instrument-Token` 携带采集端 Token。

| 接口 | 方法 | 用途 |
|---|---|---|
| `@@instrument_acquisition_api_ingest` | POST | 采集端上报读数（body 含 event_id / instrument_code / raw_text / parsed） |
| `@@instrument_acquisition_api_agent_instruments` | GET | 采集端轮询：按 Token 反查其负责的全部仪器与启停指令 `{instruments:[{code,start,ip,port}]}` |
| `@@instrument_acquisition_api_agent_config` | GET | 旧接口：按 `instrument_code` 查单台仪器启停指令 `{start,ip,port,session_id,...}` |
| `@@instrument_acquisition_api_templates_list` | GET | 解析模板列表 |
| `@@instrument_acquisition_api_forward_test` | GET | 测试模板的 HTTP 转发配置 |
| `@@instrument_acquisition_api_forward_status` | GET | 查询转发状态/队列 |
| `@@instrument_acquisition_api_forward_history` | GET | 查询转发历史 |
| `@@instrument_acquisition_api_manual_forward` | POST | 手动触发转发 |

**ingest 上报约定（与 labgate 一致）：**

- body 字段：`event_id`（必填，幂等键，格式 `agent-<32位hex>`）、
  `instrument_code`、`received_at`、`raw_text`、`parsed{value,unit,stable}`、
  可选 `site_id`、`session_id`
- Token 校验：优先按模板登记的 `agent_token` 校验；等于固定共享 Token
  `PHASE1_INGEST_TOKEN` 时始终放行（兼容旧采集端）
- 会话归属：带 `session_id` 按会话；不带则按 `instrument_code` 归入该仪器
  当前监听会话（无监听会话返回 404 `No active listening session`）
- 幂等：同一 `event_id` 重复上报返回 `duplicate`，不重复写入
- 响应：`200 + {status: created|duplicate, success: true}`

**agent_instruments 下发约定（labgate 轮询）：**

- 按 `X-Instrument-Token` 反查所有 `agent_token` 相同的解析模板
- 每台仪器：LIMS 有监听会话 → `{code, start:true, ip, port}`（ip/port 来自
  模板 `ip_address` / `port`）；否则 `{code, start:false}`
- 采集端据此自动连接/断开各仪器，**无需在采集端本地配置仪器信息**

### 4. 读数解析与写回

- 解析脚本：模板字段 `script_file` 上传 `.js` 脚本，入站数据经 JS 解析出
  `parsed{value,unit}`
- 目标位：`T_name`（名称，单值）、`T_weight`（重量，支持数组多行），
  target_key 格式 `{analysis_uid}:{keyword}[:{seq}]`
- 手动导入：PDF 报告经 `browser/deemo` 的提取/JS 解析/写回逻辑
  （`services/acquisition.py::parse_and_write_report` 复用同一套逻辑）
- 写回：读数分配到目标位后写入 Worksheet 的 Interim Field；支持
  `add_target_row` / `remove_target_row` 增删数组行

### 5. HTTP 转发（可选，模板级开关）

模板字段 `forward_enabled` 打开后，解析出的数据可按 `forward_url` /
`forward_method`（POST/PUT）/ `forward_headers` / `forward_timeout` 转发到
第三方系统（`forwarder.py`，重试 3 次、退避 1 秒）。

### 6. 采集页（Worksheet 视图）

- 进入采集页自动 `ensure_session` 创建活动会话
- 徽章显示采集端连接状态（远端模式查询 labgate `/api/state?code=xxx`）
- 「开始采集」：远端模式调用采集端 `/api/start_sync`（带 host/port/push/code），
  连接失败当场报错；进程内 relay 模式由 LIMS 直连仪器
- 读数卡片：`#event_id前8位` + 解析值/单位 + 原始文本 + 状态徽章
- 分配：下拉选择目标位（分析行的 T_name/T_weight）

---

## 二、配置说明

### 1. 解析模板（InstrumentParsingTemplate）

SENAITE 后台「仪器 → 解析模板」新建/编辑：

| 字段 | 说明 | 必填 |
|---|---|---|
| Name | 模板名称 | 是 |
| Instrument | 绑定的仪器（`Instrument` 类型） | 是 |
| Port | 仪器 TCP 端口（天平地址端口） | 采集中必填 |
| IP Address | 仪器 TCP 地址（天平地址 IP） | 采集中必填 |
| 采集端接口地址 (Agent API URL) | 本地采集端 HTTP 地址，如 `http://192.168.1.5:8090`（与天平 IP/端口分离） | 远端模式必填 |
| 采集端 Token | 采集端鉴权凭证，一个中转站一个 Token；多台仪器共用可填相同值 | 远端模式必填 |
| Parser Script File | 解析脚本（.js），把原始行解析成 `{value, unit}` | 按需 |
| Enable HTTP Forward | 是否把解析数据转发到第三方 HTTP 接口 | 否 |
| Forward URL / Method / Headers / Timeout | 转发目标与参数 | 转发时填 |

> 仪器也可以不绑定模板，改用仪器扩展字段
> （`extender/instrument.py` 的 `FIELD_NAME`）指定模板。

### 2. 代码级开关（services/phase1_targets.py）

| 常量 | 默认 | 说明 |
|---|---|---|
| `PHASE1_AGENT_MODE` | `True` | `True`=远端采集端模式（labgate）；`False`=进程内 relay 模式 |
| `PHASE1_INGEST_TOKEN` | `maitux-phase1-instrument-acquisition-token` | 固定共享 Token（兼容旧采集端；新部署建议用模板 `agent_token`） |
| `PHASE1_TCP_PROBE_TIMEOUT` | `3` | 开始采集时 TCP 连通探测超时（秒） |
| `T_NAME_KEYWORD` / `T_WEIGHT_KEYWORD` | `T_name` / `T_weight` | 回写的 Interim Field keyword |
| `PHASE1_TARGET_DEFINITIONS` | 名称/重量 | 目标位定义（keyword、显示标题、是否多值、排序、值类型） |
| `PHASE1_ANNOTATION_KEY` / `PHASE1_SESSION_INDEX_KEY` | `maitux...v1.session*` | Worksheet annotations 存储键 |

### 3. 与 labgate 采集端联动配置（本次联调结论）

| 项 | 值 |
|---|---|
| labgate 配置 `cloud.lims_url` | `http://<LIMS 主机>:8081/lims` |
| labgate 配置 `cloud.token` | = 模板「采集端 Token」（如 `jklNg_...`） |
| labgate 配置 `agent.mode` | `auto` + `cloud.poll_enabled=true`（轮询下发仪器清单） |
| labgate 配置 `cloud.lims_push_enabled` | `true`（读数 HTTP 直推 LIMS ingest） |
| labgate 容器连本机仪器 | `extra_hosts: "192.168.1.5:host-gateway"`（容器内连宿主局域网 IP） |
| LIMS 模板「采集端接口地址」 | `http://<labgate 主机>:8090` |

**联动注意事项（踩坑记录，2026-08）：**

- 「开始采集」/「停止采集」通知已改为携带 `code`（`session_store.py`），
  避免采集端用不到真实仪器 code 而建错连接（读数推不进、报 Invalid token）
- 采集端收到的读数若 `instrument_code` 在 LIMS 无模板，ingest 返回 401
  Invalid token；labgate 已改为有界重试（5 次后放弃），不会无限刷屏
- labgate 轮询 `agent_instruments` 时，模板 `agent_token` 必须与 labgate
  配置 token 完全一致（`_verify_token` 对固定共享 Token 始终放行，但
  `agent_instruments` 按模板 token 严格反查）
- 采集页徽章显示的「已登记，等待 LIMS 开始采集」说明采集端已从轮询
  得知该仪器，只等 LIMS 下发开始指令

---

## 三、常用排查

| 现象 | 处理 |
|---|---|
| 采集页徽章「该仪器未在本采集端登记」 | 模板 `agent_token` 与 labgate 配置 token 不一致；或 labgate 未启动轮询（mode=auto + poll_enabled） |
| 读数推不进，LIMS 日志 Invalid token | 检查读数 `instrument_code` 对应模板存在且 `agent_token` 匹配 |
| 点「开始采集」立即失败 | 模板 `ip_address`/`port` 未配，或采集端连不上仪器（TCP 探测失败）；远端模式看 labgate 日志 |
| 读数出现在页面但无值 | 解析脚本未配或解析不出 `value`；用 `instrument_acquisition_debug` 页面调试 JS 解析 |
| 读数重复 | 正常：同一 event_id 重复上报会去重（duplicate）；检查采集端 event_id 是否稳定生成 |
