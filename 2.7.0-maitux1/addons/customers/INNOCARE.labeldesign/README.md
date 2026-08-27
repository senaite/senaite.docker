# INNOCARE.labeldesign

INNOCARE 标签/贴纸（Label/Sticker）打印设计扩展，覆盖 3 份库存标签 + 2 份样品标签，全部含样品编号/批次二维码。

## 功能职责

- **库存标签模板**（挂在 `maitux.stock` 的 stockbatch 打印入口，见 `browser/stickers/adapters.py`）：
  - ① `InventoryNormal_40x20mm.pt` — 库存标签：库存编号、物料名称、厂家批号、存储位置 + 条码 + 二维码。
  - ② `InventoryReference_40x20mm.pt` — 库存标签·对照品：① ＋ 生产厂家、复检期、储存条件、含量/纯度。
  - ③ `InventoryStability_40x20mm.pt` — 库存标签·稳定性样品：库存编号、物料名称、厂家批号、放置条件、放置位置 + 条码 + 二维码。
- **样品标签模板 + 打印视图**（`browser/sampleprint.py` / `sampleprint.pt`，数据源为 Sample / AnalysisRequest 的 `SuperModel`）：
  - ④ `SampleNormal_40x30mm.pt` — 样品标签：样品编号、条码、物料名称、厂家批号 + 二维码。
  - ⑤ `SampleStability_40x30mm.pt` — 样品标签·稳定性：④ ＋ 放样日期、取样点、放置条件。
- 标签 HTML 结构 + CSS 分别置于 `browser/stickers/templates/{stockbatch,sample}/`，二维码/条码由打印页 JS（`BarcodeUtils`）按 `data-text`/`data-id` 渲染生成 PDF。

## 依赖

- `senaite.core` / `senaite.lims` / `bika.lims`
- `maitux.stock`（必选：库存标签模板通过其 stockbatch 打印入口以 `IGetStickerTemplates` 接入；模板数据源为 StockBatch/Stock `SuperModel`）
- `INNOCARE.arextension`（样品④⑤ 物料名称取 AR 扩展字段 `MaterialName` 等）
- `bsddb` 无关；需 `reportlab`（`bika.lims.utils.createPdf`）

**新增字段依赖（未落地前模板相应字段为空/占位）**：储存条件、含量/纯度、放置条件、放置位置。

## 安装注册（buildout）

```ini
[buildout]
develop += /opt/addons/customers/INNOCARE.labeldesign
eggs    += INNOCARE.labeldesign
[instance]
zcml    += INNOCARE.labeldesign
[plonesite]
profiles += INNOCARE.labeldesign:default
```

## 迁移 / 独立部署评估

**不能脱离 `maitux.stock` / `INNOCARE.arextension` 独立部署**——库存模板复用 stock 打印入口与 StockBatch 数据模型；样品模板复用 arextension 的 AR 字段与打印机制。

目标环境顺序：**先 `maitux.stock:default`、`INNOCARE.arextension:default`，再 `INNOCARE.labeldesign:default`**。对其它 maitux addon 无耦合。

## 卸载

- 执行 `INNOCARE.labeldesign:uninstall` profile 后，移除 `custom-addon.cfg` 三处注册。