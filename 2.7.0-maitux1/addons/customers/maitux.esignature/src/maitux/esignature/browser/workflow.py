# -*- coding: utf-8 -*-
"""Workflow action adapters and signature prompt views."""

import json
import transaction

from bika.lims import api
from bika.lims.api.user import get_user_id
from bika.lims.browser import workflow as bika_browser_workflow
from bika.lims.browser.workflow.analysisrequest import WorkflowActionReceiveAdapter
from bika.lims.browser.workflow import RequestContextAware
from bika.lims.interfaces import IAnalysis
from bika.lims.interfaces import IAnalysisRequest
from bika.lims.interfaces import IWorkflowActionUIDsAdapter
from bika.lims.workflow import doActionFor as do_action_for
from bika.lims.workflow import isTransitionAllowed as is_transition_allowed
from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from senaite.app.listing.adapters.workflow import ListingWorkflowTransition
from senaite.core.browser.listing.workflow.sample import SampleReceiveWorkflowTransition
from six.moves.urllib.parse import urlencode
from zope.component.hooks import setSite
from zope.event import notify
from zope.globalrequest import setRequest
from zope.interface import implementer
from zope.traversing.interfaces import BeforeTraverseEvent

from maitux.esignature.services.context import (
    build_signature_summary,
    clear_verified_signature_context,
    set_verified_signature_context,
)
from maitux.esignature.services.policy import SignaturePolicyResolver
from maitux.esignature.services.reauth import PasReAuthenticationProvider
from maitux.esignature.services.signflow import authenticate_countersign_users
from maitux.esignature.storage.store import SignatureRecordStore


def build_signature_prompt_url(
    context, transition_id, redirect_url, skip_transition_check=False,
    uids=None,
):
    """URL of the prompt for one signature act.

    `context` stays the *anchor* object even when the act covers a batch: the
    policy is resolved by portal_type (SignaturePolicyResolver.resolve), so
    hanging the prompt on the worksheet would look up rules for portal_type
    "Worksheet" and find none.  The rest of the batch travels in `uids`.
    """
    query_data = {
        "transition_id": transition_id,
        "redirect_url": redirect_url,
    }
    if skip_transition_check:
        query_data["skip_transition_check"] = "1"
    uids = [u for u in (uids or []) if u]
    if uids:
        query_data["uids"] = ",".join(uids)
    query = urlencode(query_data)
    return "{}/@@maitux-esignature-prompt?{}".format(api.get_url(context), query)


def build_receive_redirect_url(context, back_url):
    """为 sample receive 动作复用原有的接收后跳转行为。"""
    base_url = back_url or api.get_url(context)
    uid = api.get_uid(context)
    template = context.getTemplate()
    if template and template.getAutoPartition():
        return "{}/partition_magic?uids={}".format(base_url, uid)

    setup = api.get_senaite_setup()
    if "receive" in (setup.getAutoPrintStickers() or []):
        return "{}/sticker?autoprint=1&items={}".format(base_url, uid)

    return base_url


def is_ajax_request(request):
    return request.getHeader("X-Requested-With") == "XMLHttpRequest"


def redirect_response(request, redirect_url):
    if not is_ajax_request(request):
        return request.response.redirect(redirect_url)

    request.response.setHeader("Content-Type", "application/json")
    return json.dumps({
        "redirect_to": redirect_url,
        "success": True,
        "error": False,
    })


def warning_response(context, request, message, redirect_url):
    if not is_ajax_request(request):
        context.plone_utils.addPortalMessage(message, "warning")
        return request.response.redirect(redirect_url)

    request.response.setHeader("Content-Type", "application/json")
    return json.dumps({
        "redirect_to": redirect_url,
        "success": False,
        "error": True,
        "message": message,
    })


def build_post_transition_redirect_url(context, transition_id, back_url):
    """为不同 workflow 动作计算签名成功后的回跳地址。"""
    if IAnalysisRequest.providedBy(context) and transition_id == "receive":
        return build_receive_redirect_url(context, back_url)
    return back_url or api.get_url(context)


