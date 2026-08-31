# INNOCARE.Reportdesign — 工作表打印报表 + COA 分析证书 说明

本文档汇总当前自定义打印报表的**数据组织**与**展示规则**。本 Addon 同时提供两类模板（按入口分布）：

| 模板名称 | Worksheet 打印（AS 分组） | Analysis Request 发布（开报告） | 目录 | 注册 type |
| --- | --- | --- | --- | --- |
| **数据报告** (`reportdesign.pt`) | ✅ `reportdesign:reportdesign.pt` | ✅ `reportdesign:reportdesign.pt` | `templates/print/` + `templates/reports/` | `worksheets` + **`senaite.impress.reports`** |
| **COA 初稿报告** (`coa.pt`) | ❌（仅 COA） | ✅ `reportdesign:coa.pt` | `templates/reports/` | **`senaite.impress.reports`** |

- **数据报告 · Worksheet 版**：`src/INNOCARE/reportdesign/templates/print/reportdesign.pt` / `.css`
  - 访问路径：`/lims/worksheets/WS-xxx/print?template=reportdesign:reportdesign.pt`
  - 数据源：SENAITE 内置 `PrintView#_ws_data` → 多 AR 分组
- **数据报告 · AR 发布版**：`src/INNOCARE/reportdesign/templates/reports/reportdesign.pt` / `.css`
  - 访问路径：`/lims/analysisrequests/AR-xxx/publish?template=reportdesign:reportdesign.pt`
  - 下拉显示：`reportdesign (reportdesign)`
  - 数据源：单 AR 对象 `context.getAnalyses(full_objects=True)` → 构造伪 `worksheet` 字典，视觉与 WS 版**保持完全一致**
- **COA 初稿报告**：`src/INNOCARE/reportdesign/templates/reports/coa.pt` / `.css`
  - 访问路径：`/lims/analysisrequests/AR-xxx/publish?template=reportdesign:coa.pt`
  - 下拉显示：`reportdesign (coa)`

---

## 1. 工作表数据报告（WS 版）— 数据组织（页面数据来源）

报表渲染单个 Worksheet，数据由 SENAITE 的 `PrintView#_ws_data` 提供的 `worksheet` 字典承载，模板通过 `view.getWorksheet()` 获取：

```
worksheet
├── id                工作表编号（如 WS-003）
├── url               工作表链接
├── laboratory        实验室信息
├── portal            门户信息（用于拼接资源 URL）
├── obj               原始 Worksheet 对象（访问行为字段，如 reviewer_userid）
├── date_created      创建时间
├── createdby         创建人 {email, fullname}
├── date_printed      打印时间
├── printedby         打印人 {email, fullname}
├── analyst           分析人 {email, fullname}
├── remarks           工作表级备注（可选）
└── ars               分析请求（AR）分组列表，每个元素：
    ├── position      AR 序号（如 1）
    ├── id            AR 编号（如 H2O260825001）
    └── analyses      该 AR 下的分析项（每个分析 = 一个检验项目）列表，每项：
        ├── obj             分析对象（访问临时字段 getInterimFields()、仪器 getInstrument()）
        ├── title           分析名称（如“有关物质-专属性”）
        ├── keyword         分析关键字
        ├── position        分析序号
        ├── formatted_result 格式化结果
        ├── formatted_unit  单位
        ├── formatted_specs 规格
        ├── formatted_uncertainty 不确定度
        ├── review_state    审核状态（assigned / verified / published 等）
        ├── remarks         分析备注（可选）
        └── retested        是否复测
```

### 1.1 临时字段（Interim Fields）解析与分类

对每个分析的 `getInterimFields()`（过滤 `hidden=True`），按字段值类型分成三类：

| 类型 | 判定条件 | 说明 |
| --- | --- | --- |
| 多值字段 `afields` | 值为 JSON 字符串（以 `[` 开头，`json.loads` 解析）得到列表，且列表中**至少有一个非空值** | 用于生成对照网格（每个位置一个值） |
| 单值字段 `sfields` | 值非空、非列表（字符串/数字等） | 以「标签 → 值」行展示 |
| 空值字段 | 值为空 / 全部为空列表 | 不展示 |

- `ncols` = 多值字段数量；`pcount` = 多值字段中最大的列表长度（位置数）。
- `hasgrid = ncols >= 1`：有至少一个多值字段时进入网格布局，否则进入简单行列布局。

---

