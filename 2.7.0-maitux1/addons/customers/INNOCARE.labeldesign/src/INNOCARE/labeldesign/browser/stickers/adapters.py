# -*- coding: utf-8 -*-
# ADD(2026-08-21) - 标签模板适配器。
from senaite.core.interfaces.stickers import IGetStickerTemplates
from zope.interface import implementer


@implementer(IGetStickerTemplates)
class StockBatchLabelTemplates(object):
    """库存标签模板适配器。"""
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
    """样品标签模板适配器。"""
    default_template = "INNOCARE.labeldesign:SampleNormal_40x30mm.pt"

    def __init__(self, context):
        self.context = context

    def __call__(self, request):
        return [
            {
                "id": "INNOCARE.labeldesign:SampleNormal_40x30mm.pt",
                "title": "样品标签 (Sample Normal)",
            },
            {
                "id": "INNOCARE.labeldesign:SampleStability_40x30mm.pt",
                "title": "样品标签·稳定性 (Sample Stability)",
            },
        ]
