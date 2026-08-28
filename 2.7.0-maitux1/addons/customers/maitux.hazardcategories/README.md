# maitux.hazardcategories

危害分类（Hazard Category / 样品性质字典）管理扩展，提供可编辑的危害分类维护列表与 AR 样品性质多选。

## 功能职责

- 内容类型 `HazardCategories`（容器）/ `HazardCategory`（分类项，见 `src/maitux/hazardcategories/content/`）。
- 控制面板（`browser/controlpanel.py`）：管理危害分类的展示表格（`hazard_categories_table.pt`）。
- 默认分类（见 `config.py` / `profiles/default/registry.xml`）：GHS01–GHS09、BIO01、RAD01、NIR01、MAG01、ELEC01、HSURF01、HOT01、STEAM01、COLD01、ASPH01，含中英文与图标路径。
- 种子数据 upsert（`setuphandlers.py`）：`ensure_hazardcategory_data_synced` 按 code 幂等写入默认分类；`ensure_setup_catalog_usage_scope_index` / `ensure_hazardcategories_in_setup_catalog` 维护 catalog 索引与列。
- 翻译工具（`translation.py`）：`translate_with_fallback` 提供本域回退翻译。
- 词汇工厂（`configure.zcml` / `utils.py`）：
  - `maitux.hazardcategories.vocabularies.UsageScope`
  - `...EditableHazardCategories`
  - `...ForReference`（reference 范围）
  - `...ForAR`（AR only 范围）
- 与 AR 关联：样品性质（SampleProperties）多选在 `INNOCARE.arextension` 的 AR 扩展中引用本 addon 词汇，范围 both + AR only。

## 依赖

- `senaite.core` / `senaite.lims`
- `plone.api`、`plone.app.registry`、`plone.supermodel`
- `zope.component`、`zope.interface`、`zope.i18n`
- `Products.CMFPlone`

**不依赖** `INNOCARE.arextension` / `maitux.projects` / `maitux.roles` 或其它客户 ADD-ON。

## 安装注册（buildout）

```ini
[buildout]
develop += /opt/addons/customers/maitux.hazardcategories
eggs    += maitux.hazardcategories
[instance]
zcml    += maitux.hazardcategories
[plonesite]
profiles += maitux.hazardcategories:default
```

## 安装顺序

本 addon **独立部署**，不再依赖 `INNOCARE.arextension`。历史 pickle 别名（`maitux.arextension.* -> INNOCARE.arextension.*`）已迁回 `INNOCARE.arextension` 自己的 `__init__.py`。

目标环境顺序：**先 `maitux.hazardcategories:default`，再 `INNOCARE.arextension:default`**（INNOCARE 的 AR 扩展字段 `SampleProperties` 运行期引用本 addon 的 HazardCategory 内容类型与词汇）。

## 卸载

- 执行 `maitux.hazardcategories:uninstall` profile 清理数据后，移除 `custom-addon.cfg` 三处注册。
