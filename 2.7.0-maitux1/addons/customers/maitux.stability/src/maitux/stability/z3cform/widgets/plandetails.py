# -*- coding: utf-8 -*-
from bika.lims import api
from senaite.core.z3cform.widgets.datagrid.datagrid import DataGridWidget
from senaite.core.z3cform.widgets.uidreference.widget import UIDReferenceWidget
from z3c.form.interfaces import IFieldWidget
from z3c.form.interfaces import NO_VALUE
from z3c.form.widget import FieldWidget
from zope.browserpage.viewpagetemplatefile import ViewPageTemplateFile
from zope.interface import implementer


plandetails_datagrid_input = ViewPageTemplateFile("plandetails_datagrid_input.pt")


class PlanDetailsWidget(DataGridWidget):
    def render(self):
        if self.mode == "input":
            return plandetails_datagrid_input(self)
        return super(PlanDetailsWidget, self).render()


class SafeUIDReferenceWidget(UIDReferenceWidget):
    def get_context(self):
        context = super(SafeUIDReferenceWidget, self).get_context()
        if context in (None, NO_VALUE):
            return api.get_portal()
        return context


@implementer(IFieldWidget)
def PlanDetailsWidgetFactory(field, request):
    return FieldWidget(field, PlanDetailsWidget(request))


@implementer(IFieldWidget)
def SafeUIDReferenceWidgetFactory(field, request):
    return FieldWidget(field, SafeUIDReferenceWidget(request))
