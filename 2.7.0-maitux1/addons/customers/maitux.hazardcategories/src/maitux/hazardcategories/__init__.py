# -*- coding: utf-8 -*-
import logging

from zope.i18nmessageid import MessageFactory

PROJECTNAME = "maitux.hazardcategories"
_ = MessageFactory(PROJECTNAME)
logger = logging.getLogger(PROJECTNAME)

from maitux.hazardcategories import patches  # noqa: E402,F401
