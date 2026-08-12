# Reactivate 安装使用手册

## 1. 文档说明

本文档用于指导 `maitux.workflow` 插件中“重新激活（Reactivate）”功能的安装、升级、使用与排障。

适用范围：

- SENAITE 2.x
- Plone / Zope 环境
- Python 2.7

本文档对应的功能目标：

- 为样品 `AnalysisRequest` 增加 `Reactivate`
- 为分析项 `Analysis` 增加 `Reactivate`
- 联动处理工作表 `Worksheet`
- 审计追踪 `@@auditlog` 中可查看“重新激活原因”
- 失败时整体回滚，避免半成功状态

## 2. 功能概述

安装完成后，系统支持以下能力：

- 已审核或已发布的样品允许重新激活
- 已审核、待审核或已发布的分析项允许重新激活
- 已挂工作表的分析项会根据工作表状态执行不同回退策略
- 重新激活时要求填写原因
- 原因会进入原生审计追踪的 `Changes` 列
- 原有结果值保留，不会因为重新激活而被清空

## 3. 前置条件

部署前请先确认：

- 目标环境已正确加载 `maitux.workflow`
- 项目运行环境为 Python 2.7
- buildout 已包含 `maitux.workflow` 的 `develop`、`eggs` 和 `zcml` 配置
- 当前站点可正常安装或重装 add-on
- 当前操作者具备插件安装与站点管理权限

## 4. 代码接入

如果是新环境首次接入，请先确认以下配置已加入项目 buildout。

### 4.1 buildout 配置

在主 buildout 配置中确认以下内容存在：

```ini
[buildout]
develop +=
    src/maitux.workflow

eggs +=
    maitux.workflow
```

在实例配置中确认已加载 ZCML：

```ini
[instance]
zcml +=
    maitux.workflow
```

如果项目有测试环境配置，也建议同步加上：

```ini
[test]
eggs =
    ${buildout:package-name} [test]
    ${buildout:eggs}
```

## 5. 安装步骤

### 5.1 覆盖代码

将 `maitux.workflow` 最新代码覆盖到目标项目：

- `src/maitux.workflow/src/maitux/workflow/browser/workflow.py`
- `src/maitux.workflow/src/maitux/workflow/browser/reactivate.pt`
- `src/maitux.workflow/src/maitux/workflow/services/reactivate.py`
- `src/maitux.workflow/src/maitux/workflow/setuphandlers.py`

如果项目目录中仍有历史调试文件或旧测试文件，可一并清理。

### 5.2 重新执行 buildout

在项目根目录执行：

```bash
bin/buildout
```

### 5.3 重启实例

根据现场部署方式重启 Zope / instance。

### 5.4 安装或重装插件

进入站点 Add-ons 页面：

- 新站点：安装 `maitux.workflow`
- 已安装站点：如已同步代码但 workflow 未刷新，建议重装或执行补丁逻辑

安装时会自动执行：

- 清理历史 `workflowroot` 侧栏入口
- 补丁更新样品 workflow
- 补丁更新分析项 workflow

## 6. 升级注意事项

如果目标站点之前已经装过旧版本，请特别注意：

- 代码更新后，数据库中的 workflow 配置不一定自动刷新
- 如果页面仍提示 `No workflow provides the 'xxx' action.`，通常不是代码没同步，而是 workflow 补丁未真正写入站点数据库

此时建议手工执行 workflow 补丁。

## 7. 手工刷新 workflow 补丁

进入 debug：

```bash
bin/instance debug
```

执行：

```python
app = makerequest(app)
portal = app['lims']
setSite(portal)

from maitux.workflow import setuphandlers
setuphandlers.setup_workflows()

import transaction
transaction.commit()
```

执行完成后退出 debug，并重启实例。

## 8. 使用说明

### 8.1 入口位置

重新激活按钮会出现在以下位置：

- 样品列表页 workflow 按钮区域
- 样品对象页 workflow 操作区域

### 8.2 允许状态

当前设计中，以下状态允许重新激活：

#### 样品

- `verified`
- `published`

#### 分析项

- `to_be_verified`
- `verified`
- `published`

### 8.3 操作流程

1. 打开样品列表页或样品详情页
2. 点击 `Reactivate`
3. 进入确认页
4. 填写“重新激活原因”
5. 点击确认提交

### 8.4 系统联动行为

提交后系统会联动处理：

- 样品
- 分析项
- 工作表

具体行为如下：

#### 样品

- 样品由 `verified` / `published` 回退到 `sample_received`

#### 分析项

- 未挂工作表的分析项回退到 `unassigned`
- 已挂工作表的分析项回退到 `assigned`

#### 工作表

- `to_be_verified` 工作表走原生 `rollback_to_open`
- `verified` 工作表走受控同步到 `open`

### 8.5 审计追踪

每次重新激活都会写入审计快照：

- `action = reactivate_audit`
- `Changes` 中可看到 `重新激活原因`

查看方式：

1. 打开目标对象
2. 进入 `@@auditlog`
3. 在 `Changes` 一列查看本次差异记录

## 9. 验收建议

建议按以下场景逐项验收。

### 9.1 正常场景

- 已发布样品重新激活成功
- 样品状态回退正确
- 分析项状态回退正确
- 工作表状态回退正确
- 原始结果值仍然保留
- 审计追踪中可看到“重新激活原因”

### 9.2 异常场景

- workflow 未刷新时，按钮存在但执行报 transition 不存在
- 任一步骤失败时，样品、分析项、工作表均不应部分提交
- 提交空对象或异常 UID 时，应提示未找到对象

### 9.3 审计场景

- `@@auditlog` 中存在本次 `Reactivate audit`
- `Changes` 中出现：
  - `重新激活原因`

## 10. 常见问题

### 10.1 页面提示 `No workflow provides the 'reactivate_assigned' action.`

原因：

- workflow 补丁没有真正写入站点数据库

处理：

- 重装插件
- 或按“手工刷新 workflow 补丁”章节执行 `setup_workflows()`

### 10.2 页面提示 `No workflow provides the 'rollback_to_open' action.`

原因：

- `verified` 工作表不支持该 transition

说明：

- 当前实现已做状态分支处理
- 请确认现场代码已更新到最新版本

### 10.3 页面提示 `未找到可重新激活的对象`

原因：

- 提交参数中的 UID 格式异常
- 或页面仍在使用旧模板

处理：

- 确认 `reactivate.pt` 已同步
- 清理缓存后重试

### 10.4 审计追踪里看不到“重新激活原因”

原因：

- 旧版本实现只把原因写进 metadata
- 或当前记录是在旧代码上线前产生

处理：

- 确认已同步最新 `reactivate.py`
- 用最新代码重新执行一次 Reactivate
- 再查看新生成的审计记录

### 10.5 样品状态变了，但分析项或工作表没有一起变

原因：

- 通常是旧代码版本未包含事务回滚保护
- 或现场 workflow 补丁不完整

处理：

- 确认已同步最新代码
- 确认 `setup_workflows()` 已执行

## 11. 发布建议

正式发布前建议：

- 清理 `.pyc` 与 `__pycache__`
- 重启实例
- 在测试环境完整走一遍验收流程
- 保留本次实施记录与审计截图

可选清理命令：

```bash
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} +
```

## 12. 相关文档

- [REACTIVATE_踩雷记录.md](file:///e:/senaite/诺诚项目/senaite.core-2.x/src/maitux.workflow/REACTIVATE_踩雷记录.md)

如后续还要做版本化交付，建议基于本文档再补一份“实施测试说明”作为正式上线附件。
