# Maitux Calculation Enhancement for SENAITE LIMS

为 SENAITE LIMS 的计算公式（Calculation）模块增加三种新的 Interim Field 控件类型，支持 HPLC 含量测定、装量差异、杂质含量等复杂计算场景。

**版本：** 1.4.0
**兼容：** SENAITE 2.x（实测 2.7.0 / Plone 5.2 / Python 2.7）

---

## 1.4.0 更新概要（2026-08-25）

### 命名空间

包名由 `medai.*` 改为产品统一的 **`maitux.*`**：`maitux.calcenhance` /
`maitux.worksheet`。已有环境的 ZODB 需要一次迁移（4 条 profile 记录、
2 个 quickinstaller 对象、1 条 registry key），脚本见 `ISSUES.md` ISSUE-028。
全新环境从零安装即可，无需迁移。

### TIME_ELAPSED_HOURS 新增第三个参数：基准时间

```
TIME_ELAPSED_HOURS([时间数组], 小数位数, 基准时间)
```

基准时间可以来自**另一个分析**。溶液稳定性要的是「距对照品进样多少小时」，
而不是「距第一个质控点多少小时」—— 两者差一个常数，写错了整列都偏，
而每个值看上去都很正常。详见下方章节。

**向后兼容**：不传第三个参数时行为与 1.3.x 完全一致。

---

## 1.3.1 更新概要（2026-08-24）

### 修复：LOOKUP 目标字段现在会当场刷新

改动源字段并保存后，LOOKUP 过来的字段**在界面上立即更新**，不再需要刷新页面。

在此之前：值在数据库里保存那一刻就是对的，但屏幕上还是旧的 —— 存储值和显示值
互相矛盾，比其中任何一个单纯错了都更糟。详见 `ISSUES.md` ISSUE-027。

---

## 1.3.0 更新概要（2026-08-24）

### 函数表规模

| | 条目 | = 常量 | + 函数 |
| -- | ---- | ---- | ---- |
| CalculatedList `_SAFE` | **52** | 3 | **49** |
| 标量 `safe_globals` | 24 | 3 | 21 |

较 v1.2.0：CalculatedList 51 -> 52（新增 `SHIFT`）。标量表未变动。

### 新增函数（1 个）

| 函数 | 用途 |
| ---- | ---- |
| `SHIFT` | 取同一列**相邻行**的值。为色谱分离度表而加 —— 与后峰分离度就是与前峰分离度往下串一行 |

### 修复

| 项 | 内容 |
| -- | ---- |
| **文本型标量对数组引擎可见** | 数组引擎的标量容器原先只装 `float`，文本标量（如主成分名称）被丢掉，导致 `RESULT_NUM` / `INDEX_BY` / `LOOKUP` 这类**按名称匹配**的函数在 CalculatedList 里拿不到名称。详见 `ISSUES.md` ISSUE-024 |
| **`LOOKUP` 一行源按 key 匹配** | 源字段是标量（一行）时，真 key 现在必须匹配得上；`""` / `0` 的「给我那唯一值」写法不受影响。详见 ISSUE-022 |

### 新增文档章节

- **TIME_ELAPSED_HOURS 接受的时间格式** —— 斜杠日期（`2026/5/13 20:47`）**不被识别**，是最常见的坑

---

## 1.2.0 更新概要（2026-08-21）

本轮以**修正错值**为主，不是加功能。核心一句：
**凡是「算不出来」的地方，一律给 `---`，绝不给一个看起来合理的数字。**

### 函数表规模

| | 条目 | = 常量 | + 函数 |
| -- | ---- | ---- | ---- |
| CalculatedList `_SAFE` | **51** | 3 | **48** |
| 标量 `safe_globals` | **24** | 3 | **21** |

较 v1.1.0：CalculatedList 50 → 51（新增 `COALESCE`），
标量 23 → 24（同样新增 `COALESCE`）。

### 新增函数（1 个）

| 函数 | 用途 |
| ---- | ---- |
| `COALESCE` | 一个字段要从**多个来源**取值时，取第一个有值的；来源之间打架会告警 |

### 行为变更（重要，配置可能需要配合）

| 项 | 变更 | 需要做什么 |
| -- | ---- | ---------- |
| **求值顺序** | 由「先全部标量、再全部数组」改为**按字段定义顺序**一趟前向求值 | 见「求值顺序」章节。**字段次序现在是有意义的** |
| **`LOOKUP` 标量源** | 源只有一行时，**真 key 现在必须匹配**（原来 key 被忽略，任何行都返回那个值） | 用 `""` / `0` 作 key 的写法**不受影响**；见「LOOKUP」章节 |
| **缺失值与运算符** | 聚合函数**跳过**缺失值；二元运算符和比较**传播** `---` | 见「缺失值语义」章节 |
| **聚合空集** | `avg` / `stdev` 遇空集由返回 `0` / `0.0` 改为 `---` | 无需改动；原先的 `0` 是编造值 |
| **空列补齐** | 未使用的列（如未用到的浓度点）不再让整个 `*_ROWS` 回归失败 | 无需改动 |

> 全量归因回归（旧代码重算 vs 新代码重算，三站点）：除「原本算不出来现在算出来了」
> 与 1e-10 量级的浮点差异外无其它变化。逐项台账见 `ISSUES.md` 的 ISSUE-014 ~ 022。

---

## 1.1.0 更新概要（2026-08-19）

面向**有关物质方法验证**的函数库扩展。

### 函数表规模（口径写明，避免歧义）

CalculatedList 引擎的 `_SAFE` 表：

| | 条目 | = 常量（`True`/`False`/`None`） | + 函数 |
| -- | ---- | ---- | ---- |
| v1.0.0 | 38 | 3 | **35** |
| **v1.1.0** | **50** | 3 | **47** |

**新增 12 个函数，无删除。**（标量引擎 `safe_globals` 为 23 条目 = 3 常量 + 20 函数，本轮未变动。）

> 条目数含 3 个常量；`__builtins__` 是外层包装键，不计入。
> 引用数字时请注明是「条目」还是「函数」—— 这两个数不一样。

### 新增函数（12 个）

| 类别 | 函数 |
| ---- | ---- |
| 分组统计 | `GROUP_RSDlist`、`GROUP_CI_LOWlist`、`GROUP_CI_HIGHlist`、`GROUP_COUNTlist` |
| 修约与格式化 | `ROUND`、`ROUND_EVEN`、`FORMAT` |
| 数值化 | `RESULT_NUM` |
| 回归 | `SSE`、`SSE_ROWS`、`COUNT_ROWS` |
| 时间 | `TIME_ELAPSED_HOURS` |

### 本次补齐的既有函数文档

`STDEV_ROWS` / `RSD_ROWS` **v1.0.0 就已存在**，但一直没写进本文档。
本次补上（见「STDEV_ROWS / RSD_ROWS」章节）—— 它们的参数约定与
`*_ROWS` 回归系列**不同**（不对半分 Y/X），是容易误配的一处。

### 行为变更（配置需要配合）

| 项 | 变更 | 需要做什么 |
| -- | ---- | ---------- |
| **`RESULT_STATUS`** | 去掉硬编码 `"%.4f"`，**原样透传数值**；返回混合数组 | 展示字段外面套 `FORMAT(..., 4)`；详见对应章节 |
| **`GROUP_*` 分组 key** | 由单 key 改为**可变个数**，支持复合 key | 无需改动，单 key 写法语义不变 |
| **回归可变点数** | `SLOPE_ROWS` / `INTERCEPT_ROWS` 跳过缺失点，用剩余的算 | 无需改动 |
| **`RSQ_ROWS`** | 新增**有效点 ≥5** 下限（ICH Q2），不足则 `---` | 线性 AS 需确认水平数 |
| **缺失值语义** | 全引擎统一：算不出来输出 `---`，不再返回编造的 `0.0` | 见「缺失值语义」章节 |
| **`INDEX_BY`** | 现在也能内联在 CalculatedList 公式里 | 可选，原两步写法照旧可用 |

> 详细实施过程、逐阶段门禁与实测对照值见 `maitux.calcenhance_能力增强_Runbook.md`；
> 问题台账见 `ISSUES.md`。

---

## 新增功能

### 1. List (array) — 列表输入

允许用户输入多个并列值（如多针进样的峰面积、多个胶囊的毛重），系统以 JSON 数组存储原始数据。

- 录入时出现多个输入框，通过 **+/-** 按钮增删
- 存储时保留原始数组（如 `[0.512, 0.508, 0.515]`），不自动求平均
- 当 **Calculated** 类型引用 List 时，系统自动取平均值代入公式（向后兼容）
- 当 **Calculated List** 类型引用 List 时，逐元素配对计算（见下方说明）

### 2. Calculated — 子公式自动计算

只读字段，值由 Inter-Interim 子公式自动计算得出。支持通过 `[keyword]` 引用其他 Interim Field，引擎自动解析依赖关系并按拓扑顺序求值。

- 在 Interim Fields 表格中，**Control type** 选择 `Calculated`，在新增的 **Formula** 列中填写子公式
- 子公式语法：`([Keyword1] * [Keyword2]) / [Keyword3]`
- **裸 `[KW]` 引用 List** 时自动取平均值（向后兼容）
- **聚合函数 `sum([KW])`、`max([KW])`、`min([KW])`、`avg([KW])`、`len([KW])`** 可直接操作 List 原始数组
- 支持标准数学函数：`abs`, `max`, `min`, `round`, `sum`, `pow`, `sqrt`, `log`, `log10`, `exp`, `floor`, `ceil`, `avg`

### 3. Calculated List — 逐元素配对计算

只读字段，值为 JSON 数组。当公式引用 List 类型时，各数组按**相同索引逐元素配对**计算，结果为相同长度的数组。

- Control type 选择 `Calculated List`，在 Formula 列中填写子公式
- 语法与 Calculated 相同：`([Keyword1] * [Keyword2]) / [Keyword3]`
- 引用 List 类型时自动逐元素配对；引用普通标量时该值广播到所有元素
- 适用于 **装量差异**（每个胶囊独立计算）、**杂质含量**（每针独立计算）等场景