## 2. 工作表报告 — 页面总体结构

```
header      ：右上角二维码 + 左侧实验室 LOGO + 工作表编号（h1）
subheader   ：五行元信息（见 2.1）
content     ：
  └─ AR 分组循环（ar-group 灰框）
       └─ 分析项循环（每个分析渲染一个 test-block 表格）
            ├─ 简单布局（无多值字段）：标签/值行 + Result 行
            └─ 网格布局（有多值字段）：转置对照表（见第 3 节）
  └─ 页脚（仅当 worksheet 有备注时显示）
```

### 2.1 表头/副表头

- **二维码**（右上角）：编码 `worksheet/id`（与原先条形码信息一致），由内联脚本调用 `jquery.qrcode` 渲染（`render=image, size=128, quiet=4`）。该脚本位于模板末尾，切换打印模板（AJAX 刷新内容）时会自动重绘。
- **LOGO**：实验室 LOGO（`portal_url + '/maitu-logo-png'`）。
- **副表头五行**：
  1. `Created on <时间> by <创建人>`
  2. `Printed on <时间> by <打印人>`
  3. `Analysed by <分析人>`
  4. `审核人 <全名>`：读取 `worksheet['obj'].reviewer_userid`，经 `portal_membership.getMemberById` 取全名（为空则不显示）
  5. `仪器 <名称列表>`：遍历所有 AR 下所有分析，去重排序仪器标题，逗号分隔

### 2.2 AR 分组

- 每个 AR 渲染一个 `ar-group` 灰框（边框 `#ccc`，内边距 8px）。
- 框内顶部 `ar-header`：灰底 `#dcdcdc` 标题条，含序号徽章（`badge`，深灰底白字）+ AR 编号。
- AR 内每个分析依次渲染独立表格（test-block），相互分隔。

---

## 3. 工作表报告 — 网格布局规则（多值临时字段对照表）

### 3.1 两种朝向（Orientation）

| | 朝向 A（默认，自然方向） | 朝向 B（转置） |
| --- | --- | --- |
| 行 | 每个位置（1..pcount）一行 | 每个字段一行 |
| 列 | 每个字段一列 + 首列 `#` | 每个位置一列 + 首列字段标签 |
| 首列宽 | `#` 列固定 **12mm**（约 6 个数字字符，规则：序号为行 = 6 字符） | 标签列固定 **lcol = 12.5 × 3.4mm = 42.5mm**（规则：字段为行 = 12.5 字符，由原 25 字符减半） |
| 数据列宽 | 剩余宽度按实际列数均分（估算 6 字符/字段 = 20.4mm） | 剩余宽度按实际列数均分（估算 (位数+4) × 2.1mm） |

> 首列宽度在 `<colgroup>` 中以毫米固定；数据列设为 `auto`，配合 `table-layout: fixed` 由浏览器按剩余宽度均分。

### 3.2 宽度计算（单位 mm）

```
cwC   = 3.4    中文/字段名字符宽度
cwN   = 2.1    数字字符宽度
padC  = 4      # 列/序号列两侧补位
pageW = 277.0  A4 横向页面可用宽度

maxplen = pcount 的位数
rowA    = (maxplen + padC) × cwN          → 朝向 A 首列估算宽（渲染固定 12mm）
colws   = 每个字段列 6 × cwC（=20.4mm）    → 朝向 A 数据列估算宽
wA      = rowA + Σ(colws)                 → 朝向 A 估算总宽
lcol    = 12.5 × cwC（=42.5mm）           → 朝向 B 标签列实际宽（colgroup 应用）
pcol    = (maxplen + padC) × cwN          → 朝向 B 位置列估算宽
wB      = lcol + pcount × pcol            → 朝向 B 估算总宽
```

> `wA` / `wB` 仅用于**朝向选择**；实际渲染列宽以 `colgroup` 固定首列 + 其余数据列均分为准。

**朝向选择**：默认 A；仅当 `wA > 277` **且** `wB < wA`（B 更窄且能装下多个位置列）时转置为 B。

### 3.3 表格列数与字号分级

按当前子表数据列数 `tcols`（A 向 = 字段数，B 向 = 位置数）套用字号类：

| 类名 | 条件 | 效果 |
| --- | --- | --- |
| `cols-small` | tcols ≤ 6 | 正常字号 |
| `cols-mid` | tcols ≤ 12 | 列头字号 0.9em |
| `cols-many` | tcols > 12 | 列头/值字号 0.75em，列头允许换行 |

