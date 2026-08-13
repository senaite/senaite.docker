# -*- coding: utf-8 -*-
from bika.lims import senaiteMessageFactory as _
from bika.lims.interfaces import IDeactivable
from plone.supermodel import model
from senaite.core.catalog import SETUP_CATALOG
from senaite.core.content.base import Container
from zope import schema
from zope.interface import implementer

from maitux.stability.interfaces import IStorageCondition


class IStorageConditionSchema(model.Schema):
    title = schema.TextLine(
        title=_(u"Name"),
        required=True,
    )

    description = schema.Text(
        title=_(u"Description"),
        required=False,
    )


@implementer(IStorageCondition, IStorageConditionSchema, IDeactivable)
class StorageCondition(Container):
    _catalogs = [SETUP_CATALOG]