### 4. Cross-Analysis LOOKUP — 跨测定 Interim Field 引用

允许同一 AR 下的兄弟 Analysis 之间通过 `LOOKUP()` 函数引用对方的 Interim Field，按名称动态匹配。适用于**溶液残留方法验证**等需要跨测定数据引用的场景。

#### 核心概念

- **`cross_referenceable` 标记**：Interim Fields 表格中的 Cross-ref 复选框。勾选后，该字段才能被其他 Analysis 的 `LOOKUP()` 读到。
- **只读**：LOOKUP 仅读取数据，不会修改源分析，GMP 审计风险为零。
- **按名称匹配**：通过键值对（如溶剂名称 → 响应因子 F）实现动态匹配，无需硬编码索引。

#### LOOKUP 函数语法

```
LOOKUP("源测定Keyword", "目标字段Keyword", "键字段Keyword", 匹配值 [, 默认值])
```

| 参数           | 说明                                                  |
| -------------- | ----------------------------------------------------- |
| 源测定Keyword  | 被引用的 Analysis Service 的 Keyword（字符串）        |
| 目标字段Keyword | 要读取的 Interim Field Keyword（字符串）              |
| 键字段Keyword  | 源测定中用于匹配的 Interim Field Keyword（字符串）    |
| 匹配值         | 当前行的值，通常用`[当前字段Keyword]` 引用          |
| 默认值（可选） | 匹配失败时返回的值；省略时匹配失败抛异常              |

**返回值：** 通过键字段数组匹配位置，返回目标字段数组对应位置的元素。匹配失败时——传了第 5 个参数 `默认值` 则返回该值，否则抛异常（公式容错，不阻断保存）。

#### 配置示例

**对照品测定（ref-std）的 Interim Fields：**

| Keyword           | Field Title | Control type    | Cross-ref      | Formula                                                  |
| ----------------- | ----------- | --------------- | -------------- | -------------------------------------------------------- |
| `solvent_names` | 溶剂名称    | List (array)    | **勾选** |                                                          |
| `peak_area`     | 峰面积      | List (array)    |                |                                                          |
| `F`             | 响应因子 F  | Calculated List | **勾选** | `[peak_area] / ([std_weight] * [purity] / [dilution])` |

**样品测定（sample）的 Interim Fields：**

| Keyword           | Field Title     | Control type    | Formula                                                       |
| ----------------- | --------------- | --------------- | ------------------------------------------------------------- |
| `solvent_names` | 溶剂名称        | List (array)    |                                                               |
| `peak_area`     | 峰面积          | List (array)    |                                                               |
| `F_from_std`    | F值(来自对照品) | Calculated List | `LOOKUP("ref-std", "F", "solvent_names", [solvent_names])`  |
| `residue_ppm`   | 溶剂残留(ppm)   | Calculated List | `[peak_area] / [F_from_std] / [sample_weight] * [dilution]` |

> **工作原理：** 样品测定录入 `solvent_names = ["甲醇", "乙酸乙酯"]` 后，引擎逐元素调用 LOOKUP——用"甲醇"去对照品测定的 `solvent_names` 数组中定位索引，返回 `F` 数组对应位置的值。

#### LOOKUP 在 Calculated 中的用法

```
# 读标量值
LOOKUP("ref-std", "RF_avg", "dummy", [dummy])

# 读数组第一个元素
LOOKUP("ref-std", "F", "solvent_names", "甲醇")
```

#### 匹配失败的回退值（第 5 个参数）

LOOKUP 的第 5 个可选参数 `默认值` 指定「查不到匹配键」时返回什么，让同一 LOOKUP 在不同业务场景返回不同回退值，而不是写死单一值。

```
# 方法A：未知杂质没有校正因子 → 默认 CF = 1.0
imp_cf_lookup = LOOKUP("imp_linearity", "imp_correction_factor", "imp_name", [imp_name], 1.0)

# 方法B：未知杂质查不到 RF → 用 "---" 占位，保持数组行对齐
imp_rf_lookup = LOOKUP("imp_std_weigh", "imp_rf", "imp_name", [imp_name], "---")
```

| 场景       | 匹配失败返回 | 用途                       |
| ---------- | ------------ | -------------------------- |
| 数值回退   | `1.0`        | 未知杂质默认校正因子       |
| 字符串占位 | `"---"`      | 方法B查不到RF，保持行对齐  |

#### 占位符 "---" 的行对齐传播

当回退值为字符串 `"---"` 时，它会作为数组元素保留在 CalculatedList 的结果数组中（而不是被丢弃）。这样下游逐元素公式读到含 `"---"` 的输入时，该行结果也输出 `"---"`：

- 未知杂质行在 JSON 数组中保持原有位置，不串行
- 审核界面还原数组时，行与峰名一一对应，不会错位

数字与 `"---"` 混合的数组（如 `[0.12, "---", 0.34]`）在引擎内部按「数字转 float、`"---"` 保留字符串」处理；下游逐元素公式遇到 `"---"` 直接短路输出 `"---"`，纯数值行照常计算。

#### 作用域

**同一个样品内**，包含其全部分装（Partition）。

分装不是把分析嵌套进子对象：SENAITE 的分装会新建一个独立的 Sample（AnalysisRequest），通过 `ParentAnalysisRequest` 挂在主样品下，并把选中的分析**移入分装、从主样品移除**。因此"分装 1 上的对照品测定"与"分装 2 上的样品测定"分属两个 Sample 对象。

引擎会先向上定位到根样品，再按祖先链检索，所以以下引用都成立：

- 主样品 ↔ 分装
- 分装 1 ↔ 分装 2

> **注意**：这比 SENAITE 原生的依赖重算范围更宽。原生 `get_dependents()` 从 `analysis.getRequest()` 出发，分装内的分析只能看到本分装，**跨分装的普通 `[KEYWORD]` 依赖不会触发重算**。本 Addon 的 LOOKUP、跨测定 `[KEYWORD]` 引用与重算传播三者统一采用样品树作用域。

#### 限制

- 只能读取勾选了 Cross-ref 的 Interim Field
- 源测定数据不存在时，LOOKUP 抛出异常但不阻断保存（公式容错）；匹配失败时若传了第 5 个参数 `默认值` 则返回该值，否则同样抛异常（均不阻断保存）
- 源测定的 Cross-ref 字段保存后，引擎会自动重算引用它的分析，保证 LOOKUP 结果不滞后
- 重算传播会跳过已 retract / reject / retest 的分析（与原生 `get_dependents()` 一致），但**不跳过已提交或已核验的分析**——与原生行为一致，避免样品内出现"对照品已更新、部分结果仍按旧值"的不一致

---

## 安装方法

### 1. 准备文件

将 `maitux.calcenhance` 目录放在 SENAITE 源码目录下（与 `senaite.core` 同级）：

```
/home/senaite/senaitelims/src/maitux.calcenhance/
```

### 2. 注册 Add-on

在 SENAITE 实例的 ZCML 配置中添加（通常在 `package-includes/` 目录下创建 `.zcml` 文件）：

```xml
<include package="maitux.calcenhance" />
```

确保 `maitux.calcenhance` 在 Python 路径中（可通过 `develop-eggs` 或 `egg-link` 方式）。

### 3. 重启 Zope 实例

```bash
# Docker 环境
docker compose restart senaite

# 普通环境
bin/instance restart
```

### 4. 验证安装

重启后访问 SENAITE 后台，进入 **Setup → Calculations**，编辑任意 Calculation，在 Interim Fields 表格中：

- **Control type** 下拉框应出现 `List (array)`、`Calculated` 和 `Calculated List` 选项
- 表格最右侧应出现 **Formula** 列

---

## 功能使用说明

### List (array) 类型

在 Calculation 的 Interim Fields 中添加一个字段：

| 字段         | 值               |
| ------------ | ---------------- |
| Keyword      | `Std1PeakArea` |
| Field Title  | 对照品1峰面积    |
| Control type | List (array)     |

在 Worksheet 或 Analysis 页面录入结果时，该字段会显示多个输入框，可以输入多针进样的峰面积值（如 102345, 103210, 101980）。保存后，原始数组被保留。当 Calculated 引用时自动取平均值参与计算。

### Calculated 类型

在 Calculation 的 Interim Fields 中添加一个字段：

| 字段         | 值                          |
| ------------ | --------------------------- |
| Keyword      | `DilutionFactor`          |
| Field Title  | 稀释因子                    |
| Control type | Calculated                  |
| Formula      | `(200 * 1) / (10 * 1000)` |

或在 Formula 中使用 `[keyword]` 引用其他字段：

| 字段         | 值                                                     |
| ------------ | ------------------------------------------------------ |
| Keyword      | `RF`                                                 |
| Field Title  | 响应因子                                               |
| Control type | Calculated                                             |
| Formula      | `([AvgPeakArea] * [Volume]) / ([Weight] * [Purity])` |

### Calculated List 类型

在 Calculation 的 Interim Fields 中添加：

| 字段         | 值                               |
| ------------ | -------------------------------- |
| Keyword      | `NetWeight`                    |
| Field Title  | 净重（3粒）                      |
| Control type | Calculated List                  |
| Formula      | `[GrossWeight] - [TareWeight]` |

前提是 `GrossWeight` 和 `TareWeight` 为 List 类型（各 3 个值）。保存后自动为每粒胶囊计算独立净重，结果为 `[0.410, 0.407, 0.412]`。

---

## 示例一：HPLC 含量测定完整配置（Calculated 类型）

以 **S1905 原料药含量测定** 为例，实现从原始数据到最终含量的自动化计算。

### 业务背景

- 对照品溶液配制 2 份，供试品溶液配制 2 份
- 对照品1进样 6 针，对照品2进样 2 针
- 每份供试品进样 2 针
- 先计算响应因子 RF，再计算含量，最后计算无水物含量

### Step 1：创建 Calculation 公式