def get_request_header(request, name, default=None):
    getter = getattr(request, "get_header", None)
    if callable(getter):
        value = getter(name)
        if value:
            return value
    getter = getattr(request, "getHeader", None)
    if callable(getter):
        value = getter(name)
        if value:
            return value
    return default


def get_objects_by_uids(uids):
    items = []
    for uid in list(uids or []):
        obj = api.get_object_by_uid(uid, default=None)
        if obj is not None:
            items.append(obj)
    return items


def maybe_redirect_signature_prompt_for_action(
    context, request, action, uids, back_url=None
):
    """统一按规则表判断当前 workflow 动作是否要先走电子签名。"""
    objects = get_objects_by_uids(uids)
    if not objects:
        return None

    user_id = get_user_id()
    matched = []
    resolver = SignaturePolicyResolver()
    for obj in objects:
        policy = resolver.resolve(obj, action, user_id=user_id)
        if policy.get("signature_required"):
            matched.append(obj)

    if not matched:
        return None

    redirect_url = back_url or api.get_url(context)

    # A batch may mix objects that need a signature with objects that do not
    # (different portal_types, different workflows).  Signing for some while
    # silently transitioning the others would produce an audit trail nobody
    # can defend, so the whole action is refused instead.
    if len(matched) != len(objects):
        return warning_response(
            context,
            request,
            "The selection mixes items that require an electronic signature "
            "with items that do not. Please handle them separately.",
            redirect_url,
        )

    # One signature act for the whole batch; the anchor carries the policy,
    # the rest ride along in `uids`.
    target = matched[0]
    uids = [api.get_uid(obj) for obj in matched]
    redirect_url = build_post_transition_redirect_url(target, action, redirect_url)
    prompt_url = build_signature_prompt_url(
        target,
        action,
        redirect_url,
        skip_transition_check=True,
        uids=uids,
    )
    return redirect_response(request, prompt_url)


def patch_workflow_action_handler():
    """给默认 workflow_action 入口补一层规则表驱动的电子签名拦截。"""
    handler_class = bika_browser_workflow.WorkflowActionHandler
    if getattr(handler_class, "_maitux_esignature_patched", False):
        return

    original_call = handler_class.__call__

    def patched_call(self):
        action = self.get_action()
        if action:
            response = maybe_redirect_signature_prompt_for_action(
                self.context,
                self.request,
                action,
                self.get_uids(),
                back_url=self.get_redirect_url(),
            )
            if response is not None:
                return response
        return original_call(self)

    handler_class.__call__ = patched_call
    handler_class._maitux_esignature_patched = True


def patch_listing_workflow_transition():
    """给 listing 的默认 workflow transition 入口补统一规则表拦截。"""
    transition_class = ListingWorkflowTransition
    if getattr(transition_class, "_maitux_esignature_patched", False):
        return

    original_get_redirect_url = transition_class.get_redirect_url
    original_do_transition = transition_class.do_transition

    def patched_get_redirect_url(self):
        redirect_url = getattr(self, "_maitux_redirect_url", "")
        if redirect_url:
            return redirect_url
        return original_get_redirect_url(self)

    def patched_do_transition(self, transition, chained_uids, failed_transitions, **kw):
        user_id = get_user_id()
        policy = SignaturePolicyResolver().resolve(
            self.context,
            transition,
            user_id=user_id,
        )
        if not policy.get("signature_required"):
            return original_do_transition(
                self,
                transition,
                chained_uids,
                failed_transitions,
                **kw
            )

        current_uid = api.get_uid(self.context)
        chained_uids = list(chained_uids or [])
        if len(chained_uids) != 1 or current_uid not in chained_uids:
            self.error["message"] = (
                "The electronic signature flow currently supports one item at a time."
            )
            return

        back_url = getattr(self, "back_url", None)
        if not back_url:
            back_url = get_request_header(self.request, "referer", "")
        if not back_url:
            back_url = api.get_url(getattr(self.view, "context", self.context))

        redirect_url = build_post_transition_redirect_url(
            self.context,
            transition,
            back_url,
        )
        self._maitux_redirect_url = build_signature_prompt_url(
            self.context,
            transition,
            redirect_url,
            skip_transition_check=True,
        )
        return

    transition_class.get_redirect_url = patched_get_redirect_url
    transition_class.do_transition = patched_do_transition
    transition_class._maitux_esignature_patched = True


