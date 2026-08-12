# -*- coding: utf-8 -*-
from plone.supermodel import model
from senaite.core.content.base import Container
from zope.interface import implementer

from maitux.stock.interfaces import IStockSection


class IStockSectionSchema(model.Schema):
    pass


@implementer(IStockSection, IStockSectionSchema)
class StockSection(Container):
    pass

