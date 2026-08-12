# 审核分配 Docker 安装使用手册

## 1. 文档说明

本文档用于指导 `maitux.reviewerassignment` 在 Docker 环境中的安装、升级、验证与日常操作。

适用范围：

- SENAITE 2.x
- Plone / Zope
- Python 2.7
- Docker / Docker Compose 部署环境

当前功能包含：

- `Worksheet` 页面顶部增加“审核人”下拉框和 `Apply` 按钮
- `Worksheet` 保存审核人后，提交分析项时强制校验是否已分配审核人
- 审核工作表侧栏菜单仅供审核人员查看
- 只有被分配的审核人才能执行对应分析项审核
- 安装时自动创建审核工作表根入口、侧栏、catalog 索引和 workflow 补丁

## 2. 前置条件

部署前请先确认：

- Docker 容器内运行的是当前项目代码
- 当前项目根目录已包含 `src/maitux.reviewerassignment`
- `buildout.cfg` / `buildout.local.cfg` 已接入 `maitux.reviewerassignment`
- 站点当前可正常打开 Add-ons 管理界面
- 操作者具备容器操作权限和站点 Manager 权限

当前仓库中已经接入以下 buildout 配置：

```ini
[buildout]
develop +=
    src/maitux.reviewerassignment

eggs +=
    maitux.reviewerassignment

[instance]
zcml +=
    maitux.reviewerassignment
```

## 3. Docker 部署模式说明

现场常见有两种方式：

### 3.1 源码挂载模式

特点：

- 宿主机代码目录直接挂载到容器
- 修改代码后，在容器内重新执行 `buildout` 并重启服务即可

### 3.2 镜像构建模式

特点：

- 代码先进入镜像，再由容器运行
- 修改代码后，需要重新构建镜像并重建容器

本文下面的命令默认以 Docker Compose 服务名 `senaite` 为例。如果你现场服务名不是这个，请自行替换。

## 4. 首次安装步骤

### 4.1 同步代码

将以下目录同步到项目源码中：

- `src/maitux.reviewerassignment`

如果是覆盖部署，建议先清理历史缓存文件：

```bash
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} +
```

### 4.2 进入容器

```bash
docker compose exec senaite bash
```

如果容器没有 `bash`，可改用：

```bash
docker compose exec senaite sh
```

### 4.3 进入项目根目录

请切换到 buildout 根目录，也就是包含 `buildout.cfg` 的目录，例如：

```bash
cd /app/senaite.core-2.x
```

如果你的容器挂载目录不是这个路径，请替换为现场实际路径。

### 4.4 执行 buildout

```bash
bin/buildout
```

如果现场容器没有可执行权限，可先执行：

```bash
chmod +x bin/buildout
bin/buildout
```

### 4.5 重启容器或实例

优先使用现场统一方式重启。如果是 Docker Compose，常见命令如下：

```bash
docker compose restart senaite
```

如果现场是 supervisor 或脚本托管，请按实际方式重启 Zope 实例。

### 4.6 安装 Add-on

进入站点：

- `Site Setup`
- `Add-ons`

安装：

- `maitux.reviewerassignment`

安装完成后会自动执行：

- 启用 `Worksheet` 审核人 behavior
- 创建 `getReviewerUserId` 索引和 metadata
- 创建根容器 `reviewerassignmentroot`
- 将“审核工作表”加入 SENAITE 侧栏
- 修补分析项与工作表 workflow

## 5. 老环境升级步骤

如果目标环境之前已经跑过旧代码，建议使用以下顺序升级。

### 5.1 覆盖最新代码

将最新 `src/maitux.reviewerassignment` 覆盖到项目源码目录。

### 5.2 清理缓存

在项目根目录执行：

```bash
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} +
```

### 5.3 重新执行 buildout

```bash
bin/buildout
```

### 5.4 重启服务

```bash
docker compose restart senaite
```

### 5.5 进入站点检查

重点检查：

- Add-ons 中 `maitux.reviewerassignment` 仍为已安装
- `Worksheet` 页面顶部能看到“审核人”下拉框
- 左侧菜单能看到“审核工作表”

## 6. 老环境 workflow 手工刷新

新站点首次安装 add-on 时，会自动执行 `setup_handler()`，通常不需要手工刷新。

只有以下情况才建议手工刷新：

- 老环境曾安装过错误版本
- workflow 已被历史补丁污染
- 页面仍出现按钮缺失或权限不一致
- 新代码已同步，但 live workflow 没有正确更新

### 6.1 进入 debug