在 SENAITE 中进入 **Setup → Calculations → Add**，创建名为"含量测定-S1905"的计算公式。

**主公式（Calculation Formula）：**

```
([Content1] + [Content2]) / 2
```

该公式计算两份供试品溶液的平均含量。`Content1` 和 `Content2` 是下面定义的 Calculated 类型 Interim Field。

### Step 2：配置 Interim Fields

按以下顺序添加 Interim Fields：

#### 手工输入字段

**对照品1相关信息：**

| # | Keyword      | Field Title         | Control type           | Default value | Formula |
| - | ------------ | ------------------- | ---------------------- | ------------- | ------- |
| 1 | Weight1      | 对照品1称样量(mg)   | Numeric                |               |         |
| 2 | Volume1      | 对照品1稀释体积(ml) | Numeric                | 200           |         |
| 3 | Purity1      | 对照品1含量(%)      | Numeric                | 99.5          |         |
| 4 | Std1PeakArea | 对照品1峰面积(6针)  | **List (array)** |               |         |

**对照品2相关信息：**

| # | Keyword      | Field Title         | Control type           | Default value | Formula |
| - | ------------ | ------------------- | ---------------------- | ------------- | ------- |
| 5 | Weight2      | 对照品2称样量(mg)   | Numeric                |               |         |
| 6 | Volume2      | 对照品2稀释体积(ml) | Numeric                | 200           |         |
| 7 | Purity2      | 对照品2含量(%)      | Numeric                | 99.5          |         |
| 8 | Std2PeakArea | 对照品2峰面积(2针)  | **List (array)** |               |         |

**供试品相关信息：**

| #  | Keyword         | Field Title         | Control type           | Default value | Formula |
| -- | --------------- | ------------------- | ---------------------- | ------------- | ------- |
| 9  | SampleWeight1   | 供试品1称样量(mg)   | Numeric                |               |         |
| 10 | SampleVolume1   | 供试品1稀释体积(ml) | Numeric                | 200           |         |
| 11 | Sample1PeakArea | 供试品1峰面积(2针)  | **List (array)** |               |         |
| 12 | SampleWeight2   | 供试品2称样量(mg)   | Numeric                |               |         |
| 13 | SampleVolume2   | 供试品2稀释体积(ml) | Numeric                | 200           |         |
| 14 | Sample2PeakArea | 供试品2峰面积(2针)  | **List (array)** |               |         |

**水分：**

| #  | Keyword | Field Title | Control type | Default value | Formula |
| -- | ------- | ----------- | ------------ | ------------- | ------- |
| 15 | KF      | 水分(%)     | Numeric      | 0             |         |

#### 自动计算字段（Calculated）

**响应因子：**

| #  | Keyword | Field Title      | Control type         | Formula                                                    |
| -- | ------- | ---------------- | -------------------- | ---------------------------------------------------------- |
| 16 | RF1     | 响应因子-对照品1 | **Calculated** | `([Std1PeakArea] / [Weight1]) * ([Volume1] / [Purity1])` |
| 17 | RF2     | 响应因子-对照品2 | **Calculated** | `([Std2PeakArea] / [Weight2]) * ([Volume2] / [Purity2])` |
| 18 | RF_avg  | 平均响应因子     | **Calculated** | `([RF1] + [RF2]) / 2`                                    |

> **公式说明（对照含量方法 Section 7.1）：**
> RF = A_STD × V_STD / (W_STD × P_STD)
> = (A_STD / W_STD) × (V_STD / P_STD)

**含量计算：**

| #  | Keyword  | Field Title  | Control type         | Formula                                                                  |
| -- | -------- | ------------ | -------------------- | ------------------------------------------------------------------------ |
| 19 | Content1 | 含量-供试品1 | **Calculated** | `([Sample1PeakArea] * [SampleVolume1]) / ([SampleWeight1] * [RF_avg])` |
| 20 | Content2 | 含量-供试品2 | **Calculated** | `([Sample2PeakArea] * [SampleVolume2]) / ([SampleWeight2] * [RF_avg])` |

> **公式说明（对照含量方法 Section 7.2）：**
> 含量 = A_SPL × V_SPL / (W_SPL × RF)

### Step 3：依赖顺序说明

本例的字段**定义顺序**已经满足依赖，所以一趟就能算完（求值规则见
「求值顺序」章节）。依赖链是：

1. 手工输入的 Numeric/List 字段 → 用户填写后获得值
2. `RF1` → 依赖 `Std1PeakArea`, `Weight1`, `Volume1`, `Purity1`
3. `RF2` → 依赖 `Std2PeakArea`, `Weight2`, `Volume2`, `Purity2`
4. `RF_avg` → 依赖 `RF1`, `RF2`
5. `Content1` → 依赖 `Sample1PeakArea`, `SampleVolume1`, `SampleWeight1`, `RF_avg`
6. `Content2` → 依赖 `Sample2PeakArea`, `SampleVolume2`, `SampleWeight2`, `RF_avg`

主公式 `([Content1] + [Content2]) / 2` 在所有 Calculated 字段计算完成后求值，输出最终结果。

### Step 4：操作流程

1. 在 Analysis Service 中关联此 Calculation
2. 在 Worksheet 中录入数据：
   - 选择 `Std1PeakArea` → 弹出 2 个输入框（默认），点击 **+** 增加到 6 个，输入 6 针峰面积
   - 选择 `Std2PeakArea` → 输入 2 个值
   - 选择 `Sample1PeakArea` → 输入 2 个值
   - 选择 `Sample2PeakArea` → 输入 2 个值
   - `Weight1`, `Weight2`, `SampleWeight1`, `SampleWeight2` → 输入称样量
   - `KF` → 输入水分值
3. 每次保存任意 Interim 值后，系统自动重新计算所有 Calculated 字段
4. 提交结果时，主公式计算两份供试品的平均含量

---

## 子公式语法参考

### 基本语法

```
([Keyword1] + [Keyword2]) / [Keyword3]
```

- 用 `[keyword]` 引用其他 Interim Field 的 keyword
- 支持基本运算符：`+ - * / ( )`
- 支持幂运算：`[A] ^ 2` 或 `pow([A], 2)`

### 可用函数

| 函数                              | 说明                                 | 示例                                      |
| --------------------------------- | ------------------------------------ | ----------------------------------------- |
| `abs(x)`                        | 绝对值                               | `abs([A])`                              |
| `max(a,b,...)`                  | 多值比较 / 数组最大值                | `max([A], [B])` 或 `max([ListKW])`    |
| `min(a,b,...)`                  | 多值比较 / 数组最小值                | `min([A], 0)` 或 `min([ListKW])`      |
| `round(x,n)`                    | 四舍五入                             | `round([A], 4)`                         |
| `sum(iterable)`                 | 数组求和                             | `sum([ListKW])`                         |
| `avg(iterable)`                 | 数组平均值                           | `avg([ListKW])`                         |
| `stdev(iterable)`               | 数组标准差                           | `stdev([ListKW])`                       |
| `len(iterable)`                 | 数组长度（元素个数）                 | `len([ListKW])`                         |
| `pow(x,y)`                      | x的y次方                             | `pow([A], 2)`                           |
| `sqrt(x)`                       | 平方根                               | `sqrt([A])`                             |
| `log(x)`                        | 自然对数                             | `log([A])`                              |
| `log10(x)`                      | 常用对数                             | `log10([A])`                            |
| `exp(x)`                        | e的x次方                             | `exp([A])`                              |
| `floor(x)`                      | 向下取整                             | `floor([A])`                            |
| `ceil(x)`                       | 向上取整                             | `ceil([A])`                             |
| `LOOKUP(a,b,c,d[,default])`     | 跨分析按名称匹配读取，匹配失败返回默认值 | `LOOKUP("ref-std","F","names",[name],1.0)` |
| `INDEX_BY(a,b,c)`               | AS内部按键索引取值                   | `INDEX_BY([rt],[name],"主成分")`        |
| `SLOPE(y,x)`                    | 线性回归斜率（全数组→标量）         | `SLOPE([tst_y],[tst_x])`                |
| `INTERCEPT(y,x)`                | 线性回归截距（全数组→标量）         | `INTERCEPT([tst_y],[tst_x])`            |
| `RSQ(y,x)`                      | 线性回归决定系数 R²（全数组→标量） | `RSQ([tst_y],[tst_x])`                  |
| `SLOPE_ROWS(y…,x…)`           | 逐行线性回归斜率（数组）             | `SLOPE_ROWS([a1]…[a6],[c1]…[c6])`     |
| `INTERCEPT_ROWS(y…,x…)`       | 逐行线性回归截距（数组）             | `INTERCEPT_ROWS([a1]…[a6],[c1]…[c6])` |
| `RSQ_ROWS(y…,x…)`             | 逐行 R²，**要求 ≥5 个有效点**       | `RSQ_ROWS([a1]…[a6],[c1]…[c6])`       |
| `SSE(y,x)`                      | 残差平方和（全数组→标量）           | `SSE([tst_y],[tst_x])`                  |
| `SSE_ROWS(y…,x…)`             | 逐行残差平方和（数组）               | `SSE_ROWS([a1]…[a6],[c1]…[c6])`       |
| `COUNT_ROWS(y…,x…)`           | 逐行实际参与回归的点数（数组）       | `COUNT_ROWS([a1]…[a6],[c1]…[c6])`     |
| `STDEV_ROWS(c1,c2,…)`         | **逐行**样本标准偏差（数组）         | `STDEV_ROWS([a1]…[a6])`               |
| `RSD_ROWS(c1,c2,…)`           | **逐行** RSD%（数组）                | `RSD_ROWS([a1]…[a6])`                 |
| `RESULT_STATUS(vals,loq?,lod?)` | 逐行LOQ/LOD状态判定，**原样透传数值** | `RESULT_STATUS([val],[loq],[lod])`      |
| `RESULT_NUM(val,name?,main?)`   | 逐元素数值化：主成分/限下标记→0     | `RESULT_NUM([rep],[name],[main_ref])`   |
| `ROUND(x,n)`                    | 四舍五入，返回**数值**               | `ROUND([A], 3)`                         |
| `ROUND_EVEN(x,n)`               | 四舍六入五留双（GB/T 8170），**数值** | `ROUND_EVEN([A], 3)`                    |
| `FORMAT(x,n)`                   | 定位数格式化保留尾随零，返回**字符串** | `FORMAT([A], 4)` → `"0.0400"`        |
| `TIME_ELAPSED_HOURS(t,n=1)`     | 距数组内最早时间的小时差（数组）     | `TIME_ELAPSED_HOURS([inj_time], 1)`     |
| `GROUP_AVGlist(v,*k)`           | 按组平均（广播）                     | `GROUP_AVGlist([val],[grp])`            |
| `GROUP_STDEVlist(v,*k)`         | 按组标准差（广播）                   | `GROUP_STDEVlist([val],[grp])`          |
| `GROUP_SUMlist(v,*k)`           | 按组求和（广播）                     | `GROUP_SUMlist([val],[grp])`            |
| `GROUP_MAXlist(v,*k)`           | 按组最大值（广播）                   | `GROUP_MAXlist([val],[grp])`            |
| `GROUP_MINlist(v,*k)`           | 按组最小值（广播）                   | `GROUP_MINlist([val],[grp])`            |
| `GROUP_RSDlist(v,*k)`           | 按组 RSD%（广播）                    | `GROUP_RSDlist([rec],[level])`          |
| `GROUP_CI_LOWlist(v,*k)`        | 按组 95% 置信下限（广播）            | `GROUP_CI_LOWlist([rec],[level])`       |
| `GROUP_CI_HIGHlist(v,*k)`       | 按组 95% 置信上限（广播）            | `GROUP_CI_HIGHlist([rec],[level])`      |
| `GROUP_COUNTlist(v,*k)`         | 按组有效值个数（广播），n 的留痕     | `GROUP_COUNTlist([rec],[level])`        |

