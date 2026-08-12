# -*- coding: utf-8 -*-
"""Reactivate 工作流动作与确认页。"""

import transaction

from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.Archetypes.config import UID_CATALOG
from bika.lims import api
from bika.lims import senaiteMessageFactory as _
from bika.lims.browser.workflow import RequestContextAware
from bika.lims.interfaces import IWorkflowActionUIDsAdapter
from zope.interface import implements

from maitux.workflow.services.reactivate import reactivate_objects


class WorkflowActionReactivateAdapter(RequestContextAware):
    """将 reactivate 按钮跳转到原因确认页。"""
    implements(IWorkflowActionUIDsAdapter)

    def __call__(self, action, uids):
        if not uids:
            return self.redirect(message=_("No items selected."), level="warning")
        base_url = api.get_url(self.context)
        url = "{}/@@reactivate_workflow?uids={}".format(base_url, ",".join(uids))
        return self.request.response.redirect(url)


class ReactivateWorkflowView(BrowserView):
    """收集激活原因并执行重激活联动。"""
    template = ViewPageTemplateFile("reactivate.pt")

    def __call__(self):
        if self.request.form.get("form.submitted"):
            return self.handle_submit()
        return self.template()

    def handle_submit(self):
        if self.request.form.get("form.button.cancel"):
            return self.redirect(
                message=_(u"已取消重新激活。"),
                level="warning")

        reason = self.request.form.get("reason", u"").strip()
        if not reason:
            self.context.plone_utils.addPortalMessage(
                _(u"请填写激活原因。"), "error")
            return self.template()

        objects = self.get_objects()
        if not objects:
            return self.redirect(
                message=_(u"未找到可重新激活的对象。"),
                level="warning")

        try:
            reactivate_objects(objects, reason)
        except Exception as exc:
            # 任一步骤失败都回滚整个请求，避免样品/测试出现半成功状态。
            transaction.abort()
            self.context.plone_utils.addPortalMessage(
                _(u"重新激活失败：${message}",
                  mapping={"message": str(exc)}),
                "error")
            return self.template()
        return self.redirect(
            message=_(u"重新激活完成，原结果数据已保留，可继续修改。"))

    def redirect(self, message, level="info"):
        self.context.plone_utils.addPortalMessage(message, level)
        return self.request.response.redirect(api.get_url(self.context))

    def get_objects(self):
        uids = self.get_uids()
        if not uids:
            return []

        # 对齐 SENAITE 官方 workflow 处理方式，直接走 UID catalog 批量取对象。
        brains = api.search(dict(UID=uids), UID_CATALOG)
        objects = map(api.get_object, brains)
        return objects

    def get_items(self):
        items = []
        for obj in self.get_objects():
            items.append({
                "uid": api.get_uid(obj),
                "id": api.get_id(obj),
                "title": api.get_title(obj),
                "portal_type": getattr(obj, "portal_type", ""),
            })
        return items

    def get_reason(self):
        return self.request.form.get("reason", u"")

    def get_uids(self):
        values = self.request.form.get("uids:list") or self.request.get("uids:list", [])
        if values:
            if not isinstance(values, (list, tuple)):
                values = [values]
            return self._normalize_uids(values)

        value = self.request.form.get("uids") or self.request.get("uids", "")
        if isinstance(value, (list, tuple)):
            return self._normalize_uids(value)
        if api.is_string(value):
            return self._normalize_uids(value.split(","))
        return []

    def _normalize_uids(self, values):
        """清洗并去重 UID，兼容 querystring 与 form 同时提交的重复值。"""
        parsed = []
        seen = set()
        for value in values:
            if not api.is_string(value):
                continue
            uid = value.strip()
            if not uid or uid in seen:
                continue
            parsed.append(uid)
            seen.add(uid)
        return parsed
