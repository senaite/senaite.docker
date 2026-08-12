# -*- coding: utf-8 -*-
import collections
from datetime import datetime
from datetime import timedelta
import json
import re
import six
try:
    from urllib import urlencode
except Exception:
    from urllib.parse import urlencode

from bika.lims import api
from bika.lims import senaiteMessageFactory as _
from bika.lims.decorators import returns_json
from bika.lims.api.security import check_permission as has_permission
from bika.lims.utils import get_link
from bika.lims.browser.workflow import RequestContextAware
from bika.lims.interfaces import IWorkflowActionUIDsAdapter
from DateTime import DateTime
try:
    from ZPublisher.HTTPRequest import record as RequestRecord
except Exception:
    RequestRecord = None
try:
    from bika.lims.api import to_utf8
except Exception:
    to_utf8 = None
from plone import api as ploneapi
from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from senaite.app.listing import ListingView
from senaite.core.browser.dexterity.add import DefaultAddForm as SenaiteDefaultAddForm
from senaite.core.catalog import SETUP_CATALOG
from senaite.core.catalog import CLIENT_CATALOG
from senaite.core.catalog import CONTACT_CATALOG
from senaite.core.catalog import SAMPLE_CATALOG
from senaite.core.i18n import translate
from senaite.core.upgrade.utils import temporary_allow_type
from zope.component import getMultiAdapter
from zope.interface import implements
from zope.publisher.interfaces.browser import IBrowserPage

from maitux.stability.permissions import AddStabilityPlanTemplate


TABLE_DEFINITIONS = (
    ("storage_conditions", "500_storage_conditions", ("storage_conditions", "z_storage_conditions")),
    ("packaging_specifications", "400_packaging_specifications", ("packaging_specifications", "y_packaging_specifications")),
    ("stability_plan_templates", "300_stability_plan_templates", ("stability_plan_templates", "x_stability_plan_templates")),
    ("stability_plans", "200_stability_plans", ("stability_plans", "w_stability_plans")),
    ("task_board", "100_task_board", ("task_board", "v_task_board")),
)
TABLE_ID_BY_LOGICAL = dict([(item[0], item[1]) for item in TABLE_DEFINITIONS])
TABLE_ID_ALIASES = dict([(item[1], item[2]) for item in TABLE_DEFINITIONS])


def _first(value):
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _extract_uid(value):
    value = _first(value)
    if value is None:
        return ""
    if isinstance(value, dict):
        value = value.get("uid") or value.get("UID") or value.get("value") or ""
    if isinstance(value, six.string_types):
        return value.strip()
    return ""


def _normalize_months(value):
    """统一把时间点月份转换为非负整数，兼容下拉控件回传的字符串。"""
    try:
        value = int(value)
    except Exception:
        return 0
    return value if value >= 0 else 0


def _candidate_ids(value):
    canonical = TABLE_ID_BY_LOGICAL.get(value, value)
    related = [canonical]
    related.extend(TABLE_ID_ALIASES.get(canonical, ()))
    candidates = []
    # 兼容升级前后的菜单对象 ID，保证旧路径/旧对象仍可被查找到。
    for related_value in related:
        for v in (
            related_value,
            related_value.replace("_", "-"),
            related_value.replace("-", "_"),
        ):
            if v and v not in candidates:
                candidates.append(v)
    return candidates


def _canonical_id(value):
    return TABLE_ID_BY_LOGICAL.get(value, value)


def _matches_logical_id(value, logical_id):
    return value in _candidate_ids(logical_id)


def _as_url_value(value):
    if value is None:
        return ""
    if to_utf8 is not None:
        try:
            return to_utf8(value)
        except Exception:
            pass
    return value


def _set_prefill_value(request, name, value):
    if value is None:
        return

    try:
        request.form.setdefault("form.widgets.{0}".format(name), value)
    except Exception:
        try:
            request.form["form.widgets.{0}".format(name)] = value
        except Exception:
            pass

    if RequestRecord is None:
        return

    try:
        form_record = request.form.get("form")
        if not isinstance(form_record, RequestRecord):
            form_record = RequestRecord()
            request.form["form"] = form_record

        widgets_record = getattr(form_record, "widgets", None)
        if not isinstance(widgets_record, RequestRecord):
            widgets_record = RequestRecord()
            try:
                form_record["widgets"] = widgets_record
            except Exception:
                try:
                    setattr(form_record, "widgets", widgets_record)
                except Exception:
                    return

        try:
            widgets_record[name] = value
        except Exception:
            try:
                setattr(widgets_record, name, value)
            except Exception:
                pass
    except Exception:
        return


def _is_empty_value(value):
    if value is None:
        return True
    if value in ("", [], (), {}):
        return True
    try:
        # Compatibility with Python 3 (basestring -> str)
        string_types = (str, )
        try:
            if isinstance(value, string_types) and not value.strip():
                return True
        except Exception:
            pass
    except Exception:
        pass
    return False


def _record_for(obj):
    if obj is None:
        return {}
    return {
        "uid": api.get_uid(obj),
        "url": api.get_url(obj),
        "Title": api.get_title(obj) or api.get_id(obj),
        "Description": api.get_description(obj) or "",
    }

def _template_plan_details(template):
    # 模板不再维护 Timepoints 子对象。
    # 计划明细由用户在创建计划时直接录入，因此这里始终返回空列表。
    return []


class StabilityPlanAddFormFromTemplate(SenaiteDefaultAddForm):
    def updateWidgets(self):
        super(StabilityPlanAddFormFromTemplate, self).updateWidgets()
        template_uid = (
            self.request.get("stability_template_uid") or
            self.request.form.get("stability_template_uid")
        )
        if not api.is_uid(template_uid):
            return

        template = api.get_object(template_uid)
        if template is None:
            return

        def set_default(name, value):
            if name not in self.widgets:
                return
            widget = self.widgets.get(name)
            current = getattr(widget, "value", None)
            if _is_empty_value(current):
                widget.value = value

        set_default("plan_template", template_uid)
        set_default("title", api.get_title(template) or "")
        set_default("description", getattr(template, "description", "") or "")

        for name in ("sample_quantity", "reserve_quantity"):
            value = getattr(template, name, None)
            if isinstance(value, int):
                set_default(name, str(value))

        unit = _first(getattr(template, "unit", None))
        if unit:
            set_default("unit", unit)


