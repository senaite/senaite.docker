# -*- coding: utf-8 -*-
from plone.supermodel import model
from senaite.core.content.base import Container
from zope.interface import implementer

from maitux.stock.interfaces import IStockManager


class IStockManagerSchema(model.Schema):
    pass


@implementer(IStockManager, IStockManagerSchema)
class StockManager(Container):
    pass

