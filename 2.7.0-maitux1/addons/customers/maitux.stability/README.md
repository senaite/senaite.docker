# maitux.stability

MAITUX 稳定性研究（Stability Studies）扩展，提供稳定性研究的基础字典（储存条件、包装规格）、稳定性计划模板、稳定性计划（含时间点/检验标准明细），以及任务看板驱动的样品放置、关联样品、创建样品等流程。

## 功能职责

- 内容类型（见 `src/maitux/stability/content/`）：
  - `StabilityStudies`：稳定性研究根容器（侧边栏入口）。
  - `StorageCondition` / `StorageConditions`：储存条件字典。
  - `PackagingSpecification` / `PackagingSpecifications`：包装规格字典。
  - `StabilityPlanTemplate` / `StabilityPlanTemplates`：稳定性计划模板（样品数量、预留数量、附件等；可一键从模板创建计划）。
  - `StabilityPlan` / `StabilityPlans`：稳定性计划（起算时间 T0、存放数量、Plan Details 明细：包装规格/储存条件/放置方向/时间点/窗口期/检验标准或检验组合/检验数量/关联批次与样品）。
  - `StabilityTimepointTask`：时间点任务对象（由计划明细同步生成）。
  - `Task Board`：任务看板容器（自定义 layout）。
- 任务看板（`@@task_board`）：按计划明细展示时间点任务，支持状态筛选（全部/待放置/进行中/已完成）、计划搜索、按目标日期/窗口排序、逾期高亮与统计卡片，以及批量操作：样品放置、关联已有样品、创建样品。
- 流程页面：
  - `@@sample_placement`：为待放置任务选择库存批次（引用 `maitux.stock` 的 `StockBatch`）。
  - `@@link_sample`：为任务关联已有样品（AnalysisRequest）。
  - `@@create_sample`：按任务明细（检验标准/检验组合、批次）创建样品并写回关联。
  - `@@create_plan`：从计划模板跳转到新建计划并预填模板字段/附件。
- 计划同步：`subscribers.sync_plan_timepoint_tasks` 将 Plan Details 与 `StabilityTimepointTask` 双向同步，支持创建/更新/删除。
- 词汇：放置方向（Upright/Inverted/Horizontal）、计划/明细状态、月份时间点等。

## 依赖

- `senaite.core` / `senaite.lims`
- **`maitux.stock`**（样品放置需引用 `StockBatch`，setup.py 已声明依赖）
- `plone.api`、`plone.supermodel`、`plone.namedfile`
- `zope.component`、`zope.interface`、`z3c.form`

## 安装注册（buildout）

```ini
[buildout]
develop += /opt/addons/customers/maitux.stability
eggs    += maitux.stability
[instance]
zcml    += maitux.stability
[plonesite]
profiles += maitux.stability:default
```

安装后自动创建 `stability_studies` 侧边栏入口，及其子表（储存条件 / 包装规格 / 稳定性计划模板 / 稳定性计划 / 任务看板）。

## 双语翻译（i18n）

本 addon 使用独立的 i18n 域 `maitux.stability`，全部用户可见文案（列表标题/列名/按钮、schema 字段、任务看板、流程页面、portal 消息、侧边栏菜单标题）均通过该域的翻译目录解析，支持界面语言在中英文之间切换。

- `configure.zcml`：`<i18n:registerTranslations directory="locales" />` 注册翻译目录。
- 翻译目录：`src/maitux/stability/locales/{en,zh,zh-cn,zh_CN}/LC_MESSAGES/maitux.stability.po`（含已编译 `.mo`）。
- 侧边栏菜单标题回退：`INNOCARE.arextension` 的 `senaite.core.i18n.translate` 附加域回退列表已包含 `maitux.stability`。

## 更新说明（2026-08-31 · 双语翻译支持）

本次更新为该 addon 补充了完整的双语（中 / 英）翻译支持，遵循 `maitux.hazardcategories` 的 i18n 模式：

- `configure.zcml` 增加 `<i18n:registerTranslations directory="locales" />`。
- `__init__.py` 增加 `_` MessageFactory 别名（`maitux.stability` 域）。
- 全部 browser / content 模块的消息工厂由 `senaiteMessageFactory` 切换到本 addon 自有域（`from maitux.stability import _`），字符串按自身目录翻译。
- 新增中文翻译条目：列表标题/列名/状态页签（Active/Inactive/All）、任务看板（Expired/Pending Placement/In Progress/Completed、列头、搜索、批量按钮、TP 任务标题）、流程页面（Sample Placement / Link Existing Sample / Create Sample 及字段与提示）、schema 字段标题（时间点/窗口期/检验标准/检验组合/存放数量等）、portal 消息、文件夹/侧边栏标题（Stability Studies、Storage Conditions、Packaging Specifications、Stability Plan Templates、Stability Plans、Task Board 等），共 116 条 msgid。
- 模板补 `i18n:translate`：`task_board.pt`、`sample_placement.pt`、`create_sample.pt`、`link_sample.pt`、Plan Details datagrid；并修复了 `create_sample.pt` / `link_sample.pt` 中的乱码文本（原 GBK 乱码替换为可翻译的英文文案）。
- `setuphandlers.py` 的模块/子表标题改为 Message 对象，随界面语言翻译。
- 翻译目录 `locales/{en,zh,zh-cn,zh_CN}` 及编译后的 `.mo` 随包发布；重启实例即生效，无需重装 profile。

## 卸载

- 执行 `maitux.stability:uninstall` profile：仅从侧边栏移除 `stability_studies` 注册，不删除业务数据。

## 备注

- 任务看板直接读取计划（Plan）的 Plan Details 明细渲染，不依赖已生成的 Task 对象；Task 对象用于历史兼容与显式状态同步。
- 时间点按“月 × 30 天”计算目标日期，窗口期按天计算（`window_days`）。
- 样品放置 / 关联样品 / 创建样品页面均做服务端权限与状态校验。