class PlanTemplateDefaultsView(BrowserView):
    @returns_json
    def __call__(self):
        uid = self.request.get("uid")
        if not api.is_uid(uid):
            return {}

        template = api.get_object(uid)
        if template is None:
            return {}

        return {
            "plan_template": api.get_uid(template),
            "plan_template_record": _record_for(template),
            "title": api.get_title(template) or "",
            "description": getattr(template, "description", "") or "",
            "sample_quantity": getattr(template, "sample_quantity", 0) or 0,
            "reserve_quantity": getattr(template, "reserve_quantity", 0) or 0,
            "unit": _first(getattr(template, "unit", None)) or "",
            "unit_record": _record_for(api.get_object(_first(getattr(template, "unit", None)))) if _first(getattr(template, "unit", None)) else {},
            "plan_details": _template_plan_details(template),
        }


def _get_or_create_plans_container(request=None):
    portal = api.get_portal()
    module = None
    for cid in _candidate_ids("stability_studies"):
        module = portal.get(cid)
        if module is not None:
            break
    if module is None:
        return None

    types_tool = ploneapi.portal.get_tool("portal_types")
    if getattr(types_tool, "getTypeInfo", None):
        if types_tool.getTypeInfo("StabilityPlans") is None:
            setup = ploneapi.portal.get_tool("portal_setup")
            try:
                setup.runImportStepFromProfile(
                    "profile-maitux.stability:default",
                    "typeinfo",
                )
            except Exception:
                pass

    if getattr(types_tool, "getTypeInfo", None):
        if types_tool.getTypeInfo("StabilityPlans") is None:
            if request is not None:
                try:
                    portal.plone_utils.addPortalMessage(
                        _(u"StabilityPlans content type is not installed. Please reinstall/upgrade the maitux.stability add-on."),
                        "error",
                    )
                except Exception:
                    pass
            return None

    plans = None
    for cid in _candidate_ids("stability_plans"):
        plans = module.get(cid)
        if plans is not None:
            break

    if plans is None:
        with temporary_allow_type(module, "StabilityPlans"):
            plans = ploneapi.content.create(
                container=module,
                type="StabilityPlans",
                id=_canonical_id("stability_plans"),
                title="Stability Plans",
            )
    return plans


def _get_plans_container_in_module(module):
    if module is None:
        return None
    for cid in _candidate_ids("stability_plans"):
        container = module.get(cid)
        if container is not None:
            return container
    return None


class BaseStabilityFolderView(ListingView):
    portal_type = None
    add_type = None
    add_permission = "cmf.AddPortalContent"
    title_text = u""

    def __init__(self, context, request):
        super(BaseStabilityFolderView, self).__init__(context, request)

        self.catalog = SETUP_CATALOG
        self.show_select_column = True
        self.contentFilter = {
            "portal_type": self.portal_type,
            "sort_on": "sortable_title",
            "sort_order": "ascending",
            "path": {
                "query": api.get_path(self.context),
                "depth": 1,
            },
        }

        self.context_actions = {
            _(u"listing_stability_action_add", default=u"Add"): {
                "url": "++add++%s" % self.add_type,
                "permission": self.add_permission,
                "icon": "senaite_theme/icon/plus",
            }
        }

        self.title = translate(self.title_text)
        self.columns = collections.OrderedDict((
            ("Title", {
                "title": _(u"listing_stability_column_title", default=u"Title"),
                "index": "sortable_title",
            }),
            ("Description", {
                "title": _(u"listing_stability_column_description", default=u"Description"),
                "toggle": True,
            }),
            ("state_title", {
                "title": _(u"listing_stability_column_state", default=u"State"),
                "index": "review_state",
                "toggle": True,
            }),
        ))

        self.review_states = [
            {
                "id": "default",
                "title": _(u"listing_state_active", default=u"Active"),
                "contentFilter": {"is_active": True},
                "transitions": [{"id": "deactivate"}],
                "columns": self.columns.keys(),
            }, {
                "id": "inactive",
                "title": _(u"listing_state_inactive", default=u"Inactive"),
                "contentFilter": {"is_active": False},
                "transitions": [{"id": "activate"}],
                "columns": self.columns.keys(),
            }, {
                "id": "all",
                "title": _(u"listing_state_all", default=u"All"),
                "contentFilter": {},
                "columns": self.columns.keys(),
            },
        ]

    def folderitem(self, obj, item, index):
        item = super(BaseStabilityFolderView, self).folderitem(obj, item, index)
        obj = api.get_object(obj)
        item["replace"]["Title"] = get_link(
            href=api.get_url(obj),
            value=api.get_title(obj),
            csrf=False,
        )
        return item


class StorageConditionsView(BaseStabilityFolderView):
    portal_type = "StorageCondition"
    add_type = "StorageCondition"
    title_text = _(
        u"listing_storageconditions_title",
        default=u"Storage Conditions",
    )


class PackagingSpecificationsView(BaseStabilityFolderView):
    portal_type = "PackagingSpecification"
    add_type = "PackagingSpecification"
    title_text = _(
        u"listing_packagingspecifications_title",
        default=u"Packaging Specifications",
    )


class StabilityPlanTemplatesView(BaseStabilityFolderView):
    portal_type = "StabilityPlanTemplate"
    add_type = "StabilityPlanTemplate"
    add_permission = AddStabilityPlanTemplate
    title_text = _(
        u"listing_stabilityplantemplates_title",
        default=u"Stability Plan Templates",
    )

    def __init__(self, context, request):
        super(StabilityPlanTemplatesView, self).__init__(context, request)
        self.init_custom_transitions()

    def init_custom_transitions(self):
        for state in self.review_states:
            custom = state.get("custom_transitions", [])
            if self.custom_transition_create_plan not in custom:
                custom.append(self.custom_transition_create_plan)
            state["custom_transitions"] = custom

    @property
    def custom_transition_create_plan(self):
        return {
            "id": "create_plan",
            "title": _(u"Create Plan"),
            "url": "workflow_action?action=create_plan",
            "css_class": "btn btn-outline-primary",
            "help": _(u"Create a stability plan from the selected template"),
        }


class CreatePlanRedirectView(BrowserView):
    def __call__(self):
        template = self.context
        plans = _get_or_create_plans_container(request=self.request)
        if plans is None:
            return self.request.response.redirect(api.get_url(template))

        template_uid = api.get_uid(template)
        url = "{0}/++add++StabilityPlan?template_uid={1}".format(
            api.get_url(plans), _as_url_value(template_uid))
        return self.request.response.redirect(url)


class WorkflowActionCreatePlanAdapter(RequestContextAware):
    implements(IWorkflowActionUIDsAdapter)

    def __call__(self, action, uids):
        if not uids or len(uids) != 1:
            return self.redirect(
                message=_(u"Please select one template before creating a plan"),
                level="warning",
            )

        template = api.get_object_by_uid(uids[0])
        if template is None:
            return self.redirect(
                message=_(u"The selected template was not found"),
                level="error",
            )

        url = "{0}/@@create_plan".format(api.get_url(template))
        return self.request.response.redirect(url)


