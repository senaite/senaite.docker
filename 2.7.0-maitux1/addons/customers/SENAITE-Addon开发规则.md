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

**等价写法（推荐给已经写在 `configure.zcml` 里的注册）**：在本包的 `configure.zcml`
顶部 `<include package="senaite.core.permissions" />`，把权限的注册顺序钉在自己前面。
`custom-addon.cfg` 的显式 slug 和 autoinclude **都不保证**本包排在 `senaite.core`
之后（2026-08-28 实测两种都会炸），所以这一行是 addon 自己的责任。
`maitux.esignature` / `maitux.instrument_acquisition` 一直这么写；
`maitux.audittrail` / `groupmanagement` / `reviewerassignment` / `worksheet`
当天补上后启动恢复。

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

### R4b. 合规类 addon 可豁免卸载能力，但**必须**换成强制可升级

**背景**：`CLAUDE.md` §5 把 `profiles/uninstall/` 列为硬要求
（「卸载能力是硬要求」）。**合规类 addon 是唯一的豁免类别。**

**什么算合规类**：功能本身承担 GMP / 21 CFR Part 11 等法规义务，
被关闭即等于违规。典型是审计追踪、电子签名。
**判据不是「重要」，而是「按法规不允许被用户关闭」** ——
不要拿这条给普通功能包开口子。

**豁免的是什么**：可以不提供 `profiles/uninstall/`。理由通常有两条：

1. 法规上该能力不得被用户关闭；
2. 技术上 profile 卸不掉包外的状态（如自建的 PostgreSQL 表、外部文件），
   给一个卸不干净的「卸载」按钮，比没有按钮更危险 ——
   它让人以为卸干净了。

**★ 换来的义务（这半句同样是硬要求）**：

普通 addon 可以靠「Uninstall → Install」回到干净状态（见 R3）。
豁免掉卸载，就等于**放弃了唯一的兜底逃生口**，此后只剩升级一条路。所以：

- **`upgrades/` 必须从第一版就建起来并验证过一次**，
  不能等「真要改了再说」—— 那时已经没有退路了。
  哪怕 v1 无实际变更，也要造一个空 step，确认后台能看到、能执行。
- **profile 的任何后续变更只能走 upgrade step**，
  不得依赖「重装一次就好了」。
- **若包在 ZODB 之外还有状态**（自建表、外部文件），
  必须有**幂等的**迁移机制，且**不能只挂在站点级 upgrade step 上** ——
  多站点 / 多数据库形态下它升不全。
  推荐做成运行时惰性检查（用时比对版本号并补齐）。
- 包 `README` **首段**必须写明「本包不提供卸载能力」及理由、
  停用的正确做法、以及包外状态如何处置。

**违反后果**：
- 只豁免不补升级 → 第一次要改表 / 改 profile 时无路可走，
  只能手工进库改，且各站点状态从此发散。
- README 不写 → 下一个人把缺失的 `profiles/uninstall/` 当疏漏「补」回来，
  合规豁免被静默撤销。

**现有实例**：`maitux.auditjournal`（首例，详见
`Docs/auditlog-journal-实施方案.md` §8.3 / §8.4）。
截至该包引入前，4 个 common addon 与全部 customers addon **都有**卸载 profile。

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

### R5d. `custom-addon.cfg` 是自动生成的，不要手工改

**规则**：客户 add-on 的 buildout 配置**不再手工维护**。容器启动时
`/gen-custom-addon.sh` 会先删除旧的 `custom-addon.cfg`，再遍历
`/opt/addons/customers` 重新生成。addon 作者要做的只是把
`setup.py` 写对：

| 生成项 | 来源 |
|---|---|
| `develop +=` | 一级子目录名（必须含 `setup.py`，否则整个目录被跳过） |
| `eggs +=` | `setup.py` 的 `name=`（不是目录名） |
| `[instance] zcml +=` | 每个有 `configure.zcml` 的包都写；分发名与代码目录大小写不一致的除外（R5c） |
| `<egg>-overrides` slug | 包里存在 `overrides.zcml` 就自动补（R2 / R5b） |

**依据**：手工维护这份 cfg 的三类事故——写错包名、漏写 `-overrides` slug、
物理删掉 add-on 目录但忘了从 cfg 剔除（→ buildout 失败 → 容器无限重启）——
都是"人写清单"造成的，改成从磁盘现状推导即可根除。

**违反后果**：手改的内容下次启动就被覆盖，且会误导后来人以为配置是手写的。