> 所有 `GROUP_*` 的 key 参数是**可变个数**的：`GROUP_AVGlist([v],[k1],[k2])`
> 按两列组合分组。单 key 写法与旧版语义完全一致，**现有公式无需改动**。

### List 类型值的引用

**Calculated 引用 List**：两种方式——

| 写法              | 含义                     | 示例                                  |
| ----------------- | ------------------------ | ------------------------------------- |
| 裸`[ListKW]`    | 自动取平均值（向后兼容） | `[Std1PeakArea]` → 6 针峰面积均值  |
| `sum([ListKW])` | 原始数组求和             | `sum([NetWeight])` → 总装量        |
| `max([ListKW])` | 数组最大值               | `max([Std1PeakArea])` → 最大峰面积 |
| `min([ListKW])` | 数组最小值               | `min([Std1PeakArea])` → 最小峰面积 |
| `avg([ListKW])` | 数组平均值（显式）       | 等价于裸引用                          |
| `len([ListKW])` | 数组元素个数             | `len([std1PeakArea])` → `6`      |

聚合函数组合示例：

```
# RSD 评估
(max([Std1PeakArea]) - min([Std1PeakArea])) / avg([Std1PeakArea]) * 100

# 总装量（多粒胶囊净重之和）
sum([NetWeight])
```

**Calculated List 引用 List**：逐元素配对。无需函数包裹，裸 `[KW]` 即为逐元素值。
所有被引用的 List 必须等长。

**Calculated List 引用 Calculated**：标量值广播到所有元素（每次配对使用相同值）。

---

## INDEX_BY — AS 内部按键索引

在 Calculated / CalculatedList 中使用 `INDEX_BY(target_arr, key_arr, match_val)` 在当前 AS 内部按名称查找对应值。与 LOOKUP（跨 AS 引用）不同，INDEX_BY 仅检索当前 AS 自身的 list 字段。

```
INDEX_BY([值数组], [键数组], 匹配值) → 返回目标数组中匹配位置的值
```

|          | LOOKUP                      | INDEX_BY                 |
| -------- | --------------------------- | ------------------------ |
| 作用域   | 跨 AS（兄弟 Analysis）      | 当前 AS 自身             |
| 第一参数 | 源测定 AS Keyword（字符串） | 目标字段`[kw]` 引用    |
| 典型场景 | 跨测定引用响应因子          | 主成分 RT 按名索引算 RRT |

**示例：计算相对保留时间 RRT**

两种写法都可用，选一种即可。

**写法一：两步（说明书原写法，语义最清楚）**

```
# AS-2 色谱分离度
imp_main_rt = INDEX_BY([imp_sep_rt], [imp_sep_name], "主成分")  # Calculated → 标量
imp_sep_rrt = [imp_sep_rt] / [imp_main_rt]                       # CalculatedList → 数组广播
```

**写法二：一步（少一个中间字段）**

```
# 直接写在 CalculatedList 字段里
imp_sep_rrt = [imp_sep_rt] / INDEX_BY([imp_sep_rt], [imp_sep_name], "主成分")

# 带修约
imp_sep_rrt = ROUND([imp_sep_rt] / INDEX_BY([imp_sep_rt], [imp_sep_name], "主成分"), 3)
```

> 结果一致：`[0.3271, 1.0, 1.1981, 1.4009]`，主成分那行恰为 `1.0`。

### 使用位置

| 想要 | 放在哪个字段 |
| ---- | ------------ |
| 一个标量（主成分 RT 之类） | **Calculated** |
| 一列比值（RRT） | **CalculatedList**，用写法二一步写完 |

> `INDEX_BY(...)` **单独**放在 CalculatedList 字段里会得到**单元素数组** ——
> 该公式改写后已无数组依赖，走引擎的「无数组依赖」分支，这是该分支既有的约定
> （字面量 `LOOKUP` 也一样），不是 `INDEX_BY` 特有。要标量就放 Calculated 字段。

### 查表数组与输出列不必等长

被查的两个数组（值列、键列）的长度**不需要**等于输出列的行数：

```
# 输出列只有 2 行，却去 4 行的峰表里查主成分
[two_row_col] * INDEX_BY([imp_sep_rt], [imp_sep_name], "主成分")
```

### 键不存在时

返回 `---` 并记日志（日志里会指名是哪个键没找到），不抛异常、不留旧值。

```
INDEX_BY: key '不存在的峰' not in key array [...]
```

---

## SLOPE / INTERCEPT / RSQ — 线性回归

基于最小二乘法对两个等长数组计算线性回归参数。适用于方法验证中线性与范围（Linearity & Range）的自动计算。

| 函数                | 说明          | 公式                                                |
| ------------------- | ------------- | --------------------------------------------------- |
| `SLOPE(y, x)`     | 回归斜率 β₁ | `(n·Σxy - Σx·Σy) / (n·Σx² - (Σx)²)`     |
| `INTERCEPT(y, x)` | 回归截距 β₀ | `(Σy·Σx² - Σx·Σxy) / (n·Σx² - (Σx)²)` |
| `RSQ(y, x)`       | 决定系数 R²  | `(Σ(x-x̄)(y-ȳ))² / (Σ(x-x̄)²·Σ(y-ȳ)²)` |

这三个函数返回标量，通常在 **Calculated** 类型中使用：

```
tst_slope = SLOPE([tst_y], [tst_x])        # → 标量 2.0
tst_intercept = INTERCEPT([tst_y], [tst_x]) # → 标量 0.0
tst_rsq = RSQ([tst_y], [tst_x])             # → 标量 1.0
```

## SLOPE_ROWS / INTERCEPT_ROWS / RSQ_ROWS — 逐行（per-row）线性回归

当数据是「物质为行、每个物质各有一组 (x, y) 点」时，全数组版（`SLOPE`/`INTERCEPT`/`RSQ`）不够用。逐行版把多列并行数组按 **行索引** 分组，每一行独立做一次最小二乘回归，返回数组（每行一个结果）。用于方法验证中线性与范围的逐物质自动计算。

| 函数                         | 说明                     |
| ---------------------------- | ------------------------ |
| `SLOPE_ROWS(y…, x…)`     | 逐行斜率（数组）         |
| `INTERCEPT_ROWS(y…, x…)` | 逐行截距（数组）         |
| `RSQ_ROWS(y…, x…)`       | 逐行 R²，**要求 ≥5 个有效点** |
| `SSE_ROWS(y…, x…)`       | 逐行残差平方和（数组）   |
| `COUNT_ROWS(y…, x…)`     | 逐行实际参与回归的点数   |

**参数约定**：接收偶数个 list 参数，**前半段是 Y 列、后半段是 X 列**（与 `SLOPE([y],[x])` 的 y 在前、x 在后一致），各列按 index 对齐。所有 Y/X 列必须等长（= 物质行数）。
列数为奇数时返回空数组并记日志（`*_ROWS needs an even column count`）。

### 可变点数：缺一个点不再废掉整行

| 情形 | 行为 |
| ---- | ---- |
| 某点在 Y 或 X 任一轴缺失 | **只丢那一对**，用剩余的点回归 |
| 存活配对 `< 2` | `---` |
| **`RSQ_ROWS` 存活点 `< 5`** | `---` |
| 所有存活点落在同一个 x | `---` |

```
# 5 个浓度水平，第 3 点缺失（空串）
#   x = [1, 2, 3, 4, 5]
#   y = [2, 4, "", 8, 10]
SLOPE_ROWS(...)      → 2.0     ← 用剩下 4 个点回归
INTERCEPT_ROWS(...)  → 0.0
COUNT_ROWS(...)      → 4       ← 报表上要能看到实际用了几个点
RSQ_ROWS(...)        → ---     ← 只剩 4 个水平，未达 ICH Q2 的 5 个
```

> **`RSQ_ROWS` 的 5 点下限是刻意的**：两个点永远精确落在自己的直线上，
> R² 必然是 `1.0` —— 那是**从零证据断言完美线性**。ICH Q2 要求 5 个浓度水平，
> 所以少于 5 个存活点一律 `---`，而不是给一个好看的数字。
>
> **实用提示**：完整 5 点的 R² 会是 `0.99999999999999978`（浮点常态）。
> 验证报告里 R² 一般报 4 位，配置时写 `ROUND(RSQ_ROWS(...), 4)` → `1.0`。