class StabilityPlansView(ListingView):
    def __init__(self, context, request):
        super(StabilityPlansView, self).__init__(context, request)

        self.catalog = SETUP_CATALOG
        self.show_select_column = True
        self.contentFilter = {
            "portal_type": "StabilityPlan",
            "sort_on": "created",
            "sort_order": "descending",
            "path": {
                "query": api.get_path(self.context),
                "depth": 1,
            },
        }

        self.context_actions = {
            _(u"listing_stability_action_task_board", default=u"Task Board"): {
                "url": "@@task_board",
                "permission": "zope2.View",
                "icon": "senaite_theme/icon/file",
            },
        }

        self.title = translate(_(u"listing_stabilityplans_title", default=u"Stability Plans"))
        self.columns = collections.OrderedDict((
            ("Title", {
                "title": _(u"listing_stability_column_title", default=u"Title"),
                "index": "sortable_title",
            }),
            ("start_time", {
                "title": _(u"Start Time (T0)"),
                "toggle": True,
            }),
            ("total_quantity", {
                "title": _(u"Storage Quantity - Total"),
                "toggle": True,
            }),
        ))

        self.review_states = [
            {
                "id": "default",
                "title": _(u"listing_state_all", default=u"All"),
                "contentFilter": {},
                "columns": self.columns.keys(),
            },
        ]

    def folderitem(self, obj, item, index):
        item = super(StabilityPlansView, self).folderitem(obj, item, index)
        obj = api.get_object(obj)
        item["replace"]["Title"] = get_link(
            href=api.get_url(obj),
            value=api.get_title(obj),
            csrf=False,
        )
        item["start_time"] = getattr(obj, "start_time", "") or ""
        item["total_quantity"] = getattr(obj, "total_quantity", "") or ""
        return item


