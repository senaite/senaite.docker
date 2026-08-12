# -*- coding: utf-8 -*-
from bika.lims import api
from senaite.core.z3cform.widgets.uidreference.widget import UIDReferenceWidget
from z3c.form.interfaces import IFieldWidget
from z3c.form.interfaces import NO_VALUE
from z3c.form.widget import FieldWidget
from zope.interface import implementer


class SafeUIDReferenceWidget(UIDReferenceWidget):
    def get_context(self):
        context = super(SafeUIDReferenceWidget, self).get_context()
        if context in (None, NO_VALUE):
            return api.get_portal()
        return context


@implementer(IFieldWidget)
def SafeUIDReferenceWidgetFactory(field, request):
    return FieldWidget(field, SafeUIDReferenceWidget(request))

