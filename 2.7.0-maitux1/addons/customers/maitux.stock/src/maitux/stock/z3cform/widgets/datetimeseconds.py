# -*- coding: utf-8 -*-
from senaite.core.z3cform.widgets.datetimewidget import DatetimeWidget
from z3c.form.interfaces import IFieldWidget
from z3c.form.widget import FieldWidget
from zope.interface import implementer


class DatetimeSecondsWidget(DatetimeWidget):
    def get_time(self, value):
        dt = self.to_datetime(value)
        if not dt:
            return u""
        return u"{:02d}:{:02d}:{:02d}".format(dt.hour, dt.minute, dt.second)

    def render(self):
        name = self.name
        value = self.value
        date_value = self.get_date(value) if value else u""
        time_value = self.get_time(value) if value else u""
        attrs = self.attrs() or {}
        minv = attrs.get("min", u"")
        maxv = attrs.get("max", u"")
        disabled = u"disabled" if self.disabled else u""
        readonly = u"readonly" if self.readonly else u""
        tabindex = self.tabindex if self.tabindex is not None else u""
        title = self.title or u""
        style = self.style or u""
        portal_url = self.portal_url
        html = u"""
<div class="input-group flex-nowrap d-inline-flex w-auto datetimewidget" id="{id}" style="{style}" title="{title}">
  <input type="date" class="form-control form-control-sm" target="{name}" name="{name}-date" value="{date_value}" min="{minv}" max="{maxv}" {disabled} {readonly} tabindex="{tabindex}" />
  {time_input}
</div>
<input type="hidden" id="{id}" title="{title}" name="{name}" value="{value}" />
<script type="text/javascript" src="{portal_url}/++resource++senaite.core.z3cform.static/datetimewidget.js"></script>
<link rel="stylesheet" href="{portal_url}/++resource++senaite.core.z3cform.static/datetimewidget.css" type="text/css" media="screen" />
""".format(
            id=self.id,
            style=style,
            title=title,
            name=name,
            date_value=date_value,
            time_input=(u'<input type="time" step="1" class="form-control form-control-sm" target="{0}" name="{0}-time" value="{1}" {2} {3} tabindex="{4}" />'.format(
                name, time_value, disabled, readonly, tabindex) if self.show_time else u""),
            value=value or u"",
            portal_url=portal_url,
            disabled=disabled,
            readonly=readonly,
            tabindex=tabindex,
            minv=minv,
            maxv=maxv,
        )
        return html


@implementer(IFieldWidget)
def DatetimeSecondsWidgetFactory(field, request):
    return FieldWidget(field, DatetimeSecondsWidget(request))