class StabilityTaskBoardView(BrowserView):
    template = ViewPageTemplateFile("templates/task_board.pt")
    status_filter = "all"
    plan_query = u""
    sort_on = "target_date"
    sort_order = "asc"
    rows = []
    stats = {}
    has_pending_rows = False

    def __call__(self):
        # 批量按钮分发：在看板里提交后，统一由后端根据 bulk_action 跳转到对应页面。
        bulk_action = self.request.get("bulk_action")
        if bulk_action:
            value = self.request.get("row_ids", self.request.form.get("row_ids", []))
            if not isinstance(value, (list, tuple)):
                value = [value]

            row_ids = []
            for rid in value:
                if not rid or not isinstance(rid, six.string_types):
                    continue
                if "::" not in rid:
                    continue
                if rid not in row_ids:
                    row_ids.append(rid)

            if not row_ids:
                ploneapi.portal.show_message(
                    message=_(u"Please select at least one task."),
                    request=self.request,
                    type="warning",
                )
                return self.request.response.redirect(
                    "{0}/@@task_board".format(api.get_url(self.context))
                )

            action_to_view = {
                "sample_placement": "@@sample_placement",
                "link_sample": "@@link_sample",
                "create_sample": "@@create_sample",
            }
            view_name = action_to_view.get(bulk_action)
            if view_name:
                if bulk_action == "sample_placement":
                    # 鏍峰搧鏀剧疆鍙厑璁稿 Pending Placement 鐨勮鎵ц锛堝墠绔湁鏍￠獙锛岃繖閲屽仛鏈嶅姟绔厹搴曪級
                    all_rows = self._get_rows()
                    by_id = dict((r.get("row_id"), r) for r in all_rows if r.get("row_id"))
                    has_pending = any(
                        by_id.get(rid, {}).get("status") == "pending_placement"
                        for rid in row_ids
                    )
                    if not has_pending:
                        ploneapi.portal.show_message(
                            message=_(u"Sample Placement can only be applied to Pending Placement tasks."),
                            request=self.request,
                            type="warning",
                        )
                        return self.request.response.redirect(
                            "{0}/@@task_board".format(api.get_url(self.context))
                        )

                params = [("row_ids:list", rid) for rid in row_ids]
                url = "{0}/{1}?{2}".format(
                    api.get_url(self.context), view_name, urlencode(params)
                )
                return self.request.response.redirect(url)

        self.status_filter = self.get_status_filter()
        self.plan_query = self.get_plan_query()
        self.sort_on = self.get_sort_on()
        self.sort_order = self.get_sort_order()
        all_rows = self._get_rows()
        all_rows = self._search_rows(all_rows, self.plan_query)
        self.rows = self._filter_rows(all_rows, self.status_filter)
        self.rows = [self._ensure_row_id(row) for row in self.rows]
        self.rows = self._sort_rows(self.rows, self.sort_on, self.sort_order)
        self.stats = self._get_stats(all_rows)
        self.has_pending_rows = any(
            row.get("status") == "pending_placement" for row in self.rows
        )
        return self.template()

    def can_place_samples(self):
        # 鍏煎涓嶅悓鐜鐨勬潈闄愬懡鍚嶏紝閬垮厤鎸夐挳琚闅愯棌
        if has_permission("Modify portal content", self.context):
            return True
        if has_permission("cmf.ModifyPortalContent", self.context):
            return True
        try:
            user = ploneapi.user.get_current()
            roles = set(user.getRolesInContext(self.context))
            if roles.intersection(set(["Manager", "LabManager", "LabClerk"])):
                return True
        except Exception:
            pass
        return False

    def get_status_filter(self):
        value = self.request.get("status_filter", "all")
        if value not in ("all", "pending_placement", "active", "completed"):
            return "all"
        return value

    def get_plan_query(self):
        value = self.request.get("plan_query", "")
        if not isinstance(value, six.string_types):
            return u""
        return api.safe_unicode(value).strip()

    def get_sort_on(self):
        value = self.request.get("sort_on", "target_date")
        if value not in ("target_date", "window_start", "window_end"):
            return "target_date"
        return value

    def get_sort_order(self):
        value = self.request.get("sort_order", "asc")
        if value not in ("asc", "desc"):
            return "asc"
        return value

    def _get_base_query(self, extra=None):
        # 统一拼装看板查询参数，保证筛选、搜索、排序之间可以叠加。
        query = {}
        if self.status_filter and self.status_filter != "all":
            query["status_filter"] = self.status_filter
        if self.plan_query:
            query["plan_query"] = self.plan_query
        if self.sort_on:
            query["sort_on"] = self.sort_on
        if self.sort_order:
            query["sort_order"] = self.sort_order
        if extra:
            for key, value in extra.items():
                if value in (None, "", "all"):
                    query.pop(key, None)
                    continue
                query[key] = value
        return query

    def build_task_board_url(self, extra=None):
        base_url = "{0}/@@task_board".format(api.get_url(self.context))
        query = self._get_base_query(extra=extra)
        if not query:
            return base_url
        return "{0}?{1}".format(base_url, urlencode(query))

    def get_status_filter_options(self):
        return [
            ("all", u"All"),
            ("pending_placement", u"Pending Placement"),
            ("active", u"In Progress"),
            ("completed", u"Completed"),
        ]

    def get_status_filter_buttons(self):
        # 生成顶部状态按钮数据，样式对齐 Listing 的状态筛选按钮。
        buttons = []
        for key, title in self.get_status_filter_options():
            status_value = None if key == "all" else key
            url = self.build_task_board_url({
                "status_filter": status_value,
            })
            buttons.append({
                "id": key,
                "title": title,
                "url": url,
                "active": key == self.status_filter,
            })
        return buttons

    def _filter_rows(self, rows, status_filter):
        if status_filter == "all":
            return rows
        return [row for row in rows if row.get("status") == status_filter]

    def _search_rows(self, rows, plan_query):
        if not plan_query:
            return rows
        query = api.safe_unicode(plan_query).lower()
        result = []
        for row in rows:
            title = api.safe_unicode(row.get("plan_title", "")).lower()
            if query in title:
                result.append(row)
        return result

    def _sort_rows(self, rows, sort_on, sort_order):
        key_name = {
            "target_date": "target_dt",
            "window_start": "window_start_dt",
            "window_end": "window_end_dt",
        }.get(sort_on, "target_dt")
        reverse = sort_order == "desc"
        return sorted(
            rows,
            key=lambda r: (r.get(key_name) is None, r.get(key_name)),
            reverse=reverse,
        )

    def get_sort_url(self, sort_on):
        sort_order = "asc"
        if self.sort_on == sort_on and self.sort_order == "asc":
            sort_order = "desc"
        return self.build_task_board_url({
            "sort_on": sort_on,
            "sort_order": sort_order,
        })

    def get_sort_indicator(self, sort_on):
        if self.sort_on != sort_on:
            return u""
        return self.sort_order == "asc" and u" ^" or u" v"

    def _build_row_id(self, plan_uid, seq):
        """统一生成任务看板行标识。"""
        if not api.is_uid(plan_uid):
            return u""
        try:
            seq = int(seq)
        except Exception:
            return u""
        if seq <= 0:
            return u""
        return u"{0}::{1}".format(plan_uid, seq)

    def _guess_sequence_from_row(self, row):
        """在缺失 row_id 时，从现有行数据尽量恢复 seq。"""
        if not isinstance(row, dict):
            return None
        for key in ("seq", "sequence"):
            value = row.get(key)
            try:
                value = int(value)
            except Exception:
                value = None
            if value and value > 0:
                return value

        title = api.safe_unicode(row.get("task_title", u"") or u"")
        match = re.match(r"^\s*TP\s+(\d+)\b", title)
        if match:
            try:
                return int(match.group(1))
            except Exception:
                return None
        return None

    def _ensure_row_id(self, row):
        """兼容旧数据路径，保证模板渲染时始终可安全读取 row_id。"""
        if not isinstance(row, dict):
            return row
        if row.get("row_id"):
            return row

        row = dict(row)
        plan_uid = row.get("plan_uid")
        seq = self._guess_sequence_from_row(row)
        row["row_id"] = self._build_row_id(plan_uid, seq)
        return row

    def _to_datetime(self, value):
        if value is None:
            return None
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, DateTime):
            dt = value.asdatetime()
        elif getattr(value, "asdatetime", None):
            try:
                dt = value.asdatetime()
            except Exception:
                return None
        else:
            return None
        if getattr(dt, "tzinfo", None) is not None:
            try:
                dt = dt.replace(tzinfo=None)
            except Exception:
                pass
        return dt

    def _format_datetime(self, value):
        dt = self._to_datetime(value)
        if dt is not None:
            return dt.strftime("%Y-%m-%d %H:%M")
        return value and api.safe_unicode(value) or ""

    def _status_title(self, status):
        mapping = {
            "pending_placement": u"Pending Placement",
            "active": u"In Progress",
            "completed": u"Completed",
        }
        return mapping.get(status, status or u"")

    def _get_rows(self):
        context = self.context
        if _matches_logical_id(api.get_id(context), "task_board"):
            context = _get_plans_container_in_module(api.get_parent(context)) or context

        # 看板默认展示计划(Plan)里的 Plan Details 数据，不依赖已生成的 Task 对象。
        plans_query = {
            "portal_type": "StabilityPlan",
            "path": {
                "query": api.get_path(context),
                "depth": 1,
            },
        }
        brains = api.search(plans_query, catalog=SETUP_CATALOG)
        now = datetime.now()

        rows = []
        samples_cache = {}
        for brain in brains:
            plan = api.get_object(brain)
            if plan is None:
                continue

            plan_uid = api.get_uid(plan)
            plan_url = api.get_url(plan)
            plan_title = api.get_title(plan)

            start_time = getattr(plan, "start_time", None)
            details = getattr(plan, "plan_details", None) or []

            for seq, row in enumerate(details, start=1):
                if not isinstance(row, dict):
                    continue

                months = _normalize_months(row.get("timepoint_days", 0))

                window_days = row.get("window_days", 0)
                if not isinstance(window_days, int) or window_days < 0:
                    window_days = 0

                status = row.get("detail_status") or "pending_placement"
                # 关联样品 UID，来自 Plan Details 行的 analysis_request 字段。
                sample_uid = _first(row.get("analysis_request")) or ""
                sample_id = ""
                sample_url = ""
                if api.is_uid(sample_uid):
                    sample = samples_cache.get(sample_uid)
                    if sample is None:
                        sample = api.get_object_by_uid(sample_uid)
                        samples_cache[sample_uid] = sample
                    if sample is not None:
                        sample_id = api.get_id(sample) or ""
                        sample_url = api.get_url(sample)

                stock_batch_uid = _first(row.get("stock_batch")) or ""
                stock_batch_title = ""
                if api.is_uid(stock_batch_uid):
                    stock_batch = samples_cache.get(stock_batch_uid)
                    if stock_batch is None:
                        stock_batch = api.get_object_by_uid(stock_batch_uid)
                        samples_cache[stock_batch_uid] = stock_batch
                    if stock_batch is not None:
                        stock_batch_title = api.get_title(stock_batch) or api.get_id(stock_batch) or ""

                target_date = None
                window_start = None
                window_end = None
                if start_time:
                    # 鏃堕棿鐐规寜鏈堣绠?(1鏈?30澶?锛岀獥鍙ｆ湡鎸夊ぉ璁＄畻
                    target_date = start_time + timedelta(days=months * 30)
                    if window_days:
                        window_start = target_date - timedelta(days=window_days)
                        window_end = target_date + timedelta(days=window_days)
                    else:
                        window_start = target_date
                        window_end = target_date

                target_dt = self._to_datetime(target_date)
                window_start_dt = self._to_datetime(window_start)
                window_end_dt = self._to_datetime(window_end)
                is_overdue = bool(target_dt and status != "completed" and target_dt < now)

                rows.append({
                    # row_id 鐢ㄤ簬鏍峰搧鏀剧疆椤靛畾浣嶈鍒掑唴鐨勮锛坧lan_uid::seq锛?                    "row_id": "{0}::{1}".format(plan_uid, seq),
                    "plan_uid": plan_uid,
                    "plan_url": plan_url,
                    "plan_title": plan_title,
                    "task_title": u"TP {0} ({1} Months)".format(seq, months),
                    "sample_uid": sample_uid,
                    "sample_id": sample_id,
                    "sample_url": sample_url,
                    "stock_batch_uid": stock_batch_uid,
                    "stock_batch_title": stock_batch_title,
                    "timepoint_months": months,
                    "window_days": window_days,
                    "target_date": self._format_datetime(target_date),
                    "target_dt": target_dt,
                    "window_start": self._format_datetime(window_start),
                    "window_start_dt": window_start_dt,
                    "window_end": self._format_datetime(window_end),
                    "window_end_dt": window_end_dt,
                    "status": status,
                    "status_title": self._status_title(status),
                    "is_overdue": is_overdue,
                })
        return rows

    def _get_stats(self, rows):
        stats = {
            "expired": 0,
            "pending": 0,
            "in_progress": 0,
        }
        for row in rows:
            status = row.get("status")
            if status == "completed":
                continue
            if row.get("is_overdue"):
                stats["expired"] += 1
            elif status == "pending_placement":
                stats["pending"] += 1
            else:
                stats["in_progress"] += 1
        return stats