### 3.4 分页（列超出单页容量时拆分子表）

- 单页最大数据列数 `nper`：**朝向 A = 9 列，朝向 B = 7 列**。
- 子表数 `ngrp = ceil(tcols / nper)`；首列固定，后续数据列**按实际宽度均分**，**最后一页保持自身均分**。
- 拆分子表时，标题行追加分组范围提示，如 `有关物质-xxx (1-9)`。
- `colspan` 均按当前子表实际数据列数计算（`min(nper, tcols - gi*nper)`）。

### 3.5 可跨页表格（Tall / Breakable）

- 判定：`trows + 3 > 24`（A 向 trows = 位置数；B 向 trows = 字段数）。
- 跨页表格：`page-break-inside: auto`，`<thead>` 表头（标题行 + 列名行）在**每页顶部重复**。
- 每页表格片段底部渲染 `<tfoot>` 分隔线（`tfoot-line`，1px `#666`），提示表格在下一页继续；1px 与网格线同粗细，避免重叠加粗。
- Result 行 `page-break-inside: avoid`，保证不被拆到两页。

### 3.6 网格表格结构

```
thead：test-head 标题行（灰底，深灰边框 #666）
       └─ cols-head 列名行（A：字段名；B：#1 #2 …；浅灰底 #e8e8e8）
tbody：interim-row 数据行（边框 #ddd）
       └─ 单值字段行（仅最后一个子表，colspan 到实际列数）
       └─ result-row 结果行（浅灰底 #f5f5f5，边框 #999，colspan 到实际列数）
       └─ remarks-row 分析备注行（仅当有备注）
tfoot：tfoot-line 分页下划线（仅 breakable 表格）
```

---

## 4. 工作表报告 — 简单布局规则（无多值字段）

当分析没有任何多值字段时，渲染普通两列表格：

```
test-head ：序号 + 分析名称
interim   ：每个单值字段一行「标签 → 值」
result-row：Result 行，含结果、Unit / +/- / Specification 元信息
remarks   ：备注行（可选）
```

---

## 5. 工作表报告 — 结果与状态样式

- `Result` 行内结果值：待定/未完成状态（assigned 等）为**斜体**；`verified` / `published` 状态为**加粗**。
- 结果行下方元信息（有则显示）：`Unit`、`+/-`（不确定度）、`Specification`（规格），以 `rmeta` 小块展示。
- 复测标注：分析标题后追加 `(retested)`（灰色小字）。

---

## 6. 工作表报告 — 样式与打印要点

- 页面：A4 横向（`@page size: A4 landscape`），页边距 `10mm 10mm 12mm 10mm`，内容宽 `277mm`。
- 表格：`width:100%`、`border-collapse: collapse`；网格表 `table-layout: fixed`。
- 配色：网格线 `#ddd`，表头 `#666`/`#f0f0f0`，列名 `#e8e8e8`，Result `#999`/`#f5f5f5`，AR 框 `#ccc`。
- 页脚：仅当工作表有备注时显示（避免空页脚导致多余空白页）。
- 已知现象：毫米单位 + `table-layout: fixed` 使边框落在亚像素位置，屏幕预览时 1px 线因抗锯齿显得偏粗；**实际打印/PDF 为清晰 1px**，属正常现象。

---

## 7. 工作表报告 — 技术依赖与注意事项

- 审核人字段依赖 `maitux.reviewerassignment` 行为（`reviewer_userid`），其模块已在插件中通过 `ModuleSecurityInfo` 开放模板内安全导入。
- 二维码依赖页面加载 `thirdparty.js`（内含 `jquery.qrcode`）；模板内联脚本在内容注入（含 AJAX 切换模板）后执行，保证二维码重绘。
- 临时字段值若以 `[` 开头的字符串，需经 `json.loads` 解析为列表后再判断多值/单值。

---

## 7b. 数据报告（AR 发布版）— 结构与字段映射

**用途**：在 Analysis Request（请验单）→ **Publish 发布视图**下的可用模板下拉中，和 COA 并列显示 `reportdesign (reportdesign)`。上下文是**单个 AR**，通过 `context.getAnalyses(full_objects=True)` 取分析项列表后，构造一个**与 WS 版同形的 `pseudo_ws` 字典**（单 AR、单组 `ars_pseudo[0]`），以便渲染出和 Worksheet 版数据报告**视觉上完全一致**（A4 横向、二维码右上角、LOGO、五行副表头、AR-group 灰框 + 位置徽章、test-block 网格/简单布局、结果状态样式、分页脚注）。

