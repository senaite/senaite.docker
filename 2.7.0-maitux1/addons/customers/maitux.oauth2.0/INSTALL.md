# maitux.oauth2 安装与配置

> 下文的 `<站点id>` 指 SENAITE/Plone 站点对象的 id（例如 `lims`）。
> 一个实例可以有多个站点，id 不固定，请按实际情况替换。
> **插件代码本身不依赖站点 id** —— 所有 URL 都从 `api.portal.get().absolute_url()` 推导，只有下面这些靠外部配置（站点外的 nginx / clock-server / 竹云回调地址）的地方需要填它。

## 0. 名字说明

| 项 | 值 |
|---|---|
| 目录名 | `addons/customers/maitux.oauth2.0` |
| egg / 包名 | `maitux.oauth2` |
| Python 包 | `src/maitux/oauth2/` |
| GS profile | `maitux.oauth2:default` |

目录名带 `.0` 是按要求放置的；Python 包名不能出现 `2.0` 这种写法，所以 egg 名是
`maitux.oauth2`。buildout 里 `develop` 用目录名、`eggs` 用 egg 名。

## 1. buildout 接入

在 `addons/customers/custom-addon.cfg` 里需要三项：

```ini
[buildout]
develop +=
    /opt/addons/customers/maitux.oauth2.0
eggs +=
    maitux.oauth2
```

`develop` 让 buildout 认识源码目录（并生成 egg-info），`eggs` 把它加进 instance
的 sys.path。

`[instance] zcml += maitux.oauth2` **不是必须的**：本包在 `setup.py` 里带了
`[z3c.autoinclude.plugin] target = plone` 入口点，而运行时 buildout 会在**挂载目录
里**重新生成 egg-info（实测：宿主机上会出现 `src/maitux.oauth2.egg-info/`），
所以 autoinclude 能正常发现它。

反而走 `[instance] zcml` 有一个坑：`site.zcml` 处理 `package-includes/*-configure.zcml`
的时机在 `<five:loadProducts />` **之前**，那时 `Products.CMFCore` 还没注册
`cmf.ManagePortal`，控制面板页面会以
`ComponentLookupError: (IPermission, 'cmf.ManagePortal')` 让**整站起不来**。
本包已经在 `configure.zcml` 里显式 `<include package="Products.CMFCore"
file="permissions.zcml" />` 兜住了这一点，两种加载方式都安全 —— 但同目录其他插件
若在 ZCML 里引用了 CMF / senaite.core 的权限而没有这一行，就会踩这个坑。

**没有 `[plonesite] profiles` 这一项，是刻意的**：`buildout.cfg` 里写的是
`[plonesite] profiles = senaite.lims:default`（普通赋值），而 extends 别人的那个
文件优先级最高，所以在这里追加的 profile 会被整个丢掉 —— `common-addons.cfg` 里
那几个 `maitux.*:default` 也是同样的命运。所以 profile **必须手动安装**，见下一节。

### ⚠️ 构建时 vs 运行时

- **运行时**：`docker-initialize.py` 会生成 `custom.cfg`，于是
  `docker-entrypoint.sh` 里的 `if [ -e "custom.cfg" ]` 命中，**每次容器启动都会
  重跑 `buildout -c custom.cfg -N`**。那时 bind mount 已生效，挂载的
  `custom-addon.cfg` 和插件源码都在位，一切正常。
- **构建时**：Dockerfile 会把 `custom-addon.cfg` COPY 进镜像，但
  `/opt/addons/customers` 在构建阶段是**空目录**（compose 的挂载在
  `docker build` 期间不存在）。于是 `develop` 只打一条 warning，紧接着
  `instance` part 解析 `${buildout:eggs}` 时抛
  **`MissingDistribution: Couldn't find a distribution for 'maitux.oauth2'`**，
  构建失败。

两种解法，选一个：

1. 在 Dockerfile 里加 `COPY addons/customers /opt/addons/customers`（和
   `addons/common` 一致）。代价：客户专属代码进了共享镜像。
2. 把这三项从 `custom-addon.cfg` 挪到一个**只在运行时挂载**的
   `custom.cfg`（extends `buildout.cfg`），构建时的 `custom-addon.cfg` 保持空。
   代价：配置不在 `custom-addon.cfg` 里了。

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

