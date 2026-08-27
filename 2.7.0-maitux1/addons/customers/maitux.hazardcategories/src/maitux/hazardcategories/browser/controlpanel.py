# -*- coding: utf-8 -*-
import collections

from bika.lims import api
from bika.lims.utils import get_link
from senaite.app.listing import ListingView
from senaite.core.i18n import translate

from maitux.hazardcategories import _
from maitux.hazardcategories.translation import translate_with_fallback

from zope.publisher.interfaces import IPublishTraverse
from zope.interface import implementer

from maitux.hazardcategories.utils import SCOPE_AR
from maitux.hazardcategories.utils import SCOPE_BOTH
from maitux.hazardcategories.utils import SCOPE_REFERENCE
from maitux.hazardcategories.utils import USAGE_SCOPE_LABELS
from maitux.hazardcategories.utils import get_scope_label


ADAPTIVE_STYLE = u"""
<style type="text/css">
/* Hazard Categories listing adaptive height */
div[data-uid="hazardcategories-controlpanel"] {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 220px);
  min-height: 520px;
}
div[data-uid="hazardcategories-controlpanel"] .senaite-listing {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
div[data-uid="hazardcategories-controlpanel"] .senaite-listing .listing-filters,
div[data-uid="hazardcategories-controlpanel"] .senaite-listing .review-states {
  flex: 0 0 auto;
}
div[data-uid="hazardcategories-controlpanel"] .senaite-listing table.listing {
  width: 100%;
  table-layout: fixed;
}
div[data-uid="hazardcategories-controlpanel"] .senaite-listing .table-scroll {
  flex: 1 1 auto;
  overflow: auto;
  max-height: calc(100vh - 360px);
}
div[data-uid="hazardcategories-controlpanel"] .senaite-listing .table-scroll thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: #f8f9fa;
}
@media (max-height: 820px) {
  div[data-uid="hazardcategories-controlpanel"] {
    height: calc(100vh - 180px);
    min-height: 460px;
  }
  div[data-uid="hazardcategories-controlpanel"] .senaite-listing .table-scroll {
    max-height: calc(100vh - 320px);
  }
}
.scope-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 500;
  line-height: 16px;
}
.scope-both { background: #e7f5e7; color: #2e7d32; border: 1px solid #a5d6a7; }
.scope-reference { background: #e3f2fd; color: #1565c0; border: 1px solid #90caf9; }
.scope-ar { background: #fff3e0; color: #e65100; border: 1px solid #ffcc80; }
</style>
"""


