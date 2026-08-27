# -*- coding: utf-8 -*-
# ADD(2026-08-21) - 库存/样品标签模板适配器。
# 库存模板供 maitux.stock 的 stockbatch_print 打印入口选用；
# 样品模板供 senaite 标准 sticker 视图（/samples/sticker）选用。
from senaite.core.interfaces.stickers import IGetStickerTemplates
from zope.interface import implementer


@implementer(IGetStickerTemplates)
class StockBatchLabelTemplates(object):
    default_template = "INNOCARE.labeldesign:InventoryNormal_40x20mm.pt"

    def __init__(self, context):
        self.context = context

    def __call__(self, request):
        return [
            {
                "id": "INNOCARE.labeldesign:InventoryNormal_40x20mm.pt",
                "title": "库存标签 (Inventory Normal)",
            },
            {
                "id": "INNOCARE.labeldesign:InventoryReference_40x20mm.pt",
                "title": "库存标签·对照品 (Inventory Reference)",
            },
            {
                "id": "INNOCARE.labeldesign:InventoryStability_40x20mm.pt",
                "title": "库存标签·稳定性样品 (Inventory Stability)",
            },
        ]


@implementer(IGetStickerTemplates)
class SampleLabelTemplates(object):
    """样品标签模板（④⑤），供 senaite 标准 sticker 视图（Samples 目录上下文）枚举。
    """

    default_template = "INNOCARE.labeldesign:SampleNormal_40x30mm.pt"

    def __init__(self, context):
        self.context = context

    def __call__(self, request):
        templates = [
            {
                "id": "INNOCARE.labeldesign:SampleNormal_40x30mm.pt",
                "title": "样品标签 (Sample Normal)",
            },
            {
                "id": "INNOCARE.labeldesign:SampleStability_40x30mm.pt",
                "title": "样品标签·稳定性 (Sample Stability)",
            },
        ]
        # 默认模板标记为选中
        for template in templates:
            template["selected"] = (
                template.get("id") == self.default_template)
        return templates