### 7b.1 页面数据来源（pseudo_ws 字段对应）

| pseudo_ws 字段 | AR 对象取值逻辑 |
| --- | --- |
| `id` / `url` | `getClientReference()`（无则回退 `ar.getId()`） / `ar.absolute_url()` |
| `laboratory.url` / `portal.url` | `portal_url.absolute_url()` 即门户根 |
| `obj` | 原始 AR 对象 |
| `date_created` | `ar.created()` → `YYYY-MM-DD HH:MM` |
| `createdby.fullname` | `ar.Creator()` → 成员全名；缺失回退当前登录打印人全名 |
| `date_printed` / `printedby` | 实时 `DateTime.DateTime()`（当前登录人打印） |
| `analyst.fullname` | `ar.getAnalyst()` → 取成员全名；缺失回退为打印人全名 |
| `instruments` | 遍历本 AR 所有分析 → `getInstrument().Title()` 去重排序后 `, ` 拼接 |
| `ars_pseudo[0].position` | 徽章固定显示 `1`（请验单只有一组） |
| `ars_pseudo[0].id` | AR 编号（与标题条显示一致） |
| `ars_pseudo[0].analyses[i] dict` | `_analysis_dict()` 统一构造（见 § 7b.2） |

### 7b.2 分析项字典字段取值兜底（空值不炸 TAL）

```
_analysis_dict
├── title                   getTitle()
├── keyword                 getKeyword()
├── formatted_result        先 getFormattedResult() → 其次 str(getResult()) → 再其次 ''
├── formatted_unit          先 getFormattedUnit() → 其次 str(getUnit())
├── formatted_specs         先 getFormattedSpecs() → 其次 getSpecification()
├── formatted_uncertainty   getFormattedUncertainty()
├── review_state            getReviewState()，回退 'assigned'
├── remarks                 getRemarks()
├── retested                getRetested() 布尔值
└── position                i+1（按 1,2,3... 顺序显示）
```

- 注册：仍使用同一 `<plone:static type="senaite.impress.reports" name="reportdesign">`（senaite.impress **不接受** `type="reports"`，必须精确匹配 Impress 自身注册的 `senaite.impress.reports`；指向 `templates/reports/`，本目录内同时包含 `reportdesign.pt/.css` + `coa.pt/.css` 两份模板对）。

---

## 8. COA 分析证书（初稿报告）— 页面结构

COA 报告用于 Analysis Request（AR）发布时的打印，渲染为 A4 纵向两页（含签名页），采用**中英文双语标签**（每个字段上方中文、下方英文），严格匹配 FORM-0000553 V2.0 模板。

```
Page 1（分析证书正文）
├── doc-meta        文件编号 FORM-0000553 + 版本 V2.0（右上角）
├── company-header  INNOCARE LOGO + 诺诚健华公司名（中英双语）+ 地址（中英双语）
├── report-id       报告编号 COA-<BatchNo>-<YYYYMMDD>
├── cert-title      "分析证书 / Certificate of Analysis"（大标题居中）
├── meta-table      8 行×2 列成对元信息表（见 § 8.1）
├── analyses-table  4 列检测项目表（见 § 8.2）
├── conclusion      结论区（双语默认文本，合格判定）
└── ref-block       对照品赋值表格（仅对照品 COA 用到，默认留空）

Page 2/3（版本历史 + 签名页）
├── report-id       同 Page 1 的报告编号
├── version-table   版本历史表（版本号 / 修改内容 / 生效日期）
└── sig-block       起草人、审核人、批准人签名及日期（3 行）
```

### 8.1 元信息表（meta-table）字段映射

