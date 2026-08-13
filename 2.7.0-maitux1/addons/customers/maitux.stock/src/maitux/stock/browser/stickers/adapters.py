# -*- coding: utf-8 -*-
from senaite.core.interfaces.stickers import IGetStickerTemplates
from zope.interface import implementer


@implementer(IGetStickerTemplates)
class StockBatchStickerTemplates(object):
    default_template = "maitux.stock:Minimal_QR_30x30mm.pt"

    def __init__(self, context):
        self.context = context

    def __call__(self, request):
        return [
            {"id": "maitux.stock:Minimal_QR_30x30mm.pt", "title": "Minimal QR 30x30mm"},
            {"id": "maitux.stock:Code_128_40x20mm.pt", "title": "Code 128 40x20mm"},
        ]