> 控制面板那一项是在 `post_install` 里**用代码**注册的，不是 GS 的
> `controlpanel.xml`。因为 Plone 5.2 的 XML 导入器
> （`Products.CMFPlone.exportimport.controlpanel._initConfiglets`）会对 title 做
> `str()`，Python 2 上遇到中文直接 `UnicodeEncodeError` 并中断整个安装；而
> `registerConfiglet()` 是把 `name` 原样传给 `PloneConfiglet` 的，所以代码注册
> 可以保留中文标题，也不需要额外的翻译目录。

## 3. 配置

配置页：`站点地址/@@oauth2-controlpanel`（控制面板 → 附加产品配置）。

**正常情况下只需要勾一个开关**：把“启用统一登录”打开。
客户给的 AppId / ClientId / ClientSecret / 竹云地址已经是预置默认值，
接口路径、scope、字段映射也都有默认值，都不用填。

回调地址（redirect_uri）**不用填** —— 插件按当前站点自动推导，
并且会识别 nginx 终止 TLS 的情况（读 `X-Forwarded-Proto`）自动用 https。
只有当外网访问路径和站点自己的 URL 不一致时（比如套了一层
`/api/sso/callback` 重写）才需要在本页手填。

### 环境变量覆盖（可选，多站点部署请慎用）

每一项都可以用 `MAITUX_OAUTH2_<字段名大写>` 环境变量覆盖，优先级高于本页。

> ⚠️ **环境变量是整个容器共享的，而一个实例可以挂多个 site，
> 每个 site 各自安装本插件。** 所以和站点有关的项（`REDIRECT_URI`、
> `ENABLED`、`AUTO_REDIRECT`、`PENDING_GROUP` …）**不要**用环境变量，
> 否则所有站点被强行用同一个值。环境变量只适合全局性的东西，
> 比如单站点部署时用 `MAITUX_OAUTH2_CLIENT_SECRET` 把密钥从 ZODB 里拿出来。

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
https://<你的LIMS域名>/<站点id>/@@oauth2-callback
```

**不用自己拼** —— 配置页顶部第 ① 行会直接把当前站点真正会发送的那个地址印出来，
照抄给客户即可。多站点时每个站点的值不同，分别去各自的配置页抄。

如果客户坚持要用 `/api/sso/callback` 这个路径，不需要改代码，在 nginx 上加一条
重写就行（`nginx/conf.d/default.conf`，放在 `location /` **之前**）：

```nginx
location = /api/sso/callback {
    rewrite ^ /<站点id>/@@oauth2-callback$is_args$args break;
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

竹云的 `userinfo` 接口默认只返回 `id / userName / name / email / mobile`，没有
`external_id`。**但不需要为此去找客户配属性映射**：

- 登录时取不到 `external_id` 就退回 `id`（竹云用户 ID），一样稳定唯一
- 离职检测时，`sync_user_id_field = "external_id,user_id"` 会把 EIAM 用户列表返回的
  **两个字段都建进索引**，所以用 `id` 存下来的身份能和 EIAM 的 `user_id` 对上

也就是说“用外部 ID 作唯一键”这个需求，靠同步接口那边的双字段匹配就兜住了。

⚠️ 未经真实数据验证的假设：`userinfo` 的 `id` 和 EIAM 用户列表的 `user_id` 是同一个
标识符（两边格式一致，文档里都叫“用户ID”）。第一次同步跑完看 `missing` 计数即可确认
—— 如果 `missing` 等于本地 SSO 账号总数，说明对不上，那时才需要找客户加属性映射。

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
        method /<站点id>/@@oauth2-sync-users?token=CHANGE-ME
        period 86400
        user
        password
        host localhost
    </clock-server>
```

**B. 外部 cron / 定时任务**

```bash
curl -s "https://lims.example.com/<站点id>/@@oauth2-sync-users?token=你的口令"
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

**万一被锁在外面**：`https://<域名>/<站点id>/@@oauth2-local-login`
永远可以打开本地登录表单；再不行就把 `enabled` 用环境变量置为 `false` 重启。
