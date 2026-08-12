# -*- coding: utf-8 -*-
from bika.lims import api
from bika.lims import senaiteMessageFactory as _
from plone.namedfile.file import NamedBlobFile
from senaite.core.browser.dexterity.add import DefaultAddForm
from senaite.core.browser.dexterity.add import DefaultAddView


def _first(value):
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _as_unicode(value):
    return api.safe_unicode(value or u"")


def _extract_uid(value):
    value = _first(value)
    if value is None:
        return ""
    if isinstance(value, dict):
        value = value.get("uid") or value.get("UID") or value.get("value") or ""
    if isinstance(value, basestring):
        return value.strip()
    return ""


class StabilityPlanAddForm(DefaultAddForm):
    def __init__(self, context, request):
        super(StabilityPlanAddForm, self).__init__(context, request)

    def updateFields(self):
        super(StabilityPlanAddForm, self).updateFields()
        template = self._get_template()
        if template is None or "article" not in self.fields:
            return
        article_field = self.fields["article"].field
        article_field.required = False
        article = getattr(template, "article", None)
        filename = getattr(article, "filename", None)
        if filename:
            # 创建计划时允许用户看到附件字段；若不重新上传，则沿用模板中的附件。
            article_field.description = _(
                u"Current template article: ${filename}. Leave this field empty to keep the template file.",
                mapping={"filename": api.safe_unicode(filename)},
            )
        else:
            article_field.description = _(
                u"No template article was found. You can upload a file here if needed."
            )

    def _get_template(self):
        template_uid = (
            self.request.get("template_uid") or
            self.request.form.get("template_uid") or
            self.request.form.get("form.widgets.plan_template")
        )
        template_uid = _extract_uid(template_uid)
        if not api.is_uid(template_uid):
            return None
        try:
            return api.get_object(template_uid)
        except Exception:
            return None

    def _apply_template_defaults(self):
        template = self._get_template()
        if template is None:
            return []

        changed = []

        def set_default(name, value):
            field = self.fields.get(name)
            if field is None:
                return
            changed.append((field.field, field.field.default))
            field.field.default = value

        set_default("title", _as_unicode(api.get_title(template)))
        set_default("description", _as_unicode(getattr(template, "description", u"") or u""))
        set_default("plan_template", [api.get_uid(template)])

        for name in ("sample_quantity", "reserve_quantity"):
            set_default(name, getattr(template, name, 0) or 0)

        unit = _first(getattr(template, "unit", None))
        if unit:
            set_default("unit", [unit])

        # 模板不再维护 Timepoints 子对象，计划明细由用户在创建计划时直接添加。
        set_default("plan_details", [])
        return changed

    def _copy_template_article(self, template):
        if template is None:
            return None
        article = getattr(template, "article", None)
        if not article:
            return None
        try:
            data = article.data
        except Exception:
            data = None
        if not data:
            return None
        # 创建新文件对象，避免直接复用模板上的 Blob 引用。
        return NamedBlobFile(
            data=data,
            filename=getattr(article, "filename", None),
            contentType=getattr(article, "contentType", ""),
        )

    def _has_article(self, obj):
        if obj is None:
            return False
        article = getattr(obj, "article", None)
        if not article:
            return False
        try:
            return bool(article.data)
        except Exception:
            return True

    def updateWidgets(self):
        changed = self._apply_template_defaults()
        try:
            super(StabilityPlanAddForm, self).updateWidgets()
        finally:
            for field, default in changed:
                field.default = default

    def _get_template_from_value(self, value):
        template_uid = _extract_uid(value)
        if not api.is_uid(template_uid):
            return None
        try:
            return api.get_object(template_uid)
        except Exception:
            return None

    def create(self, data):
        template = self._get_template_from_value(data.get("plan_template")) or self._get_template()
        if template is not None:
            # 创建时再次兜底带入模板字段，避免文件控件默认值在表单提交时丢失。
            data.setdefault("title", _as_unicode(api.get_title(template)))
            data.setdefault("description", _as_unicode(getattr(template, "description", u"") or u""))
            data.setdefault("plan_template", [api.get_uid(template)])
            for name in ("sample_quantity", "reserve_quantity"):
                data.setdefault(name, getattr(template, name, 0) or 0)
            unit = _first(getattr(template, "unit", None))
            if unit:
                data.setdefault("unit", [unit])
            if not data.get("article"):
                article = self._copy_template_article(template)
                if article is not None:
                    data["article"] = article
        return super(StabilityPlanAddForm, self).create(data)

    def add(self, object):
        template = self._get_template_from_value(getattr(object, "plan_template", None)) or self._get_template()
        if template is not None and not self._has_article(object):
            article = self._copy_template_article(template)
            if article is not None:
                # 在对象真正加入容器前兜底回写附件，避免文件字段在 create(data) 阶段丢失。
                object.article = article
        super(StabilityPlanAddForm, self).add(object)
        try:
            object.reindexObject()
        except Exception:
            pass


class StabilityPlanAddView(DefaultAddView):
    form = StabilityPlanAddForm