@implementer(IWorkflowActionUIDsAdapter)
class WorkflowActionVerifyPromptAdapter(RequestContextAware):
    """Redirect analysis verify actions to the signature prompt view.

    Handles a batch: every selected analysis is authorised by the one
    signature, with the first one acting as the policy anchor.
    """

    def is_ajax_request(self):
        return is_ajax_request(self.request)

    def redirect_response(self, redirect_url):
        return redirect_response(self.request, redirect_url)

    def __call__(self, action, uids):
        uids = list(uids)
        if not uids:
            return self.redirect(
                message="No items selected.",
                level="warning",
            )

        analyses = []
        for uid in uids:
            obj = api.get_object_by_uid(uid, default=None)
            if obj is None or not IAnalysis.providedBy(obj):
                # Not our business: let the default adapter handle the action.
                return None
            analyses.append(obj)

        url = build_signature_prompt_url(
            analyses[0],
            action,
            self.back_url,
            uids=[api.get_uid(obj) for obj in analyses],
        )
        return self.redirect_response(url)


class ListingVerifyPromptTransition(ListingWorkflowTransition):
    """Redirect listing-based verify actions to the signature prompt view."""

    def __init__(self, view, context, request):
        super(ListingVerifyPromptTransition, self).__init__(view, context, request)
        self.redirect_url = ""

    def get_redirect_url(self):
        return self.redirect_url

    def do_transition(self, transition, chained_uids, failed_transitions, **kw):
        user_id = get_user_id()
        policy = SignaturePolicyResolver().resolve(
            self.context,
            transition,
            user_id=user_id,
        )
        if not policy.get("signature_required"):
            return super(ListingVerifyPromptTransition, self).do_transition(
                transition,
                chained_uids=chained_uids,
                failed_transitions=failed_transitions,
                **kw
            )

        current_uid = api.get_uid(self.context)
        chained_uids = list(chained_uids or [])
        if len(chained_uids) != 1 or current_uid not in chained_uids:
            self.error["message"] = (
                "The MVP signature prompt currently supports one Analysis at a time."
            )
            return

        self.redirect_url = build_signature_prompt_url(
            self.context,
            transition,
            api.get_url(self.view.context),
        )


class WorkflowActionReceivePromptAdapter(WorkflowActionReceiveAdapter):
    """在 Sample receive 动作前先跳到电子签名页。"""

    def is_ajax_request(self):
        return is_ajax_request(self.request)

    def redirect_response(self, redirect_url):
        return redirect_response(self.request, redirect_url)

    def __call__(self, action, objects):
        samples = filter(IAnalysisRequest.providedBy, objects)
        samples = list(samples)
        if not samples:
            return super(WorkflowActionReceivePromptAdapter, self).__call__(
                action,
                objects,
            )

        sample = samples[0]
        user_id = get_user_id()
        policy = SignaturePolicyResolver().resolve(
            sample,
            action,
            user_id=user_id,
        )
        if not policy.get("signature_required"):
            return super(WorkflowActionReceivePromptAdapter, self).__call__(
                action,
                objects,
            )

        if len(samples) != 1:
            return self.redirect(
                message=u"当前电子签名流程仅支持一次接收一个样品。",
                level="warning",
            )

        redirect_url = build_receive_redirect_url(sample, self.back_url)
        return self.redirect_response(
            build_signature_prompt_url(
                sample,
                action,
                redirect_url,
                skip_transition_check=True,
            )
        )


