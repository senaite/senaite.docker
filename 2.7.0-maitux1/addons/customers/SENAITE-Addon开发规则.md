# SENAITE Addon 开发规则（MaituxLIMS 产品环境）

> 从实际踩坑中沉淀的规则，适用于本产品环境下所有自研 addon
> （`medai.*` / `maitux.*`）。每条都注明**依据**与**违反后果**。
>
> 环境前提：SENAITE 2.x + Plone 5.2 + Python 2.7，addon 通过
> `package-includes/` slug 加载（非 buildout eggs 方式）。

---

## 一、ZCML 加载顺序（最容易踩、且症状最吓人）

### R1. 用到 SENAITE 自定义权限的注册，必须写在 `overrides.zcml`

**规则**：`browser:page` / `adapter` 等带 `permission=` 的注册，若权限来自
`senaite.core.permissions` 或 `bika.lims.permissions`（如
`ManageAnalysisRequests`、`ViewResults`、`FieldEditAnalysisResult`），
**只能写在 `overrides.zcml`，不能写在 `configure.zcml`**。

**依据**：容器内 `parts/instance/etc/site.zcml` 的加载顺序：

```
11  <include files="package-includes/*-meta.zcml" />
12  <five:loadProducts file="meta.zcml"/>
15  <include files="package-includes/*-configure.zcml" />        ← addon 的 configure
16  <five:loadProducts />                                        ← SENAITE 权限在这里才注册
19  <includeOverrides files="package-includes/*-overrides.zcml" />  ← addon 的 overrides
```

SENAITE 的自定义权限声明分散在 `bika/lims/browser/**/configure.zcml` 等文件里，
全部由**第 16 行**的 `five:loadProducts` 加载。而 addon 的 `configure.zcml` 在
**第 15 行**就执行了，此时权限尚未注册。

**违反后果**：`protectClass` 提前执行 → `ComponentLookupError(IPermission, ...)`
→ **Zope 直接启动失败**，整个站点起不来。

**安全的例外**：Zope 内置权限（`zope2.View`、`zope.Public`、
`cmf.ModifyPortalContent` 等）由第 6 行的 `Products.Five` 注册，
在 `configure.zcml` 阶段已可用，无此限制。

> 判断口诀：**权限字符串以 `zope2.` / `zope.` 开头 → configure 可用；
> 以 `senaite.core.` / `bika.lims.` 开头 → 必须 overrides。**

---

### R2. 新增 `overrides.zcml` 内容时，必须同步补 package-includes slug

**规则**：addon 首次往 `overrides.zcml` 写入实际内容时，
必须在 `package-includes/` 下补一个 `-overrides.zcml` slug，与 configure 成对。

**依据**：本环境每个 addon 需要**两个** slug 文件，缺一不可：

```
package-includes/
  10-<pkg>-configure.zcml   →  <include package="<pkg>" file="configure.zcml" />
  10-<pkg>-overrides.zcml   →  <include package="<pkg>" file="overrides.zcml" />
```

**违反后果**：整个 `overrides.zcml` **完全不被加载**，且
**不报任何错误**——viewlet 覆盖、视图注册全部静默失效，
表现为"改了没生效"，极难定位。

**易踩场景**：addon 初建时 `overrides.zcml` 往往只有一句
`<!-- Reserved for future overrides -->`，此时没有 slug 也无妨；
等某次真正往里写内容时，很容易忘了它从来就没被加载过。

---

## 二、GenericSetup Profile

### R3. 新增 profile 文件（`registry.xml` 等）必须重跑 profile 才生效

**规则**：往 `profiles/default/` 新增或修改 `registry.xml`、`workflows.xml`
等 GenericSetup 文件后，**对已安装的站点不会自动生效**，必须：

- 在 Add-ons 页面 **Uninstall → Install**，或
- 编写 upgrade step 并执行

**违反后果**：功能看似正常（若代码里有兜底默认值），但**配置项不出现在
控制面板中**——属于"静默降级"，交付方以为做完了，客户以为没做。

**要求**：部署文档中必须写明"已安装站点需重跑 profile"，
不得依赖代码兜底默认值蒙混过去。

---

### R4. `configure.zcml` 里注册的 profile，其目录必须真实存在

**规则**：`genericsetup:registerProfile` 声明的 `directory` 必须存在且含
`metadata.xml`，即使是空的 uninstall profile。

**违反后果**：ZCML 加载报错。

---

## 三、覆盖 SENAITE 原生组件

