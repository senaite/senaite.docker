# -*- coding: utf-8 -*-
# ADD(2026-08-21) - 库存标签模板适配器。
# 提供 3 份库存标签模板，供 maitux.stock 的 stockbatch_print 打印入口选用。
from senaite.core.interfaces.stickers import IGetStickerTemplates
from zope.interface import implementer


@implementer(IGetStickerTemplates)
class SampleLabelTemplates(object):
    """样品标签模板适配器。

    供 senaite.core 的 StickerView（/lims/samples/sticker）在样品列表上枚举、
    选用 labeldesign 的样品标签模板。

    为什么必须要这个适配器：senaite.core 的 get_sticker_templates() 用
    iterDirectoriesOfType("stickers") 只收集 resource 顶层目录的 *.pt，而本
    addon 的样品模板放在 sample/ 子目录，顶层没有 *.pt，因此无法被默认枚举。
    适配器通过 IGetStickerTemplates 直接提供模板列表和 default_template，
    使 /lims/samples/sticker（无 template 参数）也能渲染出本 addon 的样品标签，
    而不依赖已被清空的 Setup AutoStickerTemplate。
    """
    # NOTE: senaite.core StickerView.render_sticker 会把 id 中 ":" 后的部分
    # 直接拼接到 resource 顶层目录后（templates/<filename>）。
    # 样品模板现已移至顶层目录。
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