class WorkflowActionSamplePlacementAdapter(RequestContextAware):
    implements(IWorkflowActionUIDsAdapter)

    def __call__(self, action, uids):
        if not has_permission("Modify portal content", self.context):
            return self.redirect(
                message=_(u"You do not have permission to place samples."),
                level="error",
            )

        selected_uids = [uid for uid in (uids or []) if api.is_uid(uid)]
        if not selected_uids:
            return self.redirect(
                message=_(u"Please select pending tasks first."),
                level="warning",
            )

        query = [("uids:list", uid) for uid in selected_uids]
        url = "{0}/@@sample_placement?{1}".format(
            api.get_url(self.context), urlencode(query))
        return self.request.response.redirect(url)


class WorkflowActionSyncPlanTasksAdapter(RequestContextAware):
    implements(IWorkflowActionUIDsAdapter)

    def __call__(self, action, uids):
        # 权限校验：只有有编辑权限的人才能做同步。
        if not has_permission("Modify portal content", self.context):
            return self.redirect(
                message=_(u"You do not have permission to sync plan tasks."),
                level="error",
            )

        selected_uids = [uid for uid in (uids or []) if api.is_uid(uid)]
        if not selected_uids:
            return self.redirect(
                message=_(u"No items selected."),
                level="warning",
            )

        plans = []
        for uid in selected_uids:
            task = api.get_object_by_uid(uid)
            plan = task and api.get_parent(task) or None
            if plan is None:
                continue
            if api.get_portal_type(plan) != "StabilityPlan":
                continue
            if plan not in plans:
                plans.append(plan)

        if not plans:
            return self.redirect(
                message=_(u"No plans found for selected tasks."),
                level="warning",
            )

        try:
            from maitux.stability.subscribers import sync_plan_timepoint_tasks
        except Exception:
            sync_plan_timepoint_tasks = None

        if sync_plan_timepoint_tasks is None:
            return self.redirect(
                message=_(u"Sync feature is not available."),
                level="error",
            )

        total_created = 0
        total_updated = 0
        total_deleted = 0
        for plan in plans:
            c, u, d = sync_plan_timepoint_tasks(plan, delete_excess=True)
            total_created += c
            total_updated += u
            total_deleted += d

        return self.redirect(
            message=_(u"Sync done. Created: {0}, Updated: {1}, Deleted: {2}.")
                    .format(total_created, total_updated, total_deleted),
            level="info",
        )


