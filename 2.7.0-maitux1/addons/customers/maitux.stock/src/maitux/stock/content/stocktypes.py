# -*- coding: utf-8 -*-
from plone.supermodel import model
from senaite.core.content.base import Container
from zope.interface import implementer

from maitux.stock.interfaces import IStockTypes


class IStockTypesSchema(model.Schema):
    pass


@implementer(IStockTypes, IStockTypesSchema)
class StockTypes(Container):
    pass

