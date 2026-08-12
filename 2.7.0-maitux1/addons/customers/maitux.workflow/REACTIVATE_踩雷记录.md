# Reactivate 踩雷记录

## 背景

本次在 `maitux.workflow` 中为 SENAITE 2.x 增加样品、分析项、工作表联动的“重新激活”能力。

目标要求：

- 只通过 add-on 实现，尽量不改 `core`
- 兼容 Python 2.7
- 重新激活后保留原结果
- 失败时不能出现半成功状态
- 审计追踪里必须能看到“重新激活原因”

## 这次踩过的坑

### 1. 不能用简化版 workflow XML 直接覆盖官方 workflow

现象：

- 安装 add-on 时出现 `Invalid attribute: title`

根因：

- `profiles/default/workflows/.../definition.xml` 被当成完整 DCWorkflow 导入
- 但实际写进去的是“增量补丁式”内容，不是完整 workflow 定义

处理方式：

- 删除 add-on 自己的 workflow XML 覆盖方案
- 改为在 `setuphandlers.py` 里通过 Python 补丁给现有 workflow 动态补 transition

### 2. 站点数据库里的 workflow 不会自动跟着代码变

现象：

- 代码里已经有 `reactivate` / `reactivate_assigned`
- 页面点击仍报 `No workflow provides the 'xxx' action.`

根因：

- 代码已改，但站点数据库中的 workflow 配置没有同步刷新

处理方式：

- 通过安装步骤或 `setup_workflows()` 动态补丁
- 必要时在目标环境手工执行补丁逻辑并提交事务

### 3. Reactivate 确认页 GET 能找到对象，POST 却找不到对象

现象：

- 确认页能打开
- 提交后提示“未找到可重新激活的对象”

根因：

- 请求参数在不同场景下会出现：
  - `uids:list`
  - `uids` 字符串
  - `uids` 列表
- POST 时还可能出现 querystring 与 form 同时提交，导致重复值

处理方式：

- `get_uids()` 同时兼容 `uids:list`、字符串和列表
- 增加 UID 清洗与去重逻辑
- 模板提交统一改成 `uids:list`

### 4. 失败后对象出现半成功状态

现象：

- 样品状态已经回退
- 但分析项或工作表后续步骤失败

根因：

- 浏览器视图捕获异常后，没有显式终止本次事务

处理方式：

- 在提交异常分支中执行 `transaction.abort()`
- 保证任一步骤失败都整体回滚

### 5. `verified` 工作表没有合法的原生回退 transition

现象：

- 先报 `rollback_to_open` 不存在
- 改成 `retract` 后又报 `retract` 不存在

根因：

- 官方 `worksheet` workflow 中：
  - `to_be_verified` 支持 `rollback_to_open`
  - `verified` 不支持 `rollback_to_open`
- 同时 `worksheet.retract` 的 guard 还依赖其下 analysis 必须允许 `retract`
- 但 analysis 在对应状态下并不满足这个条件

处理方式：

- `to_be_verified` 工作表继续走官方 `rollback_to_open`
- `verified` 工作表改为受控同步到 `open`
- 同步时保留审计记录

### 6. 审计原因只写 metadata，原生 Changes 不会显示

现象：

- 审计记录存在
- 但 `@@auditlog` 的 `Changes` 一列看不到“原因”

根因：

- SENAITE 原生 `Changes` 只展示快照正文 diff
- `reason` 如果只写在 `__metadata__` 中，不会进入普通字段差异

处理方式：

- 不修改 `core` 的审计页面
- 在 add-on 自己写快照时，把“重新激活原因”写进快照正文
- 这样原生 diff 会自动显示：
  - `重新激活原因: Not set -> xxx`

### 7. Python 2.7 测试环境不能使用 Python 3 的标准写法

现象：

- `importlib.util`
- `types.SimpleNamespace`

在 Linux 测试环境报错

根因：

- 当前项目运行环境是 Python 2.7

处理方式：

- 测试动态加载统一使用 `imp.load_source`
- 不使用 `SimpleNamespace`
- 测试桩用普通对象或普通模块替代

### 8. 调试日志容易污染最终交付

现象：

- 为了排查 UID、transition、请求参数，加了大量 `logger.info/warning/error`

风险：

- 虽然有助于定位问题，但会污染正式日志输出

处理方式：

- 问题定位完成后移除临时调试日志
- 只保留真正的业务逻辑与错误处理

### 9. live workflow 可能被错误补丁覆盖到只剩 Reactivate

现象：

- 页面上只剩 `Reactivate`
- 样品 `verified` 状态看不到 `publish`
- 分析项 `to_be_verified` 状态看不到 `verify`、`retest`、`retract`、`reject`
- 即使重新新建样品再走流程，按钮仍然不恢复

根因：

- 之前错误的 workflow 补丁不仅改坏了自定义 transition
- 还把数据库中的 live `state.transitions` 覆盖成了只剩 `reactivate`
- 部分关键原生 transition 对应的 `permission-map` 也被覆盖或丢失
- 由于 workflow 配置保存在站点数据库中，所以代码修好后，旧站点不会自动恢复

处理方式：

- 不能只看代码，必须同时检查 live workflow 数据库里的：
  - `state.transitions`
  - `state permission-map`
- 正确做法是：
  - 在 `setuphandlers.py` 中显式恢复关键状态的原生 transitions
  - 同时恢复 `publish`、`verify`、`retest`、`retract`、`reject` 等关键权限映射
- 对已受影响环境，需执行一次 `setup_workflows()` 并提交事务
- 如果数据库已经被覆盖坏到只剩 `reactivate`，必要时需先在 `debug` 中手工修正，再重跑补丁

补充说明：

- 新建样品不会自动修复这个问题
- 只要站点数据库里的 workflow 还是坏的，新对象也会继续使用错误的 workflow 配置

## 最终落地原则

- 不改 `core` 页面展示逻辑
- 审计原因由 add-on 写入快照正文，交给原生 `Changes` 自动显示
- 工作流回退逻辑按官方 workflow 实际能力做分支，不强行套不存在的 transition
- workflow 修复既要看 transitions，也要看 state permission-map
- 失败必须整体回滚，不能出现半成功状态
- 所有实现保持 Python 2.7 兼容

## 后续复用建议

- 新项目安装前，先确认 workflow 补丁确实已执行
- 旧环境升级时，要优先检查数据库中的 live workflow 是否已被历史错误补丁覆盖
- 涉及 workflow 审计展示时，优先考虑“把业务字段写进快照正文”，避免再去改 `core` 页面
- 涉及对象联动回退时，先确认官方 workflow 的真实 state/transition/guard，再写代码
