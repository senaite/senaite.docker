# INNOCARE.Reportdesign — 工作表打印报表（AS 分组布局）说明

本文档汇总当前自定义打印报表（`reportdesign.pt` / `reportdesign.css`）的**数据组织**与**展示规则**。

- 模板文件：`src/INNOCARE/reportdesign/templates/print/reportdesign.pt`
- 样式文件：`src/INNOCARE/reportdesign/templates/print/reportdesign.css`
- 访问路径：`/lims/worksheets/WS-xxx/print?template=reportdesign:reportdesign.pt`

---

## 1. 数据组织（页面数据来源）

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

## 2. 页面总体结构

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

## 3. 网格布局规则（多值临时字段对照表）

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

## 4. 简单布局规则（无多值字段）

当分析没有任何多值字段时，渲染普通两列表格：

```
test-head ：序号 + 分析名称
interim   ：每个单值字段一行「标签 → 值」
result-row：Result 行，含结果、Unit / +/- / Specification 元信息
remarks   ：备注行（可选）
```

---

## 5. 结果与状态样式

- `Result` 行内结果值：待定/未完成状态（assigned 等）为**斜体**；`verified` / `published` 状态为**加粗**。
- 结果行下方元信息（有则显示）：`Unit`、`+/-`（不确定度）、`Specification`（规格），以 `rmeta` 小块展示。
- 复测标注：分析标题后追加 `(retested)`（灰色小字）。

---

## 6. 样式与打印要点

- 页面：A4 横向（`@page size: A4 landscape`），页边距 `10mm 10mm 12mm 10mm`，内容宽 `277mm`。
- 表格：`width:100%`、`border-collapse: collapse`；网格表 `table-layout: fixed`。
- 配色：网格线 `#ddd`，表头 `#666`/`#f0f0f0`，列名 `#e8e8e8`，Result `#999`/`#f5f5f5`，AR 框 `#ccc`。
- 页脚：仅当工作表有备注时显示（避免空页脚导致多余空白页）。
- 已知现象：毫米单位 + `table-layout: fixed` 使边框落在亚像素位置，屏幕预览时 1px 线因抗锯齿显得偏粗；**实际打印/PDF 为清晰 1px**，属正常现象。

---

## 7. 技术依赖与注意事项

- 审核人字段依赖 `maitux.reviewerassignment` 行为（`reviewer_userid`），其模块已在插件中通过 `ModuleSecurityInfo` 开放模板内安全导入。
- 二维码依赖页面加载 `thirdparty.js`（内含 `jquery.qrcode`）；模板内联脚本在内容注入（含 AJAX 切换模板）后执行，保证二维码重绘。
- 临时字段值若以 `[` 开头的字符串，需经 `json.loads` 解析为列表后再判断多值/单值。
- 修改 `.pt`/`.css` 后无需重启容器：Chameleon 模板自动重编译；若未生效，清空 `/data/cache/*` 并强制刷新（Ctrl+F5）。