### R5. 覆盖同名组件用 `overrides.zcml`，不要用 `configure.zcml`

**规则**：替换 senaite.core 已注册的 viewlet / view / adapter（`name` 与
`manager`/`for` 完全相同）时，注册必须放在 `overrides.zcml`。

**依据**：`configure.zcml` 走 `include`（同名注册视为**冲突**），
`overrides.zcml` 走 `includeOverrides`（同名注册视为**覆盖**）。

**违反后果**：`ConfigurationConflictError`，启动失败。

---

### R6. 覆盖 viewlet 时优先"继承 + 只改必要方法"

**规则**：覆盖原生 viewlet/view 时，继承原类并只重写必需的方法，
不要整体复制实现。

**理由**：标题、图标、`available()`、折叠状态等行为可随 senaite.core
升级自动跟进，减少版本漂移。

**实例**：`LabAnalysesGroupedViewlet` 继承 `LabAnalysesViewlet`，
仅重写 `get_listing_view()` 与 `contents_table()`。

---

### R5b. 跨 addon「同接口+同名」adapter 必须进 `overrides.zcml`，避免双注册冲突

**规则**：两个（或多个）addon 若为**同一 interface + 同一 name** 注册 adapter
（如都注册 `IStockBatches → IGetStickerTemplates`），这些注册**只能放在
各自的 `overrides.zcml`**，不能都写在 `configure.zcml`。

**依据**：`configure.zcml` 走 `include`，同名注册视为**冲突**；只有
`overrides.zcml`（`includeOverrides`）才会把后者当作**覆盖**而非冲突。

**违反后果**：`ConfigurationConflictError` → **容器重启循环、Zope 启动失败**，
且是在 ZCML 加载阶段直接崩，站点完全起不来（易误判为镜像/网络问题）。

**实例**：`INNOCARE.labeldesign` 与 `maitux.stock` 同时为
`IStockBatches` 注册 `IGetStickerTemplates` 适配器，两套 `configure.zcml`
同时加载即冲突。把该注册移入 `overrides.zcml` 并补 `-overrides` slug 后恢复。

---

### R5c. 分发名与目录名大小写必须一致，且依赖 autoinclude 入口点而非手动 include

**规则**：addon 的 **egg 分发名（`setup.py` 的 `name`，如 `INNOCARE.Reportdesign`）
与代码目录名（如 `INNOCARE/Reportdesign`）必须大小写一致**；同时，若
`setup.py` 已配置 `z3c.autoinclude.plugin` 入口点，**不要再在
`custom-addon.cfg` 的 `[instance] zcml +=` 里手动 include 该包**。

**依据**：Windows 文件系统大小写不敏感。分发名与目录名大小写不一致时，
`meld`/buildout 可能把同一包识别成两个实例，导致 zcml 里的静态资源
（如 `plone:static type="worksheets"`）被加载两次。

**违反后果**：同资源重复注册 → `ConfigurationConflictError` → 启动失败；
或手动 include 与 autoinclude 双路加载导致重复注册。移除手动 include、
仅保留 autoinclude 入口点后恢复。

---

## 四、部署（8085 Docker 环境）

### R7. 同步用 `/E` 不要用 `/MIR`

```powershell
robocopy "<源>" "<目标>" /E /XF *.pyc /NFL /NDL /NJH /NJS
```

**理由**：`/MIR` 会删除目标端多出的文件，包括容器编译产生的 `.pyc`。
本场景只需增量更新，`/E` 足够且无删除风险。

**注意**：robocopy 退出码 0–7 均为成功，PowerShell 会将非零码判为失败，
可忽略或用 `if ($LASTEXITCODE -lt 8)` 判断。

---

### R8. 改动生效方式因文件类型而异

| 改动内容 | 生效方式 |
|---------|---------|
| `.py` | **必须重启容器** |
| `.zcml` | **必须重启容器** |
| `.pt` 模板 | 重启即可（Chameleon 按内容摘要自动失效缓存） |
| `.js` / `.css` | 重启 + **浏览器硬刷新 `Ctrl+Shift+R`** |
| `profiles/*.xml` | 重启 + **重跑 GenericSetup profile**（见 R3） |

**易踩点**：静态资源经 `++resource++` 提供，带长缓存头。
只重启容器不硬刷新，浏览器仍用旧 JS/CSS，表现为"代码改了没效果"。

---

### R8b. 决不用 root 进程往 `/data/cache` 写 Chameleon 缓存

