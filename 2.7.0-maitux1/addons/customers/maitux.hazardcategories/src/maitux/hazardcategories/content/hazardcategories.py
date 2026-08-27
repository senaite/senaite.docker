# -*- coding: utf-8 -*-
from plone.supermodel import model
from senaite.core.content.base import Container
from zope.i18n import translate as zt
from zope.interface import implementer

from maitux.hazardcategories.interfaces import IHazardCategories


def safe_unicode(value):
    if value is None:
        return u""
    if isinstance(value, unicode):
        return value
    if isinstance(value, str):
        try:
            return value.decode("utf-8")
        except Exception:
            try:
                return value.decode("latin-1", errors="replace")
            except Exception:
                return u""
    return unicode(value)


class IHazardCategoriesSchema(model.Schema):
    pass


@implementer(IHazardCategories, IHazardCategoriesSchema)
class HazardCategories(Container):
    def Title(self):
        raw = getattr(self.aq_base, "title", None)
        try:
            value = zt(raw, context=self, domain="maitux.hazardcategories")
        except Exception:
            value = None
        if not value:
            value = raw
        return safe_unicode(value)
