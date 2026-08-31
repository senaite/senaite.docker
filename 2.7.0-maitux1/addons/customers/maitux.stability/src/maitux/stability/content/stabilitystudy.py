# -*- coding: utf-8 -*-
from plone.supermodel import model
from senaite.core.content.base import Item
from zope import schema
from zope.interface import implementer

from maitux.stability import _
from maitux.stability.interfaces import IStabilityStudy


class IStabilityStudySchema(model.Schema):
    title = schema.TextLine(
        title=_(u"Title"),
        required=True,
    )

    description = schema.Text(
        title=_(u"Description"),
        required=False,
    )


@implementer(IStabilityStudy, IStabilityStudySchema)
class StabilityStudy(Item):
    pass

