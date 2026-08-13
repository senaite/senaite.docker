# -*- coding: utf-8 -*-
"""Overview and explicit utility views for the electronic signature MVP."""

from bika.lims import api
from bika.lims.interfaces import IAnalysis
from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from plone.registry.interfaces import IRegistry
from six.moves.urllib.parse import urlparse
from zope.component import getUtility

from maitux.esignature.services.policy import SignaturePolicyResolver
from maitux.esignature.browser.workflow import build_signature_prompt_url
from maitux.esignature.interfaces import IESignatureControlPanelSettings


class ESignatureOverviewView(BrowserView):
    """Overview page with the current runtime configuration summary."""

    package_name = "maitux.esignature"
    guard_mode = "workflow guard"

    def _registry_value(self, name, default):
        key = "maitux.esignature.{0}".format(name)
        try:
            return api.portal.get_registry_record(key, default=default)
        except Exception:
            return default

    def policy(self):
        return SignaturePolicyResolver().resolve(
            self.context,
            self._registry_value("pilot_transition", "verify"),
        )

    def enabled(self):
        return bool(self.policy().get("enabled"))

    def pilot_portal_type(self):
        return self._registry_value("pilot_portal_type", "Analysis")

    def pilot_transition(self):
        return self._registry_value("pilot_transition", "verify")

    def signature_type(self):
        return self._registry_value("signature_type", "verification")

    def storage_mode(self):
        return "independent lightweight store"

    def auth_mode(self):
        return "Plone/PAS/acl_users re-auth provider"

    def controlpanel_url(self):
        return "{}/@@maitux-esignature-controlpanel".format(api.get_url(self.context))

    def test_entry_url(self):
        return "{}/@@maitux-esignature-test-entry".format(api.get_url(self.context))


class ESignatureTestEntryView(BrowserView):
    """Explicit test entry that launches the prompt from a pasted URL."""

    index = ViewPageTemplateFile("templates/test_entry.pt")

    def _show_message(self, message, level="info"):
        api.get_portal().plone_utils.addPortalMessage(message, level)

    def __call__(self):
        if self.request.get("form.submitted"):
            return self.handle_submit()
        return self.index()

    def pilot_transition(self):
        return SignaturePolicyResolver().resolve(
            self.context,
            "verify",
        ).get("pilot_transition") or "verify"

    def example_input(self):
        portal_url = api.get_url(api.get_portal())
        return "{}/clients/client-1/H2O-0005/analyses".format(portal_url)

    def submitted_analysis_url(self):
        return (self.request.get("analysis_url", "") or "").strip()

    def selected_analyses(self):
        return getattr(self, "_selected_analyses", [])

    def handle_submit(self):
        obj = self._resolve_target(self.submitted_analysis_url())
        if obj is None:
            self._show_message(
                "Please paste a valid Analysis, Sample, or analyses-list URL under the current site.",
                "error",
            )
            return self.index()

        if IAnalysis.providedBy(obj):
            return self._redirect_to_prompt(obj)

        analyses = self._get_sample_analyses(obj)
        if not analyses:
            self._show_message(
                "The provided URL does not point to an Analysis or a Sample with analyses.",
                "error",
            )
            return self.index()

        self._selected_analyses = analyses
        self._show_message(
            "Sample detected. Please choose one Analysis below.",
            "info",
        )
        return self.index()

    def _redirect_to_prompt(self, analysis):
        redirect_url = api.get_url(analysis)
        prompt_url = build_signature_prompt_url(
            analysis,
            self.pilot_transition(),
            redirect_url,
        )
        return self.request.response.redirect(prompt_url)

    def _resolve_target(self, value):
        value = (value or "").strip()
        if not value:
            return None

        portal = api.get_portal()
        portal_url = api.get_url(portal).rstrip("/")
        parsed = urlparse(value)
        path = parsed.path if parsed.scheme else value
        if not path:
            return None

        if path.startswith(portal_url):
            path = path[len(portal_url):]
        elif value.startswith(portal_url):
            path = value[len(portal_url):]

        path = path.strip()
        if not path.startswith("/"):
            path = "/" + path.lstrip("/")

        portal_path = "/".join(portal.getPhysicalPath())
        if path.startswith(portal_path):
            path = path[len(portal_path):]
            if not path.startswith("/"):
                path = "/" + path

        traverse_path = path.lstrip("/")
        if not traverse_path:
            return None

        # analyses 是样品上的一个列表视图，这里回退到样品对象本身，方便继续列出分析项目。
        if traverse_path.endswith("/analyses"):
            traverse_path = traverse_path[:-len("/analyses")].rstrip("/")

        try:
            return portal.unrestrictedTraverse(traverse_path)
        except Exception:
            return None

    def _get_sample_analyses(self, obj):
        if obj is None or not hasattr(obj, "getAnalyses"):
            return []
        try:
            analyses = obj.getAnalyses(full_objects=True)
        except TypeError:
            analyses = obj.getAnalyses()
        except Exception:
            return []

        items = []
        for analysis in analyses:
            if analysis is None:
                continue
            items.append({
                "title": self._analysis_title(analysis),
                "url": api.get_url(analysis),
                "prompt_url": build_signature_prompt_url(
                    analysis,
                    self.pilot_transition(),
                    api.get_url(analysis),
                ),
                "state": self._review_state(analysis),
            })
        return items

    def _analysis_title(self, analysis):
        service = None
        for attr in ("getService", "getAnalysisService"):
            getter = getattr(analysis, attr, None)
            if getter is None:
                continue
            try:
                service = getter()
            except Exception:
                service = None
            if service:
                break
        if service is not None:
            for getter_name in ("Title", "getKeyword"):
                getter = getattr(service, getter_name, None)
                if getter is None:
                    continue
                try:
                    value = getter()
                except Exception:
                    value = None
                if value:
                    return value
        title = getattr(analysis, "Title", None)
        if callable(title):
            try:
                title = title()
            except Exception:
                title = None
        return title or getattr(analysis, "id", "Analysis")

    def _review_state(self, obj):
        workflow = api.get_workflow_status_of(obj)
        if not workflow:
            return ""
        if isinstance(workflow, dict):
            return workflow.get("review_state", "")
        if isinstance(workflow, basestring):
            return workflow
        return ""


class ESignatureRepairRegistryView(BrowserView):
    """Repair malformed registry records created during earlier iterations."""

    registry_prefix = "maitux.esignature"
    setting_names = (
        "enabled",
        "auditlog_summary_enabled",
        "verified_context_ttl_seconds",
        "pilot_portal_type",
        "pilot_transition",
        "signature_type",
        "meaning_required",
        "reason_required",
        "policy_rules_json",
    )

    def _show_message(self, message, level="info"):
        api.get_portal().plone_utils.addPortalMessage(message, level)

    def __call__(self):
        registry = getUtility(IRegistry)
        existing_values = {}

        for name in self.setting_names:
            key = "{}.{}".format(self.registry_prefix, name)
            record = registry.records.get(key)
            if record is not None and hasattr(record, "value"):
                existing_values[name] = record.value
            if key in registry.records:
                del registry.records[key]

        registry.registerInterface(
            IESignatureControlPanelSettings,
            prefix=self.registry_prefix,
        )

        # 重新注册后再尽量恢复旧值，避免现场之前保存的配置丢失。
        for name, value in existing_values.items():
            key = "{}.{}".format(self.registry_prefix, name)
            if key in registry.records:
                registry.records[key].value = value

        self._show_message("Electronic signature registry records repaired.", "info")
        return self.request.response.redirect(
            "{}/@@maitux-esignature-controlpanel".format(api.get_url(self.context))
        )