**示例：6 浓度梯度 × 逐物质线性回归（AS-5 线性与范围）**

```
# 输入：6 个浓度列（x）+ 6 个峰面积列（y），每列长度 = 物质数
imp_lin_slope     = SLOPE_ROWS([imp_lin_a1],[imp_lin_a2],[imp_lin_a3],[imp_lin_a4],[imp_lin_a5],[imp_lin_a6],[imp_lin_c1],[imp_lin_c2],[imp_lin_c3],[imp_lin_c4],[imp_lin_c5],[imp_lin_c6])
imp_lin_intercept = INTERCEPT_ROWS([imp_lin_a1],[imp_lin_a2],[imp_lin_a3],[imp_lin_a4],[imp_lin_a5],[imp_lin_a6],[imp_lin_c1],[imp_lin_c2],[imp_lin_c3],[imp_lin_c4],[imp_lin_c5],[imp_lin_c6])
imp_lin_r2        = RSQ_ROWS([imp_lin_a1],[imp_lin_a2],[imp_lin_a3],[imp_lin_a4],[imp_lin_a5],[imp_lin_a6],[imp_lin_c1],[imp_lin_c2],[imp_lin_c3],[imp_lin_c4],[imp_lin_c5],[imp_lin_c6])
imp_lin_r         = sqrt([imp_lin_r2])       # → 逐行相关系数 r
imp_main_slope    = INDEX_BY([imp_lin_slope],[imp_name],"S1919（主成分）")  # 主成分斜率
imp_correction_factor = [imp_main_slope] / [imp_lin_slope]                  # 校正因子 CF
```

> **注意**：逐行版与全数组版并存，全数组版 `SLOPE`/`INTERCEPT`/`RSQ` 的原有行为**不受影响**。逐行版是**新增**能力，仅在 **Calculated List** 中使用（返回数组）。

---

## STDEV_ROWS / RSD_ROWS — 逐行精密度统计

按**行索引**对多列做统计，每行独立算一次，返回数组。方法验证里的**重复性**
（6 针进样的 RSD）就是这个形状。

| 函数 | 说明 |
| ---- | ---- |
| `STDEV_ROWS(c1, c2, …)` | 逐行样本标准偏差（n−1） |
| `RSD_ROWS(c1, c2, …)`   | 逐行 RSD% = SD / 均值 × 100 |

### ⚠️ 参数约定与 `*_ROWS` 回归系列**不同**

| | 参数含义 | 列数要求 |
| -- | -------- | -------- |
| `SLOPE_ROWS` / `INTERCEPT_ROWS` / `RSQ_ROWS` / `SSE_ROWS` / `COUNT_ROWS` | **前半段 Y 列、后半段 X 列** | 必须**偶数** |
| `STDEV_ROWS` / `RSD_ROWS` | **所有列都是数据列**，不对半分 | 任意，**奇数也可以** |

这两个函数只是「把同一行的这些列拿来做统计」，没有自变量/因变量的概念。
把它们和回归系列写成同样的参数形状是常见误配。

**示例：重复性 6 针进样的 RSD**

```
# 6 个峰面积列，每列长度 = 物质数（行数）
imp_rep_sd  = STDEV_ROWS([imp_rep_a1],[imp_rep_a2],[imp_rep_a3],[imp_rep_a4],[imp_rep_a5],[imp_rep_a6])
imp_rep_rsd = RSD_ROWS([imp_rep_a1],[imp_rep_a2],[imp_rep_a3],[imp_rep_a4],[imp_rep_a5],[imp_rep_a6])

# 报表展示（R² 同理，见前文）
imp_rep_rsd_disp = FORMAT([imp_rep_rsd], 2)
```

实测（1 行 6 列，峰面积 `10.02 / 10.05 / 9.98 / 10.01 / 10.04 / 9.99`）：

| 情形 | `STDEV_ROWS` | `RSD_ROWS` |
| ---- | ------------ | ---------- |
| 6 针完整 | `0.02738612787` | `0.27345110209` |
| 6 针缺 1（跳过缺失，用剩下 5 针） | `0.02387467277` | `0.23855588301` |
| **只剩 1 针** | **`---`** | **`---`** |
| 全部为 0（均值为 0） | `0.0` | **`---`** |

> **`---` 的两种由来**：存活值 `< 2` 时标准偏差未定义；均值为 0 时 RSD
> （对均值的比值）未定义。旧版这两种情形都返回 `0.0` —— 在精密度报告上
> **读作「精密度完美」**，这是本轮重点消灭的一类编造值。详见「缺失值语义」。

### 与 `GROUP_*` 系列的分工

| 数据形状 | 用什么 |
| -------- | ------ |
| **同一行的多列**（6 针 = 6 个列） | `STDEV_ROWS` / `RSD_ROWS` |
| **同一列的多行按 key 分组**（多个物质各 3 个平行） | `GROUP_STDEVlist` / `GROUP_RSDlist` |

---

## RESULT_STATUS — 逐行 LOQ/LOD 状态判定

对数组逐元素判定是否低于定量限 / 检出限。

```
RESULT_STATUS(值数组, [LOQ阈值], [LOD阈值]) → 数值与字符串的混合数组
```

| 条件                 | 输出                                  |
| -------------------- | ------------------------------------- |
| `val >= LOQ`       | **原样透传的数值**（不再格式化）      |
| `LOD <= val < LOQ` | `"<LOQ"`                            |
| `val < LOD`        | `"N.D."`（未检出）                  |
| `val` 为 None / 空 | `"—"`（主成分行等不适用场景）      |

### ⚠️ 返回类型已变更（2026-08-19）

旧版对达到 LOQ 的值做 `"%.4f"` 硬编码格式化，返回**纯字符串数组**。
现在**原样透传数值**，返回**混合数组**。两个后果：

| 输入 | 旧输出 | 新输出 |
| ---- | ------ | ------ |
| `0.04` | `"0.0400"` | `0.04` |
| `1.0` | `"1.0000"` | `1.0` |
| `0.12345` | `"0.1235"` | `0.12345` |

1. **下游可以计算了。** 旧版整列是字符串，进不了 `list_arrays`，
   任何下游公式都无法引用；现在数值元素可参与计算 —— 这是总杂求和
   （`RESULT_NUM` → `GROUP_SUMlist`）能成立的前提。
2. **尾随零不再自动补。** 需要固定位数展示的字段，**外面套一层 `FORMAT`**：

```
# 展示字段：恢复 4 位小数
imp_report_disp = FORMAT(RESULT_STATUS([imp_pct]), 4)     # → "0.0400"

# 参与计算的字段：引用 ROUND，不要引用 FORMAT
imp_report_num  = ROUND(RESULT_STATUS([imp_pct]), 4)
```

> 旧版还有一个隐性损失：`0.12345` 被存成字符串 `"0.1235"`，**下游连精度一起丢**。
> 现在原样保留是改善，但界面可能显示比以前更多位 —— 同样用 `FORMAT` 控制。

**两种调用方式：**

```python
# 方式一：自动读取 AS Limits 标签页（日常检测推荐）
# AS 基础设置 → Limits → LLOQ / LLOD 配置后即生效，无需额外定义字段
imp_report = RESULT_STATUS([imp_pct])

# 方式二：显式指定阈值（方法验证等 LOQ 会变的场景）
imp_report = RESULT_STATUS([imp_pct], [imp_loq], [imp_lod])
```

> **自动读取原理**：当省略 loq/lod 参数时，引擎通过 `self.getAnalysisService()` 读取 AS 的 `LLOQ`（Lower Limit of Quantification）和 `LLOD`（Lower Detection Limit）值。这意味着每个 AS 可以在其 Limits 标签页统一维护阈值，所有引用该 AS 的 Calculation 无需冗余定义 `tst_loq`/`tst_lod` 字段。

---

## GROUP_*list — 分组聚合广播

`GROUP_*list(values, *keys)` 按 key 对等长数组分组，计算每组的聚合值后广播回原始长度。在 **CalculatedList** 中使用，适用于方法验证中按物质名称分组计算 RSD 等场景。

| 函数                        | 说明                             |
| --------------------------- | -------------------------------- |
| `GROUP_AVGlist(v, *k)`    | 按组平均                         |
| `GROUP_STDEVlist(v, *k)`  | 按组标准差（样本，n−1）          |
| `GROUP_SUMlist(v, *k)`    | 按组求和                         |
| `GROUP_MAXlist(v, *k)`    | 按组最大值                       |
| `GROUP_MINlist(v, *k)`    | 按组最小值                       |
| `GROUP_RSDlist(v, *k)`    | 按组 RSD%，省去 STDEV/AVG 两次分组 |
| `GROUP_CI_LOWlist(v, *k)` | 按组 95% 置信下限                |
| `GROUP_CI_HIGHlist(v, *k)` | 按组 95% 置信上限               |
| `GROUP_COUNTlist(v, *k)`  | 按组有效值个数                   |

**示例：按物质名称分组计算 RSD**

```
# 输入：8 行数据，分组 {A:3, B:3, C:2}
tst_avg   = GROUP_AVGlist([tst_value], [tst_name])      # → [11,11,11,100,100,100,6,6]
tst_stdev = GROUP_STDEVlist([tst_value], [tst_name])     # → [1,1,1,5,5,5,1.414,1.414]
tst_rsd   = [tst_stdev] / [tst_avg] * 100                # → 按组 RSD%

# 或者一步到位
tst_rsd   = GROUP_RSDlist([tst_value], [tst_name])
```

### 复合 key：按多列组合分组

key 参数是**可变个数**的。同一个杂质在不同加标水平下要分开统计时，
把两列都传进去即可：

