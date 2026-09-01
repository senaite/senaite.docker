# maitux.hazardcategories

INNOCARE 危害分类（Hazard Category / 样品性质字典）管理扩展，提供可编辑的危害分类维护列表与 AR 样品性质多选。

## 功能职责

- 内容类型 `HazardCategories`（容器）/ `HazardCategory`（分类项，见 `src/maitux/hazardcategories/content/`）。
- 容器默认视图（`browser/controlpanel.py`）：用于 `hazard_categories` 内容容器内部维护危害分类展示表格（`hazard_categories_table.pt`），不在 `@@overview-controlpanel` 注册附加组件入口。
- 默认分类（见 `config.py` / `profiles/default/registry.xml`）：GHS01–GHS09、BIO01、RAD01、NIR01、MAG01、ELEC01、HSURF01、HOT01、STEAM01、COLD01、ASPH01，含中英文与图标路径。
- 词汇工厂（`configure.zcml` / `utils.py`）：
  - `maitux.hazardcategories.vocabularies.UsageScope`
  - `...EditableHazardCategories`
  - `...ForReference`（reference 范围）
  - `...ForAR`（AR only 范围）
- 与 AR 关联：样品性质（SampleProperties）多选在 `INNOCARE.arextension` 的 AR 扩展中引用本 addon 词汇，范围 both + AR only。
- 历史 pickle 别名兼容（`__init__.py`：`maitux.arextension.* -> INNOCARE.arextension.*`）。

## 依赖

- `senaite.core` / `senaite.lims`
- `plone.api`、`plone.app.registry`、`plone.supermodel`
- `zope.component`、`zope.interface`、`zope.processlifetime`
- `Products.CMFPlone`
- **`INNOCARE.arextension`**（必需：`__init__.py` 的 pickle 别名逻辑引入 `INNOCARE.arextension`，且 profile 依赖 `profile-INNOCARE.arextension:default`）

**不依赖** `maitux.projects` / `maitux.roles` / 其它客户 ADD-ON。

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

## 迁移 / 独立部署评估

**不能脱离 `INNOCARE.arextension` 独立部署**（`__init__.py` 运行时引入其模块 + profile 依赖）。

目标环境顺序：**先 `INNOCARE.arextension:default`，再 `maitux.hazardcategories:default`**。对其它 maitux addon 无耦合。

> 说明：`INNOCARE.arextension` 的 `defaults.py` 内置了与 `maitux.hazardcategories` 相同的默认分类数据，二者默认分类一致；功能归属上分类管理在本 addon，AR 侧引用词汇在 arextension。

## 卸载

- 执行 `maitux.hazardcategories:uninstall` profile 清理数据后，移除 `custom-addon.cfg` 三处注册。