| 位置 | 中文标签 | 英文标签 | AR 字段来源（INNOCARE.arextension） | 默认值 |
| --- | --- | --- | --- | --- |
| (1,1) | 项目号 | Project ID | `ProjectNo`（→ Project 对象 Title） | `N/A` |
| (1,2) | CoA版本号 | CoA Version | `getCoAVersion()` 访问器 | `V1.0` |
| (2,1) | 化合物编号 | Compound ID | `MaterialCode` | `N/A` |
| (2,2) | 批数量 | Batch Size | `Quantity` + 空格 + `Unit` | `N/A` |
| (3,1) | 物料名称 | Material Name | `MaterialName` | `N/A` |
| (3,2) | 生产日期 | Manufacture Date | `ManufactureDate`（格式 `YYYY.MM.DD`） | `N/A` |
| (4,1) | 批号 | Batch Number | `ClientReference`（被 arextension 重命名为 Batch No） | AR ID |
| (4,2) | 检测日期 | Test Date | `DatePublished` → `YYYY.MM.DD` | `N/A` |
| (5,1) | 规格 | Strength | `Strength` | `N/A` |
| (5,2) | 复检日期 | Retest Date | `RetentionTime` | `N/A` |
| (6)   | 生产企业 | Manufacturer | 预留（目前 `N/A`，需后续补字段） | `N/A` |
| (7)   | 储存条件 | Storage Conditions | `StorageConditions`（→ 对象 Title） | `N/A` |
| (8)   | 备注 | Comment | `SafetyPrecautions` | `N/A` |

### 8.2 检测项目表（analyses-table）字段

模板调用 `context.getAnalyses(full_objects=True)` 遍历 AR 下所有分析对象：

| 列 | 中文 | 英文 | 数据来源 |
| --- | --- | --- | --- |
| 1 (34%) | 检测项目 | Testing Item | `a.Title()` |
| 2 (18%) | 方法 | Method | `a.getInstrument().Title()`，无仪器则显示 `—` |
| 3 (24%) | 可接受标准 | Accept criteria | `a.getFormattedSpecs()`，未配置则显示 `报告 / Report` |
| 4 (24%) | 结果 | Results | `<formattedResult> <Unit> +/- <Uncertainty>`，未填显示 `N/A` |

### 8.3 签名与版本历史

- **起草人（Drafted By）**：`context.Creator()` → `portal_membership.getMemberById(...).getProperty('fullname')`，日期为 AR 创建日期
- **审核人（Reviewed By）**：遍历所有 published 分析的 `getVerificators()`，取第一个并解析全名；日期使用 DatePublished
- **批准人（Approved by）**：当前留空（等待后续业务确认批准人来源）
- **版本历史表**：内容留空，供发布后手工填入或后续接入文档管理系统

---

## 9. COA 报告 — 样式要点

- 页面：A4 纵向（`@page size: A4 portrait`），页边距 `14mm 14mm 16mm 14mm`，内容宽 `182mm`
- 字体：中文字体 `SimSun / Songti SC`，英文及数字优先 `Times New Roman`；标题加粗、英文标题统一 *italic*
- 表格边框：全部 `1px solid #000`（打印级细实线）
- 双语标签对齐：中文行字号 10-10.5pt 加粗，英文行字号 8-9pt 深灰，行间距紧凑避免行高溢出
- 分析证书大标题：中文 22pt + 字距 3mm；英文 17pt 斜体
- 页码：通过 `@page` 分页控制（`coa-page` 类自动 page-break），不显示页码号（符合 FORM-0000553 原表）
- 签名区：`margin-top: 60mm`，下划线为 `border-bottom` 实体线，防止打印时断线

---

## 10. COA 报告 — 技术注意事项

1. **注册方式**：`configure.zcml` 中新增 `<plone:static directory="templates/reports" type="reports" name="reportdesign" />`，与 worksheets 成对；**无需**单独 package-includes slug（未使用权限）
2. **扩展字段兜底**：所有自定义字段均通过 `get_field_text()` 辅助函数统一处理；字段未配置 / 值为空时回退 `N/A`，避免 TAL `Undefined` 崩溃
3. **UIDReference 字段解析**：`ProjectNo` / `StorageConditions` 需先 `getRaw(ar)` 取对象再 `.Title()`，不得直接字符串化（否则拿到 UID）
4. **日期格式统一**：所有日期强制 `YYYY.MM.DD`（点分隔，带 0 前缀），与原 FORM 模板示例一致
5. **对照品条件判断**：当前对照品标识逻辑未接入业务字段，`ref-block` 固定显示（值为空）；后续可增加 `is_reference_standard` 字段按条件渲染
6. **Install / Reinstall**：因仅 ZCML 注册 + 静态资源，修改后重启 Zope 即可，无需重跑 GenericSetup profile
7. **模板缓存**：修改 `.pt`/`.css` 后通常无需重启容器，Chameleon 自动检测文件 mtime 重编译；若界面未生效，清空 `/data/cache/*` 并强制刷新（Ctrl+F5）即可。
