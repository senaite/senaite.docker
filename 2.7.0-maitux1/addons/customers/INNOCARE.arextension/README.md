# INNOCARE.arextension

INNOCARE 检验申请（Analysis Request, AR）定制扩展包，是本项目多个客户 ADD-ON 的**公共基础层**。

## 功能职责

- **AR 字段扩展**（SchemaExtender，见 `src/INNOCARE/arextension/extenders/analysisrequest.py`）：
  - Project（关联项目）
  - SampleRecovery（样品回收，下拉 是/否）
  - SafetyPrecautions（安全注意事项/备注，多行文本）
  - SampleRetainer（样品留存）
  - RetentionTime（留存时间）
  - SampleStatus / StorageConditions / SampleProperties（基体、储存条件、样品性质）
  - 等字段的添加、显示与实际控件调整。
- **AR 新增页（ar_add2）右侧控件样式与去重**：右单元格控件顶对齐、隐藏冗余 label（CSS 见仓库根 `ar_add_align.css`、补丁见 `src/INNOCARE/arextension/patches.py`）。
- **字段标签/备注文案**：locale 目录 `en/zh/zh-cn/zh_CN` 遵循 ASCII msgid + `.po/.mo` 翻译（避免 `UnicodeEncodeError`）。
- **ID Server**（`src/INNOCARE/arextension/idserver.py`）：样品编号 `URs-025` 提供 `deptCode` 变量。
- **补丁**（`src/INNOCARE/arextension/patches.py`）：
  - senaite i18n `translate` 对其它 addon 域（`maitux.projects`、`maitux.hazardcategories`、`maitux.roles`）做附加域回退；
  - `AnalysisRequestAddView.get_input_widget` 对 AR 新增页右侧重复标签做清理；
  - `get_points_of_capture` 隐藏 Field Analyses 区块。

## 依赖

- `senaite.core` / `senaite.lims`
- `archetypes.schemaextender`
- `zope.interface`

**不依赖任何 `maitux.*` 或其它客户 ADD-ON**，是唯一可独立部署的基础层。

## 安装注册（buildout）

在 `custom-addon.cfg` 三处各加：

```ini
[buildout]
develop += /opt/addons/customers/INNOCARE.arextension
eggs   += INNOCARE.arextension
[instance]
zcml   += INNOCARE.arextension
[plonesite]
profiles += INNOCARE.arextension:default
```

源码挂载路径：容器内 `/opt/addons/customers`（仓库 `addons/customers`）。

## 迁移 / 独立部署评估

**可以独立部署迁移。** 该包对自身功能零外部定制依赖，迁移时：
1. 拷贝 `INNOCORE.arextension/` 目录（含 `src/`、`setup.py`、`ar_add_align.css`）到目标环境 `/opt/addons/customers/`；
2. 在目标 `custom-addon.cfg` 按上面三处注册；
3. 重新 buildout + 重启容器（.py/.po/.mo 变更需重启）即可。

> 注意：`ar_add_align.css` 目前是仓库内留档副本，功能样式注册在 senaite core 的 CSS 中。**镜像重建会丢失**——如需彻底持久化，应通过本 ADD-ON 的 GenericSetup profile（cssregistry）注册该样式，见项目根 `SENAITE-Addon开发规则.md` §3。

## 卸载

- 移除 `custom-addon.cfg` 中本包的三处注册；
- 若已导入 `INNOCARE.arextension:uninstall` profile 建议先执行卸载 profile 再移除。