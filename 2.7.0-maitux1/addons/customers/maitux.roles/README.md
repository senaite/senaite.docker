# maitux.roles

INNOCARE 业务角色 / 分组 / 账号 初始化扩展，按角色定义批量创建 Plone 角色、组、用户并授权。

## 功能职责

- 角色定义见 `src/maitux/roles/config.py`（`ROLE_DEFINITIONS`）：
  - MethodAdministrator / InstrumentAdministrator / InventoryAdministrator
  - StabilityAdministrator / StabilityInventoryAdministrator
  - BusinessSystemAdministrator / ITSystemEngineer
- 每个角色 = 一个 Plone 角色 + 同名组 + 一个登录账号，授予预设权限（增量授权，不覆盖已有授权）。
- 初始密码统一 `DEFAULT_PASSWORD`（`Maitux=123456`，与容器环境保持一致，可在 config.py 修改）。
- `BusinessSystemAdministrator` 直接继承 `LabManager` 全部权限。
- 安装 / 卸载 setuphandlers（创建 / 删除 角色、组、用户，见 `setuphandlers.py`）。
- 首次请求钩子：在站点就绪后补跑安装步骤并提交。

## 依赖

- `senaite.core` / `senaite.lims`
- `plone.api`、`Products.CMFPlone`、`zope.processlifetime`
- **`INNOCARE.arextension`**（必需：`setup.py` `install_requires` 声明，且 profile 依赖 `profile-INNOCARE.arextension:default`）

**不依赖** `maitux.projects` / `maitux.hazardcategories` / 其它客户 ADD-ON。

## 安装注册（buildout）

```ini
[buildout]
develop += /opt/addons/customers/maitux.roles
eggs    += maitux.roles
[instance]
zcml    += maitux.roles
[plonesite]
profiles += maitux.roles:default
```

## 迁移 / 独立部署评估

**不能脱离 `INNOCARE.arextension` 独立部署**（`install_requires` + profile 依赖均指向它）。

目标环境顺序：**先 `INNOCARE.arextension:default`，再 `maitux.roles:default`**。对其它 maitux addon 无耦合。

> 注意：`StabilityAdministrator` / `StabilityInventoryAdministrator` 的权限引用了 `maitux.stability` 的权限字符串（`maitux.stability: Add Stability Plan Template`）。未安装 `maitux.stability` 时该权限授予不会失败（增量授权，权限不存在则跳过），但对应角色在稳定性模块相关权限上不会生效。如需这两类角色完整能力，应同时部署 `maitux.stability`。

## 卸载

- 执行 `maitux.roles:uninstall` profile 会删除角色、组、用户；确认后移除 `custom-addon.cfg` 三处注册。