class ListingReceivePromptTransition(SampleReceiveWorkflowTransition):
    """在列表页的 Sample receive 动作前先跳到电子签名页。"""

    def __init__(self, view, context, request):
        super(ListingReceivePromptTransition, self).__init__(view, context, request)
        self.redirect_url = ""

    def get_redirect_url(self):
        return self.redirect_url

    def do_transition(self, transition, chained_uids, failed_transitions, **kw):
        user_id = get_user_id()
        policy = SignaturePolicyResolver().resolve(
            self.context,
            transition,
            user_id=user_id,
        )
        if not policy.get("signature_required"):
            return super(ListingReceivePromptTransition, self).do_transition(
                transition,
                chained_uids=chained_uids,
                failed_transitions=failed_transitions,
                **kw
            )

        current_uid = api.get_uid(self.context)
        chained_uids = list(chained_uids or [])
        if len(chained_uids) != 1 or current_uid not in chained_uids:
            self.error["message"] = u"当前电子签名流程仅支持一次接收一个样品。"
            return

        redirect_url = build_receive_redirect_url(self.context, self.back_url)
        self.redirect_url = build_signature_prompt_url(
            self.context,
            transition,
            redirect_url,
            skip_transition_check=True,
        )


class SignaturePromptView(BrowserView):
    """Prompt for password/meaning/reason and execute the transition."""

    provider_factory = PasReAuthenticationProvider
    index = ViewPageTemplateFile("templates/esignature_prompt.pt")

    def __call__(self):
        if self.request.get("form.submitted"):
            return self.handle_submit()
        return self.index()

    def transition_id(self):
        return self.request.get("transition_id", "verify")

    def redirect_url(self):
        return self.request.get("redirect_url") or api.get_url(self.context)

    def target_uids(self):
        """UIDs this one signature act authorises.

        Defaults to the anchor alone, so a prompt reached without `uids`
        (a bookmarked URL, an older caller) keeps behaving as before.
        """
        raw = self.request.get("uids", "") or ""
        if not isinstance(raw, (list, tuple)):
            raw = raw.split(",")
        uids = [u.strip() for u in raw if u and u.strip()]
        anchor = api.get_uid(self.context)
        if anchor not in uids:
            uids.insert(0, anchor)
        return uids

    def target_objects(self):
        objects = []
        for uid in self.target_uids():
            obj = api.get_object_by_uid(uid, default=None)
            if obj is not None:
                objects.append(obj)
        return objects

    def target_count(self):
        """Shown on the prompt so the signer knows what they are signing for."""
        return len(self.target_uids())

    def policy(self):
        return SignaturePolicyResolver().resolve(
            self.context,
            self.transition_id(),
            user_id=get_user_id(),
        )

    def current_user_id(self):
        return get_user_id()

    def require_countersign(self):
        return bool(self.policy().get("require_countersign"))

    def signature_store(self):
        return SignatureRecordStore(api.get_portal())

    def pending_countersign(self):
        if not self.require_countersign():
            return None
        return self.signature_store().get_pending_countersign(
            api.get_uid(self.context),
            self.transition_id(),
        )

    def has_pending_countersign(self):
        return self.pending_countersign() is not None

    def pending_first_signer_user_id(self):
        pending = self.pending_countersign()
        if not pending:
            return ""
        return pending.get("primary_signer_user_id") or pending.get("user_id") or ""

    def form_meaning(self):
        return self.request.get("meaning") or (
            self.pending_countersign() and self.pending_countersign().get("meaning")
        ) or ""

    def form_reason(self):
        return self.request.get("reason") or (
            self.pending_countersign() and self.pending_countersign().get("reason")
        ) or ""

    def form_primary_user_id(self):
        """回填第一操作员账号，便于校验失败后用户直接修正。"""
        return (self.request.get("primary_user_id") or "").strip()

    def form_secondary_user_id(self):
        """回填第二操作员账号，便于校验失败后用户直接修正。"""
        return (self.request.get("secondary_user_id") or "").strip()

    def ensure_workflow_skin(self):
        """确保当前请求具备完整的 workflow guard 上下文。"""
        portal = api.get_portal()
        # Sample workflow guard 依赖 skins 里的 `guard_handler`。
        # 仅切换 skin 不够，还需要补齐站点与请求初始化。
        try:
            setSite(portal)
        except Exception:
            pass
        try:
            portal.changeSkin("Plone Default")
        except Exception:
            pass
        try:
            portal.clearCurrentSkin()
        except Exception:
            pass
        try:
            portal.setupCurrentSkin(self.request)
        except Exception:
            pass
        try:
            notify(BeforeTraverseEvent(portal, self.request))
        except Exception:
            pass
        try:
            setRequest(self.request)
        except Exception:
            pass

    def allowed_transition_ids(self):
        """返回当前对象此刻允许执行的 workflow transition id 列表。"""
        self.ensure_workflow_skin()
        transitions = api.get_transitions_for(self.context) or []
        return [item.get("id") for item in transitions if item.get("id")]

    def skip_transition_check(self):
        """对于已由工作流入口确认过的动作，允许跳过二次 guard 检查。"""
        value = self.request.get("skip_transition_check", "")
        return str(value).lower() in ("1", "true", "yes", "on")

    def handle_submit(self):
        transition_id = self.transition_id()
        self.ensure_workflow_skin()
        policy = self.policy()
        if not policy.get("signature_required"):
            self.context.plone_utils.addPortalMessage(
                "Electronic signature is not configured for this transition.",
                "warning",
            )
            return self.request.response.redirect(self.redirect_url())

        password = self.request.get("password", "")
        meaning = self.request.get("meaning", "").strip()
        reason = self.request.get("reason", "").strip()

        allowed_transitions = self.allowed_transition_ids()
        if not self.skip_transition_check() and transition_id not in allowed_transitions:
            # 当前对象此刻不允许执行目标动作时，提前返回更明确的提示，
            # 避免用户先完成签名再遇到 workflow 异常。
            self.context.plone_utils.addPortalMessage(
                "Transition '{}' is not currently available for this object. Allowed transitions: {}.".format(
                    transition_id,
                    ", ".join(allowed_transitions) or "(none)",
                ),
                "error",
            )
            return self.index()

        if policy.get("meaning_required") and not meaning:
            self.context.plone_utils.addPortalMessage("Meaning is required.", "error")
            return self.index()
        if policy.get("reason_required") and not reason:
            self.context.plone_utils.addPortalMessage("Reason is required.", "error")
            return self.index()

        user_id = self.current_user_id()
        provider = self.provider_factory()
        countersign_result = None
        if policy.get("require_countersign"):
            # 双人复核改为同页一次性录入两个账号密码，不再走“先挂起再二次进入”的旧流程。
            countersign_result = authenticate_countersign_users(
                provider,
                self.request.get("primary_user_id", ""),
                self.request.get("primary_password", ""),
                self.request.get("secondary_user_id", ""),
                self.request.get("secondary_password", ""),
                request_context=self.request,
            )
            if not countersign_result.get("authenticated"):
                failure_reason = countersign_result.get("failure_reason") or "unknown_error"
                message_map = {
                    "missing_primary_user_id": u"第一操作员账号不能为空。",
                    "missing_primary_password": u"第一操作员密码不能为空。",
                    "missing_secondary_user_id": u"第二操作员账号不能为空。",
                    "missing_secondary_password": u"第二操作员密码不能为空。",
                    "same_signer_not_allowed": u"双人复核必须由两个不同的操作员完成。",
                    "primary_auth_failed": u"第一操作员认证失败：{}",
                    "secondary_auth_failed": u"第二操作员认证失败：{}",
                }
                if failure_reason in ("primary_auth_failed", "secondary_auth_failed"):
                    provider_failure = (
                        countersign_result.get("provider_failure_reason")
                        or "unknown_error"
                    )
                    message = message_map[failure_reason].format(provider_failure)
                else:
                    message = message_map.get(
                        failure_reason,
                        u"双人电子签名校验失败：{}。".format(failure_reason),
                    )
                self.context.plone_utils.addPortalMessage(message, "error")
                return self.index()
        else:
            result = provider.authenticate_current_user(
                user_id,
                password,
                request_context=self.request,
            )
            if not result.get("authenticated"):
                self.context.plone_utils.addPortalMessage(
                    "Electronic signature re-authentication failed: {}".format(
                        result.get("failure_reason") or "unknown_error"
                    ),
                    "error",
                )
                return self.index()

        ttl_seconds = policy.get("verified_context_ttl_seconds", 300)
        # 通过同页双签或单签校验后，统一只写一份最终已验证上下文并继续 workflow。
        verified_context = set_verified_signature_context(
            self.context,
            transition_id,
            user_id,
            ttl_seconds=ttl_seconds,
            meaning=meaning,
            reason=reason,
            auth_backend_id=(
                countersign_result and countersign_result.get("primary_auth_backend_id")
            ) or result.get("backend_id"),
            signature_type=policy.get("signature_type"),
            initiator_user_id=(
                countersign_result and countersign_result.get("primary_user_id")
            ) or user_id,
            execution_user_id=user_id,
            primary_signer_user_id=(
                countersign_result and countersign_result.get("primary_user_id")
            ) or user_id,
            require_countersign=policy.get("require_countersign"),
            countersigner_user_id=(
                countersign_result and countersign_result.get("secondary_user_id")
            ),
            countersign_auth_backend_id=(
                countersign_result and countersign_result.get("secondary_auth_backend_id")
            ),
            object_uids=self.target_uids(),
            request=self.request,
        )
        self.request.form["comments"] = build_signature_summary(verified_context)
        self.request["execute_transition"] = True

        # One signature, N transitions -- all of them or none.
        #
        # A signature is a declaration of intent: "I approve these N items".
        # Carrying out only some of them leaves the declaration partly
        # unfulfilled, and the unfulfilled part has no trace anywhere:
        # IActionSucceededEvent never fires for it, so there is no audit entry
        # and no SignatureRecord.  All-or-nothing keeps the story tellable --
        # either the signature took full effect, or nothing happened and the
        # signer can try again.
        #
        # The atomicity comes for free: one request is one ZODB transaction, so
        # the state changes and the SignatureRecords of the whole batch commit
        # or roll back together.  bika's doActionFor() swallows
        # WorkflowException and returns (False, message) instead of letting the
        # transaction fail, which is why the abort below has to be explicit.
        #
        # Boundary worth knowing: the transaction covers ZODB only.  Anything
        # non-transactional triggered by a transition -- an e-mail, an external
        # call -- will NOT roll back with it.  The verify path has none today.
        targets = self.target_objects()

        # Cheap gate first: refuse before touching anything if the batch cannot
        # be carried out as a whole.  This runs *after* the verified context is
        # in place on purpose -- a signature-gated transition is only allowed
        # once the signature backs it, so checking earlier would always fail.
        not_allowed = [
            obj for obj in targets
            if not is_transition_allowed(obj, transition_id)
        ]
        if not_allowed:
            clear_verified_signature_context(request=self.request)
            self.context.plone_utils.addPortalMessage(
                u"本次签名未生效：以下 {} 项当前不允许执行 '{}'，请刷新后重试："
                u"{}".format(
                    len(not_allowed), transition_id,
                    u", ".join(api.get_id(obj) for obj in not_allowed),
                ),
                "error",
            )
            return self.index()

        transitioned = []
        for obj in targets:
            success, message = do_action_for(obj, transition_id)
            if success:
                transitioned.append(obj)
                continue

            # Mid-batch failure: a cascade from an earlier object can change
            # what a later one is allowed to do, so the gate above cannot catch
            # everything.  Undo the whole act.
            transaction.abort()
            clear_verified_signature_context(request=self.request)
            self.context.plone_utils.addPortalMessage(
                u"本次签名未生效：{} 执行 '{}' 失败（{}），批次已整体回滚，"
                u"请重试。".format(
                    api.get_id(obj), transition_id,
                    message or "unknown error",
                ),
                "error",
            )
            return self.request.response.redirect(self.redirect_url())

        clear_verified_signature_context(request=self.request)

        if policy.get("require_countersign"):
            self.context.plone_utils.addPortalMessage(
                u"双人电子签名验证通过，共 {} 项。".format(len(transitioned)),
                "info",
            )
        else:
            self.context.plone_utils.addPortalMessage(
                u"电子签名验证通过，共 {} 项。".format(len(transitioned)),
                "info",
            )
        return self.request.response.redirect(self.redirect_url())


patch_workflow_action_handler()
patch_listing_workflow_transition()
