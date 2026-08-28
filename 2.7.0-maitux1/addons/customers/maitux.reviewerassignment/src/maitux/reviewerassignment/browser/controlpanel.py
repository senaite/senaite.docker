# -*- coding: utf-8 -*-
"""审核分配控制面板"""

from bika.lims import api
from plone.registry.interfaces import IRegistry
from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from zope.component import getUtility

from maitux.reviewerassignment.config import REGISTRY_PREFIX
from maitux.reviewerassignment.settings import DEFAULTS


FIELDS = (
    ("require_reviewer_on_worksheet_submit",
     u"工作表提交前必须已分配审核人",
     u"关闭后，未分配审核人的工作表也可以提交。"),
    ("require_reviewer_on_analysis_submit",
     u"工作表内分析项提交前必须已分配审核人",
     u"关闭后，工作表未分配审核人时，其中的分析项仍可单独提交。"),
    ("restrict_verify_to_assigned_reviewer",
     u"只有被指派的审核人本人可以审核",
     u"关闭后不再校验「必须是被指派的那个人」，审核权限回落到 SENAITE 自身的判断"
     u"（Verify 权限、自审限制、依赖项等仍然生效）。"),
    ("exclude_submitter_from_reviewers",
     u"审核人候选中剔除未来的提交人",
     u"依据 SENAITE 的「允许自审」设置：不允许自审时，把工作表的分析员从审核人"
     u"下拉框中剔除，避免选完提交后到审核那一步才失败。"),
)


class ReviewerAssignmentControlPanelView(BrowserView):
    """四个站点级开关 + 站点前置条件状态"""

    index = ViewPageTemplateFile("templates/controlpanel.pt")

    def __call__(self):
        if self.request.form.get("form_submitted"):
            self.handle_save()
        return self.index()

    def handle_save(self):
        registry = getUtility(IRegistry)
        for name, _title, _description in FIELDS:
            key = "%s.%s" % (REGISTRY_PREFIX, name)
            value = bool(self.request.form.get(name))
            try:
                registry[key] = value
            except Exception:
                # 记录还没注册出来时不要让整个页面炸掉，重装 profile 即可修复。
                continue
        api.get_request().response.redirect(
            "%s/@@maitux-reviewerassignment-controlpanel"
            % api.get_url(api.get_portal()))

    def get_fields(self):
        """返回 (name, title, description, value) 供模板渲染"""
        registry = getUtility(IRegistry)
        items = []
        for name, title, description in FIELDS:
            key = "%s.%s" % (REGISTRY_PREFIX, name)
            try:
                value = registry[key]
            except Exception:
                value = DEFAULTS.get(name, True)
            items.append({
                "name": name,
                "title": title,
                "description": description,
                "value": bool(value),
            })
        return items

    def get_prerequisite_status(self):
        """站点前置条件：AllowToSubmitNotAssigned 打开时本 addon 形同虚设

        审核人规则只覆盖工作表内的分析项。该设置一旦打开，不建工作表也能提交，
        整套约束可被绕过。这里把状态显式摆在面板上，而不是只写进安装日志。
        """
        setup_tool = api.get_bika_setup()
        if setup_tool is None:
            return {"ok": True, "message": u""}
        try:
            allow_not_assigned = setup_tool.getAllowToSubmitNotAssigned()
        except Exception:
            return {"ok": True, "message": u""}

        if not allow_not_assigned:
            return {
                "ok": True,
                "message": u"站点已关闭「允许提交未指派的分析项」，审核人规则覆盖提交路径。",
            }
        return {
            "ok": False,
            "message": (
                u"站点开启了「允许提交未指派的分析项」。分析项不建工作表也能提交，"
                u"而审核人规则只覆盖工作表内的分析项 —— 本插件的约束可被完全绕过。"
                u"请在 设置 > 分析 中关闭该项。"),
        }
