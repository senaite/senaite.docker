# maitux.projects

INNOCARE 项目（Project）管理扩展，仿 SENAITE Batches 的轻量项目内容类型与侧栏导航。

## 功能职责

- 新增内容类型 `Project` / 容器 `Projects`（见 `src/maitux/projects/content/`）：
  - 项目文件夹（`projects`），支持开启 / 关闭 / 取消 工作流状态（open/closed/cancelled）。
- 侧栏导航深度控制（`SIDEBAR_DEPTH`）。
- 与 AR 关联：项目字段在 `INNOCARE.arextension` 的 AR 扩展中作为 Reference 字段引用。
- 历史 pickle 别名兼容（`src/maitux/projects/__init__.py`：`INNOCARE.projects.* -> maitux.projects.*`）。
- 界面标题本地化：项目文件夹 / FTI 标题使用 MSG 并在运行时通过 `maitux.projects` catalog 翻译。

## 依赖

- `senaite.core`
- **`INNOCARE.arextension`**（必需，`setuphandlers.py` 引入其 `translate_with_fallback`，且 profile 声明依赖 `profile-INNOCARE.arextension:default`）

**不依赖** `maitux.roles` / `maitux.hazardcategories` / 其它客户 ADD-ON。

## 安装注册（buildout）

```ini
[buildout]
develop += /opt/addons/customers/maitux.projects
eggs    += maitux.projects
[instance]
zcml    += maitux.projects
[plonesite]
profiles += maitux.projects:default
```

## 迁移 / 独立部署评估

**不能脱离 `INNOCARE.arextension` 独立部署。** 原因：
1. `setuphandlers.py` 直接 `from INNOCARE.arextension.setuphandlers import translate_with_fallback`（运行时硬依赖）；
2. `profiles/default/metadata.xml` 声明 `<dependency>profile-INNOCARE.arextension:default</dependency>`。

因此在目标环境**先部署 `INNOCARE.arextension` 的 default profile，再部署 `maitux.projects`**。除此之外对其它 maitux addon 无耦合，可独立于 roles / hazardcategories 部署。

## 卸载

- 先卸载数据（建议执行 `maitux.projects:uninstall` profile），再移除 `custom-addon.cfg` 中三处注册。