```
# 6 行：杂质A/杂质A/杂质A + 杂质B/杂质B/杂质B，各含 LOQ 与 100% 两个水平
# 只按名称分组 → 两个水平被混在一起（错）
rec_avg = GROUP_AVGlist([rec], [imp_name])

# 按「名称 + 水平」分组 → 每个水平各自统计（对）
rec_avg = GROUP_AVGlist([rec], [imp_name], [spike_level])
```

> **单 key 写法与旧版语义完全一致，现有公式无需改动。**

### 置信区间：t 值按各组自身自由度取

```
rec_avg  = GROUP_AVGlist([rec], [imp_name], [spike_level])
rec_rsd  = GROUP_RSDlist([rec], [imp_name], [spike_level])
rec_lo   = GROUP_CI_LOWlist([rec], [imp_name], [spike_level])
rec_hi   = GROUP_CI_HIGHlist([rec], [imp_name], [spike_level])
rec_n    = GROUP_COUNTlist([rec], [imp_name], [spike_level])   # 把实际 n 打到报表上
```

置信区间 = 组均值 ± t(0.05, n−1) × SD/√n，**n 取自各组自身**：

| 组 | n | df | t | 均值 | RSD | 置信区间 |
| --- | - | -- | - | ---- | --- | -------- |
| LOQ 加标 | 3 | 2 | 4.302653 | 102.3 | 5.9% | 87.4 ~ 117.3 |
| 100% 加标 | 6 | 5 | 2.570582 | 101.0 | 1.1% | 99.9 ~ 102.1 |

> t 值取自源码内的 `_T_95` 字典（双侧 95%，自由度 **1–10**，精确值）。
> **自由度超出范围时返回 `---` 并记日志，不外推、不猜近似值。**
> 需要更大 n 时请补充精确表值，不要线性插值。

### 为什么要 `GROUP_COUNTlist`

`GROUP_*` 系列遇到缺失值时**跳过该值、用剩余的算**（见下节「缺失值语义」）。
这意味着一个 RSD 或置信区间背后的 n 是**隐式**的 —— 报表上看不出它用了几个点。
`GROUP_COUNTlist` 就是把这个 n 打出来的审计留痕：

```
# 3 个平行样缺 1 个
rec_rsd   = GROUP_RSDlist([rec], [level])      # → 3.35%
rec_n     = GROUP_COUNTlist([rec], [level])    # → 2    ← 报表上要能看到这个
```

---

## ROUND / ROUND_EVEN / FORMAT — 修约与格式化

三个函数**职责分离**：修约不写进具体计算函数里，精度要求变化时只改公式、
不动核心计算逻辑。

| 函数 | 返回 | 修约方式 |
| ---- | ---- | -------- |
| `ROUND(val, digits)` | **数值** | 四舍五入（round-half-up），逢五一律进位 |
| `ROUND_EVEN(val, digits)` | **数值** | 四舍六入五留双（round-half-even），GB/T 8170 / 中国药典 |
| `FORMAT(val, digits)` | **字符串** | 同 `ROUND` 的方向，但**保留尾随零** |

两者只在「正好一半」（被舍位为 5 且其后全 0）时不同：

```
ROUND(1.25, 1)       → 1.3        ROUND_EVEN(1.25, 1)  → 1.2   （2 是偶数，五留双）
ROUND(2.5, 0)        → 3.0        ROUND_EVEN(2.5, 0)   → 2.0
                                  ROUND_EVEN(3.5, 0)   → 4.0
ROUND_EVEN(1.35, 1)  → 1.4
FORMAT(0.04, 4)      → "0.0400"   FORMAT(2, 3)         → "2.000"
```

### 为什么必须拆出 `FORMAT`

制药行业对有效数字有强制要求，而 `0.04` 与 `0.0400` 表达的精度不同。
`ROUND` 返回数值 —— 数值没有「尾随零」这个概念，`0.0400` 存成数值就是 `0.04`。
所以展示用 `FORMAT`（字符串，零保住了），计算用 `ROUND`（数值，可继续参与运算）。

### ⚠️ `FORMAT` 的结果不能被下游引用

`FORMAT` 输出纯字符串数组，**进不了 `list_arrays`**，下游 CalculatedList
公式无法引用它做计算。

```
# ✅ 对：展示归展示，计算归计算
imp_pct_disp = FORMAT([imp_pct], 4)      # 只用于报表显示
imp_pct_calc = ROUND([imp_pct], 4)       # 下游引用这个

# ❌ 错：下游引用 FORMAT 的结果 → 取不到值
imp_total = GROUP_SUMlist([imp_pct_disp], [sid])
```

> **配置口径：需要参与后续计算的，引用 `ROUND`；只用于最终展示的，用 `FORMAT`。**

### 修约的是你填的那个十进制数

内部用 `Decimal(repr(值))` 而不是 `Decimal(浮点值)` —— 后者修约的是浮点二进制
展开。这样保证修约对象是**分析员实际填进去的那个十进制数**。

### 也可以套在数组函数外面

`ROUND` / `ROUND_EVEN` / `FORMAT` 对 list 入参会**逐元素映射**，所以下面这种
很自然的写法可用：

```
rec_avg_r = ROUND(GROUP_AVGlist([rec], [level]), 1)     # → [102.3, 102.3, ...]
rec_rsd_f = FORMAT(GROUP_RSDlist([rec], [level]), 2)    # → ["5.89", "5.89", ...]
r2_r      = ROUND(RSQ_ROWS(...), 4)                     # → [1.0]
```

---

## RESULT_NUM — 逐元素数值化

把报告值（可能是数值、也可能是 `<LOQ` / `N.D.` 这类标记）转成可求和的数值贡献，
用于「总杂」这类分组求和。

```
RESULT_NUM(值, 名称?, 主成分名?) → 数值
```

| 输入 | 输出 |
| ---- | ---- |
| 名称 == 主成分名 | `0`（主成分不计入总杂） |
| `N.D.` / `ND` / `<LOQ` / `<LOD` / 空 | `0`（限下结果贡献接近零） |
| 数值 | 该数值 |
| 其余非数值 | `---`（**未知**贡献，不能静默当 0 求和） |

**标量签名、逐元素路径、拆成两步写** —— 不要嵌套：

```
# 第一步：逐元素数值化（独立字段）
imp_num   = RESULT_NUM([imp_report], [imp_name], [imp_main_name_ref])

# 第二步：按样品分组求和
imp_total = GROUP_SUMlist([imp_num], [imp_sample_id])
```

> **为什么不嵌套写**：嵌套把两个函数耦合在一条公式里，任一环出错都只表现为
> 「总杂字段留空」，无法定位是数值化错了还是分组错了。拆两步后每步都有独立
> 字段可以直接看中间结果。
>
> 误把整个数组传进去时（例如公式被判到数组路径），返回 `---` 并记日志 ——
> **不会**静默取第一行的结果广播给所有行。

---

## TIME_ELAPSED_HOURS — 距最早进样的小时差

```
TIME_ELAPSED_HOURS(时间数组, 保留位数=1) → 数值数组
```

取整个数组的**最小值**为 t0，逐行算 `(t − t0)` 的小时差并修约。
最早那一行结果为 `0`。这是数组路径函数 —— 逐元素视角看不到全局最小值。

```
times = ["May 12, 2026 1:00:00 PM CST",
         "May 12, 2026 3:30:00 PM CST",
         "May 12, 2026 5:00:00 PM CST"]
TIME_ELAPSED_HOURS([inj_time], 1)   → [0.0, 2.5, 4.0]
```

支持两种格式：

| 格式 | 示例 |
| ---- | ---- |
| SENAITE 显示格式 | `May 12, 2026 1:00:00 PM CST` |
| ISO | `2026-05-12 13:00:00` / `2026-05-12T13:00:00+08:00` |

### 两条硬性约束

**① 月份名走内置表，不用 `%B`。** `%B` 经过 C locale，同一个字符串在一台部署上
能解析、换个 `LANG` 就失败，而失败只表现为字段留空。12 个月份名（缩写与全称）
都走 `_MONTHS` 表。非法月份名 → 该行 `---`。

**② 时区标识不一致则拒绝相减。** 跨夏令时切换时，同样的挂钟时差不是同样的
流逝时间。数组内时区标识不一致时**全部返回 `---` 并记日志**：

```
TIME_ELAPSED_HOURS: inconsistent timezone labels [u'CST', u'EST'] -- refusing to subtract
```

同一时区、或全部无标识都正常。**部分有标识、部分没有也拒绝** —— 此时无从判断。

其它行为：`12:00 AM` / `12:00 PM` 分别是午夜与正午；秒数计入；`digits` 可调；
跨日正常；无法解析的行为 `---` 而其余行照算；数组长度恒等于输入长度。

### 第三个参数：从别处取基准时间

```
TIME_ELAPSED_HOURS([时间数组], 小数位数, 基准时间)
```

不传第三个参数时，t0 是**数组内最早的那个时间**，所以最早那行读数为 `0`。
传了之后，t0 就是它 —— 而且**它可以来自另一个分析**：

```
imp_std1_inj_lookup = LOOKUP("imp_sys_suit","imp_std1_inj_time","imp_main_name","")
imp_qc_stab_time    = TIME_ELAPSED_HOURS([imp_qc_inj_time], 1, [imp_std1_inj_lookup])
```

这才是溶液稳定性真正测量的东西：**距对照品进样多少小时**，而不是距第一个
质控点多少小时。

| | 第一针 | 第二针 | 第三针 | 第四针 |
| -- | ---- | ---- | ---- | ---- |
| 不传基准（距首个质控点） | 0.0 | 35.1 | 55.4 | 78.6 |
| **传基准（距对照品进样）** | **34.0** | **69.1** | **89.4** | **112.6** |

两者**差一个常数**。写错了整列都偏，而每个值看上去都很正常 —— 这种错
最难在复核时发现。

### 负数是有意保留的

某一行早于基准时间，结果就是**负数**，不会被抹平也不会变成 `---`：

```
[34.0, -36.2, 89.4, 112.6]
```

