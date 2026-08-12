# -*- coding: utf-8 -*-
from z3c.form.browser.text import TextWidget
from z3c.form.interfaces import IFieldWidget
from z3c.form.widget import FieldWidget
from zope.interface import implementer


class LowQuantityWidget(TextWidget):
    def render(self):
        html = super(LowQuantityWidget, self).render()
        # force numeric input type
        html = html.replace('type="text"', 'type="number"')
        # add step and class if missing
        if 'step="' not in html:
            html = html.replace('type="number"', 'type="number" step="0.01"')
        if 'class="' in html:
            html = html.replace('class="', 'class="numeric ')
        else:
            html = html.replace('type="number"', 'type="number" class="numeric"')
        return html


@implementer(IFieldWidget)
def LowQuantityWidgetFactory(field, request):
    return FieldWidget(field, LowQuantityWidget(request))
