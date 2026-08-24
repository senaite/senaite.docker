# -*- coding: utf-8 -*-
from plone.autoform import directives

from maitux.projects import _
from plone.supermodel import model
from senaite.core.content.base import Container
from senaite.core.schema.datetimefield import DatetimeField
from senaite.core.schema import UIDReferenceField
from z3c.form.interfaces import IAddForm
from zope import schema
from zope.interface import implementer, alsoProvides

from maitux.projects.interfaces import IProject


class IProjectSchema(model.Schema):
    """仿 Batch Schema，字段 Batch -> Project。
    BatchID -> ProjectID (getId), BatchDate -> ProjectDate,
    Client/ClientBatchID -> Client/ClientProjectID
    """

    model.fieldset(
        "project_details",
        label=_(u"schema_project_details", default=u"Project Details"),
        fields=[
            "client",
            "client_project_id",
            "project_date",
        ],
    )

    directives.mode(IAddForm, created_by="hidden")
    created_by = schema.TextLine(
        title=_(u"Created By"),
        required=False,
        readonly=True,
    )

    client = UIDReferenceField(
        title=_(u"Client"),
        description=_(u"schema_project_client_description", default=u"Select the client of this project"),
        allowed_types=("Client",),
        required=False,
    )

    client_project_id = schema.TextLine(
        title=_(u"schema_client_project_id", default=u"Client Project ID"),
        description=_(u"schema_client_project_id_description", default=u"Client side reference code for this project"),
        required=False,
    )

    project_date = DatetimeField(
        title=_(u"schema_project_date", default=u"Project Date"),
        description=_(u"schema_project_date_description", default=u"Official date of the project"),
        required=False,
    )

    description = schema.Text(
        title=_(u"Description"),
        description=_(u"schema_project_description_description", default=u"Remarks or description of this project"),
        required=False,
    )


@implementer(IProject, IProjectSchema)
class Project(Container):
    """仿 Batch 的单个 Project (Dexterity)
    """

    _catalogs = ["portal_catalog", "uid_catalog"]

    def __init__(self, oid=None):
        if oid is not None:
            super(Project, self).__init__(oid)
        else:
            super(Project, self).__init__()
        try:
            alsoProvides(self, IProject)
        except Exception:
            pass

    def Title(self):
        title = getattr(self, "title", None) or u""
        title = (title or u"").strip()
        if title:
            return title
        return self.getId()

    def getClient(self):
        client_ref = getattr(self, "client", None)
        if not client_ref:
            return None
        try:
            from bika.lims import api as bapi
            return bapi.get_object(client_ref)
        except Exception:
            return None

    def getClientID(self):
        cl = self.getClient()
        if cl is None:
            return u""
        return getattr(cl, "getClientID", lambda: u"")() or u""

    def getClientTitle(self):
        cl = self.getClient()
        if cl is None:
            return u""
        try:
            return cl.Title() or u""
        except Exception:
            return u""

    def getClientProjectID(self):
        return (getattr(self, "client_project_id", None) or u"").strip()

    def getProjectDate(self):
        return getattr(self, "project_date", None) or None

    def isOpen(self):
        from bika.lims import api as bapi
        state = bapi.get_workflow_status_of(self)
        return state not in ("closed", "cancelled")
