# -*- coding: utf-8 -*-
from bika.lims.interfaces import IDeactivable
from plone.supermodel import model
from senaite.core.catalog import SETUP_CATALOG
from senaite.core.content.base import Container
from zope import schema
from zope.interface import implementer

from maitux.stock import _
from maitux.stock.interfaces import IStockUnit


class IStockUnitSchema(model.Schema):
    title = schema.TextLine(
        title=_(u"Unit"),
        required=True,
    )

    description = schema.Text(
        title=_(u"Description"),
        required=False,
    )


@implementer(IStockUnit, IStockUnitSchema, IDeactivable)
class StockUnit(Container):
    _catalogs = [SETUP_CATALOG]


