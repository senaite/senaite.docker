# -*- coding: utf-8 -*-
# ADD(2026-08-21) - 样品标签打印视图。
# 供 Sample / AnalysisRequest 选择多个 uids 后打印样品标签（④⑤）。
# 复用 maitux.stock 的 stockbatchprint 渲染+PDF 机制，模板目录在 sample/。
import os

from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from bika.lims import api as bika_api
from bika.lims.utils import createPdf
from plone.resource.utils import queryResourceDirectory
from Products.CMFPlone.utils import safe_unicode
from senaite.app.supermodel import SuperModel


class SampleLabelPrintView(BrowserView):
    def __call__(self):
        if self.request.form.get("pdf", "0") == "1":
            response = self.request.response
            response.setHeader("Content-type", "application/pdf")
            response.setHeader("Content-Disposition", "inline")
            response.setHeader("filename", "sample-sticker.pdf")
            return self.pdf_from_post()
        return self.index()

    def get_uids(self):
        uids = self.request.get("uids", "")
        if isinstance(uids, (list, tuple)):
            uids = ",".join(uids)
        uids = [u.strip() for u in bika_api.safe_unicode(uids).split(",") if u.strip()]
        uids = filter(bika_api.is_uid, uids)
        return list(uids)

    def get_items(self):
        uids = self.get_uids()
        return list(map(lambda uid: SuperModel(uid), uids))

    def get_selected_template(self):
        template_id = self.request.get("template", "")
        if template_id:
            return template_id
        return "maitux.labeldesign:SampleNormal_40x30mm.pt"

    def get_available_templates(self):
        return [
            {"id": "maitux.labeldesign:SampleNormal_40x30mm.pt",
             "title": "样品标签 (Sample Normal)", "selected": False},
            {"id": "maitux.labeldesign:SampleStability_40x30mm.pt",
             "title": "样品标签·稳定性 (Sample Stability)", "selected": False},
        ]

    def _get_templates_dir(self, prefix):
        templates_dir = queryResourceDirectory("stickers", prefix).directory
        return os.path.join(templates_dir, "sample")

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
        fullpath = os.path.join(self._get_templates_dir(prefix), filename)
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
        pdf_fn = os.path.join(os.path.dirname(__file__), "sample-sticker.pdf")
        pdf_file = createPdf(htmlreport=reporthtml, outfile=pdf_fn)
        return pdf_file