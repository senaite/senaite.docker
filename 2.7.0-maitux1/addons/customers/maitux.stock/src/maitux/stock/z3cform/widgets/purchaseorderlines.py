# -*- coding: utf-8 -*-
from senaite.core.z3cform.widgets.datagrid.datagrid import DataGridWidget
from z3c.form.interfaces import IFieldWidget
from z3c.form.widget import FieldWidget
from zope.browserpage.viewpagetemplatefile import ViewPageTemplateFile
from zope.interface import implementer


purchaseorderlines_datagrid_input = ViewPageTemplateFile(
    "purchaseorderlines_datagrid_input.pt")


class PurchaseOrderLinesWidget(DataGridWidget):
    def render(self):
        if self.mode == "input":
            return purchaseorderlines_datagrid_input(self)
        return super(PurchaseOrderLinesWidget, self).render()


@implementer(IFieldWidget)
def PurchaseOrderLinesWidgetFactory(field, request):
    return FieldWidget(field, PurchaseOrderLinesWidget(request))
