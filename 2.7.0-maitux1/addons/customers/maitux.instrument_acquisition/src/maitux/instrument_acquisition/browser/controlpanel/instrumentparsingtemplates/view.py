# -*- coding: utf-8 -*-
import collections

from bika.lims import api
from bika.lims import senaiteMessageFactory as _
from bika.lims.utils import get_link
from senaite.app.listing import ListingView
from senaite.core.catalog import SETUP_CATALOG
from senaite.core.i18n import translate

from maitux.instrument_acquisition.permissions import AddInstrumentParsingTemplate


class InstrumentParsingTemplatesView(ListingView):
    def __init__(self, context, request):
        super(InstrumentParsingTemplatesView, self).__init__(context, request)

        self.catalog = SETUP_CATALOG
        self.contentFilter = {
            "portal_type": "InstrumentParsingTemplate",
            "sort_on": "sortable_title",
            "sort_order": "ascending",
            "path": {
                "query": api.get_path(self.context),
                "depth": 1,
            },
        }

        self.context_actions = {
            _(u"listing_instrumentparsingtemplates_action_add", default=u"Add"): {
                "url": "++add++InstrumentParsingTemplate",
                "permission": AddInstrumentParsingTemplate,
                "icon": "senaite_theme/icon/plus",
            }
        }

        self.title = translate(_(
            u"listing_instrumentparsingtemplates_title",
            default=u"Instrument Parsing Templates"
        ))
        self.icon = api.get_icon("Instruments", html_tag=False)
        self.show_select_column = True

        self.columns = collections.OrderedDict((
            ("Title", {
                "title": _(u"listing_instrumentparsingtemplates_column_title", default=u"Title"),
                "index": "sortable_title",
            }),
            ("instrument", {
                "title": _(u"listing_instrumentparsingtemplates_column_instrument", default=u"Instrument"),
                "index": "instrument_title",
                "toggle": True,
            }),
            ("port", {
                "title": _(u"listing_instrumentparsingtemplates_column_port", default=u"Port"),
                "toggle": True,
            }),
            ("ip_address", {
                "title": _(u"listing_instrumentparsingtemplates_column_ip", default=u"IP Address"),
                "toggle": True,
            }),
            ("script_path", {
                "title": _(u"listing_instrumentparsingtemplates_column_script", default=u"Script File"),
                "toggle": True,
            }),
            ("description", {
                "title": _(u"listing_instrumentparsingtemplates_column_description", default=u"Remarks"),
                "toggle": True,
            }),
            ("state_title", {
                "title": _(u"listing_instrumentparsingtemplates_column_state", default=u"State"),
                "index": "review_state",
                "toggle": True,
            }),
        ))

        self.review_states = [
            {
                "id": "default",
                "title": _(u"listing_state_active", default=u"Active"),
                "contentFilter": {
                    "is_active": True,
                },
                "columns": self.columns.keys(),
            },
            {
                "id": "inactive",
                "title": _(u"listing_state_inactive", default=u"Inactive"),
                "contentFilter": {
                    "is_active": False,
                },
                "columns": self.columns.keys(),
            },
        ]
    def folderitem(self, obj, item, index):
        item = super(InstrumentParsingTemplatesView, self).folderitem(obj, item, index)
        brain = obj if api.is_brain(obj) else None
        try:
            obj = api.get_object(obj)
        except Exception:
            if brain is not None:
                try:
                    catalog = api.get_tool(SETUP_CATALOG)
                    catalog.uncatalog_object(brain.getPath())
                except Exception:
                    pass
            return item
        item.setdefault("replace", {})
        item["replace"]["Title"] = get_link(
            href="{}/edit".format(api.get_url(obj)),
            value=api.get_title(obj),
            csrf=False,
        )
        p = getattr(obj, "port", "")
        try:
            item["port"] = str(p) if p is not None else ""
        except Exception:
            item["port"] = ""
        item["ip_address"] = getattr(obj, "ip_address", "")
        item["description"] = getattr(obj, "description", "") or ""
        script_file = getattr(obj, "script_file", None)
        filename = getattr(script_file, "filename", "") if script_file else ""
        if filename:
            item["script_path"] = get_link(
                href="{}/@@download/script_file/{}".format(api.get_url(obj), filename),
                value=filename,
                csrf=False,
            )
        else:
            item["script_path"] = ""
        instrument = getattr(obj, "getInstrument", lambda: None)()
        if instrument is None:
            instrument = api.get_object(getattr(obj, "instrument", None), default=None)
        item["instrument"] = api.get_title(instrument) if instrument else ""
        return item

