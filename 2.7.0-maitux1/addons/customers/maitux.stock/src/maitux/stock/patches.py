# -*- coding: utf-8 -*-
from Products.CMFCore.utils import getToolByName

from maitux.stock.browser.stockbatchactions import get_transition_items_for_batch


_PATCHED = False


def patch_allowed_transitions_for_many():
    """为 StockBatch 扩展标准 allowedTransitionsFor_many 返回结果。"""
    global _PATCHED
    if _PATCHED:
        return

    try:
        from bika.lims.jsonapi.allowedtransitionsfor import allowedTransitionsFor
    except Exception:
        return

    original = allowedTransitionsFor.allowed_transitions_for_many

    def wrapped(self, context, request):
        # 中文注释：这里复用标准 listing 的 selected-actions 机制，
        # 仅对 StockBatch 注入自定义动作，其它对象仍保持原生逻辑。
        wftool = getToolByName(context, "portal_workflow")
        uc = getToolByName(context, 'uid_catalog')
        import json
        from zExceptions import BadRequest
        from plone.jsonapi.core import router

        uids = json.loads(request.get('uid', '[]'))
        if not uids:
            raise BadRequest("No object UID specified in request")

        allowed_transitions = []
        try:
            brains = uc(UID=uids)
            for brain in brains:
                obj = brain.getObject()
                if getattr(obj, "portal_type", "") == "StockBatch":
                    trans = get_transition_items_for_batch(obj)
                else:
                    trans = [{'id': t['id'], 'title': t['title']} for t in
                             wftool.getTransitionsFor(obj)]
                allowed_transitions.append(
                    {'uid': obj.UID(), 'transitions': trans})
        except Exception as e:
            msg = "Cannot get the allowed transitions ({})".format(
                getattr(e, "message", str(e)))
            raise BadRequest(msg)

        return {
            "url": router.url_for("allowedTransitionsFor_many",
                                  force_external=True),
            "success": True,
            "error": False,
            "transitions": allowed_transitions
        }

    allowedTransitionsFor.allowed_transitions_for_many = wrapped
    _PATCHED = True