class SamplePlacementView(BrowserView):
    template = ViewPageTemplateFile("templates/sample_placement.pt")

    def __call__(self):
        if not has_permission("Modify portal content", self.context):
            ploneapi.portal.show_message(
                message=_(u"You do not have permission to place samples."),
                request=self.request,
                type="error",
            )
            return self.request.response.redirect(self.get_back_url())

        if self.request.form.get("button_cancel"):
            return self.request.response.redirect(self.get_back_url())

        self.row_ids = self.get_selected_row_ids()
        self.tasks = self.get_tasks_data()
        self.stock_batches = self.get_stock_batches()
        self.selected_stock_batch_uids = self.get_selected_stock_batch_uids()

        if self.request.form.get("button_save"):
            return self.handle_save()

        return self.template()

    def get_back_url(self):
        return "{0}/@@task_board".format(api.get_url(self.context))

    def get_selected_row_ids(self):
        # 鏉ヨ嚜鐪嬫澘鐨?row_id 鍒楄〃锛屾牸寮忥細plan_uid::seq
        value = self.request.get("row_ids", self.request.form.get("row_ids", []))
        if not isinstance(value, (list, tuple)):
            value = [value]
        result = []
        for rid in value:
            if not rid or not isinstance(rid, six.string_types):
                continue
            if "::" not in rid:
                continue
            if rid not in result:
                result.append(rid)
        return result

    def _parse_row_id(self, row_id):
        try:
            plan_uid, seq = row_id.split("::", 1)
            seq = int(seq)
        except Exception:
            return (None, None)
        if not api.is_uid(plan_uid):
            return (None, None)
        if seq <= 0:
            return (None, None)
        return (plan_uid, seq)

    def get_tasks_data(self):
        data = []
        plans = {}
        for rid in self.row_ids:
            plan_uid, seq = self._parse_row_id(rid)
            if plan_uid is None:
                continue
            plan = plans.get(plan_uid)
            if plan is None:
                plan = api.get_object_by_uid(plan_uid)
                plans[plan_uid] = plan
            if plan is None or api.get_portal_type(plan) != "StabilityPlan":
                continue

            details = getattr(plan, "plan_details", None) or []
            if seq > len(details):
                continue
            row = details[seq - 1]
            if not isinstance(row, dict):
                continue
            status = row.get("detail_status") or "pending_placement"
            if status != "pending_placement":
                continue
            stock_batch_uid = _first(row.get("stock_batch")) or ""

            months = _normalize_months(row.get("timepoint_days", 0))
            window_days = row.get("window_days", 0)
            if not isinstance(window_days, int) or window_days < 0:
                window_days = 0

            data.append({
                "row_id": rid,
                "plan_title": api.get_title(plan) or "",
                "plan_url": api.get_url(plan),
                "task_title": u"TP {0} ({1} Months)".format(seq, months),
                "timepoint_months": months,
                "window_days": window_days,
                "stock_batch_uid": stock_batch_uid,
            })
        return data

    def get_stock_batches(self):
        query = {
            "portal_type": "StockBatch",
            "review_state": "active",
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        }
        brains = api.search(query, catalog="portal_catalog")
        data = []
        for brain in brains:
            uid = api.get_uid(brain)
            if not api.is_uid(uid):
                continue
            data.append({
                "uid": uid,
                "title": api.get_title(brain) or uid,
            })
        return data

    def get_selected_stock_batch_uids(self):
        value = self.request.form.get("stock_batch_uid", self.request.get("stock_batch_uid", []))
        if value is None:
            return []
        if isinstance(value, six.string_types):
            value = value.strip()
            return value and [value] or []
        if not isinstance(value, (list, tuple)):
            return []
        result = []
        for item in value:
            if not item:
                result.append("")
                continue
            if isinstance(item, six.string_types):
                result.append(item.strip())
            else:
                result.append("")
        return result

    def get_selected_stock_batch_uid_for(self, row, index):
        if index is None or index < 0:
            index = 0
        selected = self.selected_stock_batch_uids or []
        if index < len(selected) and selected[index]:
            return selected[index]
        return (row or {}).get("stock_batch_uid") or ""

    def handle_save(self):
        if not self.tasks:
            ploneapi.portal.show_message(
                message=_(u"No pending tasks selected."),
                request=self.request,
                type="warning",
            )
            return self.request.response.redirect(self.get_back_url())

        stock_batch_uids = self.get_selected_stock_batch_uids()
        per_row = {}
        missing = 0
        invalid = 0
        for idx, row in enumerate(self.tasks):
            rid = row.get("row_id")
            sb_uid = stock_batch_uids[idx] if idx < len(stock_batch_uids) else ""
            if not sb_uid:
                missing += 1
                continue
            if not api.is_uid(sb_uid):
                invalid += 1
                continue
            per_row[rid] = sb_uid

        if missing or invalid or len(per_row) != len(self.tasks):
            ploneapi.portal.show_message(
                message=_(u"Please select a Stock Batch for each selected task."),
                request=self.request,
                type="error",
            )
            return self.template()

        updated = 0
        # 把 StockBatch 和状态写回到 Plan Details，同时尽量同步到已生成的 Task。
        plans = {}
        seqs_by_plan = {}
        for item in self.tasks:
            rid = item.get("row_id")
            plan_uid, seq = self._parse_row_id(rid)
            if plan_uid is None:
                continue
            sb_uid = per_row.get(rid) or ""
            if not api.is_uid(sb_uid):
                continue
            seqs_by_plan.setdefault(plan_uid, {})[seq] = sb_uid

        for plan_uid, seq_map in seqs_by_plan.items():
            plan = plans.get(plan_uid)
            if plan is None:
                plan = api.get_object_by_uid(plan_uid)
                plans[plan_uid] = plan
            if plan is None:
                continue

            details = list(getattr(plan, "plan_details", None) or [])
            for seq in sorted(seq_map.keys()):
                stock_batch_uid = seq_map.get(seq) or ""
                if not api.is_uid(stock_batch_uid):
                    continue
                if seq > len(details):
                    continue
                row = details[seq - 1]
                if not isinstance(row, dict):
                    continue
                if (row.get("detail_status") or "pending_placement") != "pending_placement":
                    continue

                new_row = dict(row)
                new_row["stock_batch"] = stock_batch_uid
                new_row["detail_status"] = "active"
                details[seq - 1] = new_row
                updated += 1

                # 鍚屾鍒板凡鐢熸垚鐨勬椂闂寸偣浠诲姟锛堝鏋滃瓨鍦級
                try:
                    for child in plan.objectValues():
                        if api.get_portal_type(child) != "StabilityTimepointTask":
                            continue
                        if getattr(child, "sequence", None) != seq:
                            continue
                        if (getattr(child, "detail_status", None) or "pending_placement") != "pending_placement":
                            continue
                        try:
                            child.stock_batch = stock_batch_uid
                        except Exception:
                            try:
                                child.stock_batch = [stock_batch_uid]
                            except Exception:
                                pass
                        child.detail_status = "active"
                        child.reindexObject()
                except Exception:
                    pass

            # 鍐欏洖璁″垝
            try:
                plan.plan_details = details
                plan.reindexObject()
            except Exception:
                pass

        ploneapi.portal.show_message(
            message=_(u"Updated {0} task(s) to In Progress.").format(updated),
            request=self.request,
            type="info",
        )
        return self.request.response.redirect(self.get_back_url())