它说的是「有一针的进样时间早于它所参照的对照品」—— 实验室里不可能发生，
所以那是**录入错误**。藏起来不如摆出来。日志里会点名具体是哪一行：

```
maitux.calcenhance: TIME_ELAPSED_HOURS on imp_qc_stability produced 1
negative hour(s): row 2 = u'2026-5-11 8:00'. Those rows are timestamped
BEFORE the reference (base u'2026-5-12 20:13'), which cannot happen --
check the entered times.
```

### 基准解析不出来就给 `---`，不回退

基准时间无法解析时**整列返回 `---`**，而不是悄悄退回「数组内最早时间」：

```
TIME_ELAPSED_HOURS: base u'2026/5/12 20:13' is not a parsable timestamp
-- refusing to fall back to the array minimum
```

你明确指定了基准却读不出来，这时候换一个 t0 会算出一组**看着合理但口径
错误**的数。答不上来就说答不上来。

**最常见的触发原因就是斜杠日期**（见上文格式表）。基准字段来自别的分析时，
那个源字段的格式同样要是连字符。

### 时区规则对基准同样生效

基准的时区标识必须和数组一致，否则照样拒绝相减。

### 不需要再往数组里塞一行

在此之前，要拿到「距对照品进样」这个口径，只能把对照品的进样时间**当作一行
数据塞进质控数组**。那行会连带出现在同一张表的其它列里（一个面积、一个
回收率），将来做 RSD 或限度判定时就是个真实的污染源。有了基准参数就不必了。

---

## TIME_ELAPSED_HOURS 接受的时间格式

**只认两种写法。斜杠日期（`2026/5/13 20:47`）不被识别** ——
这是中文 Excel 和 Windows 中文区域设置的默认格式，从色谱工作站或 Excel
复制粘贴过来通常就是它，所以这是最常见的一个坑。

### 可以用的

| 形式 | 例 | 说明 |
| ---- | -- | ---- |
| **连字符日期** | `2026-05-13 20:47` | 推荐 |
| 连字符 + 秒 | `2026-05-13 20:47:30` | 秒可省略 |
| 连字符 + 不补零 | `2026-5-13 20:47` | 月/日/时都接受 1~2 位 |
| ISO `T` 分隔 | `2026-05-13T20:47:30` | |
| ISO + 时区 | `2026-05-13T20:47:30+08:00` | |
| 连字符 + 时区标签 | `2026-05-13 20:47:30 CST` | |
| **英文月份名** | `May 13, 2026 8:47:00 PM CST` | SENAITE 渲染 datetime 的样子 |
| 英文月份缩写 | `May 13 2026 20:47` | 逗号、AM/PM、时区均可省略 |

### 不能用的

| 形式 | 例 | 结果 |
| ---- | -- | ---- |
| **斜杠日期** | `2026/5/13 20:47` | **无法识别 -> 整列 `---`** |
| 只有日期没有时间 | `2026-05-13` | 无法识别 |
| 中文日期 | `2026年5月13日 20:47` | 无法识别 |
| 中文月份名 | `5月 13, 2026` | 月份名表只有英文缩写 |

### 失败时的表现（重要）

**没有报错，字段直接变成整列 `---`**，很容易被当成公式写错。
日志里会有一行说明：

```
maitux:   TIME_ELAPSED_HOURS: no parsable timestamp in 23 value(s)
```

所以「时间点(h)」整列是 `---` 时，**先检查时间格式**，再怀疑公式。

### 时区标签必须一致

数组里若出现**两种不同的时区标签**，引擎**拒绝相减**并整列给 `---`：

```
maitux:   TIME_ELAPSED_HOURS: inconsistent timezone labels ['CST', 'UTC'] -- refusing to subtract
```

跨夏令时切换时，同样的挂钟差值不代表同样的实际经过时间 —— 这是有意为之，
不是缺陷（见 `ISSUES.md` ISSUE-007）。要么全部带同一个标签，要么全部不带。

### 语义

```
TIME_ELAPSED_HOURS([时间数组], 小数位数)
```

以数组里**最早**的那个时间为 t0，逐行给出「距 t0 多少小时」。
所以最早那一行读数为 `0`。无法解析的单个值给 `---`，其余行照常计算。

```
输入  ["2026-05-13 20:47", ... x11, "2026-05-14 04:51", ... x12]
输出  [0.0, ... x11, 8.1, ... x12]        # 相差 8 小时 4 分 -> 8.1
```

---

## LOOKUP 的自动重算与界面刷新

改动一个被 LOOKUP 引用的字段并保存，引用它的分析会**自动重算**，而且那一行
**当场就在界面上更新**，不需要刷新页面。

```
有关物质-回收率称量        改 [称样量] A1: 21.352 -> 10.218
        |
        | LOOKUP("imp_rec_weigh", "imp_weight", ...)
        v
有关物质-非指定杂质回收率  [称样量] 立即变 10.218
                           [加入量] [回收率] [平均] [RSD] [置信区间] 跟着全变
```

### 前提：源字段必须勾了 Cross-ref

重算的触发条件是「**某个勾了 Cross-ref 的字段真的变了**」。LOOKUP 也只能读到
勾了 Cross-ref 的字段。所以源字段（取值列）和 key 字段（匹配列）**都要勾上**：

```
LOOKUP("imp_rec_weigh", "imp_weight", "imp_weigh_sample_id", [imp_ns_rec_prep])
                          ^^^^^^^^^^^^   ^^^^^^^^^^^^^^^^^^^^^
                          这两个都要 Cross-ref = yes
```

只勾了取值列没勾 key 列，LOOKUP 会读不到 key，整列给 `---`。

### 范围是整个样品树，含分样

分样（partition）不是嵌套的：`create_partition()` 会新建一个 AnalysisRequest 并把
选中的分析**移**过去。所以重算是从**根样品**往下找的，跨分样也能引用。

这比 SENAITE 原生的依赖遍历更宽 —— 原生的从 `analysis.getRequest()` 出发，看不到
兄弟分样。实验室说「同一个样品」时，指的是包含分样的那个意思。

### 为什么这件事需要额外做

SENAITE 自己的依赖图只认两处声明：Calculation 的**主 Formula** 里的 `[keyword]`，
以及由它推导出的 `DependentServices`。而 LOOKUP 写在**interim 的 formula** 里，
源分析名还是个**字符串字面量**，两处都碰不到它 —— `getDependents()` 返回空。

界面保存后只重新渲染 `getDependents()` 报告的那些行，所以在 1.3.1 之前，被 LOOKUP
影响的那一行始终显示旧值，直到整页重新加载。

1.3.1 的做法是：重算函数本来就持有那份准确的清单，把它交给保存端点即可 ——
而不是去扩大 `getDependents()`。后者同时驱动**撤回 / 复测 / 拒绝**的准入判定和
状态流转的级联，为一个显示问题去动受控流程，代价和收益不成比例。

### 已知限制

重算兄弟分析时**不更新它的 `modified` 时间戳**。`modified` 对应受控字段
`ModificationDate`，写它等于宣称「这条记录被人改过」，而重算是系统行为、不是人工
修改。这个口径要由质量体系决定，代码里暂不预设。

实际影响：按「最近修改」排序或筛选时，被动重算过的分析不会浮上来。

---

## SHIFT — 取相邻行的值

```
SHIFT([数组], 位移)
```

| 位移 | 取哪一行 |
| ---- | -------- |
| `-1` | **下一行**（往下看） |
| `+1` | **上一行**（往上看） |
| `-2` / `+2` | 下/上两行 |
| `0` | 本行（恒等，一般无意义） |

**越界的行给 `---`**，不是 `0`。

### 实例：色谱分离度

「与前峰分离度」是仪器采集的；「与后峰分离度」就是同一列**往下串一行**：

```
imp_sep_res_after = SHIFT([imp_sep_res_before], -1)
```

```
物质        与前峰分离度(采集)   与后峰分离度(SHIFT -1)
未知杂质    0                     59.6
未知杂质    59.6                  12.3
Z7          12.3                  2.5
U1          2.5                   2.2
...
B           36.3                  7.9
Z14         7.9                   ---        <- 没有后峰
```

在此之前这一列只能**手工把同一批数字抄第二遍、错开一行** ——
十几行的表格很容易错位，而且错了看不出来。

### 为什么越界给 `---` 而不是 `0`

**「没有后峰」和「分离度为零」是两回事。** 分离度 `0` 意味着两个峰完全重叠
（严重的系统适用性失败），而末行根本不存在后峰。若给 `0`，后面做限度判定
时会把「不存在」误判成「严重不合格」。

### 是数组路径函数

`SHIFT` 需要看到**整列**才知道相邻行是什么，所以它走数组路径
（和 `GROUP_*` / `*_ROWS` / `COALESCE` 同一条）。逐元素路径只能看到当前行，
做不了这件事。

---

## COALESCE — 一个字段，多个来源

同一个数据在不同 AS 里分别保存时使用。典型场景：**纯度**
—— 主成分的纯度在系统适用性里，杂质的纯度在杂质对照品称量里。

```
COALESCE(值1, 值2, ...)
```

逐行取**第一个有值**的参数。全都缺失则该行为 `---`。
「有值」的判定沿用缺失值规则：`---`、空串、`None` 都算缺失。

### 实例：纯度从两个 AS 自动汇总

```
# imp_lod_loq_weigh.imp_purity（改成 Calculated List）
COALESCE(
  LOOKUP("imp_sys_suit","imp_std1_purity","imp_main_name",[imp_name],"---"),
  LOOKUP("imp_std_weigh","imp_purity","imp_name",[imp_name],"---"))
```

```
imp_name        = ["S1919", "Z7",  "Z10" ]
主成分源 LOOKUP  = [0.992,   ---,    ---   ]   # 只有主成分那行匹配得上
杂质源   LOOKUP  = [---,     0.995,  0.949 ]   # 只有杂质那些行匹配得上
COALESCE 之后    = [0.992,   0.995,  0.949 ]
```

**前提**：两个源的纯度字段都要勾 **Cross-ref**，否则 LOOKUP 读不到。

