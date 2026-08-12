# -*- coding: utf-8 -*-
from plone.supermodel import model
from senaite.core.content.base import Container
from zope.interface import implementer

from maitux.stock.interfaces import IStockUnits


class IStockUnitsSchema(model.Schema):
    pass


@implementer(IStockUnits, IStockUnitsSchema)
class StockUnits(Container):
    pass