class HazardCategoriesListingView(ListingView):

    def __init__(self, context, request):
        super(HazardCategoriesListingView, self).__init__(context, request)

        self.catalog = "portal_catalog"
        self.contentFilter = {}

        self.context_actions = {
            _(u"Add", default=u"Add"): {
                "url": "++add++HazardCategory",
                "permission": "cmf.AddPortalContent",
                "icon": "senaite_theme/icon/plus",
            }
        }

        title_msg = _(
            u"HazardCategories Container",
            default=u"Sample Properties"
        )
        self.title = title_msg
        self.show_select_column = True

        self.columns = collections.OrderedDict((
            ("Code", {
                "title": _(u"listing_hazardcats_column_code", default=u"CODE"),
                "sortable": True,
            }),
            ("Title", {
                "title": _(u"listing_hazardcats_column_title", default=u"Name (English)"),
                "sortable": True,
            }),
            ("Scope", {
                "title": _(u"listing_hazardcats_column_scope", default=u"Usage scope"),
                "toggle": True,
            }),
            ("Common", {
                "title": _(u"listing_hazardcats_column_common", default=u"Common name / Chinese"),
                "toggle": True,
            }),
            ("Pictogram", {
                "title": _(u"listing_hazardcats_column_pictogram", default=u"Pictogram path"),
                "toggle": True,
            }),
            ("Preview", {
                "title": _(u"listing_hazardcats_column_preview", default=u"Preview"),
                "toggle": True,
            }),
            ("Description", {
                "title": _(u"listing_hazardcats_column_description", default=u"Description"),
                "toggle": True,
            }),
        ))

        self.review_states = [
            {
                "id": "default",
                "title": _(u"listing_state_active", default=u"Active"),
                "contentFilter": {"is_active": True},
                "columns": self.columns.keys(),
            }, {
                "id": "inactive",
                "title": _(u"listing_state_inactive", default=u"Inactive"),
                "contentFilter": {"is_active": False},
                "columns": self.columns.keys(),
            }, {
                "id": "all",
                "title": _(u"listing_state_all", default=u"All"),
                "contentFilter": {},
                "columns": self.columns.keys(),
            },
        ]

    def _is_html_page_request(self):
        req = self.request
        if req.getHeader("X-Requested-With") == "XMLHttpRequest":
            return False
        accept = req.getHeader("Accept") or ""
        if accept and "json" in accept.lower() and "html" not in accept.lower():
            return False
        url = req.get("URL") or ""
        path = req.get("PATH_INFO") or url or ""
        lower = path.lower().rstrip("/")
        for bad in ("/folderitems", "/columns", "/review_states", "/transitions",
                    "/folderactions", "/listitems", "/uid_listing"):
            if lower.endswith(bad):
                return False
        if req.form.get("form_id") or req.form.get("action") == "folderitems":
            return False
        return True

    def __call__(self):
        result = super(HazardCategoriesListingView, self).__call__()
        if not self._is_html_page_request():
            return result
        if isinstance(result, unicode):
            result = ADAPTIVE_STYLE + result
        elif isinstance(result, str):
            result = ADAPTIVE_STYLE.encode("utf-8") + result
        return result

    def get_objects_from_folder(self):
        try:
            folder = api.get_parent(self.context)
            if getattr(folder, "portal_type", None) not in (
                    "HazardCategories", "Folder"):
                folder = self.context
        except Exception:
            folder = self.context

        pt = getattr(folder, "portal_type", None)
        if pt in ("HazardCategories", "Folder"):
            container = folder
        else:
            try:
                portal = api.get_portal()
                container = portal.get("hazard_categories")
            except Exception:
                container = None

        out = []
        if container is None:
            return out
        try:
            ids = list(container.objectIds())
        except Exception:
            return out
        for cid in ids:
            try:
                obj = container[cid]
            except Exception:
                continue
            if getattr(obj, "portal_type", None) != "HazardCategory":
                continue
            out.append(obj)
        return out

    def folderitems(self):
        items = []
        objects = self.get_objects_from_folder()
        is_active_filter = None
        review_state_key = self.request.get("list_review_state") or \
            (self.review_states[0] or {}).get("id", "default")
        if review_state_key == "default":
            is_active_filter = True
        elif review_state_key == "inactive":
            is_active_filter = False

        sort_key = (self.request.get("list_sort_on") or "code").lower()
        sort_reverse = (
            self.request.get("list_sort_order") or "ascending").lower() \
            in ("descending", "reverse", "desc")

        index = 0
        for obj in objects:
            code = safe_unicode(getattr(obj, "code", None) or u"").strip()
            if not code:
                continue
            is_active = api.is_active(obj)
            if is_active_filter is not None and is_active != is_active_filter:
                continue

            name = safe_unicode(getattr(obj, "name", None) or u"").strip()
            common = safe_unicode(getattr(obj, "common", None) or u"").strip()
            pict = safe_unicode(getattr(obj, "pictogram", None) or u"").strip()
            usage_scope = safe_unicode(
                getattr(obj, "usage_scope", None) or SCOPE_BOTH).strip()
            if usage_scope not in USAGE_SCOPE_LABELS:
                usage_scope = SCOPE_BOTH

            if name:
                display_title = name
            else:
                display_title = code or u""
            title_display = display_title

            try:
                info = self.get_item_info(obj)
            except Exception:
                info = {}
            item = self.make_empty_folderitem(**info)
            item.update({
                "Code": code,
                "Code_sort": code.lower(),
                "Title": title_display,
                "Title_sort": (name or code).lower(),
                "Common": common,
                "Common_sort": common.lower(),
                "Pictogram": pict,
                "Pictogram_sort": pict.lower(),
                "Scope": get_scope_label(usage_scope),
                "Scope_sort": usage_scope,
                "Description": u" | ".join(
                    [x for x in [common, pict] if x]),
                "Preview": pict or u"",
                "review_state": api.get_review_status(obj),
                "state_class": "state-%s" % api.get_review_status(obj),
                "is_active": is_active,
            })

            item["replace"] = item.get("replace") or {}
            item["replace"]["Title"] = get_link(
                href=api.get_url(obj),
                value=safe_unicode(title_display or code),
                csrf=False,
            )
            if pict:
                portal_url = api.get_url(api.get_portal())
                preview_url = portal_url + "/" + pict.lstrip("/")
                img_tag = (
                    u'<img src="%s" alt="%s" '
                    u'style="max-height:40px;max-width:40px;" />'
                    % (preview_url, pict)
                )
            else:
                img_tag = u""
            item["replace"]["Preview"] = img_tag
            item["Preview"] = pict or u""

            tag_class = {
                SCOPE_BOTH: "scope-both",
                SCOPE_REFERENCE: "scope-reference",
                SCOPE_AR: "scope-ar",
            }.get(usage_scope, "scope-both")
            item["replace"]["Scope"] = (
                u'<span class="scope-tag %s">%s</span>'
                % (tag_class, get_scope_label(usage_scope))
            )

            try:
                extra_item = self.folderitem(obj, item, index)
                if extra_item:
                    item = extra_item
            except Exception:
                pass

            items.append(item)
            index += 1

        def _get_sort_key(item):
            sk = sort_key
            lookup = {
                "code": "Code_sort",
                "title": "Title_sort",
                "name": "Title_sort",
                "common": "Common_sort",
                "pictogram": "Pictogram_sort",
                "scope": "Scope_sort",
            }
            key = lookup.get(sk, "Code_sort")
            return item.get(key) or u""

        items.sort(key=_get_sort_key, reverse=sort_reverse)

        total = len(items)
        self.total = total
        pagesize = 50
        try:
            ps = int(self.request.get("list_pagesize") or 50)
            if ps > 0:
                pagesize = ps
        except Exception:
            pass
        self.limit = pagesize
        pages = (total + pagesize - 1) // pagesize if pagesize else 1
        try:
            current_page = int(self.request.get("list_page_num") or 1)
        except Exception:
            current_page = 1
        current_page = max(1, min(current_page, pages if pages else 1))
        start = (current_page - 1) * pagesize
        end = start + pagesize
        paged = items[start:end]
        return paged


class HazardSettingsView(HazardCategoriesListingView):
    """Alias for backwards compatibility with old browser:page registration.
    """
    pass


class HazardSettingsEditForm(HazardCategoriesListingView):
    """Alias for backwards compatibility.
    """
    pass


def safe_unicode(value):
    if value is None:
        return u""
    if isinstance(value, unicode):
        return value
    if isinstance(value, str):
        try:
            return value.decode("utf-8")
        except Exception:
            try:
                return value.decode("latin-1", errors="replace")
            except Exception:
                return u""
    return unicode(value)
