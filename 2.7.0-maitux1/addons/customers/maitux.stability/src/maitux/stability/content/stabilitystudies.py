# -*- coding: utf-8 -*-
from bika.lims.interfaces import IDoNotSupportSnapshots
from plone.supermodel import model
from senaite.core.content.base import Container
from senaite.core.interfaces import IHideActionsMenu
from zope.interface import implementer

from maitux.stability.interfaces import IStabilityStudies


class IStabilityStudiesSchema(model.Schema):
    pass


@implementer(
    IStabilityStudies,
    IStabilityStudiesSchema,
    IDoNotSupportSnapshots,
    IHideActionsMenu,
)
class StabilityStudies(Container):
    pass

