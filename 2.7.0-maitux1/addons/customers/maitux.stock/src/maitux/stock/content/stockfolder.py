# -*- coding: utf-8 -*-
from plone.supermodel import model
from senaite.core.content.base import Container
from senaite.core.interfaces import IHideActionsMenu
from zope.interface import implementer

from maitux.stock.interfaces import IStockFolder


class IStockFolderSchema(model.Schema):
    pass


@implementer(IStockFolder, IStockFolderSchema, IHideActionsMenu)
class StockFolder(Container):
    pass

