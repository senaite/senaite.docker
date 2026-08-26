# -*- coding: utf-8 -*-
# ADD(2026-08-21) - 库存标签模板适配器。
# 提供 3 份库存标签模板，供 maitux.stock 的 stockbatch_print 打印入口选用。
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