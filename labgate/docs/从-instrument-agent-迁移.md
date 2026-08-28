# 从 instrument-agent（Python 版）迁移到 labgate

面向已经在现场部署过旧采集端的实施人员。总体结论：**云 LIMS 侧不用改，
现场把程序换掉、配置文件直接拿来用即可**。

---

## 一、对外接口：保持不变

云 LIMS（`maitux.instrument_acquisition` 插件）调采集端的两个动作没有变化：

| 调用 | 旧版 | labgate |
|---|---|---|
| 点「开始采集」 | `POST {agent}/api/start_sync` | 一样，请求体与响应字段都一样 |
| 查询状态 | `GET {agent}/api/state?code=xxx` | 一样，`connected` / `current_host` / `current_port` 等字段保留 |

采集端调 LIMS 的三个接口也没变（`agent_instruments` / `agent_config` / `ingest`），
只是**默认关闭**——第一阶段读数走 NATS 上云，需要时在配置里打开
`cloud.poll_enabled` 与 `cloud.lims_push_enabled` 即可。

推送给 SENAITE 的请求体一字未改，`event_id` 的格式（`agent-<32位十六进制>`）
也保持一致，所以云端的幂等去重逻辑照旧生效。

---

## 二、配置文件：旧的直接能用

旧 `config.json` 可以原样拷过来，缺的新键会自动补默认值并写回文件。

| 旧键 | labgate | 说明 |
|---|---|---|
| `agent.host/port/mode/push_enabled` | 不变 | |
| `agent.instrument_code` | 不变 | 仍作为单仪器配置的回退 |
| `instruments[]` | 不变 | `{code, host, port, enabled}` |
| `instrument.*` | 不变 | 新增 `idle_flush_milliseconds`、`max_line_bytes` |
| `cloud.lims_url/token/*_seconds` | 不变 | 新增 `lims_push_enabled`、`poll_enabled`（默认 false） |
| `cache.dir` | 不变 | 现在放 JetStream 数据，不再是 SQLite |
| `cache.db_file` | **已废弃** | 留在文件里也无妨，程序会忽略 |
| `cache.retry_delay_seconds` | 保留 | 转发失败的重投间隔 |
| `cache.max_retries` | 语义变了 | 见下方"重试次数" |
| — | `agent.site_id`（新增） | 站点标识，进 NATS 主题，多实验室时区分 |
| — | `nats.*`（新增） | 内嵌 NATS 与 LeafNode，见 README |

### 重试次数的语义变化

旧版：推送失败超过 `max_retries` 次就**丢弃**这条读数。

labgate：

- **NATS 上云**不再因为重试次数丢数据。断网可能持续几小时，按次数丢是错的；
  数据留存改由 `nats.max_age_hours` / `nats.max_bytes_mb` 控制（默认 14 天 / 1 GB）。
  超过 `max_retries` 次只是把重投间隔拉长（最多 60 秒），避免空转刷日志。
- **边缘直推 SENAITE**（可选出口）保留旧语义：LIMS 明确拒绝（例如该仪器当前
  没有在采集的会话）且重投到 `max_retries` 次后放弃这一条，并记一条日志。
- **云端 labbridge** 根本不走这套：它按会话状态决定投不投，没有会话就不投，
  读数留在 JetStream 里等会话开起来，见下。

### "没有会话时的读数"从丢弃变成可补投

旧版：仪器没有监听中的会话 → ingest 返回 404 → 重试 5 次 → **丢弃**。
技术员先称量、后在 LIMS 点「开始采集」，那段读数就没了。

现在云端的 `labbridge` 按会话投递：会话一开，从**会话开始前
`lookback_minutes`（默认 15 分钟）**起补投。这是个新增能力，
但那个窗口值可能有合规含义，建议按你们的工作流和质量体系定，别照抄默认值。
设成 `0` 就是旧行为的保守版：只投会话开始之后的读数，之前的既不投也不丢。

---

## 三、部署上的变化

| | 旧版 | labgate |
|---|---|---|
| 运行环境 | 需要装 Python 3.8+ | 单个 exe / 二进制，无运行时依赖 |
| 开机自启 | `install.bat` 写注册表 + VBS | `labgate.exe --install-service`（真正的 Windows 服务，能自动重启） |
| 本地缓存 | `data/agent_cache.db`（SQLite） | `data/jetstream/`（NATS JetStream 文件存储） |
| 上云方式 | HTTP 轮询推送 | NATS LeafNode（HTTP 直推作为可选出口保留） |
| 界面 | 5 页 | 同样 5 页，路由不变，加了云端链路与本地缓冲的状态 |

### 迁移步骤

1. 停掉旧采集端（结束进程；装了自启的话删掉启动项）。
2. 旧的 `config.json` 拷到新目录，`labgate.exe` 放在一起。
3. 在配置里补上 `agent.site_id` 和 `nats.leaf.url`（云端 NATS 地址）。
4. `labgate.exe` 先前台跑一次，界面确认仪器连上、云端链路显示"已连接"。
5. `labgate.exe --install-service` 注册开机自启。

> 旧的 `data/agent_cache.db` **不会**被自动迁移。切换前先确认旧库里没有
> 未推送成功的读数（旧界面「状态」页的"缓存待推送"为 0），再停旧程序。

---

## 四、顺带修掉的旧问题

- **界面「实时数据」一直是空的**：旧版 `state.add_reading()` 从未被调用，
  收数线程只把数据塞进 SQLite，界面表格与 `total_received` 计数始终为 0。
  现在读数会正常进入界面缓冲。
- **原始行未做 HTML 转义**：旧界面把仪器返回的原始行直接拼进 innerHTML。
  现在统一转义后再插入。
- **单行无限增长**：对端一直不发换行符时，旧版的接收缓冲没有上限。
  现在按 `max_line_bytes`（默认 64 KB）截断并记日志。
- **停止后状态残留**：旧版停止采集后 `last_message` 可能还停在"已连接…"，
  与 `connected=false` 自相矛盾，LIMS 状态查询会显示得很奇怪。现在同步清理。

---

## 五、暂时没做的

- **控制面仍是 HTTP 入站**：SENAITE 点「开始采集」还是调
  `{agent_api_url}/api/start_sync`，云端仍需能访问到各实验室的 8090。
  LeafNode 只解决了读数上行那条。搬到 NATS request/reply 是自然的下一步，
  但会改接口，适合和 addon 开发一起做。
- **`received_at` 没有时区**：沿用旧格式（本地时间无偏移量），跨时区部署
  或机器时钟不准时数据溯源会有歧义。改成 RFC3339 成本很低，越早越好。
- **旧 SQLite 缓存的数据搬迁**：按上面的步骤在切换前清空即可。
- **接口重新设计**：这次刻意保持了旧接口形状。真正重做时，建议把
  `/api/http_test`（其实是"注入一条读数"）、`/api/config_page` 这类
  名不副实的路由一起改掉。
