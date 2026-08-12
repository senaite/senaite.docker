# -*- coding: utf-8 -*-
from bika.lims.interfaces import IDoNotSupportSnapshots
from plone.supermodel import model
from senaite.core.content.base import Container
from senaite.core.interfaces import IHideActionsMenu
from zope.interface import implementer

from maitux.instrument_acquisition.interfaces import IInstrumentParsingTemplates


class IInstrumentParsingTemplatesSchema(model.Schema):
    pass


@implementer(
    IInstrumentParsingTemplates,
    IInstrumentParsingTemplatesSchema,
    IDoNotSupportSnapshots,
    IHideActionsMenu,
)
class InstrumentParsingTemplates(Container):
    pass

