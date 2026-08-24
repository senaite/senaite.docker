# -*- coding: utf-8 -*-
from Products.CMFCore.permissions import AddPortalContent
from maitux.projects import _

PROJECTNAME = "maitux.projects"
PROFILE_ID = "profile-maitux.projects:default"
PRODUCT_PROFILE_ID = "maitux.projects:default"

ADD_CONTENT_PERMISSIONS = {
    "Project": AddPortalContent,
}

PROJECTS_FOLDER_ID = "projects"
PROJECTS_FOLDER_TITLE_MSG = _(u"folder_title_projects", default=u"Projects")
PROJECTS_FOLDER_TITLE = u"Projects"

REVIEW_STATE_OPEN = "open"
REVIEW_STATE_CLOSED = "closed"
REVIEW_STATE_CANCELLED = "cancelled"

SIDEBAR_DEPTH = 1
