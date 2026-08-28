# -*- coding: utf-8 -*-
from bika.lims import api
from bika.lims.interfaces import IDeactivable
from bika.lims.interfaces import IHaveInstrument
from bika.lims import senaiteMessageFactory as _
from plone.autoform import directives
from plone.namedfile.field import NamedBlobFile
from plone.supermodel import model
from senaite.core.catalog import SETUP_CATALOG
from senaite.core.content.base import Item
from senaite.core.schema import IntField
from senaite.core.schema import TextLineField
from senaite.core.schema import UIDReferenceField
from senaite.core.z3cform.widgets.uidreference import UIDReferenceWidgetFactory
from zope import schema
from zope.interface import Invalid
from zope.interface import implementer
from zope.interface import invariant

from maitux.instrument_acquisition.interfaces import IInstrumentParsingTemplate


class IInstrumentParsingTemplateSchema(model.Schema):
    title = schema.TextLine(
        title=_(u"title_instrumentparsingtemplate_title", default=u"Name"),
        required=True,
    )

    instrument = UIDReferenceField(
        title=_(u"title_instrumentparsingtemplate_instrument", default=u"Instrument"),
        allowed_types=("Instrument",),
        multi_valued=False,
        required=True,
    )
    directives.widget(
        "instrument",
        UIDReferenceWidgetFactory,
        catalog=SETUP_CATALOG,
        query={
            "portal_type": "Instrument",
            "is_active": True,
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        },
        columns=[
            {
                "name": "Title",
                "width": "30",
                "align": "left",
                "label": _(u"Title"),
            }, {
                "name": "Description",
                "width": "70",
                "align": "left",
                "label": _(u"Description"),
            },
        ],
        limit=15,
    )

    port = TextLineField(
        title=_(u"title_instrumentparsingtemplate_port", default=u"Port"),
        required=False,
    )

    ip_address = TextLineField(
        title=_(u"title_instrumentparsingtemplate_ip", default=u"IP Address"),
        required=False,
    )

    agent_api_url = TextLineField(
        title=_(u"title_instrumentparsingtemplate_agent_api_url",
                default=u"采集端接口地址 (Agent API URL)"),
        description=_(u"desc_instrumentparsingtemplate_agent_api_url",
                      default=u"本地采集端（中转平台）的 HTTP 接口地址，"
                              u"与上方天平 IP/端口不同，如 http://192.168.1.5:8090"),
        required=False,
    )

    agent_token = TextLineField(
        title=_(u"title_instrumentparsingtemplate_agent_token",
                default=u"采集端 Token"),
        description=_(u"desc_instrumentparsingtemplate_agent_token",
                      default=u"采集端（中转平台）生成的 Token 凭证，"
                              u"一个中转站一个 Token；多台仪器共用同一中转站可填相同值。"
                              u"采集端推送/拉取配置时用该 Token 鉴权。"),
        required=False,
    )

    script_file = NamedBlobFile(
        title=_(u"title_instrumentparsingtemplate_script", default=u"Parser Script File"),
        required=False,
    )

    description = schema.Text(
        title=_(u"title_instrumentparsingtemplate_description", default=u"Remarks"),
        required=False,
    )

    forward_enabled = schema.Bool(
        title=_(u"title_instrumentparsingtemplate_forward_enabled", default=u"Enable HTTP Forward"),
        description=_(u"desc_instrumentparsingtemplate_forward_enabled", default=u"Enable forwarding parsed data to HTTP endpoint"),
        required=False,
        default=False,
    )

    forward_url = TextLineField(
        title=_(u"title_instrumentparsingtemplate_forward_url", default=u"Forward URL"),
        description=_(u"desc_instrumentparsingtemplate_forward_url", default=u"HTTP endpoint URL to forward data"),
        required=False,
    )

    forward_method = TextLineField(
        title=_(u"title_instrumentparsingtemplate_forward_method", default=u"HTTP Method"),
        description=_(u"desc_instrumentparsingtemplate_forward_method", default=u"HTTP method for forwarding (POST, PUT)"),
        required=False,
        default=u"POST",
    )

    forward_headers = schema.Text(
        title=_(u"title_instrumentparsingtemplate_forward_headers", default=u"HTTP Headers (JSON)"),
        description=_(u"desc_instrumentparsingtemplate_forward_headers", default=u"Additional HTTP headers in JSON format"),
        required=False,
    )

    forward_timeout = IntField(
        title=_(u"title_instrumentparsingtemplate_forward_timeout", default=u"Timeout (seconds)"),
        description=_(u"desc_instrumentparsingtemplate_forward_timeout", default=u"HTTP request timeout in seconds"),
        required=False,
        default=30,
    )

    @invariant
    def validate_script_file(data):
        f = getattr(data, "script_file", None)
        if not f:
            return
        filename = getattr(f, "filename", "") or ""
        if filename and not filename.lower().endswith(".js"):
            raise Invalid(_(u"Please upload a .js JavaScript file"))


@implementer(IInstrumentParsingTemplate, IInstrumentParsingTemplateSchema, IDeactivable, IHaveInstrument)
class InstrumentParsingTemplate(Item):
    _catalogs = [SETUP_CATALOG]

    def getInstrument(self):
        value = getattr(self, "instrument", None)
        if api.is_object(value):
            return value
        if isinstance(value, list):
            if len(value) > 0:
                return value[0]
            return None
        try:
            obj = api.get_object(value)
            if api.is_object(obj):
                return obj
        except Exception:
            pass
        return None

