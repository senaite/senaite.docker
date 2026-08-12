# -*- coding: utf-8 -*-
from decimal import Decimal

from bika.lims import bikaMessageFactory as _
from bika.lims.interfaces import IDeactivable
from plone.supermodel import model
from senaite.core.content.base import Item
from senaite.core.schema import TextLineField
from zope import schema
from zope.interface import implementer

from maitux.stock.interfaces import IStockItem


class IStockItemSchema(model.Schema):
    item_id = TextLineField(
        title=_(u"Item ID"),
        required=True,
    )

    title = schema.TextLine(
        title=_(u"Name"),
        required=False,
    )

    quantity = schema.Decimal(
        title=_(u"Quantity"),
        required=True,
        default=Decimal("0.00"),
    )

    unit = TextLineField(
        title=_(u"Unit"),
        required=False,
    )

    location = TextLineField(
        title=_(u"Storage Location"),
        required=False,
    )

    expiry_date = schema.Datetime(
        title=_(u"Expiry Date"),
        required=False,
    )


@implementer(IStockItem, IStockItemSchema, IDeactivable)
class StockItem(Item):
    _catalogs = ["portal_catalog"]

    def Title(self):
        item_id = getattr(self, "item_id", None)
        if item_id:
            return item_id
        return super(StockItem, self).Title()

