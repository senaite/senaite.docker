# -*- coding: utf-8 -*-
from plone.supermodel import model
from senaite.core.content.base import Container
from zope.i18n import translate as zt
from zope.interface import implementer, alsoProvides

from maitux.projects.interfaces import IProjects


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


class IProjectsSchema(model.Schema):
    pass


@implementer(IProjects, IProjectsSchema)
class Projects(Container):
    """仿 BatchFolder 的 Projects 容器（portal 根目录存在一个 id="projects"）。
    """

    _catalogs = ["portal_catalog", "uid_catalog"]

    def Title(self):
        raw = getattr(self.aq_base, "title", None)
        try:
            value = zt(raw, context=self, domain="maitux.projects")
        except Exception:
            value = None
        if not value:
            try:
                value = zt(raw, domain="maitux.projects")
            except Exception:
                value = None
        if not value:
            value = raw
        return safe_unicode(value)

    def __init__(self, oid=None, **kw):
        if oid is not None:
            super(Projects, self).__init__(oid, **kw)
        else:
            super(Projects, self).__init__(**kw)
        try:
            alsoProvides(self, IProjects)
        except Exception:
            pass