**规则**：`CHAMELEON_CACHE=/data/cache`，Zope 实例以 `senaite` 用户运行，
缓存文件属主必须始终是 `senaite`。**禁止**用 root 身份（`docker exec` 默认 root、
或 `bin/interpreter` 直接以 root 跑诊断脚本）去渲染/编译模板——那样会把
**root 属主、mode `0600`** 的 `.py/.pyc` 写进缓存目录。

**依据**：
- Zope 以 `senaite` 运行；`/data/cache` 属主是 `senaite`。
- Chameleon 缓存文件名是模板哈希；模板失效后需重写同名文件。
- root 写入的文件 `-rw------- root`，`senaite` 既覆盖不了也删不掉。

**违反后果**：模板重新编译时对该哈希文件 `EACCES` →
`IOError: [Errno 13] Permission denied: '/data/cache/<hash>.py'`，
该模板（典型如标签预览）直接**加载失败、显示为空**，表现为"原来的预览都没了"，
看似是模板/代码问题，实则是缓存属主被 root 污染。

**修复 / 清理命令**（等价、可任选）：
```bash
# 清掉所有 root 属主的缓存条目（可再生，最干净）
docker exec maitux-lims find /data/cache -user root -delete
# 或收归 senaite（保留有效编译，避免全量重新编译）
docker exec maitux-lims find /data/cache -user root -exec chown senaite:senaite {} \+
```

**排查 root 残留**：
```bash
docker exec maitux-lims find /data/cache -maxdepth 1 ! -user senaite -ls
# 同时留意卡在 root 上的诊断进程，必要时 kill 掉（如挂起 90% CPU 的实例进程）
```

**实例**：某次用 root 跑 `/tmp/check_stickers.py` 诊断标签渲染，向缓存写入两个
root 属主文件，导致 `SampleNormal_40x30mm.pt` 及所有标签预览 `Permission denied`
全部失效；chown 收归 `senaite` 并终止该 root 进程后恢复。

---

## 五、通用原则

### R9. 本环境的失败大多是"静默"的，验证必须给可观测判据

本产品环境（尤其计算引擎）大量采用容错设计：求值失败保留原值、
异常被 `except: pass` 吞掉。因此：

- **不要用"看起来对不对"验收**
- 每项改动必须给出**具体可观测信号**：某个 HTTP 状态码、
  某个 DOM 属性、某个字段是否出值、某条日志

**已知的静默失效清单**（持续补充）：

| 现象 | 根因 |
|------|------|
| overrides 全部不生效 | 缺 package-includes slug（R2） |
| 控制面板无配置项 | 未重跑 profile（R3） |
| 前端改动无效果 | 浏览器缓存静态资源（R8） |
| 某计算字段永远空白 | 公式求值失败被静默吞掉 |
| 页面渲染成旧布局 | ZCML 中 `class` 与 `template` 并用，`__call__` 被 MRO 遮蔽 |
| 容器重启循环 / Zope 启动即崩 | 跨 addon 同接口同名 adapter 冲突（R5b）或分发名与目录名大小写不一致（R5c） |
| 模板/标签预览"没了"、报 `Permission denied /data/cache/…` | `/data/cache` 被 root 进程写入 root 属主缓存（R8b） |

---

### R10. 只改渲染，不碰数据与工作流

**规则**：新增视图/布局时，复用原生的保存端点、计算引擎与工作流适配器，
不自建 save adapter、不绕过 `IDataManager.set()`。

**理由**：计算引擎（含依赖重算）挂在原生保存链路上，绕开它会导致
计算不触发，且该问题不报错。

**实例**：AS-Grouped 布局复用 `ajax_set_fields` 端点与
`workflow_action_submit` 适配器，仅替换渲染模板。

---

## 附：新建 addon 检查清单

- [ ] `package-includes/` 下 configure + overrides **两个** slug 都建了
- [ ] 用到 senaite 自定义权限的注册，写在 `overrides.zcml`
- [ ] 覆盖原生同名组件的注册，写在 `overrides.zcml`
- [ ] 跨 addon 同接口同名 adapter，全部只落在 `overrides.zcml`（R5b）
- [ ] `setup.py` 分发名与代码目录名大小写一致；不手动 include 已配 autoinclude 入口点的包（R5c）
- [ ] `registerProfile` 声明的每个目录都真实存在且含 `metadata.xml`
- [ ] 新增 profile 文件后，部署文档写明"需重跑 profile"
- [ ] 部署说明区分了"重启"与"重启 + 硬刷新"
- [ ] 每项功能给出了可观测的验证判据
