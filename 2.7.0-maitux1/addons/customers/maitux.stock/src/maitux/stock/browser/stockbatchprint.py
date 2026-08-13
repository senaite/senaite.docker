# -*- coding: utf-8 -*-
import os
import os.path
import tempfile

from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from bika.lims import api
from bika.lims.utils import createPdf
from plone.resource.utils import queryResourceDirectory
from Products.CMFPlone.utils import safe_unicode
from senaite.app.supermodel import SuperModel
from senaite.core.interfaces.stickers import IGetStickerTemplates
from zope.component import getAdapters


class StockBatchPrintView(BrowserView):
    def __call__(self):
        if self.request.form.get("pdf", "0") == "1":
            response = self.request.response
            response.setHeader("Content-type", "application/pdf")
            response.setHeader("Content-Disposition", "inline")
            response.setHeader("filename", "sticker.pdf")
            return self.pdf_from_post()
        return self.index()

    def get_uids(self):
        uids = self.request.get("uids", "")
        if isinstance(uids, (list, tuple)):
            uids = ",".join(uids)
        uids = [u.strip() for u in api.safe_unicode(uids).split(",") if u.strip()]
        uids = filter(api.is_uid, uids)
        return list(uids)

    def get_items(self):
        uids = self.get_uids()
        return list(map(lambda uid: SuperModel(uid), uids))

    def get_selected_template(self):
        template_id = self.request.get("template", "")
        if template_id:
            return template_id
        adapters = list(getAdapters((self.context,), IGetStickerTemplates))
        for name, adapter in adapters:
            default_template = getattr(adapter, "default_template", "")
            if default_template:
                return default_template
        return "maitux.stock:Minimal_QR_30x30mm.pt"

    def get_available_templates(self):
        templates = []
        selected = self.get_selected_template()
        adapters = list(getAdapters((self.context,), IGetStickerTemplates))
        for name, adapter in adapters:
            templates += adapter(self.request) or []
        if not templates:
            templates = [{"id": selected, "title": selected}]
        for t in templates:
            t["selected"] = t.get("id", "") == selected
        return templates

    def _get_templates_dir(self, prefix):
        templates_dir = queryResourceDirectory("stickers", prefix).directory
        return os.path.join(templates_dir, "stockbatch")

    def get_selected_template_css(self):
        template = self.get_selected_template()
        if ":" not in template:
            return ""
        prefix, filename = template.split(":", 1)
        templates_dir = self._get_templates_dir(prefix)
        css_path = os.path.join(templates_dir, "{}.css".format(filename[:-3]))
        if not os.path.isfile(css_path):
            return ""
        with open(css_path, "r") as content_file:
            return content_file.read()

    def render_sticker(self, item):
        self.current_item = item
        template = self.get_selected_template()
        if ":" not in template:
            return ""
        prefix, filename = template.split(":", 1)
        templates_dir = self._get_templates_dir(prefix)
        fullpath = os.path.join(templates_dir, filename)
        embed = ViewPageTemplateFile(fullpath)
        return embed(self, item=item)

    def render_stickers(self):
        html = []
        for item in self.get_items():
            html.append("<div class='sticker'>{}</div>".format(self.render_sticker(item)))
        return "<div class='stickers'>{}</div>".format("".join(html))

    def pdf_from_post(self):
        html = self.request.form.get("html")
        style = self.request.form.get("style")
        reporthtml = "<html><head>{0}</head><body>{1}</body></html>"
        reporthtml = reporthtml.format(style, html)
        reporthtml = safe_unicode(reporthtml).encode("utf-8")
        pdf_fn = tempfile.mktemp(suffix=".pdf")
        pdf_file = createPdf(htmlreport=reporthtml, outfile=pdf_fn)
        return pdf_file

