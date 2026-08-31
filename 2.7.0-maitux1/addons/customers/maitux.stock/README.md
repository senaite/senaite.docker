# maitux.stock

MAITUX 库存管理（Stock Management）扩展，提供库存条目、库存类型/单位、采购订单、库存批次（Stock Batch）及批次动作（领用 / 分装 / 归还 / 销毁 / 盘存 / 打印标签）的完整管理能力，并支持低量库存提醒与批次过期自动同步。

## 功能职责

- 内容类型（见 `src/maitux/stock/content/`）：
  - `StockManager`：库存管理根容器（侧边栏入口）。
  - `StockFolder` / `Stock` / `StockItem`：库存条目管理（编号、类型、样品基质、供应商、数量、单位、存储位置、有效期）。
  - `StockType` / `StockUnits`：库存类型与单位字典。
  - `StockPurchaseOrder` / `StockPurchaseOrders`：采购订单及订单行（含数量、单价、税率等）。
  - `StockBatch` / `StockBatches`：库存批次（批次编号自动生成、当前/目标数量、低量阈值、有效期、使用流水）。
  - `LowStockSection`：低库存入口（`LowStockBatchesView` 列表 + 门户顶部低量提醒 viewlet）。
- 批次动作页（`browser/stockbatch*.py` + 模板）：
  - 领用（`stockbatch_consume`）、归还（`stockbatch_return`）、分装（`stockbatch_split`，支持分装至已有批次或新建批次）、销毁（`stockbatch_destroy`）、盘存（`stockbatch_stocktake`）、打印标签（`stockbatch_print`，支持 Code128 / Code39 / QR 模板并导出 PDF）。
- 过期管理（`stockbatchexpiry.py`）：批次有效期到达后自动/手动同步为 `expired` 状态，过期批次仅允许销毁；提供定时任务入口 `@@sync_expired_batches`。
- 工作流：绑定 `senaite_stockbatch_workflow`，`active / expired / destroyed` 状态与 schema `status` 字段双向同步。
- 列表视图（Listing）：`stockbatches`、`lowstock`、`stock_items`、`stock_units`、`stock_types`、`purchase_orders`，支持多选批量动作与状态页签。
- 词汇工厂（`configure.zcml` / `vocabularies.py`）：`maitux.stock.vocabularies.suppliers`。
- JSON 辅助接口：`stock_quantity_json`、`stock_suppliers_json`（表单级联用）。

## 依赖

- `senaite.core` / `senaite.lims`
- `plone.api`、`plone.supermodel`、`senaite.core.schema`
- `zope.component`、`zope.interface`、`z3c.form`
- `Products.CMFCore`、`Products.Five`

> 与 `maitux.stability` 无强制耦合；`maitux.stability` 的样品放置会引用本 addon 的 `StockBatch`。

## 安装注册（buildout）

```ini
[buildout]
develop += /opt/addons/customers/maitux.stock
eggs    += maitux.stock
[instance]
zcml    += maitux.stock
[plonesite]
profiles += maitux.stock:default
```

安装后自动创建 `stockmanager` 侧边栏入口及其子结构（`stock` / `stock_units` / `stock_types` / `purchase_orders` / `stock_batches` / `low_stock`）。

## 双语翻译（i18n）

本 addon 使用独立的 i18n 域 `maitux.stock`，全部用户可见文案（列表标题/列名/按钮、schema 字段、批次动作、模板文本、侧边栏菜单标题）均通过该域的翻译目录解析，支持界面语言在中英文之间切换。

- `configure.zcml`：`<i18n:registerTranslations directory="locales" />` 注册翻译目录。
- 翻译目录：`src/maitux/stock/locales/{en,zh,zh-cn,zh_CN}/LC_MESSAGES/maitux.stock.po`（含已编译 `.mo`）。
- 侧边栏菜单标题回退：`INNOCARE.arextension` 的 `senaite.core.i18n.translate` 附加域回退列表已包含 `maitux.stock`。

## 更新说明（2026-08-31 · 双语翻译支持）

本次更新为该 addon 补充了完整的双语（中 / 英）翻译支持，遵循 `maitux.hazardcategories` 的 i18n 模式：

- `configure.zcml` 增加 `<i18n:registerTranslations directory="locales" />`。
- `__init__.py` 增加 `_` MessageFactory 别名（`maitux.stock` 域），并将工厂定义前置到 patches 导入之前，避免 `cannot import name _` 循环导入。
- 全部 browser / content 模块的消息工厂由 `bika/senaiteMessageFactory` 切换到本 addon 自有域（`from maitux.stock import _`），字符串按自身目录翻译。
- 新增中文翻译条目：列表标题/列名/操作按钮/状态页签（Active/Expired/Destroyed/All）、批次动作（领用/分装/归还/销毁/盘存/打印标签）、流水操作标签、schema 字段标题、门户消息、文件夹/侧边栏标题（Stockinventory/库存管理、Stock Item、Units、Stock Types、Purchase Orders、Stock Batches、Low Quantity 等），共 172 条 msgid。
- 模板补 `i18n:domain="maitux.stock"` + `i18n:translate`：`stock.pt`、`stockbatch.pt`、`stockbatchconsume/destroy/return/split/stocktake/print.pt`、低量 viewlet、采购行 datagrid。
- `setuphandlers.py` 的文件夹标题改为 Message 对象，随界面语言翻译。
- 翻译目录 `locales/{en,zh,zh-cn,zh_CN}` 及编译后的 `.mo` 随包发布；重启实例即生效，无需重装 profile。

## 卸载

- 执行 `maitux.stock:uninstall` profile：仅从侧边栏移除 `stockmanager` 注册，不删除业务数据。

## 备注

- 批次编号由 `INumberGenerator` 持久化计数器生成（`subscribers.py`），并发安全。
- 批量动作对所选批次做服务端校验（`stockbatchactions.py` / `workflow.py`），前端按钮与后端限制保持一致。