class LinkSampleView(BrowserView):
    template = ViewPageTemplateFile("templates/link_sample.pt")

    def __call__(self):
        # 需要编辑权限才能关联样品。
        if not has_permission("Modify portal content", self.context):
            ploneapi.portal.show_message(
                message=_(u"You do not have permission to link samples."),
                request=self.request,
                type="error",
            )
            return self.request.response.redirect(self.get_back_url())

        self.row_ids = self.get_selected_row_ids()
        self.tasks = self.get_tasks_data()
        self.recent_samples = self.get_recent_samples()

        if self.request.form.get("button_cancel"):
            return self.request.response.redirect(self.get_back_url())
        if self.request.form.get("button_save"):
            return self.handle_save()

        return self.template()

    def get_back_url(self):
        return "{0}/@@task_board".format(api.get_url(self.context))

    def get_selected_row_ids(self):
        value = self.request.get("row_ids", self.request.form.get("row_ids", []))
        if not isinstance(value, (list, tuple)):
            value = [value]
        result = []
        for rid in value:
            if not rid or not isinstance(rid, six.string_types):
                continue
            if "::" not in rid:
                continue
            if rid not in result:
                result.append(rid)
        return result

    def _parse_row_id(self, row_id):
        try:
            plan_uid, seq = row_id.split("::", 1)
            seq = int(seq)
        except Exception:
            return (None, None)
        if not api.is_uid(plan_uid):
            return (None, None)
        if seq <= 0:
            return (None, None)
        return (plan_uid, seq)

    def get_tasks_data(self):
        data = []
        plans = {}
        for rid in self.row_ids:
            plan_uid, seq = self._parse_row_id(rid)
            if plan_uid is None:
                continue
            plan = plans.get(plan_uid)
            if plan is None:
                plan = api.get_object_by_uid(plan_uid)
                plans[plan_uid] = plan
            if plan is None or api.get_portal_type(plan) != "StabilityPlan":
                continue

            details = getattr(plan, "plan_details", None) or []
            if seq > len(details):
                continue
            row = details[seq - 1]
            if not isinstance(row, dict):
                continue

            months = _normalize_months(row.get("timepoint_days", 0))

            data.append({
                "row_id": rid,
                "plan_title": api.get_title(plan) or "",
                "plan_url": api.get_url(plan),
                "task_title": u"TP {0} ({1} Months)".format(seq, months),
                "status": row.get("detail_status") or "pending_placement",
            })
        return data

    def get_recent_samples(self, limit=50):
        query = {
            "portal_type": "AnalysisRequest",
            "sort_on": "created",
            "sort_order": "reverse",
        }
        brains = api.search(query, catalog=SAMPLE_CATALOG)
        items = []
        for brain in brains[:limit]:
            try:
                uid = api.get_uid(brain)
                if not api.is_uid(uid):
                    continue
                items.append({
                    "uid": uid,
                    "id": api.get_id(brain),
                    "title": api.get_id(brain),
                })
            except Exception:
                continue
        return items

    def get_selected_sample_uid(self):
        value = self.request.form.get("sample_uid", "").strip()
        return value

    def handle_save(self):
        sample_uid = self.get_selected_sample_uid()
        if not api.is_uid(sample_uid):
            ploneapi.portal.show_message(
                message=_(u"Please select an existing sample first."),
                request=self.request,
                type="error",
            )
            return self.template()

        updated = 0
        plans = {}
        seqs_by_plan = {}
        for item in self.tasks:
            rid = item.get("row_id")
            plan_uid, seq = self._parse_row_id(rid)
            if plan_uid is None:
                continue
            seqs_by_plan.setdefault(plan_uid, set()).add(seq)

        for plan_uid, seqs in seqs_by_plan.items():
            plan = plans.get(plan_uid)
            if plan is None:
                plan = api.get_object_by_uid(plan_uid)
                plans[plan_uid] = plan
            if plan is None:
                continue

            details = list(getattr(plan, "plan_details", None) or [])
            for seq in sorted(seqs):
                if seq > len(details):
                    continue
                row = details[seq - 1]
                if not isinstance(row, dict):
                    continue
                new_row = dict(row)
                # 鍐欏洖鍏宠仈鐨勬牱鍝乁ID
                new_row["analysis_request"] = [sample_uid]
                details[seq - 1] = new_row
                updated += 1

            try:
                plan.plan_details = details
                plan.reindexObject()
            except Exception:
                ploneapi.portal.show_message(
                    message=_(u"Failed to update Stability Plan details."),
                    request=self.request,
                    type="error",
                )
                return self.template()

        ploneapi.portal.show_message(
            message=_(u"Linked sample for {0} plan detail row(s).").format(updated),
            request=self.request,
            type="info",
        )
        return self.request.response.redirect(self.get_back_url())


