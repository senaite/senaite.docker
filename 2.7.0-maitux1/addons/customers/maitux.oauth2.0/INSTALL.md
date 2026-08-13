# maitux.oauth2 安装与配置

## 0. 名字说明

| 项 | 值 |
|---|---|
| 目录名 | `addons/customers/maitux.oauth2.0` |
| egg / 包名 | `maitux.oauth2` |
| Python 包 | `src/maitux/oauth2/` |
| GS profile | `maitux.oauth2:default` |

目录名带 `.0` 是按要求放置的；Python 包名不能出现 `2.0` 这种写法，所以 egg 名是
`maitux.oauth2`。buildout 里 `develop` 用目录名、`eggs` 用 egg 名。

## 1. 已经改好的两个文件

### `addons/customers/custom-addon.cfg`

```ini
[buildout]
develop +=
    /opt/addons/customers/maitux.oauth2.0
eggs +=
    maitux.oauth2

[instance]
zcml +=
    maitux.oauth2
```

三项各自的作用：`develop` 让 buildout 认识源码目录，`eggs` 把它加进 instance 的
sys.path，`zcml` 让 ZCML 被加载。

**没有 `[plonesite] profiles` 这一项，是刻意的**：`buildout.cfg` 里写的是
`[plonesite] profiles = senaite.lims:default`（普通赋值），而 extends 别人的那个
文件优先级最高，所以在这里追加的 profile 会被整个丢掉 —— `common-addons.cfg` 里
那几个 `maitux.*:default` 也是同样的命运。而且这个 part 还带着
`enabled = False`，压根不执行。所以 profile **必须手动安装**，见下一节。

### `Dockerfile`

原来只有 `RUN mkdir -p /opt/addons/customers`，构建时这个目录是空的，
`develop += /opt/addons/customers/maitux.oauth2.0` 会指向一个不存在的路径，
buildout 解析 `maitux.oauth2` 这个 egg 会失败。改成和 `addons/common` 一样：

```dockerfile
COPY addons/customers /opt/addons/customers
```

运行时 docker-compose 仍然把宿主机的 `./addons/customers` 挂载到同一路径，
所以在宿主机改代码、重启容器即可生效。

> 因为运行时的挂载会盖掉镜像里生成的 `*.egg-info`，`z3c.autoinclude` 可能找不到
> 入口点，所以 `[instance] zcml += maitux.oauth2` 是必须的，不能删。

## 2. 构建与启用

```bash
docker compose -f docker-compose.yml up -d --build
```

启动后用管理员登录，进入
`站点地址/prefs_install_products_form`，安装 **MAITUX 竹云统一登录 (OAuth 2.0)**。

安装时会自动完成：

- 注册 5 个 memberdata 属性（`maitux_oauth2_subject` / `_disabled` /
  `_disabled_reason` / `_last_sync` / `_last_login`）
- 创建“待授权”用户组 `oauth2-pending`（无任何角色）
- 生成 `state` 签名密钥
- 在控制面板里加一项 **竹云统一登录 (OAuth 2.0)**

## 3. 配置

配置页：`站点地址/@@oauth2-controlpanel`（控制面板 → 附加产品配置）。

**每一项都可以用环境变量覆盖，环境变量优先级更高**，变量名是
`MAITUX_OAUTH2_` + 字段名大写，例如：

```yaml
# docker-compose.yml -> services.instance.environment
MAITUX_OAUTH2_ENABLED: "true"
MAITUX_OAUTH2_PROVIDER_URL: "https://passport.innocarepharma.com"
MAITUX_OAUTH2_CLIENT_ID: "3UZLLHBzzxb4uZeKH2GGRxbtZMkqFjaY"
MAITUX_OAUTH2_CLIENT_SECRET: "……"
MAITUX_OAUTH2_REDIRECT_URI: "https://lims.example.com/MaiLIMS/@@oauth2-callback"
MAITUX_OAUTH2_SYNC_TOKEN: "一串随机字符串"
```

建议 **ClientSecret 用环境变量注入**，不要落到 ZODB 里。

### 已经预填好的客户参数

| 配置项 | 值 |
|---|---|
| AppId | `20260804155456579-E219-3F7069E8F` |
| ClientId | `3UZLLHBzzxb4uZeKH2GGRxbtZMkqFjaY` |
| ClientSecret | `lAI4L84uKn0…Gy3h` |
| 竹云地址 | `https://passport.innocarepharma.com` |

`enabled` 默认是 **关闭** 的，确认参数无误后再打开。

## 4. 需要在竹云侧登记的回调地址

```
https://<你的LIMS域名>/MaiLIMS/@@oauth2-callback
```

配置页顶部会直接显示当前生效的回调地址，照抄给客户即可。

如果客户坚持要用 `/api/sso/callback` 这个路径，不需要改代码，在 nginx 上加一条
重写就行（`nginx/conf.d/default.conf`，放在 `location /` **之前**）：

```nginx
location = /api/sso/callback {
    rewrite ^ /MaiLIMS/@@oauth2-callback$is_args$args break;
    proxy_pass http://senaite_backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
}
```