```bash
docker compose exec senaite bash
cd /app/senaite.core-2.x
bin/instance debug
```

### 6.2 执行补丁

```python
app = makerequest(app)
portal = app['lims']
from zope.component.hooks import setSite
setSite(portal)

from maitux.reviewerassignment import setuphandlers
setuphandlers.run_install_steps(portal)

import transaction
transaction.commit()
```

执行完成后退出 debug，并重启实例。

## 7. Docker 镜像构建模式示例

如果你们现场不是源码挂载，而是自定义镜像构建，可以参考下面流程。

### 7.1 在镜像构建上下文中包含源码

确保镜像中有：

- 项目根目录
- `src/maitux.reviewerassignment`
- 最新 `buildout.cfg`

### 7.2 构建镜像

示例：

```bash
docker compose build senaite
```

或者：

```bash
docker build -t senaite-custom:latest .
```

### 7.3 重建容器

```bash
docker compose up -d --force-recreate senaite
```

### 7.4 安装插件

首次启动后，仍需要进入站点 Add-ons 页面安装：

- `maitux.reviewerassignment`

## 8. 安装后验证

建议按以下顺序验收。

### 8.1 页面验证

打开任一工作表：

- 路径示例：`/lims/worksheets/WS-005/manage_results`

确认页面顶部存在：

- `检验人员`
- `审核人`
- `Apply`

### 8.2 提交流程验证

执行以下场景：

1. 不选择审核人，直接勾选分析项点击提交
2. 系统应阻止提交
3. 选择审核人并点击 `Apply`
4. 再次提交分析项
5. 系统应允许提交

### 8.3 审核权限验证

使用审核人账号登录，确认：

- 左侧菜单出现“审核工作表”
- 只能看到分配给当前用户且处于待审核状态的工作表
- 可以对分配给自己的工作表执行审核

使用非审核人或未分配人员登录，确认：

- 不应看到自己的待审核列表数据
- 不应允许执行对应审核动作

## 9. 日常操作说明

### 9.1 分配审核人

1. 打开工作表 `manage_results`
2. 在顶部“审核人”下拉框中选择审核人
3. 点击 `Apply`
4. 页面提示“审核人已保存”

### 9.2 提交分析项

1. 勾选需要提交的分析项
2. 点击 `提交`
3. 系统先检查当前 `Worksheet` 是否已分配审核人
4. 未分配时直接阻止提交
5. 已分配时允许提交，并把审核人同步写入本次提交的分析项

### 9.3 审核工作表

1. 使用审核人账号登录
2. 打开左侧“审核工作表”
3. 只会看到分配给当前审核人的待审核工作表
4. 勾选后执行审核

## 10. 常见问题

### 10.1 页面没有显示“审核人”下拉框

先检查：

- 是否已执行 `bin/buildout`
- 是否已重启容器
- 是否已安装 `maitux.reviewerassignment`
- 当前站点是否真的加载了 add-on browser layer

### 10.2 审核人为空仍可提交

先检查：

- 是否已重启实例加载最新 guard
- 当前运行容器是否确实使用了最新代码
- 是否是旧镜像未重建、旧容器未重启

### 10.3 左侧没有“审核工作表”菜单

可能原因：

- add-on 未安装完成
- 安装时 `setup_handler()` 未执行成功
- 老环境升级后侧栏配置未刷新

处理方式：

- 重新安装 add-on
- 或执行“老环境 workflow 手工刷新”章节中的 `run_install_steps(portal)`

### 10.4 工作流按钮缺失或权限异常

可能原因：

- live workflow 仍残留旧补丁
- 老环境数据库中的 workflow 状态未刷新

处理方式：

- 先执行手工补丁
- 再重启实例
- 再重新验证按钮和权限

## 11. 交付建议

建议把以下内容一起作为更新包交付：

- `src/maitux.reviewerassignment`
- 修改后的 `buildout.cfg`
- 修改后的 `buildout.local.cfg`
- 本安装手册

如果现场是老环境升级，建议同时附带一份“升级执行记录”，至少记录：

- 执行时间
- 操作人
- buildout 是否成功
- 容器是否重启
- Add-on 是否安装完成
- 是否执行过手工补丁
- 验证结果

## 12. 建议验收清单

- 页面顶部显示“审核人 + Apply”
- 空审核人时不能提交
- 选定审核人后可以提交
- 审核工作表菜单存在
- 审核人只能看到分配给自己的待审核工作表
- 非分配审核人不能审核
- 老环境升级后 workflow 按钮和权限正常