class CreateSampleView(BrowserView):
    template = ViewPageTemplateFile("templates/create_sample.pt")

    def __call__(self):
        if not has_permission("Modify portal content", self.context):
            ploneapi.portal.show_message(
                message=_(u"You do not have permission to create samples."),
                request=self.request,
                type="error",
            )
            return self.request.response.redirect(self.get_back_url())

        self.row_ids = self.get_selected_row_ids()
        self.tasks = self.get_tasks_data()
        self.clients = self.get_clients()
        self.sampletypes = self.get_sampletypes()
        self.selected_client_uid = self.request.form.get("client_uid") or self.request.get("client_uid") or ""
        self.contacts = self.get_contacts(self.selected_client_uid) if api.is_uid(self.selected_client_uid) else []

        if self.request.form.get("button_cancel"):
            return self.request.response.redirect(self.get_back_url())

        if self.request.form.get("button_create"):
            return self.handle_create()

        return self.template()

    def get_back_url(self):
        return "{0}/@@task_board".format(api.get_url(self.context))

    def get_selected_row_ids(self):
        value = self.request.get("row_ids", self.request.form.get("row_ids", []))
        if not isinstance(value, (list, tuple)):
            value = [value]
        result = []
        for rid in value:
            if not rid or not isinstance(rid, six.string_types):
                continue
            if "::" not in rid:
                continue
            if rid not in result:
                result.append(rid)
        return result

    def _parse_row_id(self, row_id):
        try:
            plan_uid, seq = row_id.split("::", 1)
            seq = int(seq)
        except Exception:
            return (None, None)
        if not api.is_uid(plan_uid):
            return (None, None)
        if seq <= 0:
            return (None, None)
        return (plan_uid, seq)

    def get_tasks_data(self):
        data = []
        plans = {}
        for rid in self.row_ids:
            plan_uid, seq = self._parse_row_id(rid)
            if plan_uid is None:
                continue
            plan = plans.get(plan_uid)
            if plan is None:
                plan = api.get_object_by_uid(plan_uid)
                plans[plan_uid] = plan
            if plan is None or api.get_portal_type(plan) != "StabilityPlan":
                continue

            details = getattr(plan, "plan_details", None) or []
            if seq > len(details):
                continue
            row = details[seq - 1]
            if not isinstance(row, dict):
                continue

            months = _normalize_months(row.get("timepoint_days", 0))

            spec_uid = _extract_uid(row.get("analysis_specification")) or _extract_uid(
                row.get("analysis_specification_record")
            )
            profile_uid = _extract_uid(row.get("analysis_profile")) or _extract_uid(
                row.get("analysis_profile_record")
            )
            batch_uid = _extract_uid(row.get("batch"))
            batch_title = u""
            if api.is_uid(batch_uid):
                batch = api.get_object_by_uid(batch_uid)
                if batch is not None:
                    batch_title = api.get_title(batch) or api.get_id(batch) or u""

            data.append({
                "row_id": rid,
                "plan_uid": plan_uid,
                "seq": seq,
                "plan_title": api.get_title(plan) or "",
                "analysis_specification": spec_uid,
                "analysis_profile": profile_uid,
                "batch_uid": batch_uid,
                "batch_title": batch_title,
                "task_title": u"TP {0} ({1} Months)".format(seq, months),
            })
        return data

    def get_clients(self, limit=200):
        query = {
            "portal_type": "Client",
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        }
        brains = api.search(query, catalog=CLIENT_CATALOG)
        items = []
        for brain in brains[:limit]:
            uid = api.get_uid(brain)
            if not api.is_uid(uid):
                continue
            items.append({
                "uid": uid,
                "title": api.get_title(brain) or api.get_id(brain),
            })
        return items

    def get_contacts(self, client_uid, limit=200):
        client = api.get_object_by_uid(client_uid) if api.is_uid(client_uid) else None
        if client is None:
            return []
        try:
            contacts = client.getContacts()
        except Exception:
            contacts = []
        items = []
        for contact in contacts[:limit]:
            try:
                items.append({
                    "uid": api.get_uid(contact),
                    "title": api.get_title(contact) or api.get_id(contact),
                })
            except Exception:
                continue
        return items

    def get_sampletypes(self, limit=200):
        query = {
            "portal_type": "SampleType",
            "is_active": True,
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        }
        brains = api.search(query, catalog=SETUP_CATALOG)
        items = []
        for brain in brains[:limit]:
            uid = api.get_uid(brain)
            if not api.is_uid(uid):
                continue
            items.append({
                "uid": uid,
                "title": api.get_title(brain) or api.get_id(brain),
            })
        return items

    def handle_create(self):
        client_uid = self.request.form.get("client_uid", "").strip()
        contact_uid = self.request.form.get("contact_uid", "").strip()
        sampletype_uid = self.request.form.get("sampletype_uid", "").strip()
        date_sampled = self.request.form.get("date_sampled", "").strip()

        if not api.is_uid(client_uid):
            ploneapi.portal.show_message(
                message=_(u"Please select a Client."),
                request=self.request,
                type="error",
            )
            return self.template()
        if not api.is_uid(contact_uid):
            ploneapi.portal.show_message(
                message=_(u"Please select a Contact."),
                request=self.request,
                type="error",
            )
            return self.template()
        if not api.is_uid(sampletype_uid):
            ploneapi.portal.show_message(
                message=_(u"Please select a Sample Type."),
                request=self.request,
                type="error",
            )
            return self.template()
        if not date_sampled:
            # DateSampled 鏄?AR 鍒涘缓鐨勫繀濉瓧娈典箣涓€
            date_sampled = DateTime().strftime("%Y-%m-%d")

        client = api.get_object_by_uid(client_uid)
        if client is None:
            ploneapi.portal.show_message(
                message=_(u"Client not found."),
                request=self.request,
                type="error",
            )
            return self.template()

        try:
            from bika.lims.utils.analysisrequest import create_analysisrequest
        except Exception:
            create_analysisrequest = None

        if create_analysisrequest is None:
            ploneapi.portal.show_message(
                message=_(u"Cannot create sample in this environment."),
                request=self.request,
                type="error",
            )
            return self.template()

        created = 0
        plans = {}
        seqs_by_plan = {}
        # 每个 PlanDetail 行创建一个样品，并写回关联。
        for item in self.tasks:
            row_id = item.get("row_id")
            plan_uid, seq = self._parse_row_id(row_id)
            if plan_uid is None:
                continue
            seqs_by_plan.setdefault(plan_uid, []).append(seq)

        for plan_uid, seqs in seqs_by_plan.items():
            plan = plans.get(plan_uid)
            if plan is None:
                plan = api.get_object_by_uid(plan_uid)
                plans[plan_uid] = plan
            if plan is None:
                continue

            details = list(getattr(plan, "plan_details", None) or [])
            for seq in seqs:
                if seq > len(details):
                    continue
                row = details[seq - 1]
                if not isinstance(row, dict):
                    continue

                spec_uid = _extract_uid(row.get("analysis_specification")) or _extract_uid(
                    row.get("analysis_specification_record")
                )
                profile_uid = _extract_uid(row.get("analysis_profile")) or _extract_uid(
                    row.get("analysis_profile_record")
                )
                batch_uid = _extract_uid(row.get("batch"))

                values = {
                    "Client": client_uid,
                    "Contact": contact_uid,
                    "DateSampled": date_sampled,
                    "SamplingDate": date_sampled,
                    "SampleType": sampletype_uid,
                }
                if api.is_uid(batch_uid):
                    values["Batch"] = batch_uid

                analyses = []
                results_ranges = None
                # 优先使用检验标准，其次使用 Profile。
                if api.is_uid(spec_uid):
                    spec_obj = api.get_object(spec_uid, None)
                    if spec_obj:
                        values["Specification"] = spec_obj
                        try:
                            ranges = spec_obj.getResultsRange() or []
                            results_ranges = ranges
                            for rr in ranges:
                                # rr 里可能同时存 uid(服务 UID) 和 keyword(服务关键字)。
                                # 为了兼容历史数据，两者都尝试，最终交给 create_analysisrequest 做解析。
                                service_uid = rr.get("uid", "") if isinstance(rr, dict) else ""
                                keyword = rr.get("keyword", "") if isinstance(rr, dict) else ""
                                if api.is_uid(service_uid):
                                    analyses.append(service_uid)
                                elif keyword:
                                    analyses.append(keyword)
                        except Exception:
                            pass
                elif api.is_uid(profile_uid):
                    values["Profiles"] = [profile_uid]

                try:
                    ar = create_analysisrequest(
                        client, self.request, values, analyses, results_ranges=results_ranges
                    )
                except Exception:
                    ar = None
                if ar is None:
                    continue
                if api.is_uid(batch_uid):
                    try:
                        batch_obj = api.get_object_by_uid(batch_uid)
                        if batch_obj is not None:
                            ar.setBatch(batch_obj)
                            ar.reindexObject()
                    except Exception:
                        pass
                try:
                    analysis_objects = [
                        o for o in ar.objectValues()
                        if api.get_portal_type(o) in ("Analysis", "DuplicateAnalysis", "ReferenceAnalysis")
                    ]
                except Exception:
                    analysis_objects = []
                if not analysis_objects:
                    ploneapi.portal.show_message(
                        message=_(u"No analyses were created for this sample. Please check the selected Specification/Profile."),
                        request=self.request,
                        type="warning",
                    )

                # 写回 PlanDetails 关联。
                new_row = dict(row)
                new_row["analysis_request"] = [api.get_uid(ar)]
                details[seq - 1] = new_row
                created += 1

            try:
                plan.plan_details = details
                plan.reindexObject()
            except Exception:
                pass

        ploneapi.portal.show_message(
            message=_(u"Created {0} sample(s).").format(created),
            request=self.request,
            type="info",
        )
        return self.request.response.redirect(self.get_back_url())