然后把配置里的“回调地址 redirect_uri”填成
`https://<域名>/api/sso/callback`。

## 5. 登录行为

| 场景 | 结果 |
|---|---|
| 竹云 Portal 点图标（带 code，无 state） | 直接走回调登录 |
| 匿名访问 LIMS 任意需要登录的页面 | 自动跳竹云授权页（`auto_redirect`） |
| 打开 `/login` | 默认仍是本地登录表单，上方多一个“竹云统一登录”按钮 |
| 打开 `/login` 也想跳竹云 | 打开 `redirect_login_form` |
| **管理员本地登录** | `站点地址/@@oauth2-local-login`（种 1 小时豁免 Cookie） |

> `login` 视图**没有**被覆盖，只有 `require_login` 被覆盖。这是刻意的：替换
> Plone 的登录表单是唯一可能把所有管理员锁在门外的改动。

## 6. 账号状态与授权

| 状态 | 判定方式 | 用户看到 |
|---|---|---|
| 待授权 | SSO 建的号，且没有任何非基础角色、也不属于除待授权组以外的任何组 | `@@oauth2-pending` |
| 已授权 | 管理员分配了任意 LIMS 角色，或加进了任意用户组 | 正常进入 LIMS |
| 已停用 | memberdata `maitux_oauth2_disabled = True` | `@@oauth2-disabled` |

管理员的操作就是标准 Plone 流程：**用户与组** → 找到该用户 → 给角色或加组。
不需要手工把用户移出 `oauth2-pending`（移不移都行）。

判定是**保守**的：如果建号时“加入待授权组”失败了，用户依然算待授权，不会被放进来。

## 7. 唯一 ID

配置项“唯一 ID 字段”默认是 `external_id,id`，按顺序取第一个非空值：

1. 优先取 `external_id`（即需求里说的**外部 ID**）
2. 取不到时退回竹云的 `id`

⚠️ 竹云的 `userinfo` 接口默认只返回 `id / userName / name / email / mobile`。
要真正拿到 `external_id`，**需要客户在竹云应用里配置属性映射**，把外部 ID 映射进
userinfo 的返回值。如果客户不做这个映射，就用默认的 `id` 兜底 —— 功能一样能跑，
只是唯一键换成了竹云用户 ID。

竹云身份和本地账号的对应关系存在 portal 的 annotation 里
（`maitux.oauth2.subjects`，一个 `subject -> userid` 的 BTree），
所以竹云那边改了用户名也不会认错人。

## 8. 每天一次的用户同步（离职处理）

流程：`POST /api/v2/tenant/token`（client_credentials）→
`GET /api/v2/tenant/users` 分页拉全量 → 对每个本地 SSO 账号：

- 竹云里 `disabled=true` 或 `locked=true` → LIMS 停用
- 竹云里查不到（账号被删） → LIMS 停用（可用 `sync_deactivate_missing` 关掉）
- 竹云里正常 → 如果之前被停用则恢复，并同步姓名/邮箱

“停用”做了三件事：打 memberdata 标记、移出所有用户组、把本地密码改成随机值。
另外每个请求都会检查一次标记，已经拿着 Cookie 的离职员工会被立刻踢出去。

### 触发方式二选一

**A. Zope 自带的 clock-server（推荐，不需要外部 cron）**

`custom-addon.cfg` 里已经写好了注释掉的片段，改掉 `token` 后取消注释重建镜像：

```ini
[instance]
zope-conf-additional +=
    <clock-server>
        method /MaiLIMS/@@oauth2-sync-users?token=CHANGE-ME
        period 86400
        user
        password
        host localhost
    </clock-server>
```

**B. 外部 cron / 定时任务**

```bash
curl -s "https://lims.example.com/MaiLIMS/@@oauth2-sync-users?token=你的口令"
```

管理员登录后也可以直接在浏览器打开
`站点地址/@@oauth2-sync-users` 手动跑一次（不需要 token）；
加 `?dry_run=1` 只看结果不改数据。返回的是 JSON：

```json
{
  "remote_total": 1200, "local_total": 83,
  "disabled": 2, "enabled": 0, "missing": 1, "updated": 5,
  "errors": [], "started": "...", "finished": "..."
}
```

最近一次的结果也会写回配置页的“上次同步结果”。

## 9. 排错

```bash
docker compose logs -f instance | grep maitux.oauth2
```

| 现象 | 原因 |
|---|---|
| `state 签名校验失败` | 浏览器禁 Cookie，或中途换了域名 |
| `安全校验未通过` | 直接手工访问了回调地址，或 state 过期（>15 分钟） |
| `Bad client credentials` | ClientId / ClientSecret 不对 |
| `Invalid redirect: ... does not match` | 竹云侧登记的可信回调地址和 `redirect_uri` 不一致 |
| 竹云返回的用户信息中没有唯一标识 | 见第 7 节，改配置或让客户加属性映射 |
| 自签证书报 SSL 错误 | 配置里关掉“校验 HTTPS 证书” |

**万一被锁在外面**：`https://<域名>/MaiLIMS/@@oauth2-local-login`
永远可以打开本地登录表单；再不行就把 `enabled` 用环境变量置为 `false` 重启。