### 参数顺序 = 优先级；来源打架会告警

同一行里有**多个来源都有值且不一致**时：按参数顺序取第一个（所以参数顺序
就是声明的优先级），同时打一条 `logger.warn` 点名冲突。

```
maitux.calcenhance: COALESCE on <分析> row 2 found more than one source
with a value: kept 0.992 (the first argument wins) and ignored [0.995]
-- decide which source is authoritative
```

**不会**静默消化分歧 —— 两个源对同一个物质给出不同纯度，本身就是数据问题，
应该被看见。

> **为什么没做 `IF`**：Python 的函数调用不是惰性的，`IF(cond, A(), B())`
> 会把 B 也算一遍，B 一抛错就毁掉整条公式。而修好 LOOKUP 的 key 匹配之后，
> 「哪个源存哪个物质」这条规则已经写在**数据**里，用 `COALESCE` 即可，
> 不需要在公式里再维护一份规则。详见 `ISSUES.md` ISSUE-022。

---

## 求值顺序 —— 按字段定义顺序

**求值顺序 = Interim Fields 在计算公式里的定义顺序（从上到下）。**

引擎把带公式的字段按定义顺序切成「连续同类型的段」，逐段前向求值：

```
# 有关物质-线性与范围 的实际分段
段1 Calculated List  [imp_lin_w1, imp_lin_c1..c7, imp_lin_slope, intercept, r2, r, sse]
段2 Calculated       [imp_main_name_ref, imp_main_slope]      <- 能读到段1的结果
段3 Calculated List  [imp_correction_factor]
```

所以**一个 Calculated 字段可以引用定义在它前面的 Calculated List 字段**
（v1.1.0 做不到：那时是「先全部标量、再全部数组」，标量永远看不到数组的结果）。

### 这条规则对配置的要求

**公式引用的字段，必须定义在自己前面。** 引用了后面的字段，引擎会打日志：

```
maitux.calcenhance: <分析> has 1 interim(s) that reference a keyword
defined after themselves; evaluation follows the Calculation field order,
so move the dependency earlier: imp_stab_time(#0) -> imp_inj_time(#1)
```

看到这条日志就把被引用的字段**往上移**。

> 兜底：顺序不对时引擎仍会多扫一趟（最多 3 趟）把值算出来，不会让你卡住，
> 但会打上面那条日志。**不要依赖兜底** —— 依赖链一长就可能扫不完。

### 顺序以「样品记录」为准，不是计算公式模板

这一条容易踩：SENAITE 在**创建分析时**把计算公式的 interim 列表**拷贝**到
样品记录上（还存了 `CalculationVersion` 供追溯）。之后：

- 改计算公式模板的字段次序 → **只影响将来新建的分析**
- **已登记的样品保留原顺序**，不会被追溯修改

这是 SENAITE 的有意设计，在 GMP 上也是对的 —— 已登记样品必须用当时那版公式算。
所以改完模板要验证效果，得**新建一个样品**，改现有样品看不到变化。

### 循环引用

A 引用 B、B 又引用 A，无论什么顺序都算不出来。引擎会在扫到上限后停止并打日志，
不会挂死，但字段会停在 `---`。**请避免循环引用。**

---

## 缺失值语义 —— `---` 占位符

**核心原则：算不出来就显示 `---`，绝不编造一个数字。**

在 GMP 场景下，「显示一个不该相信的数字」比「算不出来」危险得多 ——
数值看起来完全正常，只有把输入重算一遍才会发现它对不上。

### 聚合函数 vs 运算符 —— 规则相反，务必分清

| | 规则 | 例 |
| -- | ---- | -- |
| **聚合函数**（`min` `max` `sum` `avg` `stdev` `GROUP_*` `*_ROWS`） | **跳过**缺失成员 | `max(5.0, ---)` = `5.0` |
| 聚合后一个成员都不剩 | 给 `---`（**不是 0**） | `avg(---, ---)` = `---` |
| **二元运算符**（`+` `-` `*` `/` `**`） | **传播** | `5.0 - ---` = `---` |
| **比较运算**（`>` `<` `==` …） | **传播** | `5.0 > ---` = `---` |

**为什么运算符不能跟着「跳过」**：跳过要为每个运算符发明一个单位元，
而 `*` 和 `/` 上会静默出错值。用真实公式说明：

```
imp_pct = [imp_area]/[F_main_lookup]/[imp_weight_lookup]*[imp_dilution]*100
```

若**称样量缺失**而「跳过」它，结果是一个**看起来完全合理的百分数**，
但整体偏了一个称样量的倍数。聚合是「对一组数取统计量，缺的成员不参与」，
语义明确；二元运算是「这个公式需要这个操作数」，缺了就是**算不出来**。

典型用例：**两法计算差值** —— 一法有值、一法为 `---`，
差值必须是 `---`，不能是那个有值的数。

> Python 2 的坑（已在引擎内堵住，此处仅作说明）：`2 * u"---"` 会得到
> `u"------"`、`5.0 > u"---"` 会得到 `False`、`min(5.0, u"---")` 会得到 `5.0`
> —— 都**不抛错**。引擎把缺失值绑定为一个专用哨兵对象，任何运算符碰到它
> 一律抛错，再由调用方转成 `---`。

### 聚合与统计

| 情形 | 行为 |
| ---- | ---- |
| 组内有个别缺失值 | **跳过缺失值，用剩余的算**（一次失败进样不该让整组不出结果） |
| 组内有效值 `< 2`，求 SD / RSD / 置信区间 | `---`（1 个点算不出标准偏差） |
| 组内均值为 0，求 RSD | `---`（RSD 是对均值的比值，均值为零则未定义） |
| 组内全部缺失 | `---`；但 `GROUP_COUNTlist` 返回 **0**（「有几个」永远有确定答案） |
| 自由度超出 `_T_95` 表范围 | `---` + 日志 |

### 回归

| 情形 | 行为 |
| ---- | ---- |
| 某点某轴缺失 | **只丢那一对**，用剩余的 (x, y) 对回归 |
| 存活配对 `< 2` | `---` |
| **`RSQ_ROWS` 存活点 `< 5`** | `---`（ICH Q2 要求 5 个浓度水平；2 个点的 R² 必然是 1.0，那是从零证据断言完美线性） |
| 所有存活点落在同一个 x | `---`（没有直线被确定；`0.0` 会是「水平线」这个具体断言） |
| `SLOPE/INTERCEPT/RSQ_ROWS` 该行数据不完整 | `---`（线性数据必须完整） |

### 数组长度恒等于行数

任何一行算失败都会填入 `---`，**输出数组长度永远等于输入行数**。
这保证了它与兄弟数组的 index 对齐 —— 否则某一行的值会显示到另一行上。

> `---` 在逐元素路径上会**自动向下传播**：某行输入含 `---`，该行结果也是 `---`，
> 行位置不丢。`RESULT_STATUS` 对非数值输入降级为 em-dash `—`。

---

## 文件结构

```
maitux.calcenhance/
├── README.md                          # 本文档
├── setup.py                           # Python 包配置
└── src/
    └── maitux/
        ├── __init__.py                # namespace package
        └── calcenhance/
            ├── __init__.py            # 入口：调用 apply_patches()
            ├── configure.zcml         # 主 ZCML 配置
            ├── overrides.zcml         # 覆盖核心 vocabulary 的 ZCML
            ├── patches.py             # 所有 monkey-patch 逻辑
            ├── config/
            │   ├── __init__.py
            │   └── vocabularies.py    # ADDITIONAL_RESULT_TYPES 定义
            ├── profiles/
            │   ├── __init__.py
            │   ├── configure.zcml     # GenericSetup 注册
            │   ├── default/
            │   │   └── metadata.xml
            │   └── uninstall/
            │       └── metadata.xml
            └── vocabularies/
                ├── __init__.py
                ├── configure.zcml     # vocabulary 覆盖注册
                └── resulttypes.py     # ResultTypesVocabulary 覆盖
```

---

## 注意事项

1. **Formula 列全局可见**：Formula 列在所有 Interim Fields 表格中均显示，但仅当 Control type 选择 `Calculated` 或 `Calculated List` 时才有实际作用
2. **Cross-ref 列**：在所有 Interim Fields 表格中均显示。勾选后，该字段可被同 AR 下其他 Analysis 的 `LOOKUP()` 函数读取
3. **求值顺序 = 字段定义顺序**：公式引用的字段必须定义在自己前面，否则引擎会打日志提示上移（详见「求值顺序」章节）。真正的循环引用（A 引 B、B 引 A）无论如何都算不出来，会停在 `---`
4. **公式错误容错**：子公式求值失败时，该 Calculated/CalculatedList 字段保留原值不变，不会阻断保存流程
5. **List 数据存储**：List 类型以 JSON 数组存储原始数据。Calculated 引用时自动取平均值（向后兼容），CalculatedList 引用时逐元素配对
6. **CalculatedList 数组等长**：CalculatedList 公式引用的所有 List 数组必须长度一致，否则跳过计算。**例外**：完全为空的列（如未用到的浓度点 7）会自动补齐到行数，不会因此让整个 `*_ROWS` 回归失败
7. **CalculatedList 显示**：当前以只读文本显示 JSON 数组（如 `[0.410, 0.407, 0.412]`），后续版本会优化显示格式
8. **LOOKUP 跨分析引用**：LOOKUP 只能读取数据，不修改源分析。需要源字段勾选 Cross-ref 才能被读取。字符串数组（如溶剂名称）支持作为匹配键
9. **LOOKUP 的源只有一行时**：源字段是标量（一行）时，**真 key 必须匹配得上**，匹配不上给 `---`。若确实想说「这个源只有一行，直接给我」，把 key 实参写成 `""` 或 `0`（现有配置里的写法，继续有效）。v1.1.0 及以前 key 被忽略，任何行都会拿到那个值 —— 那会让杂质行拿到主成分的值
10. **源字段没录数据时**：LOOKUP 给 `---` 而不是空值。「源还没录」和「真的算出空」现在能区分开了
