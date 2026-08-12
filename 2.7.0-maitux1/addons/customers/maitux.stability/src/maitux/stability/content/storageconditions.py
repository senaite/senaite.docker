# -*- coding: utf-8 -*-
from bika.lims.interfaces import IDoNotSupportSnapshots
from plone.supermodel import model
from senaite.core.content.base import Container
from senaite.core.interfaces import IHideActionsMenu
from zope.interface import implementer

from maitux.stability.interfaces import IStorageConditions


class IStorageConditionsSchema(model.Schema):
    pass


@implementer(
    IStorageConditions,
    IStorageConditionsSchema,
    IDoNotSupportSnapshots,
    IHideActionsMenu,
)
class StorageConditions(Container):
    pass

