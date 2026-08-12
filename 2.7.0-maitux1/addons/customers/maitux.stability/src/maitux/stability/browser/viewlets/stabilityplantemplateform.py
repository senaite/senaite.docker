# -*- coding: utf-8 -*-
from bika.lims import api
from plone.app.layout.viewlets import ViewletBase
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile


class StabilityPlanTemplateFormViewlet(ViewletBase):
    index = ViewPageTemplateFile("templates/stabilityplantemplate_form.pt")

    def available(self):
        try:
            url = self.request.get("ACTUAL_URL", "") or ""
            if "++add++StabilityPlanTemplate" in url:
                return True
            if "++add++StabilityPlan" in url:
                return True
            return api.get_portal_type(self.context) in (
                "StabilityPlanTemplate",
                "StabilityPlan",
            )
        except Exception:
            return False

    def render(self):
        try:
            if not self.available():
                return ""
            return self.index()
        except Exception:
            return ""
