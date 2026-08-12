# -*- coding: utf-8 -*-

from archetypes.schemaextender.field import ExtensionField
from archetypes.schemaextender.interfaces import ISchemaExtender
from bika.lims import api
from bika.lims import senaiteMessageFactory as _
from bika.lims.browser.fields import UIDReferenceField
from bika.lims.interfaces import IInstrument
from Products.CMFCore import permissions
from senaite.core.browser.widgets.referencewidget import ReferenceWidget
from senaite.core.catalog import SETUP_CATALOG
from zope.component import adapts
from zope.interface import implements


FIELD_NAME = "InstrumentAcquisitionTemplate"


class ExtUIDReferenceField(ExtensionField, UIDReferenceField):
    """给 Archetypes extender 使用的 UID 关联字段。"""


class InstrumentSchemaExtender(object):
    """在原生 Instrument 上追加模块模板关联字段。"""

    implements(ISchemaExtender)
    adapts(IInstrument)

    fields = [
        ExtUIDReferenceField(
            FIELD_NAME,
            allowed_types=("InstrumentParsingTemplate",),
            required=False,
            multiValued=False,
            mode="rw",
            read_permission=permissions.View,
            write_permission=permissions.ModifyPortalContent,
            widget=ReferenceWidget(
                label=_("Parsing Template"),
                description=_(
                    "Select the Instrument Parsing Template provided by "
                    "maitux.instrument_acquisition."
                ),
                catalog=SETUP_CATALOG,
                query={
                    "portal_type": "InstrumentParsingTemplate",
                    "is_active": True,
                    "sort_on": "sortable_title",
                    "sort_order": "ascending",
                },
            ),
        ),
    ]

    def __init__(self, context):
        self.context = context

    def _is_addon_installed(self):
        """只有模块已安装时才显示扩展字段，降低卸载后的界面影响。"""
        try:
            qi = api.get_tool("portal_quickinstaller")
            return qi.isProductInstalled("maitux.instrument_acquisition")
        except Exception:
            return False

    def getFields(self):
        if not self._is_addon_installed():
            return []
        return self.fields

