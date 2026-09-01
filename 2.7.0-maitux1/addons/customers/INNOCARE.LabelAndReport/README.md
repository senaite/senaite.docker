# INNOCARE.LabelAndReport

合并后的 INNOCARE 打印模板 addon，统一承载：

- 标签/贴纸模板：原 `INNOCARE.labeldesign`
- 数据报告 / COA 模板：原 `INNOCARE.Reportdesign`

## 合并说明

- 新的分发名与 addon 根目录统一为 `INNOCARE.LabelAndReport`
- 内部继续复用 `INNOCARE.labeldesign` 与 `INNOCARE.reportdesign` 两个代码包
- 标签模板资源前缀改为 `INNOCARE.LabelAndReport:*`
- 数据报告 / COA 继续保留 `reportdesign:*` 模板前缀，避免影响既有使用入口

## 安装依赖

- `senaite.core`
- `senaite.lims`
- `maitux.stock`
- `INNOCARE.arextension`

## Profile

- 安装：`INNOCARE.LabelAndReport:default`
- 卸载：`INNOCARE.LabelAndReport:uninstall`
