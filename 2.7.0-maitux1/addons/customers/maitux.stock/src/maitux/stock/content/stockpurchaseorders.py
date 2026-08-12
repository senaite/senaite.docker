# -*- coding: utf-8 -*-
from plone.supermodel import model
from senaite.core.content.base import Container
from zope.interface import implementer

from maitux.stock.interfaces import IStockPurchaseOrders


class IStockPurchaseOrdersSchema(model.Schema):
    pass


@implementer(IStockPurchaseOrders, IStockPurchaseOrdersSchema)
class StockPurchaseOrders(Container):
    pass


