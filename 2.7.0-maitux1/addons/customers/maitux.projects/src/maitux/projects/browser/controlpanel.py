# -*- coding: utf-8 -*-
import collections

from bika.lims import api
from bika.lims.utils import get_link
from plone.memoize import view
from Products.CMFCore.permissions import View
from senaite.core.browser.listing.base import ListingView

from maitux.projects import _
from maitux.projects.translation import translate_with_fallback

from maitux.projects.interfaces import IProjects


class ProjectsListingView(ListingView):

    def __init__(self, context, request):
        super(ProjectsListingView, self).__init__(context, request)

        self.catalog = "portal_catalog"
        self.contentFilter = {
            "portal_type": "Project",
            "sort_on": "created",
            "sort_order": "descending",
            "path": {"query": "/".join(context.getPhysicalPath()), "depth": 1},
        }

        title_msg = _(u"folder_title_projects", default=u"Projects")
        icon = u"{}{}".format(self.portal_url, u"/senaite_theme/icon/batch")

        # Base ListingView may expose title/icon/form_id/listing_identifier as
        # read-only @property; try/except on assignment avoids AttributeError.
        for (attr, expected) in (
            ("title", title_msg),
            ("description", u""),
            ("icon", icon),
            ("form_id", "projects"),
            ("listing_identifier", "Project-folder_view"),
        ):
            try:
                setattr(self, attr, expected)
            except AttributeError:
                # property: try to use an override via instance dict if possible
                pass

        self.show_select_column = True
        self.context_actions = {}

        self.columns = collections.OrderedDict((
            ("Title", {
                "title": _("Title"),
                "index": "sortable_title",
                "sortable": True,
            }),
            ("ProjectID", {
                "title": _(u"column_project_id", default=u"Project ID"),
                "index": "id",
                "sortable": True,
            }),
            ("Description", {
                "title": _("Description"),
                "sortable": False,
                "toggle": True,
            }),
            ("ProjectDate", {
                "title": _("Date"),
                "sortable": False,
                "toggle": True,
            }),
            ("Client", {
                "title": _("Client"),
                "sortable": False,
                "toggle": True,
            }),
            ("ClientID", {
                "title": _("Client ID"),
                "sortable": False,
                "toggle": True,
            }),
            ("ClientProjectID", {
                "title": _(u"column_client_project_id", default=u"Client Project ID"),
                "sortable": False,
                "toggle": True,
            }),
            ("state_title", {
                "title": _("State"),
                "sortable": False,
            }),
            ("created", {
                "title": _("Created"),
                "index": "created",
                "sortable": True,
                "toggle": True,
            }),
        ))

        self.review_states = [
            {
                "id": "default",
                "contentFilter": {"review_state": "open"},
                "title": _("Open"),
                "transitions": [],
                "columns": self.columns.keys(),
            },
            {
                "id": "closed",
                "contentFilter": {"review_state": "closed"},
                "title": _("Closed"),
                "transitions": [],
                "columns": self.columns.keys(),
            },
            {
                "id": "cancelled",
                "contentFilter": {"review_state": "cancelled"},
                "title": _("Cancelled"),
                "transitions": [],
                "columns": self.columns.keys(),
            },
            {
                "id": "all",
                "title": _("All"),
                "contentFilter": {},
                "transitions": [],
                "columns": self.columns.keys(),
            },
        ]

    def update(self):
        super(ProjectsListingView, self).update()
        if self.can_add():
            add_ico = u"{}{}".format(self.portal_url, u"/senaite_theme/icon/plus")
            self.context_actions = {
                _(u"Add"): {
                    u"url": self.get_add_url(),
                    u"permission": View,
                    u"icon": add_ico,
                }
            }

    @view.memoize
    def get_add_url(self):
        container = self.context
        try:
            fti = api.get_tool("portal_types").getTypeInfo("Project")
            add_view = (fti and getattr(fti, "add_view_expr", None)
                        or u"string:${folder_url}/++add++Project")
        except Exception:
            add_view = u"string:${folder_url}/++add++Project"
        from string import Template
        tmpl = add_view[len("string:"):] if add_view.startswith("string:") else add_view
        try:
            t = Template(tmpl)
            out = t.safe_substitute(folder_url=api.get_url(container))
        except Exception:
            out = u"{}/++add++Project".format(api.get_url(container))
        return out

    @view.memoize
    def can_add(self):
        from Products.CMFCore.permissions import AddPortalContent
        return bool(api.security.check_permission(AddPortalContent, self.context))

    def folderitem(self, obj, item, index):
        obj = api.get_object(obj)
        try:
            obj_url = api.get_url(obj)
        except Exception:
            obj_url = u""
        pid = api.get_id(obj)
        title = api.get_title(obj)
        cpid = u""
        try:
            cpid = (obj.getClientProjectID() or u"").strip()
        except Exception:
            pass
        created = api.get_creation_date(obj)
        pdate = None
        try:
            pdate = obj.getProjectDate()
        except Exception:
            pass
        client = None
        try:
            client = obj.getClient()
        except Exception:
            client = None

        # 点击 Project ID / Title 进入该 Project 的 AR 列表
        # （复刻 Batches：BatchID/Title 链接到 <url>/analysisrequests）
        ar_url = u"{}/analysisrequests".format(obj_url) if obj_url else u""
        item["ProjectID"] = pid
        item["Title"] = title
        if ar_url:
            item["replace"]["ProjectID"] = get_link(ar_url, pid)
            item["replace"]["Title"] = get_link(ar_url, title)
        try:
            item["Description"] = api.safe_unicode(
                getattr(obj, "description", None) or u"")
        except Exception:
            item["Description"] = u""
        item["created"] = self.ulocalized_time(created, long_format=True)
        try:
            item["ProjectDate"] = (self.ulocalized_time(pdate, long_format=True)
                                   if pdate else u"")
        except Exception:
            item["ProjectDate"] = u""
        item["ClientProjectID"] = cpid

        if client is not None:
            try:
                cname = client.Title() or u""
            except Exception:
                cname = u""
            try:
                cid = (getattr(client, "getClientID", lambda: u"")() or u"").strip()
            except Exception:
                cid = u""
            try:
                curl = api.get_url(client)
            except Exception:
                curl = u""
            item["Client"] = cname
            item["ClientID"] = cid
            if curl:
                item["replace"]["Client"] = get_link(curl, cname)
                item["replace"]["ClientID"] = get_link(curl, cid)
        else:
            item["Client"] = u""
            item["ClientID"] = u""

        # --- state_title (required column; render workflow state title) ---
        try:
            from bika.lims.workflow import getStateTitleOf as _gsto
            item["state_title"] = _gsto(obj) or u""
        except Exception:
            try:
                item["state_title"] = api.get_workflow_status_of(obj) or u""
            except Exception:
                try:
                    rs = api.get_review_status(obj)
                except Exception:
                    rs = u""
                item["state_title"] = rs or u""
        # --- Guard: ensure every declared column exists in item to avoid
        #     TypeError / KeyError inside senaite.app.listing folderitems() ---
        try:
            for col in (self.columns or {}).keys():
                if col not in item:
                    item[col] = u""
        except Exception:
            pass

        return item