**注意**：`[plonesite] profiles` 不会被生成，profile 一律在后台
`prefs_install_products_form` 手工安装（原因见 `README.md`）。

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

---

### R9b. `actions.xml` / `controlpanel.xml` 里的 `title` / `description` 必须 ASCII

**规则**：**portal action 类**的 GenericSetup XML（`actions.xml`、
`controlpanel.xml`）里的 `<property name="title">` / `<property name="description">`
**不得包含中文或任何非 ASCII 字符**。要中文界面，写 ASCII msgid +
在 `locales/` 里给 `zh_CN` 翻译（`senaite.impress` 就是这么做的）。

> **范围为什么只到 action 类**：`types/*.xml` 有**活的反例** ——
> `maitux.reviewerassignment` 的 FTI 用中文 title + `i18n:domain`，
> 在生产里正常显示（侧边栏「审核工作表」）。`TypesTool.Title()` 同样会走
> `Message()`，两者的差别在**导入器把值存成 unicode 还是 utf-8 字节串**，
> 未挖到底。**所以本规则只覆盖有实测事故的这一类，不做过度概括** ——
> 宁可范围窄一点，也不要让 lint 对着能跑的代码报警（一旦开始误报，
> 人就会开始忽略它）。

**依据**（2026-08-31 实测事故，含事后订正）：

```python
# Products/CMFCore/ActionInformation.py
80:   i18n_domain = 'cmf_default'          # ← 类默认值，几乎总是真值
161:  elif self.i18n_domain and id in ('title', 'description'):
162:      val = Message(val, self.i18n_domain)
```

`zope.i18nmessageid.Message` 是 **unicode 的子类**，拿它去包一个含中文的
**字节串**，Py2 会隐式按 ASCII 解码 → `UnicodeDecodeError`。

> **★ 订正**：最初以为触发条件是"**你设了** `i18n_domain` + 非 ASCII"。
> 实测不是 —— `Action` 的 `i18n_domain` **有类默认值 `'cmf_default'`**，
> 所以那个 `if` 几乎恒为真，`Message()` 总会被调用。
> **结论更强：`actions.xml` 里的中文标题必炸，没有"不设 domain 就安全"这条路。**

**另一个相关的坑（同日实测）**：`i18n:domain="..."` 这个 **XML 属性设不了域** ——
CMFCore 的 actions 导入器**只在导出时**写 `xmlns:i18n`
（`exportimport/actions.py:110`），导入时根本不读它。
要让标题走本包的翻译，必须显式写：

```xml
<property name="i18n_domain">你的包名</property>
```

不写就用默认的 `cmf_default` 域，于是拿你的 msgid 去别人的域里查 ——
查不到，界面显示英文原文，**而且不报错**。

**违反后果**：若该 action 落在 `user` / `site_actions` 分类，
**personal bar 每个页面都渲染 → 整站多数页面打不开**。
`maitux.auditjournal` 的 v3 profile 就是这么把 `/Care` 站点搞崩的。

**★ 最阴的地方：它是渲染期才炸的。**
lint 过、镜像建成、实例正常起、启动日志干净、`verify` 全绿 ——
**只有真人打开页面才炸**。这是 R9「静默失效」的一个变体：
不是没报错，是**报错时机晚到所有自动判据之后**。

**已有防线**：`lint_addon.py` 的 `E14_NON_ASCII_GS_TITLE` 会扫
`profiles/**/*.xml` 拦下它（2026-08-31 加，已用真实故障回放验证过）。

**踩到之后怎么救**：坏 action 存在**站点的 ZODB 里**，重建镜像不会清掉它。
Plone 页面全崩时走 ZMI（不渲染 personal bar）：
`<site>/portal_actions/user/manage_main` → 勾选 → Delete；
再用 upgrade step 重新导入修好的 `actions.xml`。

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
- [ ] `setup.py` 有正确的 `name=`（egg 名由它生成，不是目录名），目录直接放在 `addons/customers/` 一级下（R5d）
- [ ] `registerProfile` 声明的每个目录都真实存在且含 `metadata.xml`
- [ ] 有 `profiles/uninstall/`；**若属合规类要豁免，则 `upgrades/` 已建起并验证过一次，且 README 首段写明理由（R4b）**
- [ ] 包在 ZODB 之外若有状态（自建表 / 外部文件），迁移机制幂等且不只挂在站点级 upgrade step 上（R4b）
- [ ] 新增 profile 文件后，部署文档写明"需重跑 profile"
- [ ] 部署说明区分了"重启"与"重启 + 硬刷新"
- [ ] 每项功能给出了可观测的验证判据
